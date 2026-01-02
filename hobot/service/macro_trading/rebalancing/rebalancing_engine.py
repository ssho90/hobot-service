import logging
import time
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
from service.macro_trading.rebalancing.portfolio_calculator import (
    calculate_target_quantities,
    calculate_net_trades,
    apply_minimum_trade_filter
)
from service.macro_trading.rebalancing.trading_strategy_planner import plan_trading_strategy
from service.macro_trading.rebalancing.strategy_validator import validate_strategy

from service.macro_trading.kis.kis_api import KISAPI
from service.macro_trading.kis.user_credentials import get_user_kis_credentials

logger = logging.getLogger(__name__)

async def execute_rebalancing(user_id: str, max_phase: int = 5) -> Dict[str, Any]:
    """
    전체 리밸런싱 프로세스 실행 (Revised Architecture)
    
    Args:
        max_phase (int):
             2: Drift Analysis Only
             3: Strategy Planning Only (Netting + LLM Plan)
             4: Validation Test (Netting + LLM Plan + Validation)
             5: Full Execution
    """
    logger.info(f"Starting rebalancing process for user: {user_id}, max_phase: {max_phase}")
    
    # --- Phase 1: Data Retrieval ---
    current_state = get_current_portfolio_state(user_id)
    if not current_state:
        return {"status": "error", "message": "Failed to retrieve portfolio state"}
    
    target_mp = get_target_mp_allocation()
    target_sub_mp = get_target_sub_mp_allocation()
    if not target_mp:
        return {"status": "error", "message": "Failed to retrieve target allocation"}
        
    # --- Phase 2: Drift Analysis ---
    config = get_rebalancing_config()
    thresholds = {"mp": float(config.get("mp", 3.0)), "sub_mp": float(config.get("sub_mp", 5.0))}
    
    needed, drift_info = check_rebalancing_needed(current_state, target_mp, target_sub_mp, thresholds)
    
    if max_phase <= 2:
        return {
            "status": "success",
            "message": "Phase 2 Completed",
            "rebalancing_needed": needed,
            "drift_info": drift_info
        }
        
    if not needed:
        return {"status": "success", "message": "Rebalancing not needed", "drift_info": drift_info}
        
    # --- Phase 3: Portfolio Optimization & Strategy Planning ---
    logger.info("Starting Phase 3: Netting & Planning")
    
    # 3.1 Netting & Sizing (Python)
    # Fetch current prices for all relevant tickers
    relevant_tickers = set()
    for _, sub_data in target_sub_mp.items():
        if isinstance(sub_data, dict) and 'etf_details' in sub_data:
            for etf in sub_data['etf_details']:
                relevant_tickers.add(etf['ticker'])
                
    # Also add current holdings
    for holding in current_state.get('holdings', []):
        relevant_tickers.add(holding['stock_code'])
        
    # Get Prices
    user_cred = get_user_kis_credentials(user_id)
    if not user_cred:
         return {"status": "error", "message": "User credentials not found"}
         
    kis = KISAPI(user_cred['app_key'], user_cred['app_secret'], user_cred['account_no'], is_simulation=user_cred.get('is_simulation', True)) 
    
    # Remove CASH placeholder if exists
    relevant_tickers.discard('CASH')
    
    current_prices = {}
    for ticker in relevant_tickers:
        price = kis.get_current_price(ticker)
        if price:
            current_prices[ticker] = price
        else:
             logger.warning(f"Failed to fetch price for {ticker}")
             
        # Rate Limit: Max 2 req/sec -> Sleep 0.5s
        time.sleep(0.5)
        
    # Validate if all prices are fetched
    missing_tickers = [t for t in relevant_tickers if t not in current_prices]
    if missing_tickers:
         error_msg = f"Failed to fetch current prices for: {missing_tickers}. Aborting rebalancing."
         logger.error(error_msg)
         return {"status": "error", "message": error_msg}
            
    # Flatten Target Weights (Global Weights)
    target_global_weights = {}
    for asset_class, mp_weight in target_mp.items():
        sub_info = target_sub_mp.get(asset_class, {})
        etf_details = sub_info.get('etf_details', [])
        for etf in etf_details:
             target_global_weights[etf['ticker']] = (mp_weight / 100.0) * float(etf.get('weight', 0))

    target_quantities = calculate_target_quantities(
        total_equity=current_state['total_eval_amount'],
        target_weights=target_global_weights,
        current_prices=current_prices
    )
    
    current_holdings_map = {h['stock_code']: int(h['holding_qty']) for h in current_state.get('holdings', [])}
    
    net_trades = calculate_net_trades(current_holdings_map, target_quantities)
    filtered_trades = apply_minimum_trade_filter(net_trades, current_prices)
    
    logger.info(f"Net Trades Calculated: {len(filtered_trades)} trades")
    
    # 3.2 LLM Strategy Planning
    execution_plan = await plan_trading_strategy(user_id, filtered_trades, current_state)
    logger.info(f"Execution Plan: {execution_plan}")
    
    if max_phase <= 3:
        return {
            "status": "success",
            "message": "Phase 3 Completed",
            "net_trades": filtered_trades,
            "execution_plan": execution_plan
        }

    # --- Phase 4: Strategy Validation ---
    logger.info("Starting Phase 4: Validation")
    is_valid, reasons, validation_summary = validate_strategy(
        current_state=current_state,
        target_mp=target_mp,
        execution_plan=execution_plan,
        current_prices=current_prices
    )
    
    validation_result = {
        "is_valid": is_valid,
        "reasons": reasons,
        "summary": validation_summary
    }
    
    if max_phase <= 4:
         return {
            "status": "success",
            "message": "Phase 4 Completed",
            "execution_plan": execution_plan,
            "validation_result": validation_result
        }
        
    if not is_valid:
        logger.error(f"Strategy Validation Failed: {reasons}")
        return {
            "status": "error",
            "message": "Strategy Validation Failed",
            "validation_result": validation_result
        }

    # --- Phase 5 (Execute) ---
    # TODO: Implement Phase 5 Execution
    
    return {
        "status": "success", 
        "message": "Rebalancing Completed (Phase 5 not fully linked yet)",
        "execution_plan": execution_plan,
        "validation_result": validation_result
    }

def check_rebalancing_needed(current_state, target_mp, target_sub_mp, thresholds):
    drift_details = calculate_detailed_drift(current_state, target_mp, target_sub_mp)
    is_exceeded, reasons = check_threshold_exceeded(drift_details, thresholds)
    drift_details['reasons'] = reasons
    return is_exceeded, drift_details
