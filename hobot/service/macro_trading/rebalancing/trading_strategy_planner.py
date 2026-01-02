import logging
import json
from typing import List, Dict, Any, Optional
from service.llm import LLMService

logger = logging.getLogger(__name__)

async def plan_trading_strategy(
    user_id: str,
    target_trades: List[Dict[str, Any]],
    current_state: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    확정된 매매 리스트(Target Trades)에 대한 집행 전략 수립 (LLM)
    
    Args:
        user_id: 사용자 ID
        target_trades: portfolio_calculator.calculate_net_trades 결과 (매수/매도 리스트)
        current_state: 현재 시장 상황 및 포트폴리오 상태 (VIX 등 포함 가능)
        
    Returns:
        List[Dict]: 실행 계획 (주문 유형, 호가 전략 등 포함)
    """
    if not target_trades:
        return []

    prompt = build_trading_strategy_prompt(target_trades, current_state)
    
    try:
        llm = LLMService() # Assuming LLMService is available in service.llm
        # Using gemini-2.0-flash-exp as per common usage or gemini-1.5-pro as fallback
        # The prompt asks for JSON output
        response_text = await llm.generate_response(
            prompt=prompt,
            model_name="gemini-2.0-flash-exp", # Using a fast model for strategy planning
            temperature=0.2
        )
        
        execution_plan = parse_llm_response(response_text)
        return execution_plan
        
    except Exception as e:
        logger.error(f"Error in LLM trading strategy planning: {e}", exc_info=True)
        # Fallback: Default to Market Strategy if LLM fails
        return create_fallback_strategy(target_trades)

def build_trading_strategy_prompt(trades: List[Dict[str, Any]], current_state: Dict[str, Any]) -> str:
    trades_json = json.dumps(trades, indent=2, ensure_ascii=False)
    
    # In a real scenario, you might add VIX or market sentiment here to 'current_state'
    
    return f"""
You are an expert AI Portfolio Manager responsible for execution strategy.
Your goal is to determine the best execution strategy (Order Type, Price Strategy) for the following required trades to minimize slippage and impact.

**Market Context:**
- Volatility: Normal (Assumed)
- Liquidity: High for ETFs

**Required Trades (Net Quantity):**
{trades_json}

**Instructions:**
1. For each trade, determine:
   - `order_type`: "MARKET" or "LIMIT"
   - `price_strategy`:
     - If LIMIT: "CURRENT" (Current Price), "BID_1" (1 tick below for Buy), "ASK_1" (1 tick above for Sell), etc.
     - If MARKET: "N/A"
   - `reason`: Brief explanation of your strategy.

2. **Output Format**:
   Return ONLY a valid JSON array. Do not include markdown formatting or explanations outside the JSON.
   
   Example:
   [
     {{
       "ticker": "005930",
       "action": "SELL",
       "quantity": 50,
       "order_type": "MARKET",
       "price_strategy": "N/A",
       "reason": "High liquidity, urgent rebalancing."
     }},
     {{
       "ticker": "123456",
       "action": "BUY",
       "quantity": 100,
       "order_type": "LIMIT",
       "price_strategy": "BID_1",
       "reason": "Low volatility, passive entry to save cost."
     }}
   ]
"""

def parse_llm_response(response_text: str) -> List[Dict[str, Any]]:
    try:
        # Clean up code blocks if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
            
        return json.loads(response_text.strip())
    except Exception as e:
        logger.error(f"Failed to parse LLM response: {response_text} | Error: {e}")
        raise

def create_fallback_strategy(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """LLM 실패 시 기본 전략 (전량 시장가)"""
    fallback = []
    for trade in trades:
        fallback_trade = trade.copy()
        fallback_trade["order_type"] = "MARKET"
        fallback_trade["price_strategy"] = "N/A"
        fallback_trade["reason"] = "Fallback Strategy (LLM Failed)"
        fallback.append(fallback_trade)
    return fallback
