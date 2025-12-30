import logging
from typing import Dict, Any, Tuple

from service.macro_trading.rebalancing.target_retriever import (
    get_target_mp_allocation,
    get_target_sub_mp_allocation
)
from service.macro_trading.rebalancing.asset_retriever import (
    get_current_portfolio_state,
    get_available_cash
)
from service.macro_trading.rebalancing.drift_calculator import (
    calculate_detailed_drift,
    check_threshold_exceeded
)
from service.macro_trading.rebalancing.config_retriever import get_rebalancing_config
from service.macro_trading.rebalancing.sell_strategy_planner import plan_sell_strategy
from service.macro_trading.rebalancing.buy_strategy_planner import plan_buy_strategy

logger = logging.getLogger(__name__)

async def execute_rebalancing(user_id: str, max_phase: int = 5) -> Dict[str, Any]:
    """
    전체 리밸런싱 프로세스 실행
    
    Flow:
    1. 현재 자산 상태 조회 (Asset Retriever)
    2. 목표 비중 조회 (Target Retriever)
    3. 리밸런싱 필요 여부 판단 (Drift Calculator - Phase 2)
    4. 매도 전략 수립 및 실행 (Sell Phase - Phase 3, 4, 5)
    5. 매수 전략 수립 및 실행 (Buy Phase - Phase 3, 4, 5)
    6. 결과 리포트

    Args:
        max_phase (int): 실행할 최대 단계
             2: 리밸런싱 필요 여부 판단까지만 실행 (Phase 2)
             3: 매매 전략 수립까지만 실행 (Phase 3 - LLM Planning Only)
             5: 실제 매매 실행까지 포함 (Full Execution)
    """
    logger.info(f"Starting rebalancing process for user: {user_id}, max_phase: {max_phase}")
    
    # 1. 데이터 조회
    current_state = get_current_portfolio_state(user_id)
    if not current_state:
        msg = "Failed to retrieve current portfolio state. Aborting."
        logger.error(msg)
        return {"status": "error", "message": msg}
        
    target_mp = get_target_mp_allocation()
    target_sub_mp = get_target_sub_mp_allocation()
    
    if not target_mp:
        msg = "Failed to retrieve target MP allocation. Aborting."
        logger.error(msg)
        return {"status": "error", "message": msg}

    logger.info(f"Current MP Actual: {current_state.get('mp_actual')}")
    logger.info(f"Target MP: {target_mp}")
    
    # 2. 리밸런싱 필요 여부 확인 (Phase 2)
    # DB에서 임계값 및 활성화 여부 조회
    config = get_rebalancing_config()
    if not config.get("is_active", True):
        logger.info("Rebalancing is disabled in config.")
        return {"status": "success", "message": "Rebalancing disabled by config"}
        
    thresholds = {"mp": float(config.get("mp", 3.0)), "sub_mp": float(config.get("sub_mp", 5.0))}
    logger.info(f"Using thresholds: {thresholds}")
    
    needed, drift_info = check_rebalancing_needed(current_state, target_mp, target_sub_mp, thresholds)
    
    logger.info(f"Rebalancing needed: {needed}")
    if needed:
        logger.info(f"Drift Reasons: {drift_info.get('reasons')}")
    
    # Phase 2 종료 조건
    if max_phase <= 2:
        return {
            "status": "success",
            "message": "Phase 2 (Drift Analysis) Completed",
            "rebalancing_needed": needed,
            "drift_info": drift_info,
            "thresholds": thresholds
        }

    if not needed:
        logger.info("Rebalancing not needed.")
        return {
            "status": "success", 
            "message": "Rebalancing not needed", 
            "drift_info": drift_info,
            "thresholds": thresholds
        }
    
    # 3. 매도 단계 (Phase 3~5)
    sell_result = await execute_sell_phase(user_id, current_state, target_mp, target_sub_mp, drift_info)
    if sell_result["status"] != "success":
        logger.warning(f"Sell phase issues: {sell_result.get('message')}")
        return sell_result

    # Phase 3 종료 조건 (Planning Only) - 매수 플랜까지 수립 후 종료
    if max_phase <= 3:
        # 매도 시뮬레이션: sell_result['orders']의 예상 수익금을 더해서 현금 추정 가능하나
        # 현재는 간단히 현재 현금으로 Buy Plan 수립
        buy_result = await execute_buy_phase(user_id, current_state, target_mp, target_sub_mp, drift_info)
        
        return {
            "status": "success",
            "message": "Phase 3 (Strategy Planning) Completed",
            "sell_plan": sell_result.get("orders"),
            "buy_plan": buy_result.get("orders"),
            "drift_info": drift_info
        }
        
    # 4. 현금 갱신 및 매수 단계 (Phase 3~5)
    # 매도 후 현금이 변동되었으므로 다시 조회하거나 계산해야 함
    updated_cash = get_available_cash(user_id)
    logger.info(f"Available cash after sell: {updated_cash}")
    
    # Update cash in current_state for buy phase
    current_state["cash_balance"] = updated_cash
    
    buy_result = await execute_buy_phase(user_id, current_state, target_mp, target_sub_mp, drift_info) 
    
    return {
        "status": "success", 
        "message": "Rebalancing completed",
        "sell_result": sell_result,
        "buy_result": buy_result
    }

def check_rebalancing_needed(current_state, target_mp, target_sub_mp, thresholds):
    """
    리밸런싱 필요 여부 판단 (Phase 2 Implementaiton)
    """
    # 1. 상세 편차 계산
    drift_details = calculate_detailed_drift(current_state, target_mp, target_sub_mp)
    
    # 2. 임계값 초과 여부 확인
    is_exceeded, reasons = check_threshold_exceeded(drift_details, thresholds)
    
    drift_details['reasons'] = reasons
    
    return is_exceeded, drift_details

async def execute_sell_phase(user_id, current_state, target_mp, target_sub_mp, drift_info):
    """
    매도 단계 실행 (Phase 3: LLM 전략 수립)
    """
    logger.info("Executing Sell Phase...")
    
    # Phase 3: LLM 매도 전략 수립
    sell_orders = await plan_sell_strategy(current_state, target_mp, target_sub_mp, drift_info)
    
    logger.info(f"Planned Sell Orders: {sell_orders}")
    
    if not sell_orders:
        return {"status": "success", "message": "No sell orders generated", "orders": []}

    # TODO: Phase 4 (Validation) & Phase 5 (Execution)
    
    return {"status": "success", "message": "Sell strategy planned", "orders": sell_orders}

async def execute_buy_phase(user_id, current_state, target_mp, target_sub_mp, drift_info):
    """
    매수 단계 실행 (Phase 3: LLM 전략 수립)
    """
    logger.info("Executing Buy Phase...")
    
    # Phase 3: LLM 매수 전략 수립
    buy_orders = await plan_buy_strategy(current_state, target_mp, target_sub_mp, drift_info)
    
    logger.info(f"Planned Buy Orders: {buy_orders}")
    
    if not buy_orders:
        return {"status": "success", "message": "No buy orders generated", "orders": []}

    # TODO: Phase 4 (Validation) & Phase 5 (Execution)
    
    return {"status": "success", "message": "Buy strategy planned", "orders": buy_orders}
