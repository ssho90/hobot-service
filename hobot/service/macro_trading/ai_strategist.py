"""
AI 전략가 모듈
Gemini 2.5 Pro를 사용하여 거시경제 데이터를 분석하고 자산 배분 전략을 결정합니다.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
from pydantic import BaseModel, Field, field_validator

from service.llm import llm_gemini_pro
from service.database.db import get_db_connection
from service.llm_monitoring import track_llm_call

logger = logging.getLogger(__name__)


class TargetAllocation(BaseModel):
    """목표 자산 배분 모델"""
    Stocks: float = Field(..., ge=0, le=100, description="주식 비중 (%)")
    Bonds: float = Field(..., ge=0, le=100, description="채권 비중 (%)")
    Alternatives: float = Field(..., ge=0, le=100, description="대체투자 비중 (%)")
    Cash: float = Field(..., ge=0, le=100, description="현금 비중 (%)")
    
    @field_validator('*')
    @classmethod
    def validate_total(cls, v, info):
        """총합이 100%인지 검증"""
        if info.data:
            total = sum(info.data.values())
            if abs(total - 100.0) > 0.01:
                raise ValueError(f"총 비중이 100%가 아닙니다. (현재: {total}%)")
        return v


class AIStrategyDecision(BaseModel):
    """AI 전략 결정 결과 모델"""
    analysis_summary: str = Field(..., description="AI 분석 요약")
    target_allocation: TargetAllocation = Field(..., description="목표 자산 배분")
    reasoning: str = Field(..., description="판단 근거")


def collect_fred_signals() -> Optional[Dict[str, Any]]:
    """FRED 정량 시그널 수집"""
    try:
        from service.macro_trading.signals.quant_signals import QuantSignalCalculator
        
        calculator = QuantSignalCalculator()
        signals = calculator.calculate_all_signals()
        additional_indicators = calculator.get_additional_indicators()
        
        return {
            "yield_curve_spread_trend": signals.get("yield_curve_spread_trend"),
            "real_interest_rate": signals.get("real_interest_rate"),
            "taylor_rule_signal": signals.get("taylor_rule_signal"),
            "net_liquidity": signals.get("net_liquidity"),
            "high_yield_spread": signals.get("high_yield_spread"),
            "additional_indicators": additional_indicators
        }
    except Exception as e:
        logger.error(f"FRED 시그널 수집 실패: {e}", exc_info=True)
        return None


def collect_economic_news(hours: int = 24) -> Optional[Dict[str, Any]]:
    """경제 뉴스 수집"""
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id,
                    title,
                    title_ko,
                    link,
                    country,
                    country_ko,
                    category,
                    category_ko,
                    description,
                    description_ko,
                    published_at,
                    collected_at,
                    source
                FROM economic_news
                WHERE published_at >= %s
                ORDER BY published_at DESC
                LIMIT 50
            """, (cutoff_time,))
            
            news = cursor.fetchall()
            
            # datetime 객체를 문자열로 변환
            for item in news:
                if item.get('published_at'):
                    item['published_at'] = item['published_at'].strftime('%Y-%m-%d %H:%M:%S')
                if item.get('collected_at'):
                    item['collected_at'] = item['collected_at'].strftime('%Y-%m-%d %H:%M:%S')
            
            return {
                "total_count": len(news),
                "hours": hours,
                "news": news
            }
    except Exception as e:
        logger.error(f"경제 뉴스 수집 실패: {e}", exc_info=True)
        return None


def collect_account_status() -> Optional[Dict[str, Any]]:
    """계좌 현황 수집 (자산군별 손익 포함)"""
    try:
        from service.macro_trading.kis.kis import get_balance_info_api
        
        balance_data = get_balance_info_api()
        
        if balance_data.get('status') != 'success':
            logger.warning(f"계좌 조회 실패: {balance_data.get('message')}")
            return None
        
        # 자산군별 정보 추출
        asset_class_info = balance_data.get('asset_class_info', {})
        
        return {
            "total_eval_amount": balance_data.get('total_eval_amount', 0),
            "cash_balance": balance_data.get('cash_balance', 0),
            "asset_class_info": asset_class_info
        }
    except Exception as e:
        logger.error(f"계좌 현황 수집 실패: {e}", exc_info=True)
        return None


def create_analysis_prompt(fred_signals: Dict, economic_news: Dict, account_status: Dict) -> str:
    """AI 분석용 프롬프트 생성"""
    
    # FRED 시그널 요약
    fred_summary = "=== FRED 정량 시그널 (가장 신뢰도 높음) ===\n"
    if fred_signals:
        yield_curve = fred_signals.get('yield_curve_spread_trend', {})
        if yield_curve:
            fred_summary += f"금리 곡선 국면: {yield_curve.get('regime_kr', 'N/A')}\n"
            fred_summary += f"스프레드: {yield_curve.get('spread', 'N/A'):.2f}%\n"
            fred_summary += f"금리 대세: {yield_curve.get('yield_regime_kr', 'N/A')}\n"
        
        real_rate = fred_signals.get('real_interest_rate')
        if real_rate is not None:
            fred_summary += f"실질 금리: {real_rate:.2f}%\n"
        
        taylor = fred_signals.get('taylor_rule_signal')
        if taylor is not None:
            fred_summary += f"테일러 준칙 신호: {taylor:.2f}%\n"
        
        net_liq = fred_signals.get('net_liquidity', {})
        if net_liq:
            trend = net_liq.get('ma_trend')
            if trend == 1:
                fred_summary += "연준 순유동성: 상승 추세 (유동성 공급 확대)\n"
            elif trend == -1:
                fred_summary += "연준 순유동성: 하락 추세 (유동성 공급 축소)\n"
        
        hy_spread = fred_signals.get('high_yield_spread', {})
        if hy_spread:
            signal_name = hy_spread.get('signal_name', 'N/A')
            spread_val = hy_spread.get('spread', 'N/A')
            fred_summary += f"하이일드 스프레드: {signal_name} ({spread_val}%)\n"
    
    # 경제 뉴스 요약
    news_summary = "\n=== 경제 뉴스 (비중 낮게 참고) ===\n"
    if economic_news and economic_news.get('news'):
        news_list = economic_news['news'][:10]  # 최근 10개만
        for news in news_list:
            news_summary += f"- [{news.get('country', 'N/A')}] {news.get('title', 'N/A')}\n"
            if news.get('description'):
                desc = news.get('description', '')[:100]  # 처음 100자만
                news_summary += f"  {desc}...\n"
    else:
        news_summary += "최근 뉴스 없음\n"
    
    # 계좌 현황 요약
    account_summary = "\n=== 계좌 현황 (비중 낮게 참고) ===\n"
    if account_status:
        total = account_status.get('total_eval_amount', 0)
        account_summary += f"총 평가금액: {total:,} 원\n"
        
        asset_info = account_status.get('asset_class_info', {})
        for asset_class, info in asset_info.items():
            if isinstance(info, dict):
                total_eval = info.get('total_eval_amount', 0)
                pnl_rate = info.get('total_pnl_rate', 0)
                account_summary += f"{asset_class}: {total_eval:,} 원 (수익률: {pnl_rate:.2f}%)\n"
    else:
        account_summary += "계좌 정보 없음\n"
    
    prompt = f"""당신은 거시경제 전문가입니다. 다음 데이터를 분석하여 자산 배분 전략을 결정하세요.

{fred_summary}

{news_summary}

{account_summary}

## 분석 지침:
1. **FRED 지표를 가장 신뢰도 높게** 사용하세요. FRED 지표는 객관적이고 정량적입니다.
2. **경제 뉴스와 계좌 현황은 보조적으로만** 참고하세요. 비중을 낮게 두세요.
3. 자산군별 비중을 결정하세요:
   - Stocks (주식): 0-100%
   - Bonds (채권): 0-100%
   - Alternatives (대체투자: 금, 달러 등): 0-100%
   - Cash (현금): 0-100%
4. 총 비중은 반드시 100%가 되어야 합니다.

## 출력 형식 (JSON):
{{
    "analysis_summary": "분석 요약 (한국어, 200-300자)",
    "target_allocation": {{
        "Stocks": 40.0,
        "Bonds": 30.0,
        "Alternatives": 20.0,
        "Cash": 10.0
    }},
    "reasoning": "판단 근거 (한국어, 300-500자)"
}}

JSON 형식으로만 응답하세요. 다른 설명은 포함하지 마세요.
"""
    
    return prompt


def analyze_and_decide() -> Optional[AIStrategyDecision]:
    """AI 분석 및 전략 결정"""
    try:
        logger.info("AI 전략 분석 시작")
        
        # 데이터 수집
        logger.info("FRED 시그널 수집 중...")
        fred_signals = collect_fred_signals()
        
        logger.info("경제 뉴스 수집 중...")
        economic_news = collect_economic_news(hours=24)
        
        logger.info("계좌 현황 수집 중...")
        account_status = collect_account_status()
        
        # 프롬프트 생성
        prompt = create_analysis_prompt(fred_signals, economic_news, account_status)
        
        # LLM 호출
        logger.info("Gemini 2.5 Pro 분석 중...")
        llm = llm_gemini_pro()
        
        # LLM 호출 추적
        with track_llm_call(
            model_name="gemini-2.5-pro",
            provider="Google",
            service_name="ai_strategist",
            request_prompt=prompt
        ) as tracker:
            # JSON 응답 강제
            response = llm.invoke(prompt)
            tracker.set_response(response)
        
        # 응답 파싱
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # JSON 추출 (마크다운 코드 블록 제거)
        response_text = response_text.strip()
        if response_text.startswith('```'):
            # 코드 블록 제거
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1]) if lines[-1].startswith('```') else '\n'.join(lines[1:])
        
        # JSON 파싱
        try:
            decision_data = json.loads(response_text)
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 재시도
            logger.warning("JSON 파싱 실패, 재시도 중...")
            # 간단한 JSON 추출 시도
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                decision_data = json.loads(json_match.group())
            else:
                raise ValueError("JSON 형식이 올바르지 않습니다.")
        
        # Pydantic 모델로 검증
        decision = AIStrategyDecision(**decision_data)
        
        logger.info(f"AI 분석 완료: {decision.analysis_summary[:50]}...")
        
        return decision
        
    except Exception as e:
        logger.error(f"AI 분석 실패: {e}", exc_info=True)
        return None


def save_strategy_decision(decision: AIStrategyDecision, fred_signals: Dict, economic_news: Dict, account_status: Dict) -> bool:
    """전략 결정 결과를 DB에 저장"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # analysis_summary에 reasoning 포함
            analysis_summary_with_reasoning = decision.analysis_summary
            if decision.reasoning:
                analysis_summary_with_reasoning += f"\n\n판단 근거:\n{decision.reasoning}"
            
            cursor.execute("""
                INSERT INTO ai_strategy_decisions (
                    decision_date,
                    analysis_summary,
                    target_allocation,
                    quant_signals,
                    qual_sentiment,
                    account_pnl
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                analysis_summary_with_reasoning,
                json.dumps(decision.target_allocation.model_dump()),
                json.dumps(fred_signals) if fred_signals else None,
                json.dumps(economic_news) if economic_news else None,
                json.dumps(account_status) if account_status else None
            ))
            
            conn.commit()
            logger.info("전략 결정 결과 저장 완료")
            return True
            
    except Exception as e:
        logger.error(f"전략 결정 저장 실패: {e}", exc_info=True)
        return False


def run_ai_analysis():
    """AI 분석 실행 (스케줄러용)"""
    try:
        logger.info("=" * 60)
        logger.info("AI 전략 분석 시작")
        logger.info("=" * 60)
        
        # 데이터 수집
        fred_signals = collect_fred_signals()
        economic_news = collect_economic_news(hours=24)
        account_status = collect_account_status()
        
        # AI 분석
        decision = analyze_and_decide()
        
        if not decision:
            logger.error("AI 분석 실패")
            return False
        
        # 결과 저장
        success = save_strategy_decision(decision, fred_signals, economic_news, account_status)
        
        if success:
            logger.info("=" * 60)
            logger.info("AI 전략 분석 완료")
            logger.info(f"분석 요약: {decision.analysis_summary}")
            logger.info(f"목표 배분: Stocks={decision.target_allocation.Stocks}%, "
                       f"Bonds={decision.target_allocation.Bonds}%, "
                       f"Alternatives={decision.target_allocation.Alternatives}%, "
                       f"Cash={decision.target_allocation.Cash}%")
            logger.info("=" * 60)
        
        return success
        
    except Exception as e:
        logger.error(f"AI 분석 실행 실패: {e}", exc_info=True)
        return False
