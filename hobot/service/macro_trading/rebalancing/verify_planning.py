import sys
import os
import asyncio
import logging
from typing import Dict, Any

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from service.macro_trading.rebalancing.rebalancing_engine import execute_rebalancing, execute_sell_phase, execute_buy_phase
from service.macro_trading.rebalancing.sell_strategy_planner import plan_sell_strategy
from service.macro_trading.rebalancing.buy_strategy_planner import plan_buy_strategy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_llm_planning():
    logger.info("Starting Phase 3 Verification (LLM Strategy Planning)...")
    
    # 1. Mock Data
    current_state = {
        "total_eval_amount": 10000000,
        "cash_balance": 500000, # 50만원
        "mp_actual": {
            "stocks": 45.0,
            "bonds": 40.0,
            "alternatives": 10.0,
            "cash": 5.0
        },
        "holdings": [
             {"stock_code": "005930", "stock_name": "Samsung Elec", "eval_amount": 4500000} # 45%
        ]
    }
    
    target_mp = {
        "stocks": 30.0, # Target lower than actual (Overweight) -> SELL needed
        "bonds": 50.0,  # Target higher than actual (Underweight) -> BUY needed
        "alternatives": 15.0, # Underweight -> BUY needed
        "cash": 5.0
    }
    
    target_sub_mp = {
        "stocks": {
            "etf_details": [{"ticker": "005930", "name": "Samsung Elec", "weight": 1.0}]
        },
         "bonds": {
            "etf_details": [{"ticker": "148070", "name": "KOSEF 10Y Treasury", "weight": 1.0}]
        }
    }
    
    drift_info = {
        "mp_drifts": {
            "stocks": -15.0, # Overweight
            "bonds": 10.0,   # Underweight
            "alternatives": 5.0
        },
        "sub_mp_drifts": {
            "stocks": [{"ticker": "005930", "name": "Samsung Elec", "drift": -15.0}],
            "bonds": [{"ticker": "148070", "name": "KOSEF 10Y Treasury", "drift": 10.0}]
        }
    }
    
    # 2. Test Sell Strategy
    logger.info("--- Testing Sell Strategy ---")
    sell_orders = await plan_sell_strategy(current_state, target_mp, target_sub_mp, drift_info)
    print(f"Generated Sell Orders: {sell_orders}")
    
    if sell_orders:
        assert isinstance(sell_orders, list)
        assert "ticker" in sell_orders[0]
        assert sell_orders[0]["ticker"] == "005930"
        logger.info("Sell Strategy Check Passed!")
    else:
        logger.warning("Sell Strategy returned empty list. Check LLM or logic.")

    # 3. Test Buy Strategy
    logger.info("--- Testing Buy Strategy ---")
    buy_orders = await plan_buy_strategy(current_state, target_mp, target_sub_mp, drift_info)
    print(f"Generated Buy Orders: {buy_orders}")
    
    if buy_orders:
        assert isinstance(buy_orders, list)
        assert "ticker" in buy_orders[0]
        # Expecting bond purchase
        logger.info("Buy Strategy Check Passed!")
    else:
        logger.warning("Buy Strategy returned empty list. Check LLM or logic.")

if __name__ == "__main__":
    asyncio.run(verify_llm_planning())
