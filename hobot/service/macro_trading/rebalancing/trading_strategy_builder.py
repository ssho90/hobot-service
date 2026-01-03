import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def build_sell_orders(
    trades: List[Dict[str, Any]], 
    current_prices: Dict[str, float],
    tick_size: int = 5
) -> List[Dict[str, Any]]:
    """
    매도 주문 전략 생성 (Step 3)
    
    Logic:
        - 대상: Net Trades 중 'SELL' 항목
        - 가격: 현재가 - 1 tick (즉시 체결 유도)
    """
    sell_orders = []
    
    for trade in trades:
        if trade['action'] != 'SELL':
            continue
            
        ticker = trade['ticker']
        quantity = trade['quantity']
        current_price = current_prices.get(ticker)
        
        if not current_price:
            logger.warning(f"Skipping SELL order for {ticker}: Price not found")
            continue
            
        # 1 Tick 낮은 가격 (최소 0원 방지)
        limit_price = max(current_price - tick_size, 0)
        
        sell_orders.append({
            "ticker": ticker,
            "action": "SELL",
            "quantity": quantity,
            "limit_price": int(limit_price),
            "price_logic": f"current_price ({current_price}) - {tick_size}"
        })
        
    return sell_orders

def build_buy_orders(
    trades: List[Dict[str, Any]], 
    current_prices: Dict[str, float],
    tick_size: int = 5
) -> List[Dict[str, Any]]:
    """
    매수 주문 전략 생성 (Step 5)
    
    Logic:
        - 대상: Net Trades 중 'BUY' 항목
        - 가격: 현재가 + 1 tick (즉시 체결 유도)
    """
    buy_orders = []
    
    for trade in trades:
        if trade['action'] != 'BUY':
            continue
            
        ticker = trade['ticker']
        quantity = trade['quantity']
        current_price = current_prices.get(ticker)
        
        if not current_price:
            logger.warning(f"Skipping BUY order for {ticker}: Price not found")
            continue
            
        # 1 Tick 높은 가격
        limit_price = current_price + tick_size
        
        buy_orders.append({
            "ticker": ticker,
            "action": "BUY",
            "quantity": quantity,
            "limit_price": int(limit_price),
            "price_logic": f"current_price ({current_price}) + {tick_size}"
        })
        
    return buy_orders
