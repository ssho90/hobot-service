import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

def validate_buy_strategy(
    buy_orders: List[Dict[str, Any]],
    current_cash: float,
    current_state: Dict[str, Any],
    target_mp: Dict[str, float],
    current_prices: Dict[str, float]
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    매수 전략 유효성 검증 (Step 6)
    
    Args:
        buy_orders: 생성된 매수 주문 리스트
        current_cash: 현재 가용 현금 (매도 후 확정 예수금)
        current_state: 현재 자산 상태 (Holdings 포함)
        target_mp: 목표 MP 비중
        current_prices: 현재가
        
    Returns:
        (is_valid, failure_reasons, validation_details)
    """
    reasons = []
    
    # 1. Cash Flow Verification
    est_buy_amount = 0.0
    
    for order in buy_orders:
        ticker = order.get('ticker')
        qty = int(order.get('quantity', 0))
        price = order.get('limit_price', 0) 
        
        # If limit price is not set (market), use current price with buffer? 
        # But our builder sets limit price.
        if price == 0:
            price = current_prices.get(ticker, 0)
        
        est_buy_amount += (qty * price)
            
    # 매수 대금은 101% 필요하다고 가정 (수수료)
    required_cash_for_buy = est_buy_amount * 1.01
    
    # Check if we have enough cash
    if current_cash < required_cash_for_buy:
        shortfall = required_cash_for_buy - current_cash
        reasons.append(f"Insufficient Cash: Required {required_cash_for_buy:,.0f} > Available {current_cash:,.0f} (Shortfall: {shortfall:,.0f} KRW)")
    
    # 2. Ratio Consistency Verification (Simulation)
    # TODO: Implement full drift simulation if needed. 
    # For now, we trust the Netting logic but ensure no single order is absurdingly large relative to total equity.
    
    total_equity = float(current_state.get('total_eval_amount', 1)) 
    for order in buy_orders:
        ticker = order.get('ticker')
        qty = int(order.get('quantity', 0))
        price = order.get('limit_price', 0)
        amount = qty * price
        
        if amount > (total_equity * 0.8): # Raised to 80% just in case single ETF portfolio
             reasons.append(f"Warning: Single Trade for {ticker} ({amount:,.0f} KRW) exceeds 80% of Total Equity")

    validation_summary = {
        "est_buy_amount": est_buy_amount,
        "required_cash": required_cash_for_buy,
        "available_cash": current_cash,
        "is_sufficient": current_cash >= required_cash_for_buy
    }
    
    is_valid = len(reasons) == 0
    return is_valid, reasons, validation_summary
