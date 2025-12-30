import logging
import json
from typing import Dict, Any, List

from langchain_core.output_parsers import JsonOutputParser

from service.llm import llm_gemini_3_pro

logger = logging.getLogger(__name__)

def build_sell_prompt(current_portfolio: str, target_portfolio: str, drift_analysis: str) -> str:
    template = """
    You are an expert Portfolio Manager. Your goal is to rebalance the portfolio by SELLING overweight assets to align with the target allocation.
    
    Current Portfolio Status:
    {current_portfolio}
    
    Target Allocation:
    {target_portfolio}
    
    Drift Analysis (Difference between Target and Actual):
    {drift_analysis}
    
    Task:
    1. Identify assets that are OVERWEIGHT (Drift < 0).
    2. Generate specific SELL orders for these assets to reduce their weight towards the target.
    3. The output must be a valid JSON list of orders.
    4. Each order must include:
       - "ticker": Stock code
       - "name": Stock name
       - "quantity": Integer amount to sell (must be > 0)
       - "reason": A brief explanation for the sell decision based on the drift.
    
    Constraints:
    - Do NOT sell more than currently held.
    - Do NOT generate buy orders here. Only SELL.
    - If no rebalancing is needed (drifts are within thresholds), return an empty list [].
    
    Output Format (JSON Only):
    [
        {{
            "ticker": "005930",
            "name": "Samsung Electronics",
            "quantity": 10,
            "reason": "Overweight by 3.5% (Target 20% vs Actual 23.5%)"
        }}
    ]
    """
    return template.format(
        current_portfolio=current_portfolio,
        target_portfolio=target_portfolio,
        drift_analysis=drift_analysis
    )

async def plan_sell_strategy(current_state: Dict[str, Any], target_mp: Dict[str, Any], target_sub_mp: Dict[str, Any], drift_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    LLM을 활용하여 매도 전략 수립
    """
    # 1. 과비중 자산 식별 (Drift < 0)
    overweight_assets = []
    
    # MP Level check
    mp_drifts = drift_info.get("mp_drifts", {})
    sub_mp_drifts = drift_info.get("sub_mp_drifts", {})
    
    # Check if there's any negative drift needing action
    has_negative_drift = False
    for drift in mp_drifts.values():
        if drift < 0:
            has_negative_drift = True
            break
            
    if not has_negative_drift:
         for asset_class, items in sub_mp_drifts.items():
            for item in items:
                if item.get("drift", 0) < 0:
                    has_negative_drift = True
                    break
    
    if not has_negative_drift:
        logger.info("No overweight assets found. Skipping sell strategy.")
        return []

    # 2. Prepare Context for LLM
    current_portfolio_str = json.dumps(current_state.get('holdings', []), ensure_ascii=False, indent=2)
    
    target_info = {
        "mp_target": target_mp,
        "sub_mp_target": target_sub_mp
    }
    target_portfolio_str = json.dumps(target_info, ensure_ascii=False, indent=2)
    
    drift_analysis_str = json.dumps(drift_info, ensure_ascii=False, indent=2)

    prompt = build_sell_prompt(current_portfolio_str, target_portfolio_str, drift_analysis_str)
    
    # 3. Call LLM
    try:
        llm = llm_gemini_3_pro()
        chain = llm | JsonOutputParser()
        
        result = chain.invoke(prompt)
        
        logger.info(f"LLM Sell Strategy Result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in generated sell strategy: {e}")
        return []
