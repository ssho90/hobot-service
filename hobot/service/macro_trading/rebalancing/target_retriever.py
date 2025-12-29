import json
import logging
from typing import Dict, Any, Optional
from service.database.db import get_db_connection
from service.macro_trading.ai_strategist import (
    get_model_portfolio_allocation,
    get_sub_mp_details,
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
    """최신 AI 전략의 MP 목표 비중 조회"""
    target_data = get_latest_target_data()
    if not target_data:
        return None
    return target_data["mp_target"]

def get_target_sub_mp_allocation() -> Optional[Any]:
    """최신 AI 전략의 Sub-MP 목표 상세 조회"""
    target_data = get_latest_target_data()
    if not target_data:
        return None
    return target_data["sub_mp_details"]

def get_latest_target_data() -> Optional[Dict[str, Any]]:
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
                ORDER BY decision_date DESC
                LIMIT 1
                """
            )
            decision_row = cursor.fetchone()

        if not decision_row:
            logger.info("No AI strategy decision found.")
            return None

        target_allocation_raw = decision_row["target_allocation"]
        decision_date = decision_row["decision_date"]
        
        if isinstance(target_allocation_raw, str):
            target_allocation_raw = json.loads(target_allocation_raw)

        mp_id = None
        target_alloc = None
        sub_mp_data = None
        
        if isinstance(target_allocation_raw, dict):
            if "mp_id" in target_allocation_raw:
                mp_id = target_allocation_raw["mp_id"]
                # 1. MP ID로 현재 정의된 비중 가져오기 (DB의 Model Portfolio 정의 우선)
                allocation_from_mp = get_model_portfolio_allocation(mp_id)
                
                # 2. 없다면 decision 당시 저장된 비중 사용
                target_alloc = allocation_from_mp or target_allocation_raw.get("target_allocation", target_allocation_raw)
                
                sub_mp_data = target_allocation_raw.get("sub_mp")
            else:
                # 구버전 데이터 호환
                target_alloc = target_allocation_raw
        else:
            target_alloc = target_allocation_raw

        target_alloc_norm = normalize_alloc(target_alloc)

        sub_mp_details = None
        if sub_mp_data and mp_id:
            sub_mp_details = get_sub_mp_details(sub_mp_data)

        return {
            "mp_target": target_alloc_norm,
            "sub_mp_details": sub_mp_details,
            "decision_date": decision_date
        }

    except Exception as e:
        logger.error(f"Error retrieving target allocation: {e}", exc_info=True)
        return None
