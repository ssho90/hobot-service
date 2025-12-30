import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

def calculate_mp_drift(current_state: Dict[str, Any], target_mp: Dict[str, float]) -> Dict[str, float]:
    """
    MP 자산군별 편차(Drift) 계산
    Drift = Target % - Actual %
    
    Args:
        current_state: get_current_portfolio_state()의 결과
        target_mp: get_target_mp_allocation()의 결과
        
    Returns:
        Dict[str, float]: 자산군별 편차 (단위: % 포인트)
    """
    drifts = {}
    mp_actual = current_state.get('mp_actual', {})
    
    # 자산군 목록 정규화 (대소문자 처리 등)
    # target_mp 키를 기준으로 계산
    for asset_class, target_pct in target_mp.items():
        # mp_actual 키와 매핑 (보통 소문자로 통일되어 있음)
        actual_pct = float(mp_actual.get(asset_class, 0.0))
        target_pct = float(target_pct)
        
        # 편차 계산 (절대값 아님, 방향성 포함)
        # 양수: 매수 필요 (Target > Actual)
        # 음수: 매도 필요 (Target < Actual)
        drift = target_pct - actual_pct
        drifts[asset_class] = round(drift, 2)
        
    return drifts

def calculate_sub_mp_drift(current_state: Dict[str, Any], target_sub_mp: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """
    Sub-MP 종목별 편차 계산
    
    Args:
        current_state: get_current_portfolio_state()의 결과
        target_sub_mp: get_target_sub_mp_allocation()의 결과
        
    Returns:
        Dict[str, Dict[str, float]]: 자산군별 -> 티커별 편차
    """
    # Sub-MP 로직은 calculate_detailed_drift에서 통합 처리함
    return {}

def calculate_detailed_drift(current_state, target_mp, target_sub_mp):
    """
    MP와 Sub-MP를 통합하여 종목별 전체 비중(Global Weight) 기준 편차 계산
    """
    drifts = {
        "mp_drifts": {},
        "sub_mp_drifts": {}
    }
    
    # 1. MP Drift
    drifts["mp_drifts"] = calculate_mp_drift(current_state, target_mp)
    
    # 2. Sub-MP Drift (Global Weight 기준)
    total_eval = float(current_state.get('total_eval_amount', 0))
    current_holdings_flat = current_state.get('holdings', []) # 전체 보유 종목 리스트
    current_map = {h.get('stock_code'): float(h.get('eval_amount', 0)) for h in current_holdings_flat}
    
    sub_drifts = {}
    
    for asset_class, mp_weight in target_mp.items():
        # 해당 자산군의 Sub-MP 정보
        sub_info = target_sub_mp.get(asset_class, {})
        etf_details = sub_info.get('etf_details', [])
        
        if not etf_details:
            continue
            
        for etf in etf_details:
            ticker = etf.get('ticker')
            # 자산군 내 비중 (0.0 ~ 1.0)
            local_weight = float(etf.get('weight', 0))
            
            # 전체 포트폴리오 대비 목표 비중 (Global Target %)
            # MP Weight(%) * Local Weight(0.0~1.0)
            global_target_pct = float(mp_weight) * local_weight
            
            # 현재 실제 비중 (Global Actual %)
            current_amt = current_map.get(ticker, 0)
            global_actual_pct = (current_amt / total_eval * 100) if total_eval > 0 else 0.0
            
            drift = global_target_pct - global_actual_pct
            
            if asset_class not in sub_drifts:
                sub_drifts[asset_class] = []
                
            sub_drifts[asset_class].append({
                "ticker": ticker,
                "name": etf.get('name'),
                "target_pct": round(global_target_pct, 2),
                "actual_pct": round(global_actual_pct, 2),
                "drift": round(drift, 2)
            })
            
    drifts["sub_mp_drifts"] = sub_drifts
    return drifts

def check_threshold_exceeded(drift_info: Dict[str, Any], thresholds: Dict[str, float]) -> Tuple[bool, list]:
    """
    임계값 초과 여부 확인
    
    Args:
        drift_info: calculate_detailed_drift() 결과
        thresholds: {"mp": 3.0, "sub_mp": 5.0} 등
    
    Returns:
        (bool, list): (초과여부, 초과된 항목 리스트)
    """
    is_exceeded = False
    reasons = []
    
    mp_threshold = thresholds.get("mp", 3.0)
    sub_mp_threshold = thresholds.get("sub_mp", 5.0)
    
    # 1. MP Drift Check
    mp_drifts = drift_info.get("mp_drifts", {})
    for asset, drift in mp_drifts.items():
        if abs(drift) >= mp_threshold:
            is_exceeded = True
            reasons.append(f"MP [{asset}] Drift {drift}% exceeds threshold {mp_threshold}%")
            
    # 2. Sub-MP Drift Check
    sub_drifts = drift_info.get("sub_mp_drifts", {})
    for asset, items in sub_drifts.items():
        for item in items:
            drift = item.get("drift", 0.0)
            ticker = item.get("ticker")
            if abs(drift) >= sub_mp_threshold:
                is_exceeded = True
                reasons.append(f"Sub-MP [{asset}/{ticker}] Drift {drift}% exceeds threshold {sub_mp_threshold}%")
                
    return is_exceeded, reasons
