"""
AI 전략가 모듈
Gemini 3 Pro Preview를 사용하여 거시경제 데이터를 분석하고 자산 배분 전략을 결정합니다.
LangGraph를 사용하여 워크플로우를 관리합니다.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List, TypedDict
from pydantic import BaseModel, Field, model_validator

from langgraph.graph import StateGraph, START, END

from service.llm import llm_gemini_pro
from service.database.db import get_db_connection
from service.llm_monitoring import track_llm_call

logger = logging.getLogger(__name__)


# ============================================================================
# 모델 포트폴리오 (MP) 시나리오 정의
# ============================================================================

MODEL_PORTFOLIOS = {
    "MP-1": {
        "id": "MP-1",
        "name": "Risk On (골디락스)",
        "description": "경기 지표(GDP, PMI)가 확장 국면이며 기업 이익이 증가하지만, 물가는 안정적인 최상의 시나리오. 실업률은 완전고용 수준을 유지하며, 시장에 위험자산 선호 심리(Risk-on)가 지배적임.",
        "strategy": "주식 풀매수",
        "allocation": {
            "Stocks": 80.0,
            "Bonds": 10.0,
            "Alternatives": 5.0,
            "Cash": 5.0
        }
    },
    "MP-2": {
        "id": "MP-2",
        "name": "Reflation (물가상승)",
        "description": "경기는 여전히 확장세이나, 수요 과열 또는 공급 충격으로 인해 물가(CPI/PCE)가 목표치를 상회하며 급등하는 구간. 금리 인상 압력이 존재하며, 화폐 가치 하락 방어를 위해 실물 자산이 선호됨.",
        "strategy": "원자재/금 헤지 (인플레이션 방어)",
        "allocation": {
            "Stocks": 50.0,
            "Bonds": 10.0,
            "Alternatives": 30.0,
            "Cash": 10.0
        }
    },
    "MP-3": {
        "id": "MP-3",
        "name": "Neutral (중립)",
        "description": "경제 지표가 호재와 악재가 섞여 뚜렷한 방향성(추세)이 보이지 않는 구간. 고용은 견조하나 소비가 둔화되는 등 지표 간 괴리가 발생하며, 시장은 연준의 정책 결정이나 새로운 모멘텀을 기다리며 박스권 등락을 반복함.",
        "strategy": "자산배분 정석 (균형 투자)",
        "allocation": {
            "Stocks": 40.0,
            "Bonds": 40.0,
            "Alternatives": 10.0,
            "Cash": 10.0
        }
    },
    "MP-4": {
        "id": "MP-4",
        "name": "Defensive (경기둔화)",
        "description": "제조업 PMI 등 선행 지표가 위축되고 실업률이 바닥을 찍고 완만하게 상승하기 시작하는 경기 하강 초기 국면. 물가 상승 압력이 둔화되면서 중앙은행의 '금리 인하' 기대감이 형성되어 채권 가격 상승(수익률 하락)이 유력함.",
        "strategy": "채권 매집 (자본 차익 기대)",
        "allocation": {
            "Stocks": 20.0,
            "Bonds": 50.0,
            "Alternatives": 20.0,
            "Cash": 10.0
        }
    },
    "MP-5": {
        "id": "MP-5",
        "name": "Recession (침체/공포)",
        "description": "실업률이 급격히 치솟으며(샴의 법칙 발동 등), 하이일드 스프레드가 급등하는 등 신용 위험이 현실화된 위기 국면. 주식 등 위험자산 투매가 나오며 안전자산(달러, 초단기 국채)으로의 자금 쏠림(Flight to Quality)이 발생함.",
        "strategy": "안전자산 올인 (자산 방어 최우선)",
        "allocation": {
            "Stocks": 10.0,
            "Bonds": 60.0,
            "Alternatives": 10.0,
            "Cash": 20.0
        }
    }
}


def get_model_portfolio_allocation(mp_id: str) -> Optional[Dict[str, float]]:
    """MP ID에 해당하는 자산 배분 비율 반환"""
    mp = MODEL_PORTFOLIOS.get(mp_id)
    if mp:
        return mp["allocation"].copy()
    return None


# ============================================================================
# Sub-MP (자산군별 세부 모델) 정의
# ============================================================================

SUB_MODEL_PORTFOLIOS = {
    # 주식 (Equity) Sub-Models
    "Eq-A": {
        "id": "Eq-A",
        "name": "Aggressive (성장 공격형)",
        "description": "금리 인하기, 유동성 풍부, Risk-On. 기술주가 주도하는 상황.",
        "asset_class": "Stocks",
        "allocation": {
            "나스닥": 0.5,
            "S&P500": 0.3,
            "배당주": 0.2
        },
        "etf_details": [
            {"category": "나스닥", "ticker": "411420", "name": "KODEX 미국나스닥AI테크액티브", "weight": 0.5},
            {"category": "S&P500", "ticker": "360750", "name": "TIGER 미국S&P500", "weight": 0.3},
            {"category": "배당주", "ticker": "458730", "name": "TIGER 미국배당다우존스", "weight": 0.2}
        ]
    },
    "Eq-N": {
        "id": "Eq-N",
        "name": "Neutral (시장 중립형)",
        "description": "방향성 불확실, 일반적인 상승장.",
        "asset_class": "Stocks",
        "allocation": {
            "S&P500": 0.5,
            "나스닥": 0.3,
            "배당주": 0.2
        },
        "etf_details": [
            {"category": "S&P500", "ticker": "360750", "name": "TIGER 미국S&P500", "weight": 0.5},
            {"category": "나스닥", "ticker": "411420", "name": "KODEX 미국나스닥AI테크액티브", "weight": 0.3},
            {"category": "배당주", "ticker": "458730", "name": "TIGER 미국배당다우존스", "weight": 0.2}
        ]
    },
    "Eq-D": {
        "id": "Eq-D",
        "name": "Defensive (방어형)",
        "description": "고금리 장기화, 경기 침체 우려, 변동성 확대. 현금흐름이 좋은 배당주 선호.",
        "asset_class": "Stocks",
        "allocation": {
            "배당주": 0.5,
            "S&P500": 0.3,
            "나스닥": 0.2
        },
        "etf_details": [
            {"category": "배당주", "ticker": "458730", "name": "TIGER 미국배당다우존스", "weight": 0.5},
            {"category": "S&P500", "ticker": "360750", "name": "TIGER 미국S&P500", "weight": 0.3},
            {"category": "나스닥", "ticker": "411420", "name": "KODEX 미국나스닥AI테크액티브", "weight": 0.2}
        ]
    },
    # 채권 (Bond) Sub-Models
    "Bnd-L": {
        "id": "Bnd-L",
        "name": "Long Duration (장기채 베팅)",
        "description": "금리 인하가 확실시될 때. 금리가 1% 떨어지면 장기채는 15% 폭등.",
        "asset_class": "Bonds",
        "allocation": {
            "미국 장기채": 0.8,
            "한국 단기채": 0.2
        },
        "etf_details": [
            {"category": "미국 장기채", "ticker": "453850", "name": "ACE 미국30년국채액티브(H)", "weight": 0.8},
            {"category": "한국 단기채", "ticker": "357870", "name": "TIGER CD금리투자KIS", "weight": 0.2}
        ]
    },
    "Bnd-N": {
        "id": "Bnd-N",
        "name": "Balanced (균형)",
        "description": "금리 동결 또는 완만한 인하.",
        "asset_class": "Bonds",
        "allocation": {
            "미국 장기채": 0.5,
            "한국 단기채": 0.5
        },
        "etf_details": [
            {"category": "미국 장기채", "ticker": "453850", "name": "ACE 미국30년국채액티브(H)", "weight": 0.5},
            {"category": "한국 단기채", "ticker": "357870", "name": "TIGER CD금리투자KIS", "weight": 0.5}
        ]
    },
    "Bnd-S": {
        "id": "Bnd-S",
        "name": "Short Duration (단기채 방어)",
        "description": "금리 인상기, 인플레이션 쇼크. 장기채 가격 폭락 방어.",
        "asset_class": "Bonds",
        "allocation": {
            "한국 단기채": 0.8,
            "미국 장기채": 0.2
        },
        "etf_details": [
            {"category": "한국 단기채", "ticker": "357870", "name": "TIGER CD금리투자KIS", "weight": 0.8},
            {"category": "미국 장기채", "ticker": "453850", "name": "ACE 미국30년국채액티브(H)", "weight": 0.2}
        ]
    },
    # 대체자산 (Alternatives) Sub-Models
    "Alt-I": {
        "id": "Alt-I",
        "name": "Inflation Fighter (인플레 방어)",
        "description": "스태그플레이션, 물가 급등, 달러 약세.",
        "asset_class": "Alternatives",
        "allocation": {
            "금": 0.8,
            "달러": 0.2
        },
        "etf_details": [
            {"category": "금", "ticker": "132030", "name": "KODEX 골드선물(H)", "weight": 0.8},
            {"category": "달러", "ticker": "261240", "name": "KODEX 미국달러선물", "weight": 0.2}
        ]
    },
    "Alt-C": {
        "id": "Alt-C",
        "name": "Crisis Hedge (위기 방어)",
        "description": "금융 위기, 시스템 리스크, 주식 폭락(달러 강세).",
        "asset_class": "Alternatives",
        "allocation": {
            "달러": 0.7,
            "금": 0.3
        },
        "etf_details": [
            {"category": "달러", "ticker": "261240", "name": "KODEX 미국달러선물", "weight": 0.7},
            {"category": "금", "ticker": "132030", "name": "KODEX 골드선물(H)", "weight": 0.3}
        ]
    }
}


def get_sub_model_portfolio_allocation(sub_mp_id: str) -> Optional[Dict[str, float]]:
    """Sub-MP ID에 해당하는 자산군 내 배분 비율 반환"""
    sub_mp = SUB_MODEL_PORTFOLIOS.get(sub_mp_id)
    if sub_mp:
        return sub_mp["allocation"].copy()
    return None


def get_sub_models_by_asset_class(asset_class: str) -> Dict[str, Dict]:
    """자산군별 Sub-MP 목록 반환"""
    result = {}
    for sub_mp_id, sub_mp in SUB_MODEL_PORTFOLIOS.items():
        if sub_mp.get("asset_class") == asset_class:
            result[sub_mp_id] = sub_mp
    return result


def get_sub_mp_etf_details(sub_mp_id: str) -> Optional[List[Dict]]:
    """Sub-MP ID에 해당하는 ETF 세부 정보 반환"""
    sub_mp = SUB_MODEL_PORTFOLIOS.get(sub_mp_id)
    if sub_mp:
        return sub_mp.get("etf_details", []).copy()
    return None


class TargetAllocation(BaseModel):
    """목표 자산 배분 모델"""
    Stocks: float = Field(..., ge=0, le=100, description="주식 비중 (%)")
    Bonds: float = Field(..., ge=0, le=100, description="채권 비중 (%)")
    Alternatives: float = Field(..., ge=0, le=100, description="대체투자 비중 (%)")
    Cash: float = Field(..., ge=0, le=100, description="현금 비중 (%)")
    
    @model_validator(mode='after')
    def validate_total(self):
        """총합이 100%인지 검증"""
        total = self.Stocks + self.Bonds + self.Alternatives + self.Cash
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"총 비중이 100%가 아닙니다. (현재: {total}%)")
        return self


class RecommendedStock(BaseModel):
    """추천 종목/섹터 모델"""
    category: str = Field(..., description="카테고리/섹터 (예: '미국 대형주', '테크 섹터', '금', '미국 장기채권' 등)")
    ticker: Optional[str] = Field(default=None, description="특정 ETF 티커 (선택적, 특정 종목을 추천하는 경우에만)")
    name: Optional[str] = Field(default=None, description="ETF 이름 또는 설명 (선택적)")
    weight: float = Field(..., ge=0, le=1, description="자산군 내 비중 (0-1)")

class RecommendedStocks(BaseModel):
    """자산군별 추천 종목 모델"""
    Stocks: Optional[List[RecommendedStock]] = Field(default=None, description="주식 추천 종목")
    Bonds: Optional[List[RecommendedStock]] = Field(default=None, description="채권 추천 종목")
    Alternatives: Optional[List[RecommendedStock]] = Field(default=None, description="대체투자 추천 종목")
    Cash: Optional[List[RecommendedStock]] = Field(default=None, description="현금 추천 종목")

class SubMPDecision(BaseModel):
    """Sub-MP 결정 모델"""
    stocks_sub_mp: Optional[str] = Field(default=None, description="주식 Sub-MP ID (Eq-A, Eq-N, Eq-D)")
    bonds_sub_mp: Optional[str] = Field(default=None, description="채권 Sub-MP ID (Bnd-L, Bnd-N, Bnd-S)")
    alternatives_sub_mp: Optional[str] = Field(default=None, description="대체자산 Sub-MP ID (Alt-I, Alt-C)")
    reasoning: str = Field(..., description="Sub-MP 선택 근거")


class AIStrategyDecision(BaseModel):
    """AI 전략 결정 결과 모델"""
    analysis_summary: str = Field(..., description="AI 분석 요약")
    mp_id: str = Field(..., description="선택된 모델 포트폴리오 ID (MP-1 ~ MP-5)")
    reasoning: str = Field(..., description="판단 근거")
    sub_mp: Optional[SubMPDecision] = Field(default=None, description="자산군별 Sub-MP 결정")
    recommended_stocks: Optional[RecommendedStocks] = Field(default=None, description="자산군별 추천 종목")
    
    def get_target_allocation(self) -> TargetAllocation:
        """MP ID에 해당하는 자산 배분 비율 반환"""
        allocation = get_model_portfolio_allocation(self.mp_id)
        if not allocation:
            raise ValueError(f"유효하지 않은 MP ID: {self.mp_id}")
        return TargetAllocation(**allocation)


def collect_fred_signals() -> Optional[Dict[str, Any]]:
    """FRED 정량 시그널 수집"""
    try:
        from service.macro_trading.signals.quant_signals import QuantSignalCalculator
        from service.macro_trading.collectors.fred_collector import get_fred_collector
        
        calculator = QuantSignalCalculator()
        signals = calculator.calculate_all_signals()
        additional_indicators = calculator.get_additional_indicators()
        
        # 추가 지표: PCEPI, CPI, 실업률, 비농업 고용의 지난 10개 데이터
        fred_collector = get_fred_collector()
        inflation_employment_data = {}
        
        # PCEPI (Personal Consumption Expenditures Price Index)
        try:
            pcepi_data = fred_collector.get_latest_data("PCEPI", days=365)
            if len(pcepi_data) > 0:
                # 최근 10개 데이터 (날짜와 값)
                latest_10 = pcepi_data.tail(10)
                inflation_employment_data["pcepi"] = [
                    {"date": str(date), "value": float(value)}
                    for date, value in zip(latest_10.index, latest_10.values)
                ]
        except Exception as e:
            logger.warning(f"PCEPI 데이터 수집 실패: {e}")
            inflation_employment_data["pcepi"] = []
        
        # CPI (CPIAUCSL)
        try:
            cpi_data = fred_collector.get_latest_data("CPIAUCSL", days=365)
            if len(cpi_data) > 0:
                latest_10 = cpi_data.tail(10)
                inflation_employment_data["cpi"] = [
                    {"date": str(date), "value": float(value)}
                    for date, value in zip(latest_10.index, latest_10.values)
                ]
        except Exception as e:
            logger.warning(f"CPI 데이터 수집 실패: {e}")
            inflation_employment_data["cpi"] = []
        
        # 실업률 (UNRATE)
        try:
            unrate_data = fred_collector.get_latest_data("UNRATE", days=365)
            if len(unrate_data) > 0:
                latest_10 = unrate_data.tail(10)
                inflation_employment_data["unemployment_rate"] = [
                    {"date": str(date), "value": float(value)}
                    for date, value in zip(latest_10.index, latest_10.values)
                ]
        except Exception as e:
            logger.warning(f"실업률 데이터 수집 실패: {e}")
            inflation_employment_data["unemployment_rate"] = []
        
        # 비농업 고용 (PAYEMS)
        try:
            payems_data = fred_collector.get_latest_data("PAYEMS", days=365)
            if len(payems_data) > 0:
                latest_10 = payems_data.tail(10)
                inflation_employment_data["nonfarm_payroll"] = [
                    {"date": str(date), "value": float(value)}
                    for date, value in zip(latest_10.index, latest_10.values)
                ]
        except Exception as e:
            logger.warning(f"비농업 고용 데이터 수집 실패: {e}")
            inflation_employment_data["nonfarm_payroll"] = []
        
        return {
            "yield_curve_spread_trend": signals.get("yield_curve_spread_trend"),
            "real_interest_rate": signals.get("real_interest_rate"),
            "taylor_rule_signal": signals.get("taylor_rule_signal"),
            "net_liquidity": signals.get("net_liquidity"),
            "high_yield_spread": signals.get("high_yield_spread"),
            "additional_indicators": additional_indicators,
            "inflation_employment_data": inflation_employment_data
        }
    except Exception as e:
        logger.error(f"FRED 시그널 수집 실패: {e}", exc_info=True)
        return None


def summarize_news_with_llm(news_list: List[Dict], target_countries: List[str]) -> Optional[str]:
    """
    LLM을 사용하여 뉴스를 정제하고 요약
    gemini-3.0-pro를 사용하여 주요 경제 지표와 흐름을 도출
    """
    try:
        if not news_list:
            return None
        
        # 뉴스 데이터를 텍스트로 변환
        news_text = ""
        for idx, news in enumerate(news_list[:150], 1):  # 최대 100개까지만 처리
            title = news.get('title_ko') or news.get('title', 'N/A')
            description = news.get('description_ko') or news.get('description', '')
            country = news.get('country_ko') or news.get('country', 'N/A')
            published_at = news.get('published_at', 'N/A')
            
            news_text += f"[{idx}] [{country}] {published_at}\n"
            news_text += f"제목: {title}\n"
            if description:
                news_text += f"내용: {description[:500]} ...\n"  # 최대 500자만
            news_text += "\n"
        
        # LLM 프롬프트 생성
        prompt = f"""당신은 거시경제 전문가입니다. 다음은 지난 20일간 {', '.join(target_countries)} 국가의 경제 뉴스입니다.

이 뉴스들을 분석하여:
1. 주요 경제 지표의 변화 (GDP, 인플레이션, 고용, 금리 등)
2. 경제 흐름과 트렌드
3. 시장에 영향을 미칠 수 있는 주요 이벤트

를 도출하고 요약해주세요.

뉴스 목록:
{news_text}

요약 형식:
- 주요 경제 지표 변화: (각 지표별로 간단히 설명)
- 경제 흐름 및 트렌드: (전반적인 경제 동향 설명)
- 주요 이벤트: (시장에 영향을 미칠 수 있는 중요한 사건들)

한국어로 간결하게 요약해주세요 (500-800자 정도).
"""
        
        # gemini-3.0-pro-preview 사용
        logger.info("Gemini 3.0 Pro로 뉴스 요약 중...")
        llm = llm_gemini_pro(model="gemini-3-pro-preview")
        
        with track_llm_call(
            model_name="gemini-3-pro-preview",
            provider="Google",
            service_name="ai_strategist_news_summary",
            request_prompt=prompt
        ) as tracker:
            response = llm.invoke(prompt)
            tracker.set_response(response)
        
        # 응답 텍스트 추출
        response_text = None
        if hasattr(response, 'content'):
            if isinstance(response.content, list) and len(response.content) > 0:
                first_item = response.content[0]
                if isinstance(first_item, dict) and 'text' in first_item:
                    response_text = first_item['text']
                else:
                    response_text = str(first_item)
            elif isinstance(response.content, str):
                response_text = response.content
            else:
                response_text = str(response.content)
        elif hasattr(response, 'text'):
            response_text = response.text
        elif isinstance(response, str):
            response_text = response
        else:
            response_text = str(response)
        
        if isinstance(response_text, list):
            if len(response_text) > 0:
                first_item = response_text[0]
                if isinstance(first_item, dict) and 'text' in first_item:
                    response_text = first_item['text']
                else:
                    response_text = str(first_item)
            else:
                response_text = ""
        
        if not isinstance(response_text, str):
            response_text = str(response_text)
        
        logger.info(f"뉴스 요약 완료: {len(response_text)}자")
        return response_text.strip()
        
    except Exception as e:
        logger.error(f"LLM 뉴스 요약 실패: {e}", exc_info=True)
        return None


def collect_economic_news(days: int = 20, include_summary: bool = True) -> Optional[Dict[str, Any]]:
    """
    경제 뉴스 수집 및 LLM 요약
    지난 N일간 특정 국가의 뉴스를 수집하고, gemini-3.0-pro로 정제하여 요약합니다.
    
    Args:
        days: 수집할 기간 (일 단위, 기본값: 20일)
        include_summary: LLM 요약 포함 여부 (기본값: True)
    """
    try:
        # 지난 N일 기준으로 cutoff_time 설정
        cutoff_time = datetime.now() - timedelta(days=days)
        
        # AI 분석에 사용할 국가 목록
        target_countries = ['Crypto', 'Commodity', 'Euro Area', 'China', 'United States']
        
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
                  AND country IN (%s, %s, %s, %s, %s)
                ORDER BY published_at DESC
            """, (cutoff_time, *target_countries))
            
            news = cursor.fetchall()
            
            # datetime 객체를 문자열로 변환
            for item in news:
                if item.get('published_at'):
                    item['published_at'] = item['published_at'].strftime('%Y-%m-%d %H:%M:%S')
                if item.get('collected_at'):
                    item['collected_at'] = item['collected_at'].strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(f"경제 뉴스 수집 완료: 지난 {days}일간 {len(news)}개의 뉴스 (국가: {', '.join(target_countries)})")
            
            # LLM으로 뉴스 요약 (include_summary가 True인 경우에만)
            news_summary = None
            if include_summary and news:
                news_summary = summarize_news_with_llm(news, target_countries)
            
            return {
                "total_count": len(news),
                "days": days,
                "target_countries": target_countries,
                "news": news,
                "news_summary": news_summary  # LLM 요약 결과 추가
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


def get_overview_recommended_sectors() -> Dict[str, Dict[str, List[Dict]]]:
    """Overview AI 추천 가능한 섹터/그룹 리스트 조회"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT asset_class, sector_group, ticker, name, display_order
                FROM overview_recommended_sectors
                WHERE is_active = TRUE
                ORDER BY asset_class, sector_group, display_order
            """)
            
            rows = cursor.fetchall()
            
            # 자산군 > 섹터 그룹 > ETF 구조로 그룹화
            result = {
                "stocks": {},
                "bonds": {},
                "alternatives": {},
                "cash": {}
            }
            
            for row in rows:
                asset_class = row["asset_class"]
                sector_group = row["sector_group"]
                if asset_class in result:
                    if sector_group not in result[asset_class]:
                        result[asset_class][sector_group] = []
                    result[asset_class][sector_group].append({
                        "ticker": row["ticker"],
                        "name": row["name"]
                    })
            
            return result
    except Exception as e:
        logger.warning(f"Overview 추천 섹터 조회 실패: {e}")
        return {
            "stocks": {},
            "bonds": {},
            "alternatives": {},
            "cash": {}
        }


def get_previous_decision() -> Optional[Dict[str, Any]]:
    """이전 전략 결정 결과 조회 (가장 최근 것)"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    decision_date,
                    analysis_summary,
                    target_allocation,
                    recommended_stocks
                FROM ai_strategy_decisions
                ORDER BY decision_date DESC
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if not row:
                return None
            
            # target_allocation에서 mp_id 추출
            target_allocation_data = None
            mp_id = None
            if row.get('target_allocation'):
                try:
                    target_allocation_data = json.loads(row['target_allocation'])
                    mp_id = target_allocation_data.get('mp_id')
                except (json.JSONDecodeError, TypeError):
                    pass
            
            # recommended_stocks에서 sub_mp 추출
            sub_mp_data = None
            if row.get('recommended_stocks'):
                try:
                    recommended_stocks_data = json.loads(row['recommended_stocks'])
                    # Sub-MP 정보는 별도로 저장하지 않았을 수 있으므로 None일 수 있음
                    sub_mp_data = None
                except (json.JSONDecodeError, TypeError):
                    pass
            
            return {
                "decision_date": row.get('decision_date'),
                "mp_id": mp_id,
                "sub_mp": sub_mp_data,
                "analysis_summary": row.get('analysis_summary')
            }
    except Exception as e:
        logger.warning(f"이전 결정 조회 실패: {e}")
        return None


def get_previous_decision_with_sub_mp() -> Optional[Dict[str, Any]]:
    """이전 전략 결정 결과 조회 (Sub-MP 포함)"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    decision_date,
                    analysis_summary,
                    target_allocation,
                    recommended_stocks
                FROM ai_strategy_decisions
                ORDER BY decision_date DESC
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if not row:
                return None
            
            # target_allocation에서 mp_id 추출
            target_allocation_data = None
            mp_id = None
            if row.get('target_allocation'):
                try:
                    target_allocation_data = json.loads(row['target_allocation'])
                    mp_id = target_allocation_data.get('mp_id')
                except (json.JSONDecodeError, TypeError):
                    pass
            
            # target_allocation에서 sub_mp 추출
            sub_mp_data = None
            if target_allocation_data:
                sub_mp_data = target_allocation_data.get('sub_mp')
            
            return {
                "decision_date": row.get('decision_date'),
                "mp_id": mp_id,
                "sub_mp": sub_mp_data,
                "analysis_summary": row.get('analysis_summary')
            }
    except Exception as e:
        logger.warning(f"이전 결정 조회 실패: {e}")
        return None


def get_available_etf_list() -> Dict[str, List[Dict]]:
    """사용 가능한 ETF 목록 조회 (DB 우선, 없으면 설정 파일)"""
    try:
        from service.database.db import get_db_connection
        
        # 먼저 DB에서 조회
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT asset_class, ticker, name, weight
                FROM asset_class_details
                WHERE is_active = TRUE
                ORDER BY asset_class, weight DESC
            """)
            rows = cursor.fetchall()
            
            if rows:
                result = {
                    "stocks": [],
                    "bonds": [],
                    "alternatives": [],
                    "cash": []
                }
                for row in rows:
                    asset_class = row["asset_class"]
                    if asset_class in result:
                        result[asset_class].append({
                            "ticker": row["ticker"],
                            "name": row["name"],
                            "weight": float(row["weight"])
                        })
                return result
    except Exception as e:
        logger.warning(f"DB에서 ETF 목록 조회 실패: {e}")
    
    # DB 조회 실패 시 설정 파일에서 로드
    try:
        from service.macro_trading.config.config_loader import get_config
        config = get_config()
        etf_mapping = config.etf_mapping
        
        result = {
            "stocks": [],
            "bonds": [],
            "alternatives": [],
            "cash": []
        }
        
        for asset_class, mapping in etf_mapping.items():
            if asset_class in result:
                for ticker, name, weight in zip(mapping.tickers, mapping.names, mapping.weights):
                    result[asset_class].append({
                        "ticker": ticker,
                        "name": name,
                        "weight": weight
                    })
        
        return result
    except Exception as e:
        logger.warning(f"설정 파일에서 ETF 목록 로드 실패: {e}")
        return {
            "stocks": [],
            "bonds": [],
            "alternatives": [],
            "cash": []
        }


def create_mp_analysis_prompt(fred_signals: Dict, economic_news: Dict, previous_mp_id: Optional[str] = None) -> str:
    """MP 분석용 프롬프트 생성"""
    
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
            fred_summary += f"실질 금리 (DFII10): {real_rate:.2f}%\n"
        
        # 실질 금리 지난 12개월 데이터 추가 (DFII10 직접 조회)
        try:
            from service.macro_trading.collectors.fred_collector import get_fred_collector
            collector = get_fred_collector()
            dfii10_data = collector.get_latest_data("DFII10", days=365)
            if dfii10_data is not None and len(dfii10_data) > 0:
                # 최근 12개월 데이터 추출 (월별로 샘플링)
                import pandas as pd
                real_rate_monthly = dfii10_data.resample('M').last().tail(12)
                if len(real_rate_monthly) > 0:
                    fred_summary += "\n=== 실질 금리 지난 12개월 데이터 (DFII10) ===\n"
                    for date_idx, value in real_rate_monthly.items():
                        if pd.notna(value):
                            date_str = date_idx.strftime("%Y-%m") if hasattr(date_idx, 'strftime') else str(date_idx)
                            fred_summary += f"  {date_str}: {value:.2f}%\n"
        except Exception as e:
            logger.warning(f"실질 금리 시계열 데이터 조회 실패: {e}")
        
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
        
        # 연준 순 유동성 지난 12개월 데이터 추가
        try:
            from service.macro_trading.signals.quant_signals import QuantSignalCalculator
            calculator = QuantSignalCalculator()
            net_liquidity_series = calculator.get_net_liquidity_series(days=365)
            if net_liquidity_series is not None and len(net_liquidity_series) > 0:
                # 최근 12개월 데이터 추출 (월별로 샘플링)
                import pandas as pd
                net_liquidity_monthly = net_liquidity_series.resample('M').last().tail(12)
                if len(net_liquidity_monthly) > 0:
                    fred_summary += "\n=== 연준 순 유동성 지난 12개월 데이터 ===\n"
                    for date_idx, value in net_liquidity_monthly.items():
                        if pd.notna(value):
                            date_str = date_idx.strftime("%Y-%m") if hasattr(date_idx, 'strftime') else str(date_idx)
                            # Billions로 변환하여 표시
                            value_billions = value / 1000
                            fred_summary += f"  {date_str}: {value_billions:.2f}B $\n"
        except Exception as e:
            logger.warning(f"연준 순 유동성 시계열 데이터 조회 실패: {e}")
        
        hy_spread = fred_signals.get('high_yield_spread', {})
        if hy_spread:
            signal_name = hy_spread.get('signal_name', 'N/A')
            spread_val = hy_spread.get('spread', 'N/A')
            fred_summary += f"하이일드 스프레드: {signal_name} ({spread_val}%)\n"
        
        # 물가 및 고용 지표 (지난 10개 데이터)
        inflation_employment = fred_signals.get('inflation_employment_data', {})
        if inflation_employment:
            fred_summary += "\n=== 물가 지표 (지난 10개 데이터) ===\n"
            
            # PCEPI
            pcepi = inflation_employment.get('pcepi', [])
            if pcepi:
                fred_summary += "PCEPI (Personal Consumption Expenditures Price Index):\n"
                for item in pcepi:
                    fred_summary += f"  {item['date']}: {item['value']:.2f}\n"
            else:
                fred_summary += "PCEPI: 데이터 없음\n"
            
            # CPI
            cpi = inflation_employment.get('cpi', [])
            if cpi:
                fred_summary += "\nCPI (Consumer Price Index):\n"
                for item in cpi:
                    fred_summary += f"  {item['date']}: {item['value']:.2f}\n"
            else:
                fred_summary += "\nCPI: 데이터 없음\n"
            
            fred_summary += "\n=== 고용 지표 (지난 10개 데이터) ===\n"
            
            # 실업률
            unrate = inflation_employment.get('unemployment_rate', [])
            if unrate:
                fred_summary += "실업률 (Unemployment Rate, %):\n"
                for item in unrate:
                    fred_summary += f"  {item['date']}: {item['value']:.2f}%\n"
            else:
                fred_summary += "실업률: 데이터 없음\n"
            
            # 비농업 고용
            payroll = inflation_employment.get('nonfarm_payroll', [])
            if payroll:
                fred_summary += "\n비농업 고용 (Nonfarm Payroll, Thousands):\n"
                for item in payroll:
                    fred_summary += f"  {item['date']}: {item['value']:,.0f}\n"
            else:
                fred_summary += "\n비농업 고용: 데이터 없음\n"
    
    # 경제 뉴스 요약 (LLM으로 정제된 요약 사용)
    news_summary = "\n=== 경제 뉴스 (비중 낮게 참고) ===\n"
    if economic_news:
        target_countries = economic_news.get('target_countries', [])
        total_count = economic_news.get('total_count', 0)
        days = economic_news.get('days', 20)
        
        # LLM으로 정제된 요약이 있으면 사용
        llm_summary = economic_news.get('news_summary')
        if llm_summary:
            news_summary += f"지난 {days}일간 {', '.join(target_countries)} 국가 뉴스 {total_count}개를 분석한 결과:\n\n"
            news_summary += llm_summary
        elif economic_news.get('news'):
            # LLM 요약이 없는 경우 기존 방식으로 표시
            news_summary += f"지난 {days}일간 {', '.join(target_countries)} 국가 뉴스 {total_count}개\n\n"
            news_summary += "(LLM 요약 실패 - 원본 뉴스 일부 표시)\n\n"
            news_list = economic_news['news'][:10]  # 최근 10개만
            for news in news_list:
                news_summary += f"- [{news.get('country', 'N/A')}] {news.get('title', 'N/A')}\n"
                if news.get('description'):
                    desc = news.get('description', '')[:100]  # 처음 100자만
                    news_summary += f"  {desc}...\n"
        else:
            news_summary += "최근 뉴스 없음\n"
    else:
        news_summary += "최근 뉴스 없음\n"
    
    # 이전 MP 정보
    previous_mp_info = ""
    if previous_mp_id:
        previous_mp = MODEL_PORTFOLIOS.get(previous_mp_id)
        if previous_mp:
            previous_mp_info = f"\n=== 이전 MP 정보 ===\n"
            previous_mp_info += f"이전에 선택된 MP: {previous_mp_id} - {previous_mp['name']}\n"
            previous_mp_info += f"이전 MP 특징: {previous_mp['description']}\n\n"
            previous_mp_info += "**중요:** 경제 상황이 크게 달라지지 않은 경우, 이전 MP를 유지하는 것이 좋습니다.\n"
            previous_mp_info += "경제 지표의 변화가 명확하고 지속적인 경우에만 MP를 변경하세요.\n\n"
    
    # MP 시나리오 정보를 프롬프트에 포함
    mp_info = "\n=== 모델 포트폴리오 (MP) 시나리오 ===\n"
    mp_info += "현재 거시경제 국면을 분석하여 다음 5가지 모델 포트폴리오 중 하나를 선택하세요:\n\n"
    for mp_id, mp in MODEL_PORTFOLIOS.items():
        mp_info += f"{mp_id}: {mp['name']}\n"
        mp_info += f"  - 특징: {mp['description']}\n"
        mp_info += f"  - 핵심 전략: {mp['strategy']}\n"
        mp_info += f"  - 자산 배분: 주식 {mp['allocation']['Stocks']}% / 채권 {mp['allocation']['Bonds']}% / 대체투자 {mp['allocation']['Alternatives']}% / 현금 {mp['allocation']['Cash']}%\n\n"
    
    prompt = f"""당신은 거시경제 전문가입니다. 다음 데이터를 분석하여 현재 거시경제 국면에 가장 적합한 모델 포트폴리오(MP)를 선택하세요.

{previous_mp_info}

{fred_summary}

{news_summary}

{mp_info}

## 분석 지침:
1. **FRED 지표를 가장 신뢰도 높게** 사용하세요. FRED 지표는 객관적이고 정량적입니다.
2. **경제 뉴스는 보조 수단입니다.** FRED 지표 기반 분석한 내용을 한번 더 검토하는 수단입니다.
3. **현재 거시경제 국면을 정확히 파악**하여 위의 5가지 MP 시나리오 중 하나를 선택하세요.
4. **이전 MP 고려사항:**
   - 경제 상황이 크게 달라지지 않은 경우 이전 MP를 유지하세요.
   - 경제 지표의 변화가 명확하고 지속적인 경우에만 MP를 변경하세요.
5. MP 선택 시 고려사항:
   - 성장률 추세 (상승/하락/중립)
   - 물가 추세 (상승/안정/하락)
   - 금리 정책 방향 (인상/안정/인하)
   - 유동성 상황 (확대/축소)
   - 하이일드 스프레드 (Greed/Fear/Panic)
   - 실업률 및 고용 동향

## 출력 형식 (JSON):
{{
    "analysis_summary": "분석 요약 (한국어, 200-300자)",
    "mp_id": "MP-4",
    "reasoning": "판단 근거 (한국어, 500-700자) - 왜 이 MP를 선택했는지 설명 (이전 MP와 비교하여 변경 이유 포함)"
}}

**중요:**
- mp_id는 반드시 "MP-1", "MP-2", "MP-3", "MP-4", "MP-5" 중 하나여야 합니다.
- 경제 상황이 크게 달라지지 않은 경우 이전 MP를 유지하세요.
- MP 변경 시에는 명확한 근거를 제시하세요.

JSON 형식으로만 응답하세요. 다른 설명은 포함하지 마세요.
"""
    
    return prompt


def create_sub_mp_analysis_prompt(
    fred_signals: Dict, 
    economic_news: Dict, 
    mp_id: str,
    previous_sub_mp: Optional[Dict[str, str]] = None
) -> str:
    """Sub-MP 분석용 프롬프트 생성
    
    Args:
        fred_signals: FRED 시그널 데이터
        economic_news: 경제 뉴스 데이터
        mp_id: 선택된 MP ID
        previous_sub_mp: 이전 Sub-MP 정보 ({"stocks": "Eq-A", "bonds": "Bnd-L", "alternatives": "Alt-I"} 형태)
    """
    
    # FRED 시그널 요약 (간단히)
    fred_summary = "=== FRED 정량 시그널 요약 ===\n"
    if fred_signals:
        yield_curve = fred_signals.get('yield_curve_spread_trend', {})
        if yield_curve:
            fred_summary += f"금리 곡선 국면: {yield_curve.get('regime_kr', 'N/A')}\n"
            fred_summary += f"금리 대세: {yield_curve.get('yield_regime_kr', 'N/A')}\n"
        
        real_rate = fred_signals.get('real_interest_rate')
        if real_rate is not None:
            fred_summary += f"실질 금리: {real_rate:.2f}%\n"
        
        hy_spread = fred_signals.get('high_yield_spread', {})
        if hy_spread:
            signal_name = hy_spread.get('signal_name', 'N/A')
            fred_summary += f"하이일드 스프레드: {signal_name}\n"
    
    # 선택된 MP 정보
    selected_mp = MODEL_PORTFOLIOS.get(mp_id, {})
    mp_info = f"\n=== 선택된 MP 정보 ===\n"
    mp_info += f"MP: {mp_id} - {selected_mp.get('name', 'N/A')}\n"
    mp_info += f"자산 배분: 주식 {selected_mp.get('allocation', {}).get('Stocks', 0)}% / "
    mp_info += f"채권 {selected_mp.get('allocation', {}).get('Bonds', 0)}% / "
    mp_info += f"대체투자 {selected_mp.get('allocation', {}).get('Alternatives', 0)}% / "
    mp_info += f"현금 {selected_mp.get('allocation', {}).get('Cash', 0)}%\n\n"
    
    # 이전 Sub-MP 정보
    previous_sub_mp_info = ""
    if previous_sub_mp:
        previous_sub_mp_info = "\n=== 이전 Sub-MP 정보 ===\n"
        if previous_sub_mp.get('stocks'):
            prev_stocks = SUB_MODEL_PORTFOLIOS.get(previous_sub_mp['stocks'], {})
            previous_sub_mp_info += f"이전 주식 Sub-MP: {previous_sub_mp['stocks']} - {prev_stocks.get('name', 'N/A')}\n"
        if previous_sub_mp.get('bonds'):
            prev_bonds = SUB_MODEL_PORTFOLIOS.get(previous_sub_mp['bonds'], {})
            previous_sub_mp_info += f"이전 채권 Sub-MP: {previous_sub_mp['bonds']} - {prev_bonds.get('name', 'N/A')}\n"
        if previous_sub_mp.get('alternatives'):
            prev_alt = SUB_MODEL_PORTFOLIOS.get(previous_sub_mp['alternatives'], {})
            previous_sub_mp_info += f"이전 대체자산 Sub-MP: {previous_sub_mp['alternatives']} - {prev_alt.get('name', 'N/A')}\n"
        previous_sub_mp_info += "\n**중요:** 경제 상황이 크게 달라지지 않은 경우, 이전 Sub-MP를 유지하는 것이 좋습니다.\n"
        previous_sub_mp_info += "경제 지표의 변화가 명확하고 지속적인 경우에만 Sub-MP를 변경하세요.\n\n"
    
    # Sub-MP 시나리오 정보
    sub_mp_info = "\n=== Sub-MP (자산군별 세부 모델) 시나리오 ===\n"
    
    # 주식 Sub-MP
    sub_mp_info += "\n### 주식 (Equity) Sub-Models:\n"
    for sub_mp_id in ["Eq-A", "Eq-N", "Eq-D"]:
        sub_mp = SUB_MODEL_PORTFOLIOS.get(sub_mp_id, {})
        if sub_mp:
            sub_mp_info += f"{sub_mp_id}: {sub_mp.get('name', 'N/A')}\n"
            sub_mp_info += f"  - 상황: {sub_mp.get('description', 'N/A')}\n"
            etf_details = sub_mp.get('etf_details', [])
            if etf_details:
                sub_mp_info += f"  - 세부 종목:\n"
                for etf in etf_details:
                    sub_mp_info += f"    * {etf.get('ticker', 'N/A')} ({etf.get('name', 'N/A')}): {etf.get('weight', 0)*100:.0f}%\n"
            sub_mp_info += "\n"
    
    # 채권 Sub-MP
    sub_mp_info += "\n### 채권 (Bond) Sub-Models:\n"
    for sub_mp_id in ["Bnd-L", "Bnd-N", "Bnd-S"]:
        sub_mp = SUB_MODEL_PORTFOLIOS.get(sub_mp_id, {})
        if sub_mp:
            sub_mp_info += f"{sub_mp_id}: {sub_mp.get('name', 'N/A')}\n"
            sub_mp_info += f"  - 상황: {sub_mp.get('description', 'N/A')}\n"
            etf_details = sub_mp.get('etf_details', [])
            if etf_details:
                sub_mp_info += f"  - 세부 종목:\n"
                for etf in etf_details:
                    sub_mp_info += f"    * {etf.get('ticker', 'N/A')} ({etf.get('name', 'N/A')}): {etf.get('weight', 0)*100:.0f}%\n"
            sub_mp_info += "\n"
    
    # 대체자산 Sub-MP
    sub_mp_info += "\n### 대체자산 (Alternatives) Sub-Models:\n"
    for sub_mp_id in ["Alt-I", "Alt-C"]:
        sub_mp = SUB_MODEL_PORTFOLIOS.get(sub_mp_id, {})
        if sub_mp:
            sub_mp_info += f"{sub_mp_id}: {sub_mp.get('name', 'N/A')}\n"
            sub_mp_info += f"  - 상황: {sub_mp.get('description', 'N/A')}\n"
            etf_details = sub_mp.get('etf_details', [])
            if etf_details:
                sub_mp_info += f"  - 세부 종목:\n"
                for etf in etf_details:
                    sub_mp_info += f"    * {etf.get('ticker', 'N/A')} ({etf.get('name', 'N/A')}): {etf.get('weight', 0)*100:.0f}%\n"
            sub_mp_info += "\n"
    
    prompt = f"""당신은 거시경제 전문가입니다. 선택된 MP({mp_id})에 기반하여 각 자산군별 Sub-MP를 선택하세요.

{previous_sub_mp_info}

{mp_info}

{fred_summary}

{sub_mp_info}

## 분석 지침:
1. **선택된 MP를 고려**하여 각 자산군별로 적합한 Sub-MP를 선택하세요.
2. **주식 Sub-MP 선택 기준:**
   - 금리 인하기, 유동성 풍부, Risk-On → Eq-A (성장 공격형)
   - 방향성 불확실, 일반적인 상승장 → Eq-N (시장 중립형)
   - 고금리 장기화, 경기 침체 우려 → Eq-D (방어형)
3. **채권 Sub-MP 선택 기준:**
   - 금리 인하 확실시 → Bnd-L (장기채 베팅)
   - 금리 동결 또는 완만한 인하 → Bnd-N (균형)
   - 금리 인상기, 인플레이션 쇼크 → Bnd-S (단기채 방어)
4. **대체자산 Sub-MP 선택 기준:**
   - 스태그플레이션, 물가 급등, 달러 약세 → Alt-I (인플레 방어)
   - 금융 위기, 시스템 리스크, 주식 폭락 → Alt-C (위기 방어)
5. **이전 Sub-MP 고려사항:**
   - 경제 상황이 크게 달라지지 않은 경우 이전 Sub-MP를 유지하세요.
   - 경제 지표의 변화가 명확하고 지속적인 경우에만 Sub-MP를 변경하세요.
6. **자산군 비중이 0%인 경우:**
   - 해당 자산군의 Sub-MP는 null로 설정하세요.

## 출력 형식 (JSON):
{{
    "stocks_sub_mp": "Eq-A" 또는 "Eq-N" 또는 "Eq-D" 또는 null,
    "bonds_sub_mp": "Bnd-L" 또는 "Bnd-N" 또는 "Bnd-S" 또는 null,
    "alternatives_sub_mp": "Alt-I" 또는 "Alt-C" 또는 null,
    "reasoning": "Sub-MP 선택 근거 (한국어, 300-500자) - 각 자산군별 선택 이유 및 이전 Sub-MP와 비교"
}}

**중요:**
- 각 자산군의 Sub-MP ID는 위에 명시된 것만 사용하세요.
- 자산군 비중이 0%인 경우 해당 Sub-MP는 null로 설정하세요.
- 경제 상황이 크게 달라지지 않은 경우 이전 Sub-MP를 유지하세요.

JSON 형식으로만 응답하세요. 다른 설명은 포함하지 마세요.
"""
    
    return prompt


def _parse_llm_response(response) -> str:
    """LLM 응답을 텍스트로 파싱"""
    response_text = None
    if hasattr(response, 'content'):
        if isinstance(response.content, list) and len(response.content) > 0:
            first_item = response.content[0]
            if isinstance(first_item, dict) and 'text' in first_item:
                response_text = first_item['text']
            elif isinstance(first_item, dict) and 'type' in first_item and first_item.get('type') == 'text':
                response_text = str(first_item.get('text', ''))
            else:
                response_text = str(first_item)
        elif isinstance(response.content, str):
            response_text = response.content
        else:
            response_text = str(response.content)
    elif hasattr(response, 'text'):
        response_text = response.text
    elif isinstance(response, str):
        response_text = response
    else:
        response_text = str(response)
    
    if isinstance(response_text, list):
        if len(response_text) > 0:
            first_item = response_text[0]
            if isinstance(first_item, dict) and 'text' in first_item:
                response_text = first_item['text']
            else:
                response_text = str(first_item)
        else:
            response_text = ""
    
    if not isinstance(response_text, str):
        response_text = str(response_text)
    
    # 마크다운 코드 블록 제거
    response_text = response_text.strip()
    if response_text.startswith('```'):
        lines = response_text.split('\n')
        if len(lines) > 1:
            if lines[-1].strip() == '```' or lines[-1].strip().startswith('```'):
                response_text = '\n'.join(lines[1:-1])
            else:
                response_text = '\n'.join(lines[1:])
    
    return response_text


def _parse_json_response(response_text: str) -> Dict:
    """JSON 응답 파싱"""
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 파싱 실패, 재시도 중... (오류: {e})")
        logger.warning(f"응답 텍스트 (처음 500자): {response_text[:500]}")
        logger.warning(f"응답 텍스트 (마지막 500자): {response_text[-500:]}")
        import re
        json_match = re.search(r'\{[\s\S]*\}', response_text, re.MULTILINE)
        if json_match:
            try:
                extracted_json = json_match.group()
                logger.info(f"정규식으로 JSON 추출 성공 (길이: {len(extracted_json)}자)")
                return json.loads(extracted_json)
            except json.JSONDecodeError as e2:
                logger.error(f"정규식 추출 후 JSON 파싱 실패: {e2}")
                logger.error(f"추출된 JSON (처음 500자): {extracted_json[:500]}")
                raise ValueError(f"JSON 형식이 올바르지 않습니다. 원본 오류: {e}, 추출 오류: {e2}")
        else:
            logger.error(f"JSON 객체를 찾을 수 없습니다. 전체 응답 길이: {len(response_text)}자")
            logger.error(f"응답 텍스트 (처음 1000자): {response_text[:1000]}")
            raise ValueError(f"JSON 형식이 올바르지 않습니다. JSON 객체를 찾을 수 없습니다.")


def analyze_and_decide(fred_signals: Optional[Dict] = None, economic_news: Optional[Dict] = None) -> Optional[AIStrategyDecision]:
    """AI 분석 및 전략 결정 (MP 분석 + Sub-MP 분석 분리)
    
    Args:
        fred_signals: FRED 시그널 데이터 (None이면 수집)
        economic_news: 경제 뉴스 데이터 (None이면 수집)
    """
    try:
        logger.info("AI 전략 분석 시작 (MP + Sub-MP 분리 분석)")
        
        # 데이터 수집 (파라미터로 전달되지 않은 경우에만)
        if fred_signals is None:
            logger.info("FRED 시그널 수집 중...")
            fred_signals = collect_fred_signals()
        
        if economic_news is None:
            logger.info("경제 뉴스 수집 중... (지난 20일, 특정 국가 필터)")
            economic_news = collect_economic_news(days=20)
        
        # 이전 결정 조회
        previous_decision = get_previous_decision_with_sub_mp()
        previous_mp_id = previous_decision.get('mp_id') if previous_decision else None
        previous_sub_mp = previous_decision.get('sub_mp') if previous_decision else None
        
        # 설정에서 모델명 가져오기
        from service.macro_trading.config.config_loader import get_config
        config = get_config()
        model_name = config.llm.model
        llm = llm_gemini_pro(model=model_name)
        
        # ===== 1단계: MP 분석 =====
        logger.info("1단계: MP 분석 중...")
        mp_prompt = create_mp_analysis_prompt(fred_signals, economic_news, previous_mp_id)
        
        with track_llm_call(
            model_name=model_name,
            provider="Google",
            service_name="ai_strategist_mp",
            request_prompt=mp_prompt
        ) as tracker:
            mp_response = llm.invoke(mp_prompt)
            tracker.set_response(mp_response)
        
        mp_response_text = _parse_llm_response(mp_response)
        mp_decision_data = _parse_json_response(mp_response_text)
        
        # MP ID 검증
        mp_id = mp_decision_data.get('mp_id')
        if not mp_id or mp_id not in MODEL_PORTFOLIOS:
            valid_mp_ids = ', '.join(MODEL_PORTFOLIOS.keys())
            logger.error(f"유효하지 않은 MP ID: {mp_id}. 유효한 MP ID: {valid_mp_ids}")
            raise ValueError(f"유효하지 않은 MP ID: {mp_id}. 유효한 MP ID는 {valid_mp_ids} 중 하나여야 합니다.")
        
        logger.info(f"MP 분석 완료: {mp_id}")
        
        # ===== 2단계: Sub-MP 분석 =====
        logger.info("2단계: Sub-MP 분석 중...")
        try:
            sub_mp_prompt = create_sub_mp_analysis_prompt(fred_signals, economic_news, mp_id, previous_sub_mp)
            logger.info(f"Sub-MP 프롬프트 생성 완료 (길이: {len(sub_mp_prompt)}자)")
            
            with track_llm_call(
                model_name=model_name,
                provider="Google",
                service_name="ai_strategist_sub_mp",
                request_prompt=sub_mp_prompt
            ) as tracker:
                logger.info("Sub-MP LLM 호출 시작...")
                sub_mp_response = llm.invoke(sub_mp_prompt)
                tracker.set_response(sub_mp_response)
                logger.info("Sub-MP LLM 응답 수신 완료")
            
            logger.info("Sub-MP 응답 파싱 시작...")
            sub_mp_response_text = _parse_llm_response(sub_mp_response)
            logger.info(f"Sub-MP 응답 텍스트 추출 완료 (길이: {len(sub_mp_response_text)}자)")
            
            sub_mp_decision_data = _parse_json_response(sub_mp_response_text)
            logger.info(f"Sub-MP JSON 파싱 완료: {sub_mp_decision_data}")
        except Exception as e:
            logger.error(f"Sub-MP 분석 중 오류 발생: {e}", exc_info=True)
            logger.error(f"Sub-MP 분석 오류 타입: {type(e).__name__}")
            import traceback
            logger.error(f"Sub-MP 분석 전체 traceback:\n{traceback.format_exc()}")
            raise
        
        # Sub-MP 검증
        stocks_sub_mp = sub_mp_decision_data.get('stocks_sub_mp')
        bonds_sub_mp = sub_mp_decision_data.get('bonds_sub_mp')
        alternatives_sub_mp = sub_mp_decision_data.get('alternatives_sub_mp')
        
        # 자산군 비중 확인
        target_allocation = get_model_portfolio_allocation(mp_id)
        if target_allocation:
            if target_allocation.get('Stocks', 0) == 0:
                stocks_sub_mp = None
            if target_allocation.get('Bonds', 0) == 0:
                bonds_sub_mp = None
            if target_allocation.get('Alternatives', 0) == 0:
                alternatives_sub_mp = None
        
        # Sub-MP 유효성 검증
        valid_stocks_sub_mp = ["Eq-A", "Eq-N", "Eq-D"]
        valid_bonds_sub_mp = ["Bnd-L", "Bnd-N", "Bnd-S"]
        valid_alternatives_sub_mp = ["Alt-I", "Alt-C"]
        
        if stocks_sub_mp and stocks_sub_mp not in valid_stocks_sub_mp:
            logger.warning(f"유효하지 않은 주식 Sub-MP: {stocks_sub_mp}, None으로 설정")
            stocks_sub_mp = None
        if bonds_sub_mp and bonds_sub_mp not in valid_bonds_sub_mp:
            logger.warning(f"유효하지 않은 채권 Sub-MP: {bonds_sub_mp}, None으로 설정")
            bonds_sub_mp = None
        if alternatives_sub_mp and alternatives_sub_mp not in valid_alternatives_sub_mp:
            logger.warning(f"유효하지 않은 대체자산 Sub-MP: {alternatives_sub_mp}, None으로 설정")
            alternatives_sub_mp = None
        
        logger.info(f"Sub-MP 분석 완료: Stocks={stocks_sub_mp}, Bonds={bonds_sub_mp}, Alternatives={alternatives_sub_mp}")
        
        # ===== 최종 결정 생성 =====
        sub_mp_decision = SubMPDecision(
            stocks_sub_mp=stocks_sub_mp,
            bonds_sub_mp=bonds_sub_mp,
            alternatives_sub_mp=alternatives_sub_mp,
            reasoning=sub_mp_decision_data.get('reasoning', '')
        )
        
        decision = AIStrategyDecision(
            analysis_summary=mp_decision_data.get('analysis_summary', ''),
            mp_id=mp_id,
            reasoning=mp_decision_data.get('reasoning', ''),
            sub_mp=sub_mp_decision,
            recommended_stocks=None  # 추천 종목은 Sub-MP 기반으로 나중에 생성 가능
        )
        
        target_allocation = decision.get_target_allocation()
        logger.info(f"AI 분석 완료: MP={decision.mp_id}, {decision.analysis_summary[:50]}...")
        logger.info(f"자산 배분: Stocks={target_allocation.Stocks}%, Bonds={target_allocation.Bonds}%, "
                   f"Alternatives={target_allocation.Alternatives}%, Cash={target_allocation.Cash}%")
        if decision.sub_mp:
            logger.info(f"Sub-MP: Stocks={decision.sub_mp.stocks_sub_mp}, "
                       f"Bonds={decision.sub_mp.bonds_sub_mp}, "
                       f"Alternatives={decision.sub_mp.alternatives_sub_mp}")
        
        return decision
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 실패: {e}")
        raise
    except ValueError as e:
        logger.error(f"데이터 검증 실패: {e}")
        raise
    except Exception as e:
        logger.error(f"AI 분석 실패: {e}", exc_info=True)
        raise


# ============================================================================
# LangGraph 워크플로우 정의
# ============================================================================

class AIAnalysisState(TypedDict):
    """AI 분석 워크플로우 상태"""
    fred_signals: Optional[Dict[str, Any]]
    economic_news: Optional[Dict[str, Any]]
    news_summary: Optional[str]
    decision: Optional[AIStrategyDecision]
    error: Optional[str]
    success: bool


def collect_fred_node(state: AIAnalysisState) -> AIAnalysisState:
    """FRED 시그널 수집 노드"""
    try:
        logger.info("1단계: FRED 시그널 수집 중...")
        fred_signals = collect_fred_signals()
        if not fred_signals:
            logger.warning("FRED 시그널 수집 실패 (None 반환)")
        return {
            **state,
            "fred_signals": fred_signals
        }
    except Exception as e:
        logger.error(f"FRED 시그널 수집 실패: {e}", exc_info=True)
        return {
            **state,
            "fred_signals": None,
            "error": f"FRED 시그널 수집 실패: {str(e)}"
        }


def collect_news_node(state: AIAnalysisState) -> AIAnalysisState:
    """경제 뉴스 수집 노드 (LLM 요약 제외)"""
    try:
        logger.info("2단계: 경제 뉴스 수집 중...")
        # LLM 요약 없이 뉴스만 수집
        economic_news = collect_economic_news(days=20, include_summary=False)
        if not economic_news:
            logger.warning("경제 뉴스 수집 실패 (None 반환)")
        return {
            **state,
            "economic_news": economic_news
        }
    except Exception as e:
        logger.error(f"경제 뉴스 수집 실패: {e}", exc_info=True)
        return {
            **state,
            "economic_news": None,
            "error": f"경제 뉴스 수집 실패: {str(e)}"
        }


def summarize_news_node(state: AIAnalysisState) -> AIAnalysisState:
    """뉴스 LLM 요약 노드"""
    try:
        economic_news = state.get("economic_news")
        if not economic_news or not economic_news.get("news"):
            logger.warning("요약할 뉴스가 없습니다.")
            return {
                **state,
                "news_summary": None
            }
        
        news_list = economic_news.get("news", [])
        target_countries = economic_news.get("target_countries", [])
        
        logger.info("2-1단계: 뉴스 LLM 요약 중...")
        news_summary = summarize_news_with_llm(news_list, target_countries)
        
        # economic_news에 요약 결과 추가
        if economic_news:
            economic_news["news_summary"] = news_summary
        
        return {
            **state,
            "economic_news": economic_news,
            "news_summary": news_summary
        }
    except Exception as e:
        logger.error(f"뉴스 요약 실패: {e}", exc_info=True)
        return {
            **state,
            "news_summary": None,
            "error": f"뉴스 요약 실패: {str(e)}"
        }


def analyze_node(state: AIAnalysisState) -> AIAnalysisState:
    """AI 분석 및 전략 결정 노드"""
    try:
        logger.info("3단계: AI 분석 및 전략 결정 중...")
        fred_signals = state.get("fred_signals")
        economic_news = state.get("economic_news")
        
        logger.info(f"FRED 시그널 상태: {'있음' if fred_signals else '없음'}")
        logger.info(f"경제 뉴스 상태: {'있음' if economic_news else '없음'}")
        
        decision = analyze_and_decide(fred_signals=fred_signals, economic_news=economic_news)
        
        if not decision:
            logger.error("AI 분석 실패: analyze_and_decide()가 None 반환")
            return {
                **state,
                "decision": None,
                "error": "AI 분석 실패: analyze_and_decide()가 None 반환"
            }
        
        logger.info(f"AI 분석 완료: decision 객체 생성 성공, MP={decision.mp_id if decision else 'None'}")
        return {
            **state,
            "decision": decision
        }
    except Exception as e:
        logger.error(f"AI 분석 실패: {e}", exc_info=True)
        logger.error(f"AI 분석 실패 타입: {type(e).__name__}")
        import traceback
        logger.error(f"AI 분석 전체 traceback:\n{traceback.format_exc()}")
        return {
            **state,
            "decision": None,
            "error": f"AI 분석 실패: {str(e)}"
        }


def save_decision_node(state: AIAnalysisState) -> AIAnalysisState:
    """전략 결정 결과 저장 노드"""
    try:
        logger.info("4단계: 결과 저장 중...")
        decision = state.get("decision")
        fred_signals = state.get("fred_signals")
        economic_news = state.get("economic_news")
        
        if not decision:
            logger.error("저장할 결정이 없습니다.")
            return {
                **state,
                "success": False,
                "error": "저장할 결정이 없습니다."
            }
        
        success = save_strategy_decision(decision, fred_signals, economic_news)
        
        if success:
            target_allocation = decision.get_target_allocation()
            mp_info = MODEL_PORTFOLIOS.get(decision.mp_id, {})
            logger.info("=" * 60)
            logger.info("AI 전략 분석 완료")
            logger.info(f"선택된 MP: {decision.mp_id} - {mp_info.get('name', 'N/A')}")
            logger.info(f"분석 요약: {decision.analysis_summary}")
            logger.info(f"목표 배분: Stocks={target_allocation.Stocks}%, "
                       f"Bonds={target_allocation.Bonds}%, "
                       f"Alternatives={target_allocation.Alternatives}%, "
                       f"Cash={target_allocation.Cash}%")
            if decision.recommended_stocks:
                logger.info(f"추천 섹터: {len(decision.recommended_stocks.Stocks or [])}개 주식, "
                           f"{len(decision.recommended_stocks.Bonds or [])}개 채권, "
                           f"{len(decision.recommended_stocks.Alternatives or [])}개 대체투자, "
                           f"{len(decision.recommended_stocks.Cash or [])}개 현금")
            logger.info("=" * 60)
        
        return {
            **state,
            "success": success
        }
    except Exception as e:
        logger.error(f"결과 저장 실패: {e}", exc_info=True)
        return {
            **state,
            "success": False,
            "error": f"결과 저장 실패: {str(e)}"
        }


# LangGraph 워크플로우 구성
def create_ai_analysis_graph():
    """AI 분석 워크플로우 그래프 생성"""
    graph = StateGraph(AIAnalysisState)
    
    # 노드 추가
    graph.add_node("collect_fred", collect_fred_node)
    graph.add_node("collect_news", collect_news_node)
    graph.add_node("summarize_news", summarize_news_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("save_decision", save_decision_node)
    
    # 엣지 연결: 순차 실행
    graph.add_edge(START, "collect_fred")
    graph.add_edge("collect_fred", "collect_news")
    graph.add_edge("collect_news", "summarize_news")
    graph.add_edge("summarize_news", "analyze")
    graph.add_edge("analyze", "save_decision")
    graph.add_edge("save_decision", END)
    
    return graph.compile()


# 전역 그래프 인스턴스 (필요시 재사용)
_ai_analysis_graph = None


def get_ai_analysis_graph():
    """AI 분석 그래프 인스턴스 반환 (싱글톤)"""
    global _ai_analysis_graph
    if _ai_analysis_graph is None:
        _ai_analysis_graph = create_ai_analysis_graph()
    return _ai_analysis_graph


# ============================================================================
# 기존 함수들 (하위 호환성 유지)
# ============================================================================

def save_strategy_decision(decision: AIStrategyDecision, fred_signals: Dict, economic_news: Dict) -> bool:
    """전략 결정 결과를 DB에 저장"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # analysis_summary에 reasoning 포함
            analysis_summary_with_reasoning = decision.analysis_summary
            if decision.reasoning:
                analysis_summary_with_reasoning += f"\n\n판단 근거:\n{decision.reasoning}"
            
            # MP ID로 자산 배분 비율 계산
            target_allocation = decision.get_target_allocation()
            
            # mp_id와 sub_mp를 포함한 저장 데이터 준비
            save_data = {
                "mp_id": decision.mp_id,
                "target_allocation": target_allocation.model_dump()
            }
            
            # Sub-MP 정보 추가
            if decision.sub_mp:
                save_data["sub_mp"] = {
                    "stocks": decision.sub_mp.stocks_sub_mp,
                    "bonds": decision.sub_mp.bonds_sub_mp,
                    "alternatives": decision.sub_mp.alternatives_sub_mp,
                    "reasoning": decision.sub_mp.reasoning
                }
            
            cursor.execute("""
                INSERT INTO ai_strategy_decisions (
                    decision_date,
                    analysis_summary,
                    target_allocation,
                    recommended_stocks,
                    quant_signals,
                    qual_sentiment,
                    account_pnl
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                analysis_summary_with_reasoning,
                json.dumps(save_data),  # mp_id와 target_allocation을 함께 저장
                json.dumps(decision.recommended_stocks.model_dump()) if decision.recommended_stocks else None,
                json.dumps(fred_signals) if fred_signals else None,
                json.dumps(economic_news) if economic_news else None,
                None  # account_pnl은 더 이상 사용하지 않음
            ))
            
            conn.commit()
            logger.info(f"전략 결정 결과 저장 완료: MP={decision.mp_id}")
            return True
            
    except Exception as e:
        logger.error(f"전략 결정 저장 실패: {e}", exc_info=True)
        return False


def run_ai_analysis():
    """AI 분석 실행 (스케줄러용) - LangGraph 기반"""
    try:
        logger.info("=" * 60)
        logger.info("AI 전략 분석 시작")
        logger.info("=" * 60)
        
        # LangGraph 워크플로우 실행
        graph = get_ai_analysis_graph()
        initial_state: AIAnalysisState = {
            "fred_signals": None,
            "economic_news": None,
            "news_summary": None,
            "decision": None,
            "error": None,
            "success": False
        }
        
        final_state = graph.invoke(initial_state)
        
        success = final_state.get("success", False)
        error = final_state.get("error")
        
        if error:
            logger.error(f"워크플로우 실행 중 오류: {error}")
        
        return success
        
    except Exception as e:
        logger.error(f"AI 분석 실행 실패: {e}", exc_info=True)
        logger.error(f"에러 타입: {type(e).__name__}")
        import traceback
        logger.error(f"전체 traceback:\n{traceback.format_exc()}")
        return False
