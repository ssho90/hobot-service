import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

def validate_strategy(
    current_state: Dict[str, Any],
    target_mp: Dict[str, float],
    execution_plan: List[Dict[str, Any]],
    current_prices: Dict[str, float]
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    LLM이 수립한 전략 유효성 검증
    
    Args:
        current_state: 현재 자산 상태
        target_mp: 목표 MP 비중
        execution_plan: LLM의 집행 전략 리스트
        current_prices: 종목별 현재가
        
    Returns:
        (is_valid, failure_reasons, validation_details)
    """
    reasons = []
    
    # 1. Cash Flow Simulation
    current_cash = float(current_state.get('cash_balance', 0))
    est_sell_amount = 0.0
    est_buy_amount = 0.0
    
    for plan in execution_plan:
        ticker = plan.get('ticker')
        qty = int(plan.get('quantity', 0))
        action = plan.get('action') 
        price = current_prices.get(ticker, 0)
        
        amount = qty * price
        
        if action == 'SELL':
            est_sell_amount += amount
        elif action == 'BUY':
            est_buy_amount += amount
            
    # 매도 대금의 99%만 현금으로 인정 (가상 슬리피지/수수료)
    available_cash_after_sell = current_cash + (est_sell_amount * 0.99)
    # 매수 대금은 101% 필요하다고 가정 (수수료)
    required_cash_for_buy = est_buy_amount * 1.01
    
    if available_cash_after_sell < required_cash_for_buy:
        shortfall = required_cash_for_buy - available_cash_after_sell
        reasons.append(f"Insufficient Cash: Shortfall of {shortfall:,.0f} KRW")
    
    # 2. Anomaly Detection (Single Trade > 50% of Total Equity)
    total_equity = float(current_state.get('total_eval_amount', 1)) 
    for plan in execution_plan:
        ticker = plan.get('ticker')
        qty = int(plan.get('quantity', 0))
        price = current_prices.get(ticker, 0)
        amount = qty * price
        
        if amount > (total_equity * 0.5):
            reasons.append(f"Anomaly Detected: Trade for {ticker} ({amount:,.0f} KRW) exceeds 50% of Total Equity")

    # 3. Post-Trade Drift Check (Simplified)
    # 실제 매매 후 MP 비중이 타겟과 유사해지는지 체크
    # 여기서는 간단히 방향성만 체크하거나, 시뮬레이션된 비중과 타겟 차이 계산
    # (Portfolio Calculator가 정확하다면 맞겠지만, LLM이 수량을 변경했는지 체크 필요)
    
    # TODO: Detailed Drift Simulation if needed. Assuming Python Calculator provided correct Net Quantities.
    
    execution_summary = {
        "est_sell_amount": est_sell_amount,
        "est_buy_amount": est_buy_amount,
        "expected_cash_balance": available_cash_after_sell - required_cash_for_buy
    }
    
    is_valid = len(reasons) == 0
    return is_valid, reasons, execution_summary
