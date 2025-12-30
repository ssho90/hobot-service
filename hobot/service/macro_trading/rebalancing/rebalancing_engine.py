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

logger = logging.getLogger(__name__)

def execute_rebalancing(user_id: str) -> Dict[str, Any]:
    """
    전체 리밸런싱 프로세스 실행
    
    Flow:
    1. 현재 자산 상태 조회 (Asset Retriever)
    2. 목표 비중 조회 (Target Retriever)
    3. 리밸런싱 필요 여부 판단 (Drift Calculator - Phase 2)
    4. 매도 전략 수립 및 실행 (Sell Phase - Phase 3, 4, 5)
    5. 매수 전략 수립 및 실행 (Buy Phase - Phase 3, 4, 5)
    6. 결과 리포트
    """
    logger.info(f"Starting rebalancing process for user: {user_id}")
    
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
        
    thresholds = {"mp": float(config["mp"]), "sub_mp": float(config["sub_mp"])}
    logger.info(f"Using thresholds: {thresholds}")
    
    needed, drift_info = check_rebalancing_needed(current_state, target_mp, target_sub_mp, thresholds)
    
    logger.info(f"Rebalancing needed: {needed}")
    if needed:
        logger.info(f"Drift Reasons: {drift_info.get('reasons')}")

    if not needed:
        logger.info("Rebalancing not needed.")
        return {
            "status": "success", 
            "message": "Rebalancing not needed", 
            "drift_info": drift_info,
            "thresholds": thresholds
        }
    
    # 3. 매도 단계 (Phase 3~5)
    sell_result = execute_sell_phase(user_id, current_state, target_mp, target_sub_mp)
    if sell_result["status"] != "success":
        logger.warning(f"Sell phase issues: {sell_result.get('message')}")
        # 매도 실패시 중단할지 계속할지 정책 결정 필요. 여기선 중단.
        return sell_result
        
    # 4. 현금 갱신 및 매수 단계 (Phase 3~5)
    # 매도 후 현금이 변동되었으므로 다시 조회하거나 계산해야 함
    updated_cash = get_available_cash(user_id)
    logger.info(f"Available cash after sell: {updated_cash}")
    
    buy_result = execute_buy_phase(user_id, current_state, target_mp, target_sub_mp) 
    
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

def execute_sell_phase(user_id, current_state, target_mp, target_sub_mp):
    """
    매도 단계 실행 (Phase 3, 4, 5 구현 예정)
    """
    # TODO: Implement sell strategy planning, validation, execution
    return {"status": "success", "message": "No sell action (Not implemented)"}

def execute_buy_phase(user_id, current_state, target_mp, target_sub_mp):
    """
    매수 단계 실행 (Phase 3, 4, 5 구현 예정)
    """
    # TODO: Implement buy strategy planning, validation, execution
    return {"status": "success", "message": "No buy action (Not implemented)"}
