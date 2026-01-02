import logging
import json
import asyncio
import time
from typing import Dict, Any, List

from langchain_core.output_parsers import JsonOutputParser

from service.llm import llm_gemini_3_pro
from service.macro_trading.kis.kis import get_current_price_api

logger = logging.getLogger(__name__)

def build_buy_prompt(current_holdings: str, cash_available: float, target_portfolio: str, drift_analysis: str) -> str:
    template = """
    You are an expert Portfolio Manager. Your goal is to rebalance the portfolio by BUYING underweight assets to align with the target allocation, utilizing the available cash.
    
    Current Status:
    - Available Cash: {cash_available} KRW
    - Current Holdings:
    {current_holdings}

    Target Allocation (Includes Current Prices):
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
       - "quantity": Integer amount to buy (must be > 0). Calculate based on 'current_price' in Target Allocation and Available Cash.
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

    # 3. Fetch Current Prices for Potential Buy Candidates (Optimized Parallel Version)
    # 후보: Drift > 0 인 종목들 + Target Sub MP에 있는 모든 종목
    # 효율성을 위해 target_sub_mp에 있는 종목들의 현재가를 병렬로 조회
    
    current_prices = {}
    tickers_to_fetch = set()
    
    # 1. Collect all tickers and check holdings first
    for asset_class, data in target_sub_mp.items():
        # Handle structure: could be list of items OR dict with 'etf_details' list
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and 'etf_details' in data:
            items = data['etf_details']
        else:
            logger.warning(f"Unexpected data structure for {asset_class}: {type(data)}. Skipping.")
            continue
            
        for item in items:
            ticker = None
            if isinstance(item, str):
                ticker = item
            elif isinstance(item, dict):
                ticker = item.get('ticker')
            
            if ticker and ticker != 'CASH':
                # Optimization: Check holdings first (Fast Path)
                # If we already have the price from the recent balance check, use it.
                price_from_holdings = None
                for h in current_state.get('holdings', []):
                    if h.get('stock_code') == ticker:
                        p = h.get('current_price')
                        if p and p > 0:
                            price_from_holdings = p
                        break
                
                if price_from_holdings:
                    current_prices[ticker] = price_from_holdings
                else:
                    # Not found in holdings, add to fetch list
                    tickers_to_fetch.add(ticker)

    # 2. Execute parallel fetch for missing tickers
    if tickers_to_fetch:
        logger.info(f"Fetching prices for {len(tickers_to_fetch)} items in parallel: {tickers_to_fetch}")
        
        # Rate Limiting: Max 1 concurrent request (Sequential) to ensure stability
        # KIS API limit is very strict (EGW00201: Transactions per second exceeded)
        sem = asyncio.Semaphore(1)

        async def fetch_price_async(t):
            async with sem:
                try:
                    # Small delay between requests
                    await asyncio.sleep(0.5)
                    loop = asyncio.get_event_loop()
                    p = await loop.run_in_executor(None, get_current_price_api, user_id, t)
                    return t, p
                except Exception as e:
                    logger.error(f"Error fetching price for {t}: {e}")
                    return t, None

        tasks = [fetch_price_async(t) for t in tickers_to_fetch]
        
        fetch_start = time.time()
        results = await asyncio.gather(*tasks)
        fetch_end = time.time()
        logger.info(f"Parallel fetch for {len(tickers_to_fetch)} items took {fetch_end - fetch_start:.2f}s")
        
        for t, p in results:
            if p:
                current_prices[t] = p
            else:
                logger.warning(f"Failed to fetch price for {t}")

    # 4. Inject Current Prices into Target Sub MP for Prompt
    # Deep copy slightly safer but here we might just modify in place if we don't reuse strictly
    import copy
    target_sub_mp_with_prices = copy.deepcopy(target_sub_mp)
    
    for asset_class, data in target_sub_mp_with_prices.items():
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and 'etf_details' in data:
            items = data['etf_details']
            
        for item in items:
            if isinstance(item, dict):
                t = item.get('ticker')
                if t and t in current_prices:
                    item['current_price'] = current_prices[t]

    # Validation: Ensure all target assets (except CASH) have a current price
    missing_prices = []
    for asset_class, data in target_sub_mp_with_prices.items():
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and 'etf_details' in data:
            items = data['etf_details']
            
        for item in items:
            ticker = None
            if isinstance(item, dict):
                ticker = item.get('ticker')
            elif isinstance(item, str):
                ticker = item
            
            if ticker and ticker != 'CASH':
                has_price = False
                if isinstance(item, dict) and 'current_price' in item:
                    has_price = True
                
                if not has_price:
                    missing_prices.append(ticker)
    
    if missing_prices:
        raise ValueError(f"CRITICAL: Missing current prices for {missing_prices}. Cannot proceed with buy strategy.")

    # 5. Prepare Context for LLM
    current_holdings_str = json.dumps(current_state.get('holdings', []), ensure_ascii=False, indent=2)
    
    target_info = {
        "mp_target": target_mp,
        "sub_mp_target": target_sub_mp_with_prices
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
