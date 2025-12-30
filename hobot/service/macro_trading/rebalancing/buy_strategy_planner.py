import logging
import json
from typing import Dict, Any, List

from langchain_core.output_parsers import JsonOutputParser

from service.llm import llm_gemini_3_pro

logger = logging.getLogger(__name__)

def build_buy_prompt(current_holdings: str, cash_available: float, target_portfolio: str, drift_analysis: str) -> str:
    template = """
    You are an expert Portfolio Manager. Your goal is to rebalance the portfolio by BUYING underweight assets to align with the target allocation, utilizing the available cash.
    
    Current Status:
    - Available Cash: {cash_available} KRW
    - Current Holdings:
    {current_holdings}
    
    Target Allocation:
    {target_portfolio}
    
    Drift Analysis (Difference between Target and Actual):
    {drift_analysis}
    
    Task:
    1. Identify assets that are UNDERWEIGHT (Drift > 0).
    2. Generate specific BUY orders for these assets to increase their weight towards the target.
    3. Ensure the total buy amount does NOT exceed the available cash.
    4. The output must be a valid JSON list of orders.
    5. Each order must include:
       - "ticker": Stock code
       - "name": Stock name
       - "quantity": Integer amount to buy (must be > 0)
       - "reason": A brief explanation for the buy decision based on the drift.
    
    Constraints:
    - Total estimated buy cost (Quantity * Current Price) must be <= Available Cash.
    - Do NOT generate sell orders here. Only BUY.
    - Prioritize assets with larger positive drifts.
    
    Output Format (JSON Only):
    [
        {{
            "ticker": "005930",
            "name": "Samsung Electronics",
            "quantity": 5,
            "reason": "Underweight by 2.0% (Target 20% vs Actual 18%)"
        }}
    ]
    """
    return template.format(
        current_holdings=current_holdings,
        cash_available=cash_available,
        target_portfolio=target_portfolio,
        drift_analysis=drift_analysis
    )

async def plan_buy_strategy(current_state: Dict[str, Any], target_mp: Dict[str, Any], target_sub_mp: Dict[str, Any], drift_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    LLM을 활용하여 매수 전략 수립
    """
    # 1. 저비중 자산 식별 (Drift > 0)
    has_positive_drift = False
    mp_drifts = drift_info.get("mp_drifts", {})
    sub_mp_drifts = drift_info.get("sub_mp_drifts", {})
    
    for drift in mp_drifts.values():
        if drift > 0:
            has_positive_drift = True
            break
            
    if not has_positive_drift:
         for asset_class, items in sub_mp_drifts.items():
            for item in items:
                if item.get("drift", 0) > 0:
                    has_positive_drift = True
                    break
    
    if not has_positive_drift:
        logger.info("No underweight assets found. Skipping buy strategy.")
        return []

    # 2. Get Available Cash
    # current_state should contain cash info. 
    # If sell phase was executed before, this might need to receive updated cash.
    # For now assume current_state has the latest cash info or it's passed separately.
    # In rebalancing_engine, we might need to re-fetch cash or estimate it.
    cash = float(current_state.get('cash_balance', 0))
    
    if cash < 1000: # 최소 주문 가능 금액 등 체크
        logger.info(f"Insufficient cash: {cash}. Skipping buy strategy.")
        return []

    # 3. Prepare Context for LLM
    current_holdings_str = json.dumps(current_state.get('holdings', []), ensure_ascii=False, indent=2)
    
    target_info = {
        "mp_target": target_mp,
        "sub_mp_target": target_sub_mp
    }
    target_portfolio_str = json.dumps(target_info, ensure_ascii=False, indent=2)
    
    drift_analysis_str = json.dumps(drift_info, ensure_ascii=False, indent=2)

    prompt = build_buy_prompt(current_holdings_str, cash, target_portfolio_str, drift_analysis_str)
    
    # 4. Call LLM
    try:
        from service.llm_monitoring import track_llm_call
        
        llm = llm_gemini_3_pro()
        
        with track_llm_call(
            model_name="gemini-3-pro-preview",
            provider="Google",
            service_name="rebalancing_buy_strategy",
            request_prompt=prompt
        ) as tracker:
            response = llm.invoke(prompt)
            tracker.set_response(response)
            
            parser = JsonOutputParser()
            if hasattr(response, 'content'):
                result = parser.parse(response.content)
            else:
                result = parser.parse(str(response))
        
        logger.info(f"LLM Buy Strategy Result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in generated buy strategy: {e}")
        return []
