import logging
import math
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

def calculate_target_quantities(
    total_equity: float,
    target_weights: Dict[str, float],
    current_prices: Dict[str, float]
) -> Dict[str, int]:
    """
    총 자산과 목표 비중을 기반으로 종목별 목표 수량 계산
    
    Args:
        total_equity: 총 자산 평가액 (현금 포함)
        target_weights: 종목별 목표 비중 (0.0 ~ 1.0, 예: {"005930": 0.2})
        current_prices: 종목별 현재가 (예: {"005930": 70000})
        
    Returns:
        Dict[str, int]: 종목별 목표 수량
    """
    target_quantities = {}
    
    for ticker, weight in target_weights.items():
        price = current_prices.get(ticker)
        if not price or price <= 0:
            logger.warning(f"Price not found or invalid for {ticker}. Skipping calculation.")
            continue
            
        target_amount = total_equity * weight
        quantity = math.floor(target_amount / price)
        target_quantities[ticker] = quantity
        
    return target_quantities

def calculate_net_trades(
    current_holdings: Dict[str, int],
    target_quantities: Dict[str, int]
) -> List[Dict[str, Any]]:
    """
    목표 수량과 현재 수량을 비교하여 순매매(Net Trade) 수량 계산
    Delta = Target - Current
    
    Args:
        current_holdings: 현재 보유 수량 (예: {"005930": 100})
        target_quantities: 목표 수량 (예: {"005930": 120})
        
    Returns:
        List[Dict]: 매매 리스트
        [
            {"ticker": "005930", "action": "BUY", "quantity": 20, "diff": 20},
            {"ticker": "123456", "action": "SELL", "quantity": 10, "diff": -10}
        ]
    """
    trades = []
    
    # 모든 관련 티커 합집합
    all_tickers = set(current_holdings.keys()) | set(target_quantities.keys())
    
    for ticker in all_tickers:
        current_qty = current_holdings.get(ticker, 0)
        target_qty = target_quantities.get(ticker, 0)
        
        diff = target_qty - current_qty
        
        if diff == 0:
            continue
            
        action = "BUY" if diff > 0 else "SELL"
        quantity = abs(diff)
        
        trades.append({
            "ticker": ticker,
            "action": action,
            "quantity": quantity,
            "diff": diff
        })
        
    return trades

    trades: List[Dict[str, Any]], 
    current_prices: Dict[str, float], 
    min_amount: float = 0.0 # Changed from 10000.0 to 0.0 to allow small rebalancing
) -> List[Dict[str, Any]]:
    """
    최소 거래 금액 미만의 주문 필터링
    
    Args:
        trades: calculate_net_trades 결과
        current_prices: 현재가 정보
        min_amount: 최소 거래 금액 (KRW)
        
    Returns:
        List[Dict]: 필터링된 매매 리스트
    """
    filtered_trades = []
    
    for trade in trades:
        ticker = trade["ticker"]
        quantity = trade["quantity"]
        price = current_prices.get(ticker, 0)
        
        est_amount = quantity * price
        
        if est_amount >= min_amount:
            trade["est_amount"] = est_amount
            filtered_trades.append(trade)
        else:
            logger.info(f"Trade filtered for {ticker}: Amount {est_amount} < {min_amount}")
            
    return filtered_trades

def verify_strategy_feasibility(
    trades: List[Dict[str, Any]], 
    current_holdings: Dict[str, int]
) -> Tuple[bool, List[str]]:
    """
    1차 검증: 산출된 매매 계획의 논리적 타당성 검증
    
    Args:
        trades: 산출된 매매 리스트
        current_holdings: 현재 보유 수량
        
    Returns:
        (is_valid, error_messages)
    """
    errors = []
    
    for trade in trades:
        ticker = trade["ticker"]
        action = trade["action"]
        quantity = trade["quantity"]
        
        if action == "SELL":
            current_qty = current_holdings.get(ticker, 0)
            if quantity > current_qty:
                errors.append(f"Invalid SELL quantity for {ticker}: Request {quantity} > Holding {current_qty}")
                
    return len(errors) == 0, errors
