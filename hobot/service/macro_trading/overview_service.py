
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from service.database.db import get_db_connection
from service.graph.neo4j_client import get_neo4j_client
from service.macro_trading.ai_strategist import (
    get_model_portfolio_allocation,
    get_model_portfolios,
    get_sub_mp_details,
)

logger = logging.getLogger(__name__)
ASSET_KEYS = ("stocks", "bonds", "alternatives", "cash")
QUALITY_GATE_LINE_PATTERN = re.compile(r"^\s*(Quality Gate 적용:|품질\s*게이트)", re.IGNORECASE)
CONFIDENCE_PATTERN = re.compile(r"(?:confidence|신뢰도)\s*=\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
RISK_ACTION_PATTERN = re.compile(r"(?:risk_action|리스크 판단)\s*=\s*([A-Z_가-힣 ]+)")

USER_FRIENDLY_REPLACEMENTS = (
    ("Quant 모델", "정량 분석"),
    ("Narrative Report", "시장 해석 분석"),
    ("Risk Report", "리스크 점검"),
    ("Quality Gate", "품질 게이트"),
    ("previous_mp 유지", "기존 MP 유지"),
    ("HOLD_PREVIOUS", "기존 전략 유지"),
    ("Late Cycle Slowdown (Stagflationary)", "후기 경기둔화(물가압력 동반)"),
    ("Bear Steepening", "장단기 금리차 확대"),
    ("Sub-Allocator", "자산군 세부 배분"),
    ("Sub-Agent", "세부 분석 모듈"),
    ("Supervisor:", "종합 판단:"),
    ("Sub-Allocator:", "세부 배분 판단:"),
    ("Stocks=", "주식="),
    ("Bonds=", "채권="),
    ("Alternatives=", "대체자산="),
    ("Cash=", "현금="),
)

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


def _dedupe_lines(text: str) -> str:
    if not text:
        return ""
    seen = set()
    deduped: List[str] = []
    for line in text.splitlines():
        normalized = line.strip()
        if not normalized:
            if deduped and deduped[-1]:
                deduped.append("")
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(line)
    return "\n".join(deduped).strip()


def _strip_quality_gate_lines(text: str) -> str:
    if not text:
        return ""
    kept = [line for line in text.splitlines() if not QUALITY_GATE_LINE_PATTERN.match(line)]
    return "\n".join(kept).strip()


def _to_user_friendly_text(text: str) -> str:
    if not text:
        return ""
    converted = text
    for before, after in USER_FRIENDLY_REPLACEMENTS:
        converted = converted.replace(before, after)
    return converted.strip()


def _extract_decision_meta_from_text(*texts: Optional[str]) -> Dict[str, Any]:
    candidates = [text for text in texts if isinstance(text, str) and text.strip()]
    if not candidates:
        return {}

    joined = "\n".join(candidates)
    meta: Dict[str, Any] = {}

    lowered = joined.lower()
    if ("quality gate 적용" in lowered) or ("품질 게이트" in joined):
        meta["quality_gate_applied"] = True
        first_gate_line = next(
            (line.strip() for line in joined.splitlines() if QUALITY_GATE_LINE_PATTERN.match(line)),
            "",
        )
        if first_gate_line:
            meta["quality_gate_reason"] = _to_user_friendly_text(first_gate_line)

    confidence_match = CONFIDENCE_PATTERN.search(joined)
    if confidence_match:
        try:
            meta["confidence"] = float(confidence_match.group(1))
        except (TypeError, ValueError):
            pass

    risk_action_match = RISK_ACTION_PATTERN.search(joined)
    if risk_action_match:
        action = risk_action_match.group(1).strip().upper()
        if action:
            meta["quality_gate_risk_action"] = action
            meta["risk_summary"] = {"recommended_action": action}

    return meta


def _merge_decision_meta(
    primary: Optional[Dict[str, Any]],
    fallback: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(primary, dict) and not isinstance(fallback, dict):
        return None

    merged: Dict[str, Any] = {}
    if isinstance(primary, dict):
        merged.update(primary)
    if isinstance(fallback, dict):
        for key, value in fallback.items():
            if key == "risk_summary":
                base = merged.get("risk_summary")
                merged["risk_summary"] = {**(base if isinstance(base, dict) else {}), **(value if isinstance(value, dict) else {})}
            elif key == "quality_gate_applied":
                if value is True:
                    merged["quality_gate_applied"] = True
                elif key not in merged:
                    merged[key] = value
            elif key not in merged or merged.get(key) in (None, "", []):
                merged[key] = value

    quality_reason = str(merged.get("quality_gate_reason") or "").strip()
    if quality_reason:
        merged["quality_gate_reason"] = _to_user_friendly_text(quality_reason)

    if "quality_gate_applied" not in merged and (
        merged.get("quality_gate_reason") or merged.get("quality_gate_risk_action")
    ):
        merged["quality_gate_applied"] = True

    return merged if merged else None


def _finalize_readable_text(summary: str, reasoning: str) -> tuple[str, str]:
    clean_summary = _to_user_friendly_text(_dedupe_lines(summary or ""))
    clean_reasoning = _strip_quality_gate_lines(reasoning or "")
    clean_reasoning = _to_user_friendly_text(_dedupe_lines(clean_reasoning))
    return clean_summary, clean_reasoning


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
        if not dt:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue
    else:
        dt = None

    if not dt:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _normalize_target_allocation(value: Any) -> Dict[str, float]:
    if not isinstance(value, dict):
        return {}

    normalized: Dict[str, float] = {}
    for key in ASSET_KEYS:
        candidate = value.get(key)
        if candidate is None:
            candidate = value.get(key.capitalize())
        if candidate is None:
            candidate = value.get(key.upper())

        try:
            if candidate is not None:
                normalized[key] = float(candidate)
        except (TypeError, ValueError):
            continue

    return normalized


def _extract_target_allocation_payload(value: Any) -> Dict[str, float]:
    payload = _parse_json(value)
    if not isinstance(payload, dict):
        return {}

    nested = payload.get("target_allocation")
    if isinstance(nested, dict):
        return _normalize_target_allocation(nested)
    return _normalize_target_allocation(payload)


def _infer_mp_id_from_target_allocation(target_allocation: Dict[str, float]) -> Optional[str]:
    if not target_allocation:
        return None

    try:
        model_portfolios = get_model_portfolios()
    except Exception:
        return None

    tolerance = 0.05
    for mp_id, mp_data in model_portfolios.items():
        candidate = _normalize_target_allocation(mp_data.get("allocation"))
        if not candidate:
            continue

        if all(abs(candidate.get(key, 0.0) - target_allocation.get(key, 0.0)) <= tolerance for key in ASSET_KEYS):
            return mp_id

    return None


def _extract_mp_id_from_payload(value: Any) -> Optional[str]:
    payload = _parse_json(value)
    if not isinstance(payload, dict):
        return None

    mp_id = payload.get("mp_id")
    if mp_id:
        return str(mp_id)

    inferred = _infer_mp_id_from_target_allocation(_extract_target_allocation_payload(payload))
    return str(inferred) if inferred else None


def _extract_sub_mp_ids_from_payload(value: Any) -> Dict[str, str]:
    payload = _parse_json(value)
    if not isinstance(payload, dict):
        return {}

    candidate = payload.get("sub_mp")
    if not isinstance(candidate, dict):
        candidate = payload

    extracted: Dict[str, str] = {}
    for key in ASSET_KEYS:
        raw = candidate.get(key) if isinstance(candidate, dict) else None
        if isinstance(raw, dict):
            raw = raw.get("sub_mp_id") or raw.get(f"{key}_sub_mp")
        if isinstance(raw, str) and raw.strip():
            extracted[key] = raw.strip()

    return extracted


def _calculate_elapsed_days(started_at: Any) -> Optional[int]:
    start_dt = _coerce_datetime(started_at)
    if not start_dt:
        return None

    diff_seconds = (datetime.utcnow() - start_dt).total_seconds()
    if diff_seconds < 0:
        return 1
    return max(1, int(diff_seconds // 86400))

def _get_strategy_history(limit: int = 2000) -> List[Dict[str, Any]]:
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
            row_mp_id = _extract_mp_id_from_payload(row.get("target_allocation"))
            
            if row_mp_id == current_mp_id:
                # date -> datetime 변환 (MySQL 커넥터 설정에 따라 다를 수 있음)
                d = _coerce_datetime(row.get("decision_date")) or row.get("decision_date")
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
            row_sub_mp_ids = _extract_sub_mp_ids_from_payload(row.get("target_allocation"))
            row_id = row_sub_mp_ids.get(asset_key)
            
            if row_id == current_id:
                d = _coerce_datetime(row.get("decision_date")) or row.get("decision_date")
                started_at_map[asset_key] = d
            else:
                break
    
    return started_at_map

async def get_overview_data() -> Dict[str, Any]:
    """AI 분석 Overview 데이터 조회 (MySQL 우선, Graph fallback)"""
    graph_data = _get_from_graph()
    mysql_data = _get_from_mysql()

    # 수동 업데이트 직후에는 MySQL이 source-of-truth 이므로 MySQL을 우선 사용
    data = mysql_data or graph_data
    if graph_data and mysql_data:
        logger.info("[OverviewService] Selected overview source: mysql (preferred), graph as fallback")
    elif not data:
        logger.info("[OverviewService] Graph/MySQL 모두 데이터 없음")
    
    if not data:
        return {"status": "success", "data": None, "message": "데이터 없음"}

    raw_analysis_summary = str(data.get("analysis_summary") or "")
    raw_reasoning = str(data.get("reasoning") or "")

    derived_meta = _extract_decision_meta_from_text(raw_reasoning, raw_analysis_summary)

    analysis_summary, reasoning = _finalize_readable_text(raw_analysis_summary, raw_reasoning)
    data["analysis_summary"] = analysis_summary
    data["reasoning"] = reasoning
    data["sub_mp_reasoning"] = _to_user_friendly_text(
        _dedupe_lines(str(data.get("sub_mp_reasoning") or ""))
    )
    data["decision_meta"] = _merge_decision_meta(data.get("decision_meta"), derived_meta)

    # 이력 데이터 조회 (공통)
    history_rows = _get_strategy_history()
    
    # 1. MP Info Enriched (started_at 계산)
    mp_info = data.get("mp_info", {})
    current_mp_id = data.get("mp_id") or _extract_mp_id_from_payload(
        {"target_allocation": data.get("target_allocation")}
    )
    if current_mp_id:
        data["mp_id"] = current_mp_id
        started_at = _calculate_mp_started_at(current_mp_id, history_rows)
        if started_at:
            fmt_date = started_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(started_at, datetime) else str(started_at)
            mp_info["started_at"] = fmt_date
            # update_at도 started_at으로 설정 (UI 호환성)
            mp_info["updated_at"] = fmt_date
            elapsed_days = _calculate_elapsed_days(started_at)
            if elapsed_days is not None:
                mp_info["duration_days"] = elapsed_days
    data["mp_info"] = mp_info

    # 2. Sub-MP Info Enriched (started_at 계산)
    sub_mp_details = data.get("sub_mp", {})
    if sub_mp_details:
        # current sub_mp IDs 추출
        current_ids = {}
        for k in ("stocks", "bonds", "alternatives", "cash"):
            v = sub_mp_details.get(k)
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
                    elapsed_days = _calculate_elapsed_days(dt)
                    if elapsed_days is not None:
                        sub_mp_details[k]["duration_days"] = elapsed_days

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

        target_allocation_raw = _parse_json(row.get("target_allocation"))
        decision_meta = None
        embedded_sub_mp = None
        mp_id = row.get("mp_id")

        target_allocation = target_allocation_raw
        if isinstance(target_allocation_raw, dict):
            if target_allocation_raw.get("mp_id"):
                mp_id = target_allocation_raw.get("mp_id") or mp_id
            if "target_allocation" in target_allocation_raw:
                target_allocation = target_allocation_raw.get("target_allocation")
            embedded_sub_mp = target_allocation_raw.get("sub_mp")
            raw_decision_meta = target_allocation_raw.get("decision_meta")
            if isinstance(raw_decision_meta, dict):
                decision_meta = raw_decision_meta

        if not isinstance(target_allocation, dict):
            target_allocation = {}

        sub_mp_json = _parse_json(row.get("sub_mp"))
        if (not isinstance(sub_mp_json, dict) or not sub_mp_json) and embedded_sub_mp is not None:
            sub_mp_json = _parse_json(embedded_sub_mp)
        
        # Sub-MP Details 구성
        # Graph DB에는 ID 매핑만 있을 수 있으므로 get_sub_mp_details로 확장 시도
        sub_mp_details = sub_mp_json
        if sub_mp_json and isinstance(sub_mp_json, dict):
            # 자산군 키에 문자열 ID가 있으면 단순 ID 매핑으로 간주하고 확장 시도
            is_simple_mapping = any(
                isinstance(sub_mp_json.get(asset_key), str)
                for asset_key in ("stocks", "bonds", "alternatives", "cash")
            )
            if is_simple_mapping:
                try:
                    sub_mp_details = get_sub_mp_details(sub_mp_json)
                except Exception as e:
                    logger.warning(f"[OverviewService] Sub-MP 상세 정보 확장 실패: {e}")
        
        # MP Info 구성
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
        sub_mp_reasoning_by_asset = None
        if isinstance(sub_mp_details, dict):
            sub_mp_reasoning = sub_mp_details.get("reasoning")
            candidate_reasoning_map = sub_mp_details.get("reasoning_by_asset")
            if isinstance(candidate_reasoning_map, dict):
                sub_mp_reasoning_by_asset = candidate_reasoning_map
            # 만약 reasoning이 없으면 원래 sub_mp_json에서 찾아봄 (ETFs 확장 과정에서 유실 가능성 대비)
            if not sub_mp_reasoning and isinstance(sub_mp_json, dict):
                 sub_mp_reasoning = sub_mp_json.get("reasoning")
            if not sub_mp_reasoning_by_asset and isinstance(sub_mp_json, dict):
                fallback_reasoning_map = sub_mp_json.get("reasoning_by_asset")
                if isinstance(fallback_reasoning_map, dict):
                    sub_mp_reasoning_by_asset = fallback_reasoning_map

        return {
            "decision_date": row.get("decision_date"),
            "analysis_summary": analysis_summary,
            "reasoning": reasoning,
            "mp_id": mp_id,
            "mp_info": mp_info,
            "target_allocation": target_allocation,
            "sub_mp": sub_mp_details,
            "sub_mp_reasoning": sub_mp_reasoning,
            "sub_mp_reasoning_by_asset": sub_mp_reasoning_by_asset,
            "decision_meta": decision_meta,
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
            decision_meta = None
            
            if isinstance(target_allocation_raw, dict):
                raw_decision_meta = target_allocation_raw.get("decision_meta")
                if isinstance(raw_decision_meta, dict):
                    decision_meta = raw_decision_meta
                if "mp_id" in target_allocation_raw:
                    mp_id = target_allocation_raw.get("mp_id")
                    alloc_from_mp = get_model_portfolio_allocation(mp_id)
                    target_allocation = alloc_from_mp or target_allocation_raw.get("target_allocation")
                    sub_mp_data = target_allocation_raw.get("sub_mp")
                else:
                    target_allocation = target_allocation_raw
            
            if not isinstance(target_allocation, dict):
                target_allocation = {}
            
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
            sub_mp_reasoning_by_asset = None
            if isinstance(sub_mp_data, dict):
                sub_mp_reasoning = sub_mp_data.get("reasoning")
                candidate_reasoning_map = sub_mp_data.get("reasoning_by_asset")
                if isinstance(candidate_reasoning_map, dict):
                    sub_mp_reasoning_by_asset = candidate_reasoning_map
            
            return {
                "decision_date": row['decision_date'].strftime('%Y-%m-%d %H:%M:%S') if row['decision_date'] else None,
                "analysis_summary": analysis_summary,
                "reasoning": reasoning,
                "mp_id": mp_id,
                "mp_info": mp_info,
                "target_allocation": target_allocation,
                "sub_mp": sub_mp_details,
                "sub_mp_reasoning": sub_mp_reasoning,
                "sub_mp_reasoning_by_asset": sub_mp_reasoning_by_asset,
                "decision_meta": decision_meta,
                "recommended_stocks": recommended_stocks,
                "created_at": row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if row['created_at'] else None
            }
            
    except Exception as e:
        logger.error(f"[OverviewService] MySQL 조회 실패: {e}")
        return None
