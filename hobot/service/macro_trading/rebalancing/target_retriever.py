import logging
from typing import Dict, Any, Optional
from service.database.db import get_db_connection
from service.macro_trading.rebalancing.signal_tracker import (
    build_signal_bundle,
    DEFAULT_STRATEGY_PROFILE_ID,
    normalize_target_payload,
)

logger = logging.getLogger(__name__)

"""
[Reference Data Structure for ai_strategy_decisions.target_allocation]
{
  "mp_id": "MP-4", 
  "sub_mp": {
    "cash": "Cash-N", 
    "bonds": "Bnd-L", 
    "stocks": "Eq-D", 
    "reasoning": "...", 
    "alternatives": "Alt-I"
  }, 
  "target_allocation": {
    "Cash": 10.0, 
    "Bonds": 50.0, 
    "Stocks": 20.0, 
    "Alternatives": 20.0
  }
}
"""

def normalize_alloc(alloc: dict) -> Dict[str, float]:
    """자산 배분 딕셔너리를 표준 형식으로 변환"""
    if not alloc:
        return {"stocks": 0.0, "bonds": 0.0, "alternatives": 0.0, "cash": 0.0}
    return {
        "stocks": float(alloc.get("stocks") or alloc.get("Stocks") or 0),
        "bonds": float(alloc.get("bonds") or alloc.get("Bonds") or 0),
        "alternatives": float(alloc.get("alternatives") or alloc.get("Alternatives") or 0),
        "cash": float(alloc.get("cash") or alloc.get("Cash") or 0),
    }

def get_target_mp_allocation() -> Optional[Dict[str, float]]:
    """현재 확정 target 기준 MP 목표 비중 조회"""
    target_data = get_current_target_data()
    if not target_data:
        return None
    return target_data["mp_target"]

def get_target_sub_mp_allocation() -> Optional[Any]:
    """현재 확정 target 기준 Sub-MP 목표 상세 조회"""
    target_data = get_current_target_data()
    if not target_data:
        return None
    return target_data["sub_mp_details"]

def get_current_target_data(
    strategy_profile_id: str = DEFAULT_STRATEGY_PROFILE_ID,
) -> Optional[Dict[str, Any]]:
    """자동 리밸런싱용 현재 target. 확정 target이 없으면 최신 AI 판단으로 fallback한다."""
    return (
        get_effective_target_data(strategy_profile_id=strategy_profile_id)
        or get_latest_target_data(strategy_profile_id=strategy_profile_id)
    )


def get_effective_target_data(
    strategy_profile_id: str = DEFAULT_STRATEGY_PROFILE_ID,
) -> Optional[Dict[str, Any]]:
    """현재 ACTIVE 상태의 확정 target을 조회한다."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    target_signature,
                    target_payload_json,
                    effective_from_date
                FROM effective_rebalancing_targets
                WHERE strategy_profile_id = %s
                  AND status = 'ACTIVE'
                ORDER BY effective_from_date DESC, id DESC
                LIMIT 1
                """,
                (strategy_profile_id,),
            )
            target_row = cursor.fetchone()

        if not target_row:
            return None

        return _build_target_data(
            target_signature=target_row.get("target_signature"),
            target_payload=target_row["target_payload_json"],
            decision_date=target_row["effective_from_date"],
        )
    except Exception as e:
        logger.error(f"Error retrieving effective target allocation: {e}", exc_info=True)
        return None


def get_latest_target_data(
    strategy_profile_id: str = DEFAULT_STRATEGY_PROFILE_ID,
) -> Optional[Dict[str, Any]]:
    """
    최신 AI 전략 데이터를 조회하여 정규화된 형태로 반환
    Returns:
        {
            "mp_target": {"stocks": ..., "bonds": ..., ...},
            "sub_mp_details": { ... },
            "decision_date": "YYYY-MM-DD ..."
        }
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    target_allocation,
                    decision_date
                FROM ai_strategy_decisions
                WHERE strategy_profile_id = %s
                   OR strategy_profile_id IS NULL
                ORDER BY decision_date DESC
                LIMIT 1
                """,
                (strategy_profile_id,),
            )
            decision_row = cursor.fetchone()

        if not decision_row:
            logger.info("No AI strategy decision found.")
            return None

        return _build_target_data(
            target_payload=decision_row["target_allocation"],
            decision_date=decision_row["decision_date"],
        )

    except Exception as e:
        logger.error(f"Error retrieving target allocation: {e}", exc_info=True)
        return None


def _build_target_data(
    target_payload: Any,
    decision_date: Any,
    target_signature: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    normalized_payload = normalize_target_payload(target_payload)
    signal_bundle = build_signal_bundle(normalized_payload)
    target_alloc_norm = normalize_alloc(normalized_payload.get("target_allocation"))
    sub_mp_details = _resolve_sub_mp_details(normalized_payload)
    return {
        "mp_target": target_alloc_norm,
        "sub_mp_details": sub_mp_details,
        "decision_date": decision_date,
        "target_payload": normalized_payload,
        "target_signature": target_signature or signal_bundle["effective_target_signature"],
        "mp_signature": signal_bundle["mp_signature"],
        "sub_mp_signatures": signal_bundle["sub_mp_signatures"],
    }


def _resolve_sub_mp_details(normalized_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sub_mp_details_snapshot = normalized_payload.get("sub_mp_details_snapshot")
    if isinstance(sub_mp_details_snapshot, dict) and sub_mp_details_snapshot:
        return sub_mp_details_snapshot

    sub_mp_data = normalized_payload.get("sub_mp")
    if not sub_mp_data:
        return None

    from service.macro_trading.ai_strategist import get_sub_mp_details

    return get_sub_mp_details(sub_mp_data)
