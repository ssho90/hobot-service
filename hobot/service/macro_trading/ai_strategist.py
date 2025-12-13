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


# ============================================================================
# 세부 자산군 모델 (Sub-Models) 정의
# ============================================================================

SUB_PORTFOLIO_MODELS = {
    "Stocks": {
        "Eq-A": {
            "name": "Aggressive (성장 공격형)",
            "description": "금리 인하기, 유동성 풍부, Risk-On. (기술주 50% / S&P 30% / 배당 20%)",
            "composition": [
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "weight": 0.5},
                {"ticker": "360750", "name": "TIGER 미국S&P500", "weight": 0.3},
                {"ticker": "458730", "name": "TIGER 미국배당다우존스", "weight": 0.2}
            ]
        },
        "Eq-N": {
            "name": "Neutral (시장 중립형)",
            "description": "방향성 불확실, 일반적인 상승장. (S&P 50% / 나스닥 30% / 배당 20%)",
            "composition": [
                {"ticker": "360750", "name": "TIGER 미국S&P500", "weight": 0.5},
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "weight": 0.3},
                {"ticker": "458730", "name": "TIGER 미국배당다우존스", "weight": 0.2}
            ]
        },
        "Eq-D": {
            "name": "Defensive (방어형)",
            "description": "고금리 장기화, 경기 침체 우려. (배당 50% / S&P 30% / 나스닥 20%)",
            "composition": [
                {"ticker": "458730", "name": "TIGER 미국배당다우존스", "weight": 0.5},
                {"ticker": "360750", "name": "TIGER 미국S&P500", "weight": 0.3},
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "weight": 0.2}
            ]
        }
    },
    "Bonds": {
        "Bnd-L": {
            "name": "Long Duration (장기채 베팅)",
            "description": "금리 인하 확실시. (미국장기채 80% / 한국단기채 20%)",
            "composition": [
                {"ticker": "448430", "name": "ACE 미국30년국채액티브(H)", "weight": 0.8},
                {"ticker": "130730", "name": "TIGER CD금리투자KIS", "weight": 0.2}
            ]
        },
        "Bnd-N": {
            "name": "Balanced (균형)",
            "description": "금리 동결 또는 완만한 인하. (미국장기채 50% / 한국단기채 50%)",
            "composition": [
                {"ticker": "448430", "name": "ACE 미국30년국채액티브(H)", "weight": 0.5},
                {"ticker": "130730", "name": "TIGER CD금리투자KIS", "weight": 0.5}
            ]
        },
        "Bnd-S": {
            "name": "Short Duration (단기채 방어)",
            "description": "금리 인상기, 인플레이션 쇼크. (한국단기채 80% / 미국장기채 20%)",
            "composition": [
                {"ticker": "130730", "name": "TIGER CD금리투자KIS", "weight": 0.8},
                {"ticker": "448430", "name": "ACE 미국30년국채액티브(H)", "weight": 0.2}
            ]
        }
    },
    "Alternatives": {
        "Alt-I": {
            "name": "Inflation Fighter (인플레 방어)",
            "description": "스태그플레이션, 물가 급등. (금 80% / 달러 20%)",
            "composition": [
                {"ticker": "132030", "name": "KODEX 골드선물(H)", "weight": 0.8},
                {"ticker": "138230", "name": "KODEX 미국달러선물", "weight": 0.2}
            ]
        },
        "Alt-C": {
            "name": "Crisis Hedge (위기 방어)",
            "description": "금융 위기, 시스템 리스크. (달러 70% / 금 30%)",
            "composition": [
                {"ticker": "138230", "name": "KODEX 미국달러선물", "weight": 0.7},
                {"ticker": "132030", "name": "KODEX 골드선물(H)", "weight": 0.3}
            ]
        }
    },
    "Cash": {
         "Cash-N": {
            "name": "Cash Normal",
            "description": "현금성 자산",
            "composition": [
                {"ticker": "130730", "name": "TIGER CD금리투자KIS", "weight": 1.0}
            ]
        }
    }
}


def get_model_portfolio_allocation(mp_id: str) -> Optional[Dict[str, float]]:
    """MP ID에 해당하는 자산 배분 비율 반환"""
    mp = MODEL_PORTFOLIOS.get(mp_id)
    if mp:
        return mp["allocation"].copy()
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


class SubModelSelection(BaseModel):
    """자산군별 세부 모델 선택"""
    Stocks: str = Field(..., description="주식 서브 모델 ID (예: Eq-A)")
    Bonds: str = Field(..., description="채권 서브 모델 ID (예: Bnd-N)")
    Alternatives: str = Field(..., description="대체자산 서브 모델 ID (예: Alt-I)")
    Cash: str = Field(default="Cash-N", description="현금 모델 ID")


class AIStrategyDecision(BaseModel):
    """AI 전략 결정 결과 모델"""
    analysis_summary: str = Field(..., description="AI 분석 요약")
    mp_id: str = Field(..., description="선택된 모델 포트폴리오 ID (MP-1 ~ MP-5)")
    sub_models: SubModelSelection = Field(..., description="자산군별 선택된 세부 전략 모델")
    reasoning: str = Field(..., description="판단 근거")
    recommended_stocks: Optional[Dict[str, List[Dict]]] = Field(default=None, description="최종 계산된 포트폴리오 (자동 계산됨)")
    
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
        
        # 추가 지표: Core PCE, CPI, 실업률, 비농업 고용의 지난 10개 데이터
        fred_collector = get_fred_collector()
        inflation_employment_data = {}
        
        # Core PCE (PCEPILFE - Personal Consumption Expenditures Price Index, Less Food and Energy)
        try:
            pcepilfe_data = fred_collector.get_latest_data("PCEPILFE", days=365)
            if len(pcepilfe_data) > 0:
                # 최근 10개 데이터 (날짜와 값)
                latest_10 = pcepilfe_data.tail(10)
                inflation_employment_data["core_pce"] = [
                    {"date": str(date), "value": float(value)}
                    for date, value in zip(latest_10.index, latest_10.values)
                ]
        except Exception as e:
            logger.warning(f"Core PCE 데이터 수집 실패: {e}")
            inflation_employment_data["core_pce"] = []
        
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


def get_latest_decision() -> Dict[str, Any]:
    """DB에서 가장 최근의 전략 결정 조회 (MP ID 및 Sub-Models)"""
    try:
        from service.database.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT target_allocation
                FROM ai_strategy_decisions
                ORDER BY decision_date DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if not row:
                return None
                
            # JSON 파싱
            target_alloc_json = row['target_allocation']
            target_data = json.loads(target_alloc_json) if isinstance(target_alloc_json, str) else target_alloc_json
            
            # 이전 MP ID 추출
            prev_mp_id = target_data.get('mp_id')
            
            # 이전 Sub-Models 추출
            prev_sub_models = target_data.get('sub_models', {
                "Stocks": "Eq-N", "Bonds": "Bnd-N", "Alternatives": "Alt-I", "Cash": "Cash-N"
            })
            
            return {
                "mp_id": prev_mp_id,
                "sub_models": prev_sub_models
            }
            
    except Exception as e:
        logger.warning(f"이전 전략 조회 실패: {e}")
        return None


def summarize_fred_signals(fred_signals: Dict) -> str:
    """FRED 시그널을 텍스트로 요약"""
    if not fred_signals:
        return "FRED 시그널 데이터 없음"
        
    fred_summary = "=== FRED 정량 시그널 (가장 신뢰도 높음) ===\n"
    
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
    
    # 물가 및 고용 지표 (지난 10개 데이터 중 최근값)
    inflation_employment = fred_signals.get('inflation_employment_data', {})
    if inflation_employment:
        fred_summary += "\n[주요 지표 최근 동향]\n"
        
        # Core PCE
        core_pce = inflation_employment.get('core_pce', [])
        if core_pce:
            latest = core_pce[-1]
            fred_summary += f"Core PCE: {latest['value']:.2f} ({latest['date']})\n"
        
        # CPI
        cpi = inflation_employment.get('cpi', [])
        if cpi:
            latest = cpi[-1]
            fred_summary += f"CPI: {latest['value']:.2f} ({latest['date']})\n"
        
        # 실업률
        unrate = inflation_employment.get('unemployment_rate', [])
        if unrate:
            latest = unrate[-1]
            fred_summary += f"실업률: {latest['value']:.2f}% ({latest['date']})\n"
            
        # 비농업 고용
        payroll = inflation_employment.get('nonfarm_payroll', [])
        if payroll:
            latest = payroll[-1]
            fred_summary += f"비농업 고용: {latest['value']:,.0f} ({latest['date']})\n"

    return fred_summary


def create_mp_analysis_prompt(fred_summary: str, news_summary: str, prev_mp_id: str) -> str:
    """1단계: Main MP 결정을 위한 프롬프트 생성"""
    mp_info = "\n=== 모델 포트폴리오 (MP) 시나리오 ===\n"
    mp_info += "현재 거시경제 국면을 분석하여 다음 5가지 모델 포트폴리오 중 하나를 선택하세요:\n\n"
    for mp_id, mp in MODEL_PORTFOLIOS.items():
        mp_info += f"{mp_id}: {mp['name']}\n"
        mp_info += f"  - 특징: {mp['description']}\n"
        mp_info += f"  - 핵심 전략: {mp['strategy']}\n"
        mp_info += f"  - 자산 배분: 주식 {mp['allocation']['Stocks']}% / 채권 {mp['allocation']['Bonds']}% / 대체투자 {mp['allocation']['Alternatives']}% / 현금 {mp['allocation']['Cash']}%\n\n"

    prev_state_context = ""
    if prev_mp_id:
        prev_state_context = f"""
        [현재 상태]
        - 직전 포트폴리오 모델: {prev_mp_id} ({MODEL_PORTFOLIOS.get(prev_mp_id, {}).get('name', 'N/A')})
        
        [중요 지침 - 관성(Inertia) 유지]
        - 현재 경제 지표가 직전 상태({prev_mp_id})와 크게 다르지 않다면, 불필요한 매매 비용을 줄이기 위해 기존 모델을 **유지**하세요.
        - 모델을 변경해야 한다면, 경제 상황이 확실하게 변했다는 명확한 근거가 있어야 합니다.
        """
    else:
        prev_state_context = "[현재 상태] 초기 실행입니다."

    return f"""당신은 거시경제 자산배분 전문가입니다.
    
    [입력 데이터]
    {fred_summary}
    
    {news_summary}
    
    {prev_state_context}
    
    [사용 가능한 모델 포트폴리오(MP)]
    {mp_info}
    
    다음 형식의 JSON으로만 응답하세요:
    {{
        "analysis_summary": "분석 요약 (한국어, 200자 내외)",
        "mp_id": "MP-3",
        "reasoning": "판단 근거 (변경 시 변경 이유 강조, 500자 내외)"
    }}
    """


def create_sub_model_analysis_prompt(fred_summary: str, selected_mp_id: str, prev_sub_models: Dict) -> str:
    """2단계: Sub-Models 결정을 위한 프롬프트 생성"""
    sub_model_info = "\n=== 자산군별 세부 모델 (Sub-Models) ===\n"
    for asset, models in SUB_PORTFOLIO_MODELS.items():
        if asset == 'Cash': continue
        sub_model_info += f"\n[{asset} Models]\n"
        for mid, m in models.items():
            sub_model_info += f"  - {mid}: {m['name']} ({m['description']})\n"

    prev_sub_context = ""
    if prev_sub_models:
        prev_sub_context = f"""
        [직전 세부 모델]
        - Stocks: {prev_sub_models.get('Stocks', 'N/A')}
        - Bonds: {prev_sub_models.get('Bonds', 'N/A')}
        - Alternatives: {prev_sub_models.get('Alternatives', 'N/A')}
        
        [지침]
        - 세부 모델 또한 잦은 교체는 좋지 않습니다.
        - 현재 선택된 Main MP는 "{selected_mp_id}" 입니다. 이 MP의 전략 방향과 경제 데이터를 고려하여 세부 모델을 결정하세요.
        - 특별한 이유가 없다면 이전 세부 모델을 유지하는 것을 우선 고려하세요.
        """

    return f"""선택된 자산배분 모델(MP)인 "{selected_mp_id}" 내에서 실행할 세부 전술(Sub-Model)을 결정하세요.

    [입력 데이터]
    {fred_summary}
    
    {prev_sub_context}

    [선택 가능한 세부 모델]
    {sub_model_info}

    다음 형식의 JSON으로만 응답하세요:
    {{
        "Stocks": "Eq-N",
        "Bonds": "Bnd-N",
        "Alternatives": "Alt-I",
        "reasoning_details": "세부 모델 선택 이유 요약"
    }}
    """


def invoke_llm_with_retry(prompt: str, service_name: str) -> Dict[str, Any]:
    """LLM 호출 및 JSON 파싱 (재시도 로직 포함)"""
    from service.macro_trading.config.config_loader import get_config
    config = get_config()
    model_name = config.llm.model
    
    logger.info(f"Gemini {model_name} 호출 ({service_name})...")
    llm = llm_gemini_pro(model=model_name)
    
    with track_llm_call(
        model_name=model_name,
        provider="Google",
        service_name=service_name,
        request_prompt=prompt
    ) as tracker:
        response = llm.invoke(prompt)
        tracker.set_response(response)
        
    # 응답 파싱
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
    
    response_text = response_text.strip()
    
    # 마크다운 코드 블록 제거
    if response_text.startswith('```'):
        lines = response_text.split('\n')
        if len(lines) > 1:
            if lines[-1].strip().startswith('```'):
                response_text = '\n'.join(lines[1:-1])
            else:
                response_text = '\n'.join(lines[1:])

    # JSON 파싱
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        import re
        json_match = re.search(r'\{[\s\S]*\}', response_text, re.MULTILINE)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError(f"JSON 파싱 실패. 응답: {response_text[:200]}")


def analyze_and_decide(fred_signals: Optional[Dict] = None, economic_news: Optional[Dict] = None) -> Optional[AIStrategyDecision]:
    """AI 분석 및 전략 결정 (2단계: Main MP -> Sub-Models)"""
    try:
        logger.info("AI 전략 분석 시작")
        
        # 1. 데이터 수집
        if fred_signals is None:
            logger.info("FRED 시그널 수집 중...")
            fred_signals = collect_fred_signals()
        
        if economic_news is None:
            logger.info("경제 뉴스 수집 중...")
            economic_news = collect_economic_news(days=20)
            
        # 2. 데이터 요약
        fred_summary = summarize_fred_signals(fred_signals)
        
        news_summary = "=== 경제 뉴스 (보조 지표) ===\n"
        if economic_news and economic_news.get('news_summary'):
            news_summary += economic_news['news_summary']
        else:
            news_summary += "뉴스 요약 없음"
            
        # 3. 이전 상태 조회
        prev_state = get_latest_decision()
        prev_mp_id = prev_state['mp_id'] if prev_state else None
        prev_sub_models = prev_state['sub_models'] if prev_state else {}
        
        # =========================================================
        # Step 1: Main MP 결정
        # =========================================================
        logger.info(f"1단계 분석: Main MP 결정 (이전: {prev_mp_id})")
        
        prompt_step1 = create_mp_analysis_prompt(fred_summary, news_summary, prev_mp_id)
        result_step1 = invoke_llm_with_retry(prompt_step1, "ai_strategist_step1_mp")
        
        mp_id = result_step1.get('mp_id')
        mp_reasoning = result_step1.get('reasoning')
        
        if not mp_id or mp_id not in MODEL_PORTFOLIOS:
            raise ValueError(f"유효하지 않은 MP ID: {mp_id}")
            
        logger.info(f"Main MP 결정 완료: {mp_id}")

        # =========================================================
        # Step 2: Sub-Models 결정
        # =========================================================
        logger.info(f"2단계 분석: Sub-Models 결정 (MP: {mp_id})")
        
        prompt_step2 = create_sub_model_analysis_prompt(fred_summary, mp_id, prev_sub_models)
        result_step2 = invoke_llm_with_retry(prompt_step2, "ai_strategist_step2_sub")
        
        sub_models_data = {
            "Stocks": result_step2.get('Stocks'),
            "Bonds": result_step2.get('Bonds'),
            "Alternatives": result_step2.get('Alternatives'),
            "Cash": "Cash-N" # 현금은 고정
        }
        
        sub_reasoning = result_step2.get('reasoning_details', '')
        
        # Sub-Model ID 검증
        for asset, mid in sub_models_data.items():
            if asset in SUB_PORTFOLIO_MODELS and mid not in SUB_PORTFOLIO_MODELS[asset]:
                 # LLM이 없는 ID를 뱉으면 기본값(첫번째)으로 대체하거나 에러 처리
                 # 여기서는 로그 남기고 첫번째 키로 대체
                 first_key = list(SUB_PORTFOLIO_MODELS[asset].keys())[0]
                 logger.warning(f"잘못된 Sub-Model ID: {asset}={mid}, 기본값({first_key})으로 대체합니다.")
                 sub_models_data[asset] = first_key

        # =========================================================
        # 결과 통합 및 최종 포트폴리오 계산
        # =========================================================
        
        final_portfolio = {}
        target_allocation = get_model_portfolio_allocation(mp_id) # e.g. {"Stocks": 50.0, ...}
        
        # 각 자산군별 종목 비중 계산
        for asset_class, sub_model_id in sub_models_data.items():
            if asset_class not in target_allocation:
                continue
                
            asset_total_weight = target_allocation[asset_class] # e.g. 50.0 (%)
            
            # 자산군 비중이 0이면 스킵
            if asset_total_weight <= 0:
                final_portfolio[asset_class] = []
                continue
                
            model_info = SUB_PORTFOLIO_MODELS[asset_class][sub_model_id]
            composition = model_info['composition']
            
            asset_portfolio = []
            for item in composition:
                # item['weight']는 해당 서브모델 내 비중 (0.0 ~ 1.0)
                # 최종 비중은 자산군 비중을 고려하지 않고, 일단 서브모델 내 비중만 저장해도 되지만,
                # 여기서는 포트폴리오 구성을 위해 그대로 저장
                asset_portfolio.append({
                    "ticker": item['ticker'],
                    "name": item['name'],
                    "weight": item['weight'], # 서브모델 내 비중
                    "category": model_info['name'] # 카테고리 정보로 모델명 사용
                })
            
            final_portfolio[asset_class] = asset_portfolio

        decision = AIStrategyDecision(
            analysis_summary=result_step1.get('analysis_summary'),
            mp_id=mp_id,
            sub_models=SubModelSelection(**sub_models_data),
            reasoning=f"{mp_reasoning}\n\n[세부 전략 근거]\n{sub_reasoning}",
            recommended_stocks=final_portfolio
        )
        
        return decision

    except Exception as e:
        logger.error(f"AI 분석 실패: {e}", exc_info=True)
        return None


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
        
        decision = analyze_and_decide(fred_signals=fred_signals, economic_news=economic_news)
        
        if not decision:
            logger.error("AI 분석 실패: analyze_and_decide()가 None 반환")
            return {
                **state,
                "decision": None,
                "error": "AI 분석 실패: analyze_and_decide()가 None 반환"
            }
        
        return {
            **state,
            "decision": decision
        }
    except Exception as e:
        logger.error(f"AI 분석 실패: {e}", exc_info=True)
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
            
            # mp_id를 포함한 저장 데이터 준비
            # DB에 mp_id 컬럼이 있으면 저장, 없으면 target_allocation에 포함
            save_data = {
                "mp_id": decision.mp_id,
                "target_allocation": target_allocation.model_dump(),
                "sub_models": decision.sub_models.model_dump()
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
                json.dumps(decision.recommended_stocks) if decision.recommended_stocks else None,
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
