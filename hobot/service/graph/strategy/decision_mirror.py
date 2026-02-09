"""
Phase E-4: Strategy Decision Mirror
MySQL ai_strategy_decisions → Macro Graph StrategyDecision 미러링
"""

import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List

from service.database.db import get_db_connection
from service.graph.neo4j_client import get_neo4j_client
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)


def _generate_decision_id(decision_date: date, mp_id: str, sub_mp_json: Optional[str]) -> str:
    """
    Deterministic decision_id 생성
    동일 날짜/MP/Sub-MP 조합은 동일 ID → upsert 가능
    
    Format: sd:{date}:{mp_id}:{hash8}
    """
    hash_input = f"{decision_date.isoformat()}:{mp_id}:{sub_mp_json or ''}"
    hash_value = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
    return f"sd:{decision_date.isoformat()}:{mp_id}:{hash_value}"


class StrategyDecisionMirror:
    """
    MySQL ai_strategy_decisions → Macro Graph 미러링
    
    Source-of-Truth는 MySQL이며, Graph는 분석/탐색용 미러입니다.
    """

    def __init__(self):
        self.neo4j_client = None

    def _get_neo4j_client(self):
        """Neo4j 클라이언트 lazy 초기화"""
        if self.neo4j_client is None:
            try:
                self.neo4j_client = get_neo4j_client()
            except Exception as e:
                logger.warning(f"[DecisionMirror] Neo4j 클라이언트 초기화 실패: {e}")
                self.neo4j_client = None
        return self.neo4j_client

    def mirror_latest_decision(self) -> Optional[Dict[str, Any]]:
        """
        MySQL의 최신 전략 결정을 Macro Graph에 미러링
        
        Returns:
            미러링된 결정 정보 또는 None
        """
        try:
            # MySQL에서 최신 결정 조회
            decision = self._fetch_latest_decision_from_mysql()
            if not decision:
                logger.info("[DecisionMirror] MySQL에 전략 결정이 없습니다.")
                return None

            # Graph에 upsert
            result = self._upsert_decision_to_graph(decision)
            return result

        except Exception as e:
            logger.error(f"[DecisionMirror] 최신 결정 미러링 실패: {e}", exc_info=True)
            return None

    def mirror_decisions_backfill(self, days: int = 30) -> Dict[str, Any]:
        """
        MySQL의 최근 N일 전략 결정을 Macro Graph에 미러링 (Backfill)
        
        Args:
            days: 백필할 일수
            
        Returns:
            백필 결과 요약
        """
        try:
            # MySQL에서 최근 N일 결정 조회
            decisions = self._fetch_decisions_from_mysql(days=days)
            if not decisions:
                logger.info(f"[DecisionMirror] MySQL에 최근 {days}일 전략 결정이 없습니다.")
                return {"success": True, "count": 0, "message": "No decisions to mirror"}

            success_count = 0
            error_count = 0

            for decision in decisions:
                try:
                    self._upsert_decision_to_graph(decision)
                    success_count += 1
                except Exception as e:
                    logger.warning(f"[DecisionMirror] 결정 미러링 실패: {e}")
                    error_count += 1

            logger.info(f"[DecisionMirror] Backfill 완료: success={success_count}, error={error_count}")
            return {
                "success": True,
                "count": success_count,
                "errors": error_count,
                "message": f"Mirrored {success_count} decisions ({error_count} errors)"
            }

        except Exception as e:
            logger.error(f"[DecisionMirror] Backfill 실패: {e}", exc_info=True)
            return {"success": False, "count": 0, "message": str(e)}

    def _fetch_latest_decision_from_mysql(self) -> Optional[Dict[str, Any]]:
        """MySQL에서 최신 전략 결정 조회"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(DictCursor)
                cursor.execute("""
                    SELECT id, decision_date, analysis_summary, target_allocation,
                           recommended_stocks, quant_signals, created_at
                    FROM ai_strategy_decisions
                    ORDER BY decision_date DESC, created_at DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    return self._parse_decision_row(row)
                return None
        except Exception as e:
            logger.error(f"[DecisionMirror] MySQL 조회 실패: {e}")
            return None

    def _fetch_decisions_from_mysql(self, days: int = 30) -> List[Dict[str, Any]]:
        """MySQL에서 최근 N일 전략 결정 조회"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(DictCursor)
                cursor.execute("""
                    SELECT id, decision_date, analysis_summary, target_allocation,
                           recommended_stocks, quant_signals, created_at
                    FROM ai_strategy_decisions
                    WHERE decision_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    ORDER BY decision_date DESC, created_at DESC
                """, (days,))
                rows = cursor.fetchall()
                return [self._parse_decision_row(row) for row in rows]
        except Exception as e:
            logger.error(f"[DecisionMirror] MySQL 조회 실패: {e}")
            return []

    def _parse_decision_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """MySQL 결과 행 파싱"""
        # target_allocation JSON 파싱
        target_allocation_raw = row.get("target_allocation")
        if isinstance(target_allocation_raw, str):
            try:
                target_allocation_raw = json.loads(target_allocation_raw)
            except json.JSONDecodeError:
                target_allocation_raw = {}
        elif target_allocation_raw is None:
            target_allocation_raw = {}

        # recommended_stocks JSON 파싱
        recommended_stocks_raw = row.get("recommended_stocks")
        if isinstance(recommended_stocks_raw, str):
            try:
                recommended_stocks_raw = json.loads(recommended_stocks_raw)
            except json.JSONDecodeError:
                recommended_stocks_raw = {}
        elif recommended_stocks_raw is None:
            recommended_stocks_raw = {}

        mp_id = target_allocation_raw.get("mp_id", "Unknown")
        target_allocation = target_allocation_raw.get("target_allocation", {})
        sub_mp_ids = target_allocation_raw.get("sub_mp", {})
        
        # sub_mp 구조 확장 (ID + ETF Details)
        sub_mp_expanded = {}
        # asset_classes = ["stocks", "bonds", "alternatives", "cash"]
        
        # sub_mp_ids는 {"stocks": "Eq-A", ...} 형태라고 가정
        if isinstance(sub_mp_ids, dict):
            for asset_class, sub_id in sub_mp_ids.items():
                # recommended_stocks에서 해당 자산군 ETF 정보 가져오기
                # recommended_stocks 구조: {"stocks": [...], "bonds": [...]}
                etf_details = recommended_stocks_raw.get(asset_class, [])
                
                # 대소문자 매칭 시도 (Stocks vs stocks)
                if not etf_details:
                    etf_details = recommended_stocks_raw.get(asset_class.capitalize(), [])
                if not etf_details:
                    etf_details = recommended_stocks_raw.get(asset_class.lower(), [])
                
                sub_mp_expanded[asset_class] = {
                    "sub_mp_id": sub_id,
                    "sub_mp_name": sub_id,  # TODO: 이름 매핑 필요
                    "etf_details": etf_details
                }
        else:
            sub_mp_expanded = sub_mp_ids

        # decision_date 처리
        decision_date = row.get("decision_date")
        if isinstance(decision_date, datetime):
            decision_date = decision_date.date()
        elif isinstance(decision_date, str):
            decision_date = datetime.fromisoformat(decision_date).date()

        # decision_id 생성 (expanded sub_mp 반영)
        sub_mp_json = json.dumps(sub_mp_expanded, sort_keys=True) if sub_mp_expanded else None
        decision_id = _generate_decision_id(decision_date, mp_id, sub_mp_json)

        return {
            "mysql_id": row.get("id"),
            "decision_id": decision_id,
            "decision_date": decision_date,
            "mp_id": mp_id,
            "target_allocation": target_allocation,
            "sub_mp": sub_mp_expanded,
            "analysis_summary": row.get("analysis_summary", ""),
            "reasoning": sub_mp_ids.get("reasoning", "") if isinstance(sub_mp_ids, dict) else "", # sub_mp_ids에 reasoning이 있을 수 있음
            "created_at": row.get("created_at"),
        }

    def _upsert_decision_to_graph(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Macro Graph에 StrategyDecision upsert"""
        client = self._get_neo4j_client()
        if client is None:
            raise RuntimeError("Neo4j 클라이언트 연결 불가")

        decision_id = decision["decision_id"]
        decision_date = decision["decision_date"]
        mp_id = decision["mp_id"]

        # StrategyDecision 노드 upsert
        query = """
        // phase_e_upsert_strategy_decision
        MERGE (sd:StrategyDecision {decision_id: $decision_id})
        ON CREATE SET
            sd.decision_date = date($decision_date),
            sd.mp_id = $mp_id,
            sd.target_allocation = $target_allocation_json,
            sd.sub_mp = $sub_mp_json,
            sd.analysis_summary = $analysis_summary,
            sd.reasoning = $reasoning,
            sd.created_at = datetime()
        ON MATCH SET
            sd.mp_id = $mp_id,
            sd.target_allocation = $target_allocation_json,
            sd.sub_mp = $sub_mp_json,
            sd.analysis_summary = $analysis_summary,
            sd.reasoning = $reasoning,
            sd.updated_at = datetime()
        RETURN sd.decision_id AS decision_id, 
               'upserted' AS status
        """

        params = {
            "decision_id": decision_id,
            "decision_date": decision_date.isoformat(),
            "mp_id": mp_id,
            "target_allocation_json": json.dumps(decision.get("target_allocation", {})),
            "sub_mp_json": json.dumps(decision.get("sub_mp", {})),
            "analysis_summary": decision.get("analysis_summary", "")[:2000],
            "reasoning": decision.get("reasoning", "")[:2000],
        }

        result = client.run_write(query, params)

        # MacroState와 연결 시도 (당일 MacroState가 있으면)
        self._link_to_macro_state(client, decision_id, decision_date)

        logger.info(f"[DecisionMirror] StrategyDecision upsert 완료: {decision_id}")
        return {
            "decision_id": decision_id,
            "mp_id": mp_id,
            "decision_date": decision_date.isoformat(),
        }

    def _link_to_macro_state(self, client, decision_id: str, decision_date: date):
        """StrategyDecision과 MacroState 연결"""
        try:
            query = """
            // phase_e_link_decision_to_macro_state
            MATCH (sd:StrategyDecision {decision_id: $decision_id})
            MATCH (ms:MacroState)
            WHERE date(ms.as_of_date) = date($decision_date)
            MERGE (sd)-[:BASED_ON]->(ms)
            RETURN count(*) AS linked_count
            """
            result = client.run_write(query, {
                "decision_id": decision_id,
                "decision_date": decision_date.isoformat(),
            })
            if result and result[0].get("linked_count", 0) > 0:
                logger.info(f"[DecisionMirror] MacroState 연결 완료: {decision_id}")
        except Exception as e:
            logger.warning(f"[DecisionMirror] MacroState 연결 실패 (무시): {e}")


# 싱글톤 인스턴스
_strategy_decision_mirror = None


def get_strategy_decision_mirror() -> StrategyDecisionMirror:
    """StrategyDecisionMirror 싱글톤 인스턴스 반환"""
    global _strategy_decision_mirror
    if _strategy_decision_mirror is None:
        _strategy_decision_mirror = StrategyDecisionMirror()
    return _strategy_decision_mirror


def mirror_latest_strategy_decision() -> Optional[Dict[str, Any]]:
    """최신 전략 결정 미러링 (편의 함수)"""
    mirror = get_strategy_decision_mirror()
    return mirror.mirror_latest_decision()


def mirror_strategy_decisions_backfill(days: int = 30) -> Dict[str, Any]:
    """전략 결정 백필 (편의 함수)"""
    mirror = get_strategy_decision_mirror()
    return mirror.mirror_decisions_backfill(days=days)
