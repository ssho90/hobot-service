import time
import logging
import json
from typing import Dict, List, Optional
from service.macro_trading.kis.kis_api import KISAPI
from service.macro_trading.kis.user_credentials import get_user_kis_credentials
from service.macro_trading.kis.kis import get_balance_info_api

logger = logging.getLogger("rebalancing")

class OrderExecutor:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.credentials = get_user_kis_credentials(user_id)
        if not self.credentials:
             raise ValueError(f"No credentials for user {user_id}")
        
        self.api = KISAPI(
             self.credentials['app_key'],
             self.credentials['app_secret'],
             self.credentials['account_no'],
             is_simulation=self.credentials.get('is_simulation', False)
        )

    def execute_rebalancing_trades(self, trading_plan: Dict) -> Dict:
        """
        Executes the rebalancing strategy:
        1. Execute Sell Orders
        2. Wait for Sell Execution Confirmation
        3. Execute Buy Orders
        """
        logger.info(f"Starting Rebalancing Order Execution for user {self.user_id}")
        
        # 0. Validate Input
        if not trading_plan or trading_plan.get('status') != 'success':
             msg = f"Invalid trading plan input: {trading_plan.get('message', 'Unknown error')}"
             logger.error(msg)
             return {'status': 'error', 'message': msg}

        sell_orders = trading_plan.get('sell_orders', [])
        buy_orders = trading_plan.get('buy_orders', [])
        
        validation_result = trading_plan.get('validation_result', {})
        if not validation_result.get('is_valid', False):
             msg = "Trading Strategy Validation Failed. Aborting Execution."
             logger.error(msg)
             return {'status': 'error', 'message': msg}

        # 1. Execute SELL Phase
        logger.info(f">>> Executing SELL Phase ({len(sell_orders)} orders)")
        sell_results = self._execute_sell_phase(sell_orders)
        
        # Check if all sells are filled
        # If any sell failed or timed out, we should be cautious about buying (cash might be insufficient)
        # But for rebalancing, maybe we can proceed with partial buys? 
        # User requirement: "체결 완료 확인 후 매수 주문 실행" -> Strict check.
        
        if not sell_results['all_filled']:
             msg = "Sell orders not fully filled/confirmed. Aborting Buy Phase to prevent cash issues."
             logger.warning(msg)
             return {
                 'status': 'stopped', 
                 'message': msg,
                 'sell_results': sell_results,
                 'buy_results': []
             }

        # 2. Execute BUY Phase
        logger.info(f">>> Executing BUY Phase ({len(buy_orders)} orders)")
        buy_results = self._execute_buy_phase(buy_orders)
        
        return {
            'status': 'success',
            'message': 'Phase 5 Execution Completed',
            'sell_results': sell_results,
            'buy_results': buy_results
        }
        
    def _execute_sell_phase(self, orders: List[Dict]) -> Dict:
        results = []
        all_filled = True
        
        if not orders:
            return {'all_filled': True, 'orders': results}

        # 1. Snapshot Current Holdings to calculate targets
        # We need this to verify "Did it actually sell?"
        initial_balance = get_balance_info_api(self.user_id)
        if initial_balance['status'] != 'success':
            logger.error(f"Failed to fetch initial balance: {initial_balance.get('message')}")
            return {'all_filled': False, 'orders': [], 'error': 'Balance fetch failed'}
            
        initial_holdings_map = {h['stock_code']: h['quantity'] for h in initial_balance['holdings']}
        
        # 2. Place Orders
        target_holdings = {} # ticker -> expected_qty
        
        for order in orders:
            ticker = order['ticker']
            qty = order['quantity']
            limit_price = order.get('limit_price', 0) # Should be present for limit order
            
            # Calculate target
            current_qty = initial_holdings_map.get(ticker, 0)
            target_qty = max(0, current_qty - qty)
            target_holdings[ticker] = target_qty
            
            logger.info(f"Placing SELL Limit Order: {ticker}, Qty: {qty}, Price: {limit_price}")
            resp = self.api.sell_limit_order(ticker, qty, limit_price)
            
            # Rate Limit Prevention
            time.sleep(0.3)
            
            rt_cd = resp.get('rt_cd')
            if rt_cd != '0':
                logger.error(f"Sell Order Failed for {ticker}: {resp.get('msg1')}")
                results.append({'ticker': ticker, 'status': 'failed', 'response': resp})
                all_filled = False
            else:
                logger.info(f"Sell Order Placed: {ticker}")
                results.append({'ticker': ticker, 'status': 'placed', 'response': resp, 'target_qty': target_qty})

        # 3. Wait for Completion (Polling)
        # Timeout: 60 seconds? 
        # If user price logic is "current_price - 5", it should fill fast.
        timeout_seconds = 60 
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            # Check Balance
            time.sleep(2) # Polling interval
            current_balance = get_balance_info_api(self.user_id)
            if current_balance['status'] != 'success':
                continue
                
            current_holdings_map = {h['stock_code']: h['quantity'] for h in current_balance['holdings']}
            
            pending_tickers = []
            for res in results:
                if res['status'] == 'placed':
                    ticker = res['ticker']
                    target = res.get('target_qty')
                    current = current_holdings_map.get(ticker, 0)
                    
                    if current <= target:
                        res['status'] = 'filled'
                        logger.info(f"See Order Filled: {ticker} (Current: {current} <= Target: {target})")
                    else:
                        pending_tickers.append(ticker)
            
            if not pending_tickers:
                logger.info("All Sell Orders Confirmed Filled.")
                break
                
            logger.info(f"Waiting for fills... Pending: {pending_tickers}")
        
        # Check if any still pending
        for res in results:
            if res['status'] == 'placed': # Still pending after timeout
                 logger.warning(f"Sell Order Timeout: {res['ticker']}")
                 res['status'] = 'timeout'
                 all_filled = False

        return {'all_filled': all_filled, 'orders': results}

    def _execute_buy_phase(self, orders: List[Dict]) -> Dict:
        results = []
        
        if not orders:
            return {'orders': results}

        # Just place orders, no strict wait required by "Phase 5 logic" typically, 
        # but verifying is good. For now, fire and forget (or simple check).
        # User prompt only emphasized "매도 주문 실행하고, 체결 완료 확인 후 매수 주문 실행".
        # It didn't explicitly demand "Wait for Buy Completion".
        
        for order in orders:
            ticker = order['ticker']
            qty = order['quantity']
            limit_price = order.get('limit_price', 0)
            
            logger.info(f"Placing BUY Limit Order: {ticker}, Qty: {qty}, Price: {limit_price}")
            resp = self.api.buy_limit_order(ticker, qty, limit_price)
            
            # Rate Limit Prevention
            time.sleep(0.3)
            
            rt_cd = resp.get('rt_cd')
            if rt_cd != '0':
                logger.error(f"Buy Order Failed for {ticker}: {resp.get('msg1')}")
                results.append({'ticker': ticker, 'status': 'failed', 'response': resp})
            else:
                 logger.info(f"Buy Order Placed: {ticker}")
                 results.append({'ticker': ticker, 'status': 'placed', 'response': resp})

        return {'orders': results}
