import logging
from typing import Dict, Any, List, Optional
from service.macro_trading.kis.kis import get_balance_info_api

logger = logging.getLogger(__name__)

def get_available_cash(user_id: str) -> float:
    """사용자의 주문 가능 현금 조회"""
    # 현재 kis.py의 구조상 get_balance_info_api 내에서 현금 정보를 가져옴.
    # 더 정확한 '주문가능금액' API가 있다면 그것을 사용하는 것이 좋지만, 
    # 일단 get_balance_info_api 결과를 활용하거나, kis_api 직접 호출이 필요할 수 있음.
    # 여기서는 get_balance_info_api의 cash_balance를 활용.
    balance = get_balance_info_api(user_id)
    if not balance or balance.get("status") != "success":
        logger.error(f"Failed to get balance for user {user_id}: {balance.get('message')}")
        return 0.0
    return float(balance.get("cash_balance") or 0)

def get_current_portfolio_state(user_id: str) -> Optional[Dict[str, Any]]:
    """
    현재 포트폴리오 상태 조회
    Returns:
        {
            "mp_actual": {"stocks": ..., "bonds": ..., ...},
            "holdings_by_asset_class": {
                "stocks": [...],
                "bonds": [...],
                ...
            },
            "total_eval_amount": float,
            "cash_balance": float
        }
    """
    try:
        balance = get_balance_info_api(user_id)
        if not balance or balance.get("status") != "success":
            logger.error(f"KIS balance lookup failed: {balance.get('message') if balance else 'No response'}")
            return None

        asset_class_info = balance.get("asset_class_info") or {}
        total_eval_amount = float(balance.get("total_eval_amount") or 0)
        cash_balance = float(balance.get("cash_balance") or 0)

        def get_class_total(key: str) -> float:
            info = asset_class_info.get(key) or {}
            return float(info.get("total_eval_amount") or 0)

        # MP 실제 비중 계산
        actual_alloc = {"stocks": 0.0, "bonds": 0.0, "alternatives": 0.0, "cash": 0.0}
        if total_eval_amount > 0:
            actual_alloc["stocks"] = round(get_class_total("stocks") / total_eval_amount * 100, 2)
            actual_alloc["bonds"] = round(get_class_total("bonds") / total_eval_amount * 100, 2)
            actual_alloc["alternatives"] = round(get_class_total("alternatives") / total_eval_amount * 100, 2)
            
            # cash asset class total might differ from cash_balance depending on logic
            # Use logic consistent with main.py
            cash_total_in_class = get_class_total("cash")
            cash_val = cash_total_in_class or cash_balance
            actual_alloc["cash"] = round(cash_val / total_eval_amount * 100, 2)

        # 자산군별 보유 종목 정리
        holdings_by_asset_class = {}
        for key in ["stocks", "bonds", "alternatives", "cash"]:
            info = asset_class_info.get(key) or {}
            holdings = info.get("holdings") or []
            # Normalize holding structure if needed
            holdings_by_asset_class[key] = holdings

        return {
            "mp_actual": actual_alloc,
            "holdings_by_asset_class": holdings_by_asset_class,
            "total_eval_amount": total_eval_amount,
            "cash_balance": cash_balance
        }

    except Exception as e:
        logger.error(f"Error retrieving portfolio state: {e}", exc_info=True)
        return None

