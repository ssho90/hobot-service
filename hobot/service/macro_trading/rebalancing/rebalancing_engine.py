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
    logger.info("Starting Phase 3: Netting & Planning (Python Algorithmic)")
    
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

    # 3.1.2 Feasibility Check
    from service.macro_trading.rebalancing.portfolio_calculator import verify_strategy_feasibility
    is_feasible, logic_errors = verify_strategy_feasibility(filtered_trades, current_holdings_map)
    
    if not is_feasible:
         return {"status": "error", "message": f"Strategy Logic Error: {logic_errors}"}

    # 3.2 Build Sell Orders
    from service.macro_trading.rebalancing.trading_strategy_builder import build_sell_orders, build_buy_orders
    sell_orders = build_sell_orders(filtered_trades, current_prices, tick_size=5)
    
    logger.info(f"Sell Orders Built: {len(sell_orders)}")
    
    if max_phase <= 3:
        return {
            "status": "success",
            "message": "Phase 3 Completed (Planning)",
            "net_trades": filtered_trades,
            "sell_orders": sell_orders
        }

    # --- Phase 5 (Step 4): Execute Sell Orders ---
    # NOTE: In a real scenario, this should be async and wait for completion. 
    # Here we assume immediate execution or we just log it for now as infrastructure might not be fully ready.
    # To properly implement, we need OrderExecutor.
    # from service.macro_trading.rebalancing.order_executor import execute_sell_phase
    # executed_sells = execute_sell_phase(sell_orders)
    
    # Mocking Sell Execution Effect for Cash Calculation
    # We need to know 'Available Cash' after Sell.
    # Since we can't real-trade here without user auth/market open, we simulate.
    current_cash = float(current_state.get('cash_balance', 0))
    est_sell_proceeds = sum([o['quantity'] * o['limit_price'] for o in sell_orders])
    
    # Simulate Cash (Current + Sell Proceeds - Fees)
    simulated_cash_balance = current_cash + int(est_sell_proceeds * 0.998) # 0.2% fee/tax buffer
    
    logger.info(f"Simulated Cash after SELL: {simulated_cash_balance} (Start: {current_cash} + Sell: {est_sell_proceeds})")

    # 3.3 Build Buy Orders
    buy_orders = build_buy_orders(filtered_trades, current_prices, tick_size=5)
    logger.info(f"Buy Orders Built: {len(buy_orders)}")

    # --- Phase 4: Buy Strategy Validation ---
    logger.info("Starting Phase 4: Buy Validation")
    from service.macro_trading.rebalancing.strategy_validator import validate_buy_strategy
    
    is_valid, reasons, validation_summary = validate_buy_strategy(
        buy_orders=buy_orders,
        current_cash=simulated_cash_balance,
        current_state=current_state,
        target_mp=target_mp,
        current_prices=current_prices
    )
    
    validation_result = {
        "is_valid": is_valid,
        "reasons": reasons,
        "summary": validation_summary
    }
    
    if not is_valid:
        logger.error(f"Buy Strategy Validation Failed: {reasons}")
        return {
            "status": "error",
            "message": "Buy Strategy Validation Failed",
            "validation_result": validation_result,
            "sell_orders": sell_orders, # Return what was planned/executed
            "buy_orders": buy_orders
        }
        
    if max_phase <= 4:
         return {
            "status": "success",
            "message": "Phase 4 Completed (Validation)",
            "sell_orders": sell_orders,
            "buy_orders": buy_orders,
            "validation_result": validation_result
        }

    # --- Phase 5 (Step 7): Execute Buy Orders ---
    # execute_buy_phase(buy_orders)
    
    return {
        "status": "success", 
        "message": "Rebalancing Completed (Simulated)",
        "sell_orders": sell_orders,
        "buy_orders": buy_orders,
        "validation_result": validation_result
    }

def check_rebalancing_needed(current_state, target_mp, target_sub_mp, thresholds):
    drift_details = calculate_detailed_drift(current_state, target_mp, target_sub_mp)
    is_exceeded, reasons = check_threshold_exceeded(drift_details, thresholds)
    drift_details['reasons'] = reasons
    return is_exceeded, drift_details
