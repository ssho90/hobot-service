
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, List

from service.database.db import get_db_connection
from service.graph.neo4j_client import get_neo4j_client
from service.macro_trading.ai_strategist import (
    get_model_portfolio_allocation,
    get_model_portfolios,
    get_sub_mp_details,
)

logger = logging.getLogger(__name__)

def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value

def _extract_reasoning(summary: str) -> tuple[str, str]:
    """분석 요약에서 판단 근거 분리"""
    reasoning = ""
    refined_summary = summary or ""
    if "판단 근거:" in refined_summary:
        parts = refined_summary.split("판단 근거:")
        if len(parts) > 1:
            reasoning = parts[1].strip()
            refined_summary = parts[0].strip()
    return refined_summary, reasoning

def _get_strategy_history(limit: int = 100) -> List[Dict[str, Any]]:
    """MySQL에서 최근 전략 결정 이력 조회 (연속성 판단용)"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT decision_date, target_allocation
                FROM ai_strategy_decisions
                ORDER BY decision_date DESC
                LIMIT %s
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            return rows
    except Exception as e:
        logger.error(f"[OverviewService] 이력 조회 실패: {e}")
        return []

def _calculate_mp_started_at(current_mp_id: str, history_rows: List[Dict[str, Any]]) -> Optional[datetime]:
    """MP 연속 적용 시작일 계산"""
    mp_started_at = None
    if history_rows:
        for row in history_rows:
            row_alloc = _parse_json(row["target_allocation"])
            row_mp_id = row_alloc.get("mp_id") if isinstance(row_alloc, dict) else None
            
            if row_mp_id == current_mp_id:
                # date -> datetime 변환 (MySQL 커넥터 설정에 따라 다를 수 있음)
                d = row["decision_date"]
                if isinstance(d, str):
                    try:
                        d = datetime.fromisoformat(d)
                    except:
                        pass
                mp_started_at = d
            else:
                break
    return mp_started_at

def _calculate_sub_mp_started_at(current_sub_mp_ids: Dict[str, str], history_rows: List[Dict[str, Any]]) -> Dict[str, Optional[datetime]]:
    """Sub-MP 연속 적용 시작일 계산"""
    started_at_map = {k: None for k in current_sub_mp_ids.keys()}
    
    for asset_key, current_id in current_sub_mp_ids.items():
        if not current_id: continue
        
        for row in history_rows:
            row_alloc = _parse_json(row["target_allocation"])
            row_sub_mp = row_alloc.get("sub_mp", {}) if isinstance(row_alloc, dict) else {}
            # row_sub_mp가 dict of dict일 수도 있고, dict of str일 수도 있음
            # MySQL 기존 데이터: dict of str (ID만)
            # Graph DB 백필 데이터: dict of dict (상세정보 포함)
            
            row_id = None
            if isinstance(row_sub_mp, dict):
                val = row_sub_mp.get(asset_key)
                if isinstance(val, dict):
                    row_id = val.get("sub_mp_id")
                else:
                    row_id = val
            
            if row_id == current_id:
                d = row["decision_date"]
                if isinstance(d, str):
                    try:
                        d = datetime.fromisoformat(d)
                    except:
                        pass
                started_at_map[asset_key] = d
            else:
                break
    
    return started_at_map

async def get_overview_data() -> Dict[str, Any]:
    """AI 분석 Overview 데이터 조회 (Graph DB 우선)"""
    data = _get_from_graph()
    
    if not data:
        logger.info("[OverviewService] Graph DB 데이터 없음, MySQL Fallback")
        data = _get_from_mysql()
    
    if not data:
        return {"status": "success", "data": None, "message": "데이터 없음"}

    # 이력 데이터 조회 (공통)
    history_rows = _get_strategy_history()
    
    # 1. MP Info Enriched (started_at 계산)
    mp_info = data.get("mp_info", {})
    if data.get("mp_id"):
        started_at = _calculate_mp_started_at(data["mp_id"], history_rows)
        if started_at:
            fmt_date = started_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(started_at, datetime) else str(started_at)
            mp_info["started_at"] = fmt_date
            # update_at도 started_at으로 설정 (UI 호환성)
            mp_info["updated_at"] = fmt_date 
    data["mp_info"] = mp_info

    # 2. Sub-MP Info Enriched (started_at 계산)
    sub_mp_details = data.get("sub_mp", {})
    if sub_mp_details:
        # current sub_mp IDs 추출
        current_ids = {}
        for k, v in sub_mp_details.items():
            if isinstance(v, dict):
                current_ids[k] = v.get("sub_mp_id")
            else:
                current_ids[k] = v # 혹시 ID만 있는 경우
        
        started_at_map = _calculate_sub_mp_started_at(current_ids, history_rows)
        
        for k, dt in started_at_map.items():
            if dt and k in sub_mp_details:
                fmt_date = dt.strftime("%Y-%m-%d %H:%M:%S") if isinstance(dt, datetime) else str(dt)
                if isinstance(sub_mp_details[k], dict):
                    sub_mp_details[k]["started_at"] = fmt_date
                    sub_mp_details[k]["updated_at"] = fmt_date

    data["sub_mp"] = sub_mp_details
    
    return {"status": "success", "data": data}

def _get_from_graph() -> Optional[Dict[str, Any]]:
    client = get_neo4j_client()
    if not client: return None
    
    try:
        # Graph DB에는 recommended_stocks 컬럼이 없고 sub_mp JSON에 포함됨
        query = """
        MATCH (sd:StrategyDecision)
        RETURN 
            sd.decision_id AS id,
            toString(sd.decision_date) AS decision_date,
            sd.analysis_summary AS analysis_summary,
            sd.reasoning AS reasoning,
            sd.mp_id AS mp_id,
            sd.target_allocation AS target_allocation,
            sd.sub_mp AS sub_mp,
            toString(sd.created_at) AS created_at
        ORDER BY sd.decision_date DESC
        LIMIT 1
        """
        rows = client.run_read(query, {})
        if not rows: return None
        
        row = rows[0]
        
        # 기본 필드
        analysis_summary = row.get("analysis_summary", "")
        reasoning = row.get("reasoning")
        
        # 만약 Graph DB reasoning이 비어있으면 analysis_summary에서 추출 시도
        if not reasoning:
            analysis_summary, extracted_reasoning = _extract_reasoning(analysis_summary)
            reasoning = extracted_reasoning

        target_allocation = _parse_json(row.get("target_allocation"))
        sub_mp_json = _parse_json(row.get("sub_mp"))
        
        # Sub-MP Details 구성
        # Graph DB에는 ID 매핑만 있을 수 있으므로 get_sub_mp_details로 확장 시도
        sub_mp_details = sub_mp_json
        if sub_mp_json and isinstance(sub_mp_json, dict):
            # 간단한 체크: 값 중에 문자열이 있다면 ID 매핑으로 간주하고 확장 시도
            # (이미 확장된 데이터는 dict 값을 가짐)
            is_simple_mapping = any(isinstance(v, str) for v in sub_mp_json.values())
            if is_simple_mapping:
                try:
                    sub_mp_details = get_sub_mp_details(sub_mp_json)
                except Exception as e:
                    logger.warning(f"[OverviewService] Sub-MP 상세 정보 확장 실패: {e}")
        
        # MP Info 구성
        mp_id = row.get("mp_id")
        mp_info = {}
        if mp_id:
            all_mps = get_model_portfolios()
            mp_data = all_mps.get(mp_id, {})
            mp_info = {
                "name": mp_data.get("name"),
                "description": mp_data.get("description"),
                "updated_at": mp_data.get("updated_at")
            }

        # sub_mp_reasoning 추출
        sub_mp_reasoning = None
        if isinstance(sub_mp_details, dict):
            sub_mp_reasoning = sub_mp_details.get("reasoning")
            # 만약 reasoning이 없으면 원래 sub_mp_json에서 찾아봄 (ETFs 확장 과정에서 유실 가능성 대비)
            if not sub_mp_reasoning and isinstance(sub_mp_json, dict):
                 sub_mp_reasoning = sub_mp_json.get("reasoning")

        return {
            "decision_date": row.get("decision_date"),
            "analysis_summary": analysis_summary,
            "reasoning": reasoning,
            "mp_id": mp_id,
            "mp_info": mp_info,
            "target_allocation": target_allocation,
            "sub_mp": sub_mp_details,
            "sub_mp_reasoning": sub_mp_reasoning,
            "recommended_stocks": None, 
            "created_at": row.get("created_at")
        }

    except Exception as e:
        logger.warning(f"[OverviewService] Graph DB 조회 실패: {e}")
        return None

def _get_from_mysql() -> Optional[Dict[str, Any]]:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    decision_date,
                    analysis_summary,
                    target_allocation,
                    recommended_stocks,
                    created_at
                FROM ai_strategy_decisions
                ORDER BY decision_date DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if not row: return None
            
            # JSON 파싱
            target_allocation_raw = _parse_json(row['target_allocation'])
            recommended_stocks = _parse_json(row.get('recommended_stocks'))
            
            # MP 추출
            mp_id = None
            target_allocation = None
            sub_mp_data = None
            
            if isinstance(target_allocation_raw, dict):
                if "mp_id" in target_allocation_raw:
                    mp_id = target_allocation_raw.get("mp_id")
                    alloc_from_mp = get_model_portfolio_allocation(mp_id)
                    target_allocation = alloc_from_mp or target_allocation_raw.get("target_allocation")
                    sub_mp_data = target_allocation_raw.get("sub_mp")
                else:
                    target_allocation = target_allocation_raw
            
            # MP Info
            mp_info = {}
            if mp_id:
                all_mps = get_model_portfolios()
                mp_data = all_mps.get(mp_id, {})
                mp_info = {
                    "name": mp_data.get("name"),
                    "description": mp_data.get("description"),
                    "updated_at": mp_data.get("updated_at")
                }
            
            # Sub-MP Details (MySQL은 ID만 있으므로 확장 필요)
            sub_mp_details = None
            if sub_mp_data:
                sub_mp_details = get_sub_mp_details(sub_mp_data)
                
            # Analysis Summary & Reasoning
            analysis_summary, reasoning = _extract_reasoning(row['analysis_summary'])
            
            # Sub-MP Reasoning
            sub_mp_reasoning = None
            if isinstance(sub_mp_data, dict):
                sub_mp_reasoning = sub_mp_data.get("reasoning")
            
            return {
                "decision_date": row['decision_date'].strftime('%Y-%m-%d %H:%M:%S') if row['decision_date'] else None,
                "analysis_summary": analysis_summary,
                "reasoning": reasoning,
                "mp_id": mp_id,
                "mp_info": mp_info,
                "target_allocation": target_allocation,
                "sub_mp": sub_mp_details,
                "sub_mp_reasoning": sub_mp_reasoning,
                "recommended_stocks": recommended_stocks,
                "created_at": row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if row['created_at'] else None
            }
            
    except Exception as e:
        logger.error(f"[OverviewService] MySQL 조회 실패: {e}")
        return None
