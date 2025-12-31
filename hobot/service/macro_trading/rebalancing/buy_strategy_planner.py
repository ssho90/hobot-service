import logging
import json
from typing import Dict, Any, List

from langchain_core.output_parsers import JsonOutputParser

from service.llm import llm_gemini_3_pro
from service.macro_trading.kis.kis import get_current_price_api

logger = logging.getLogger(__name__)

def build_buy_prompt(current_holdings: str, cash_available: float, target_portfolio: str, drift_analysis: str, current_prices_str: str = '{}') -> str:
    template = """
    You are an expert Portfolio Manager. Your goal is to rebalance the portfolio by BUYING underweight assets to align with the target allocation, utilizing the available cash.
    
    Current Status:
    - Available Cash: {cash_available} KRW
    - Current Holdings:
    {current_holdings}

    Current Prices for Candidates (Reference):
    {current_prices_str}
    
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
        drift_analysis=drift_analysis,
        current_prices_str=current_prices_str
    )

async def plan_buy_strategy(user_id: str, current_state: Dict[str, Any], target_mp: Dict[str, Any], target_sub_mp: Dict[str, Any], drift_info: Dict[str, Any]) -> List[Dict[str, Any]]:
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

    # 3. Fetch Current Prices for Potential Buy Candidates
    # 후보: Drift > 0 인 종목들 + Target Sub MP에 있는 모든 종목 (혹시 보유 안한 종목 매수해야 할 수도 있으므로)
    # 효율성을 위해 target_sub_mp에 있는 종목들의 현재가를 조회
    
    current_prices = {}
    for asset_class, items in target_sub_mp.items():
        if not isinstance(items, list):
            logger.warning(f"Expected list for items in {asset_class}, got {type(items)}: {items}")
            continue
            
        for item in items:
            ticker = None
            if isinstance(item, str):
                ticker = item
            elif isinstance(item, dict):
                ticker = item.get('ticker')
            else:
                logger.warning(f"Unexpected item type in {asset_class}: {type(item)}")
                continue

            if ticker and ticker != 'CASH':
                price = None
                # 1. Check holdings first (optional optimization, but user requested "fetch current price of ALL stocks")
                # To be safe and meet the requirement "fetch current price of ALL stocks", 
                # we SHOULD try to get the most up-to-date price.
                # However, calling API for every stock might be slow.
                # Let's try API first, or fallback to holding price if API fails?
                # Actually, KIS API limit is generous. Let's try to fetch fresh price if possible.
                
                # But wait, if we hold it, we have a price from balance lookup. Is it real-time?
                # Balance lookup is usually near real-time.
                # Let's stick to the logic: If we have it in holdings, use it. If not, fetch it.
                # BUT ensure we populate current_prices for EVERYTHING.
                
                for h in current_state.get('holdings', []):
                    if h.get('stock_code') == ticker:
                        price = h.get('current_price')
                        break
                
                # If price is 0 or None, definitely fetch from API
                if not price:
                   price = get_current_price_api(user_id, ticker)
                
                if price:
                    current_prices[ticker] = price
                    
    current_prices_str = json.dumps(current_prices, ensure_ascii=False, indent=2)

    # 4. Prepare Context for LLM
    current_holdings_str = json.dumps(current_state.get('holdings', []), ensure_ascii=False, indent=2)
    
    target_info = {
        "mp_target": target_mp,
        "sub_mp_target": target_sub_mp
    }
    target_portfolio_str = json.dumps(target_info, ensure_ascii=False, indent=2)
    
    drift_analysis_str = json.dumps(drift_info, ensure_ascii=False, indent=2)

    prompt = build_buy_prompt(current_holdings_str, cash, target_portfolio_str, drift_analysis_str, current_prices_str=current_prices_str)
    
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
            
            # 2. Parse the content
            parser = JsonOutputParser()
            if hasattr(response, 'content'):
                content = response.content
                # Handle case where content is a list (multimodal response)
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and 'text' in part:
                            text_parts.append(part['text'])
                        elif isinstance(part, str):
                            text_parts.append(part)
                    content = "".join(text_parts)
                
                result = parser.parse(content)
            else:
                result = parser.parse(str(response))
        
        logger.info(f"LLM Buy Strategy Result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in generated buy strategy: {e}")
        return []
