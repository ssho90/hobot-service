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

from service.llm import llm_gemini_pro, llm_gemini_flash
from service.database.db import get_db_connection
from service.llm_monitoring import track_llm_call

logger = logging.getLogger(__name__)


# ============================================================================
# 모델 포트폴리오 (MP) 시나리오 정의
# ============================================================================

# DB에서 로드된 포트폴리오 캐시
_MODEL_PORTFOLIOS_CACHE = None
_SUB_MODEL_PORTFOLIOS_CACHE = None


def _load_model_portfolios_from_db() -> Dict[str, Dict]:
    """DB에서 모델 포트폴리오 로드
    
    Returns:
        Dict[str, Dict]: 모델 포트폴리오 딕셔너리
        
    Raises:
        ValueError: DB에서 포트폴리오를 로드할 수 없거나 데이터가 없는 경우
    """
    global _MODEL_PORTFOLIOS_CACHE
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, mp_id, name, description, strategy, 
                       stocks_allocation, bonds_allocation, 
                       alternatives_allocation, cash_allocation,
                       display_order, is_active, updated_at
                FROM model_portfolios
                WHERE is_active = TRUE
                ORDER BY display_order, id
            """)
            rows = cursor.fetchall()
            
            result = {}
            for row in rows:
                stocks_allocation = row.get('stocks_allocation') or 0
                bonds_allocation = row.get('bonds_allocation') or 0
                alternatives_allocation = row.get('alternatives_allocation') or 0
                cash_allocation = row.get('cash_allocation') or 0
                
                # mp_id를 키로 사용 (예: "MP-1", "MP-2")
                mp_id = row.get('mp_id') or str(row['id'])
                
                result[mp_id] = {
                    'id': row['id'],
                    'mp_id': mp_id,
                    'name': row['name'],
                    'description': row['description'],
                    'strategy': row['strategy'],
                    'updated_at': row['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if row.get('updated_at') else None,
                    'allocation': {
                        'Stocks': float(stocks_allocation) if stocks_allocation is not None else 0.0,
                        'Bonds': float(bonds_allocation) if bonds_allocation is not None else 0.0,
                        'Alternatives': float(alternatives_allocation) if alternatives_allocation is not None else 0.0,
                        'Cash': float(cash_allocation) if cash_allocation is not None else 0.0
                    }
                }
            
            if not result:
                error_msg = "DB에서 활성화된 모델 포트폴리오를 찾을 수 없습니다. 포트폴리오 데이터가 필요합니다."
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            _MODEL_PORTFOLIOS_CACHE = result
            return result
    except ValueError:
        raise  # ValueError는 그대로 전파
    except Exception as e:
        error_msg = f"DB에서 모델 포트폴리오 로드 실패: {e}. 포트폴리오 데이터가 없으면 LLM 분석을 수행할 수 없습니다."
        logger.error(error_msg, exc_info=True)
        raise ValueError(error_msg) from e


def _load_sub_model_portfolios_from_db() -> Dict[str, Dict]:
    """DB에서 Sub-MP 포트폴리오 로드
    
    Returns:
        Dict[str, Dict]: Sub-MP 포트폴리오 딕셔너리
        
    Raises:
        ValueError: DB에서 포트폴리오를 로드할 수 없거나 데이터가 없는 경우
    """
    global _SUB_MODEL_PORTFOLIOS_CACHE
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # sub_portfolio_models 테이블 사용
            cursor.execute("""
                SELECT id, sub_model_id, name, description, asset_class, display_order, is_active, updated_at
                FROM sub_portfolio_models
                WHERE is_active = TRUE
                ORDER BY asset_class, display_order, id
            """)
            rows = cursor.fetchall()
            
            result = {}
            for row in rows:
                # sub_model_id를 키로 사용 (예: "Eq-D", "Bnd-L", "Alt-I")
                sub_model_id = row.get('sub_model_id')
                
                # ETF 상세 정보 로드 (sub_portfolio_compositions 테이블)
                # 외래키 컬럼: sub_portfolio_model_id
                # category 컬럼이 없으므로 ticker나 name을 category로 사용
                cursor.execute("""
                    SELECT ticker, name, weight, display_order
                    FROM sub_portfolio_compositions
                    WHERE sub_portfolio_model_id = %s
                    ORDER BY display_order
                """, (row['id'],))
                etf_rows = cursor.fetchall()
                
                etf_details = []
                allocation = {}
                for etf_row in etf_rows:
                    ticker = etf_row.get('ticker') or ""
                    name = etf_row.get('name') or ""
                    weight = etf_row.get('weight') or 0
                    
                    # category 컬럼이 없으므로 name의 첫 단어를 category로 사용
                    category = name.split()[0] if name else ""
                    
                    etf_details.append({
                        'category': category,
                        'ticker': ticker,
                        'name': name,
                        'weight': float(weight) if weight is not None else 0.0
                    })
                    if category:
                        allocation[category] = float(weight) if weight is not None else 0.0
                
                result[sub_model_id] = {
                    'id': row['id'],
                    'sub_model_id': sub_model_id,
                    'name': row['name'],
                    'description': row['description'],
                    'asset_class': row['asset_class'],
                    'updated_at': row['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if row.get('updated_at') else None,
                    'allocation': allocation,
                    'etf_details': etf_details
                }
            
            if not result:
                error_msg = "DB에서 활성화된 Sub-MP 포트폴리오를 찾을 수 없습니다. 포트폴리오 데이터가 필요합니다."
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            _SUB_MODEL_PORTFOLIOS_CACHE = result
            return result
    except ValueError:
        raise  # ValueError는 그대로 전파
    except Exception as e:
        error_msg = f"DB에서 Sub-MP 포트폴리오 로드 실패: {e}. 포트폴리오 데이터가 없으면 LLM 분석을 수행할 수 없습니다."
        logger.error(error_msg, exc_info=True)
        raise ValueError(error_msg) from e


def get_model_portfolios() -> Dict[str, Dict]:
    """모델 포트폴리오 조회 (DB에서 로드, 캐시 사용)
    
    Returns:
        Dict[str, Dict]: 모델 포트폴리오 딕셔너리
        
    Raises:
        ValueError: DB에서 포트폴리오를 로드할 수 없거나 데이터가 없는 경우
    """
    if _MODEL_PORTFOLIOS_CACHE is None:
        return _load_model_portfolios_from_db()
    return _MODEL_PORTFOLIOS_CACHE


def get_sub_model_portfolios() -> Dict[str, Dict]:
    """Sub-MP 포트폴리오 조회 (DB에서 로드, 캐시 사용)
    
    Returns:
        Dict[str, Dict]: Sub-MP 포트폴리오 딕셔너리
        
    Raises:
        ValueError: DB에서 포트폴리오를 로드할 수 없거나 데이터가 없는 경우
    """
    if _SUB_MODEL_PORTFOLIOS_CACHE is None:
        return _load_sub_model_portfolios_from_db()
    return _SUB_MODEL_PORTFOLIOS_CACHE


def refresh_portfolio_cache():
    """포트폴리오 캐시 갱신"""
    global _MODEL_PORTFOLIOS_CACHE, _SUB_MODEL_PORTFOLIOS_CACHE
    _MODEL_PORTFOLIOS_CACHE = None
    _SUB_MODEL_PORTFOLIOS_CACHE = None
    get_model_portfolios()
    get_sub_model_portfolios()


# 하위 호환성을 위한 변수 (더 이상 사용하지 않음)
# 주의: 직접 접근 대신 get_model_portfolios() / get_sub_model_portfolios() 함수 사용
# DEFAULT 포트폴리오 정의는 삭제되었으며, 모든 데이터는 DB에서 로드됩니다.
MODEL_PORTFOLIOS = None  # 사용하지 않음 (get_model_portfolios() 사용)
SUB_MODEL_PORTFOLIOS = None  # 사용하지 않음 (get_sub_model_portfolios() 사용)


def get_model_portfolio_allocation(mp_id: str) -> Optional[Dict[str, float]]:
    """MP ID에 해당하는 자산 배분 비율 반환"""
    portfolios = get_model_portfolios()
    mp = portfolios.get(mp_id)
    if mp:
        return mp["allocation"].copy()
    return None


# ============================================================================
# Sub-MP (자산군별 세부 모델) 정의
# ============================================================================


def get_sub_model_portfolio_allocation(sub_mp_id: str) -> Optional[Dict[str, float]]:
    """Sub-MP ID에 해당하는 자산군 내 배분 비율 반환"""
    portfolios = get_sub_model_portfolios()
    sub_mp = portfolios.get(sub_mp_id)
    if sub_mp:
        return sub_mp["allocation"].copy()
    return None


def get_sub_models_by_asset_class(asset_class: str) -> Dict[str, Dict]:
    """자산군별 Sub-MP 목록 반환"""
    portfolios = get_sub_model_portfolios()
    result = {}
    for sub_mp_id, sub_mp in portfolios.items():
        if sub_mp.get("asset_class") == asset_class:
            result[sub_mp_id] = sub_mp
    return result


def get_sub_mp_etf_details(sub_mp_id: str) -> Optional[List[Dict]]:
    """Sub-MP ID에 해당하는 ETF 세부 정보 반환"""
    portfolios = get_sub_model_portfolios()
    sub_mp = portfolios.get(sub_mp_id)
    if sub_mp:
        return sub_mp.get("etf_details", []).copy()
    return None


def get_sub_mp_details(sub_mp_data: Optional[Dict[str, str]]) -> Optional[Dict[str, Dict]]:
    """자산군별 Sub-MP ID 목록에서 세부 종목 정보를 구성 (cash 포함, 미지정 시 cash 기본값 사용)"""
    if not sub_mp_data:
        return None

    sub_portfolios = get_sub_model_portfolios()
    sub_mp_details: Dict[str, Dict] = {}

    # stocks, bonds, alternatives, cash 모두 처리
    for asset_key in ("stocks", "bonds", "alternatives", "cash"):
        sub_mp_id = sub_mp_data.get(asset_key)

        if not sub_mp_id:
            continue

        etf_details = get_sub_mp_etf_details(sub_mp_id)
        if not etf_details:
            continue

        sub_mp_info = sub_portfolios.get(sub_mp_id, {})
        sub_mp_details[asset_key] = {
            "sub_mp_id": sub_mp_id,
            "sub_mp_name": sub_mp_info.get("name", ""),
            "sub_mp_description": sub_mp_info.get("description", ""),
            "updated_at": sub_mp_info.get("updated_at"),
            "etf_details": etf_details,
        }

    return sub_mp_details or None


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
    cash_sub_mp: Optional[str] = Field(default=None, description="현금 Sub-MP ID (Cash 계열)")
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
        
        # Dashboard Data 수집
        dashboard_data = calculator.get_macro_dashboard_indicators()
        
        # CNN Fear & Greed Index (fear_and_greed 패키지 사용)
        try:
            import fear_and_greed
            index_data = fear_and_greed.get()
            
            dashboard_data["sentiment"]["cnn_index"] = {
                "value": float(index_data.value),
                "status": index_data.description
            }
            logger.info(f"CNN Fear & Greed Index 수집 성공: {index_data.value} ({index_data.description})")
            
        except Exception as e:
            logger.warning(f"CNN Fear & Greed Index 수집 실패: {e}")
            # 실패 시 기존 Placeholder 유지 (quant_signals.py에서 설정됨)
        
        return_data = {
            "yield_curve_spread_trend": signals.get("yield_curve_spread_trend"),
            "real_interest_rate": signals.get("real_interest_rate"),
            "taylor_rule_signal": signals.get("taylor_rule_signal"),
            "net_liquidity": signals.get("net_liquidity"),
            "high_yield_spread": signals.get("high_yield_spread"),
            "additional_indicators": additional_indicators,
            "inflation_employment_data": inflation_employment_data,
            "dashboard_data": dashboard_data
        }
        
        logger.info(f"FRED Signals Collected: {json.dumps(return_data, default=str, indent=2, ensure_ascii=False)}")
        
        return return_data
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
        for idx, news in enumerate(news_list[:100], 1):  # 최대 100개까지만 처리
            title = news.get('title_ko') or news.get('title', 'N/A')
            description = news.get('description_ko') or news.get('description', '')
            country = news.get('country_ko') or news.get('country', 'N/A')
            published_at = news.get('published_at', 'N/A')
            
            news_text += f"[{idx}] [{country}] {published_at}\n"
            news_text += f"제목: {title}\n"
            if description:
                news_text += f"내용: {description[:550]} ...\n"  # 최대 550자만
            news_text += "\n"
        
        # LLM 프롬프트 생성
        prompt = f"""당신은 거시경제 전문가입니다. 다음은 최근 {', '.join(target_countries)} 국가의 경제 뉴스입니다.

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

한국어로 요약해주세요 (1500자 이내).
"""
        
        # gemini-3.0-pro-preview 사용
        logger.info("Gemini 3.0 Pro로 뉴스 요약 중...")
        llm = llm_gemini_pro()
        
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



def generate_market_briefing(summary_text: str) -> str:
    """
    gemini-2.5-flash를 사용하여 Market Briefing용 2차 요약 생성
    """
    try:
        if not summary_text:
            return ""
            
        logger.info("Market Briefing용 2차 요약 생성 중...")
        llm = llm_gemini_flash(model="gemini-2.5-flash")
        
        prompt = f"""당신은 글로벌 금융 시장 뉴스 에디터입니다. 
아래의 거시경제 분석 리포트를 바탕으로, 일반 투자자가 Dashboard에서 빠르게 읽을 수 있는 3~4문장의 'Market Briefing'을 작성해주세요.

[지침]
1. 핵심 트렌드, 주요 지표 변화, 시장 이슈 위주로 요약하세요.
2. 톤앤매너: 전문적이지만 이해하기 쉽게, 객관적인 어조 유지 (존댓말).
3. 분량: 한국어 200~300자 내외.
4. 첫 문장은 전체 시장 분위기를 한마디로 요약하는 것이 좋습니다.

[분석 리포트]
{summary_text}

[Market Briefing]
"""

        with track_llm_call(
            model_name="gemini-2.5-flash",
            provider="Google",
            service_name="market_briefing_generation",
            request_prompt=prompt
        ) as tracker:
            response = llm.invoke(prompt)
            tracker.set_response(response)
            
        if hasattr(response, 'content'):
            return str(response.content)
        elif hasattr(response, 'text'):
            return response.text
        return str(response)
        
    except Exception as e:
        logger.error(f"Market Briefing 생성 실패: {e}", exc_info=True)
        return ""


def collect_economic_news(days: int = 20, include_summary: bool = True) -> Optional[Dict[str, Any]]:
    """
    경제 뉴스 수집 및 요약 (캐싱 적용)
    
    1. 최근 12시간 내의 market_news_summaries가 있으면 그것을 반환 (뉴스 수집 생략)
    2. 없으면 economic_news 테이블에서 뉴스 수집 후 LLM 요약 및 Briefing 생성하여 저장
    
    Args:
        days: 수집할 기간 (일 단위, 기본값: 20일)
        include_summary: LLM 요약 포함 여부 (기본값: True)
    """
    try:
        # AI 분석에 사용할 국가 목록
        target_countries = ['Crypto', 'Commodity', 'Euro Area', 'China', 'United States']
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 캐시 확인 (12시간 이내)
            if include_summary:
                try:
                    cursor.execute("""
                        SELECT summary_text, briefing_text, created_at 
                        FROM market_news_summaries 
                        WHERE created_at >= NOW() - INTERVAL 12 HOUR
                        ORDER BY created_at DESC 
                        LIMIT 1
                    """)
                    cached_row = cursor.fetchone()
                    
                    if cached_row:
                        summary_text = cached_row['summary_text']
                        briefing_text = cached_row['briefing_text']
                        created_at = cached_row['created_at']
                        
                        logger.info(f"✅ 캐시된 뉴스 요약 사용 (생성일: {created_at})")
                        
                        # 뉴스 목록은 캐시 사용 시 빈 리스트로 반환 (성능 최적화)
                        return {
                            "total_count": 0,
                            "days": days,
                            "target_countries": target_countries,
                            "news": [],
                            "news_summary": summary_text,
                            "briefing_text": briefing_text or "",  # Briefing text 추가 반환
                            "cached": True
                        }
                except Exception as e:
                    logger.warning(f"뉴스 요약 캐시 확인 중 오류 (무시하고 진행): {e}")

            # 2. 캐시 없으면 뉴스 수집 및 요약 실행
            logger.info("캐시된 요약 없음. 뉴스 수집 및 분석 시작...")
            
            # 지난 N일 기준으로 cutoff_time 설정
            cutoff_time = datetime.now() - timedelta(days=days)
            
            cursor.execute("""
                SELECT 
                    id, title, title_ko, link, country, country_ko, 
                    category, category_ko, description, description_ko, 
                    published_at, collected_at, source
                FROM economic_news
                WHERE published_at >= %s
                  AND country IN (%s, %s, %s, %s, %s)
                ORDER BY published_at DESC
            """, (cutoff_time, *target_countries))
            
            news = cursor.fetchall()
            
            # datetime 객체를 문자열로 변환
            for item in news:
                for date_field in ['published_at', 'collected_at']:
                    if item.get(date_field):
                        item[date_field] = item[date_field].strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(f"경제 뉴스 수집 완료: 지난 {days}일간 {len(news)}개의 뉴스")
            
            # LLM 요약 및 Briefing 생성
            news_summary = None
            briefing_text = ""
            
            if include_summary and news:
                news_summary = summarize_news_with_llm(news, target_countries)
                
                if news_summary:
                    # Briefing 생성
                    briefing_text = generate_market_briefing(news_summary)
                    
                    # DB 저장
                    try:
                        cursor.execute("""
                            INSERT INTO market_news_summaries (summary_text, briefing_text, created_at)
                            VALUES (%s, %s, %s)
                        """, (news_summary, briefing_text, datetime.now()))
                        conn.commit()
                        logger.info("✅ 뉴스 요약 및 Briefing DB 저장 완료")
                    except Exception as e:
                        logger.error(f"뉴스 요약 DB 저장 실패: {e}")
            
            return {
                "total_count": len(news),
                "days": days,
                "target_countries": target_countries,
                "news": news,
                "news_summary": news_summary,
                "briefing_text": briefing_text,
                "cached": False
            }
            
    except Exception as e:
        logger.error(f"경제 뉴스 수집 및 분석 실패: {e}", exc_info=True)
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


def _format_fred_dashboard_data(fred_signals: Dict) -> str:
    """FRED 대시보드 데이터 포맷팅 (공통 함수)"""
    # Dashboard Data 활용
    dash = fred_signals.get('dashboard_data', {})
    
    # 1. Growth
    growth = dash.get('growth', {})
    
    # Philly Fed Indicators
    philly_curr = growth.get('philly_current', {})
    philly_curr_val =  f"{philly_curr.get('value', 'N/A')}"
    philly_curr_status = philly_curr.get('status', 'N/A')
    
    philly_new_orders = growth.get('philly_new_orders', 'N/A')
    philly_future = growth.get('philly_future', 'N/A')
    
    gdp_now = growth.get('gdp_now', 'N/A')
    
    unemp = growth.get('unemployment', {})
    unemp_curr = unemp.get('current', 'N/A')
    unemp_past = unemp.get('past_3m', 'N/A')
    unemp_diff = unemp.get('diff_trend', 'N/A')
    sams_rule = unemp.get('sams_rule', 'N/A')
    
    nfp = growth.get('nfp', {})
    nfp_val = nfp.get('value', 'N/A')
    nfp_diff_prev = nfp.get('diff_prev', 'N/A')
    nfp_diff_year = nfp.get('diff_year', 'N/A')
    
    # NFP 포맷팅 (전월차, 전년차 포함)
    nfp_str = f"{nfp_val}K"
    if isinstance(nfp_diff_prev, (int, float)) and isinstance(nfp_diff_year, (int, float)):
        nfp_str += f" (전월 대비 {nfp_diff_prev:+.0f}K, 전년 동월 대비 {nfp_diff_year:+.0f}K)"
    elif isinstance(nfp_diff_prev, (int, float)):
        nfp_str += f" (전월 대비 {nfp_diff_prev:+.0f}K)"

    # 2. Inflation
    infl = dash.get('inflation', {})
    pce = infl.get('core_pce_yoy', {})
    cpi = infl.get('cpi_yoy', {})
    exp_inf = infl.get('expected_inflation', 'N/A')
    
    pce_val = pce.get('value', 'N/A')
    if isinstance(pce_val, (int, float)):
        pce_val = f"{pce_val:.2f}"
    pce_gap = pce.get('target_gap', 'N/A')
    
    cpi_val = cpi.get('value', 'N/A')
    if isinstance(cpi_val, (int, float)):
        cpi_val = f"{cpi_val:.2f}"
    cpi_trend = cpi.get('trend', 'N/A')
    
    if isinstance(exp_inf, (int, float)):
        exp_inf = f"{exp_inf:.2f}"

    # 3. Liquidity
    liq = dash.get('liquidity', {})
    yc = liq.get('yield_curve', {})
    soma = liq.get('soma', {})
    net_liq = liq.get('net_liquidity', {})
    hy = liq.get('hy_spread', {})
    
    yc_val = yc.get('value_bp', 'N/A')
    if isinstance(yc_val, (int, float)):
        yc_val = f"{yc_val:.0f}"
    yc_status = yc.get('status', 'N/A')
    
    soma_val = soma.get('value', 'N/A')
    if isinstance(soma_val, (int, float)):
        soma_val = f"{soma_val:.0f}"
    qt_speed = soma.get('qt_speed', 'N/A')
    
    nl_val = net_liq.get('value', 'N/A')
    if isinstance(nl_val, (int, float)):
        nl_val = f"{nl_val:.0f}"
    nl_status = net_liq.get('status', 'N/A')
    nl_text = nl_status
    
    hy_val = hy.get('value', 'N/A')
    if isinstance(hy_val, (int, float)):
        hy_val = f"{hy_val:.2f}"
    hy_eval = hy.get('evaluation', 'N/A')

    # 4. Sentiment
    sent = dash.get('sentiment', {})
    vix = sent.get('vix', 'N/A')
    if isinstance(vix, (int, float)):
        vix = f"{vix:.2f}"
        
    stlfsi = sent.get('stlfsi4', {})
    stlfsi_val = stlfsi.get('value', 'N/A')
    if isinstance(stlfsi_val, (int, float)):
        stlfsi_val = f"{stlfsi_val:.2f}"
    
    cnn = sent.get('cnn_index', {})
    cnn_val = cnn.get('value', 'N/A')
    cnn_status = cnn.get('status', 'N/A')

    # Construct the Analysis Prompt
    fred_summary = f"""
=== Macro Economic Indicators ===

### 1. Growth (경기 성장 & 선행 지표)
* **Philly Fed 제조업 지수 (Current Activity):** {philly_curr_val} (설명: ISM PMI 대체재. 기준선 0 {philly_curr_status}. 현재 제조업 체감 경기)
* **Philly Fed 신규 주문 (New Orders):** {philly_new_orders} (설명: ISM New Orders 대체재. 실제 공장에 들어오는 주문량. 가장 강력한 선행 지표)
* **Philly Fed 6개월 전망 (Future Activity):** {philly_future} (설명: 기업들의 미래 기대 심리. 수치가 높으면 낙관적)
* **GDPNow 예상치:** {gdp_now}%
* **실업률:** {unemp_curr}% (3개월 전 {unemp_past}% 대비 {unemp_diff} - Sam's Rule {sams_rule})
* **비농업 고용(NFP):** {nfp_str}

### 2. Inflation (물가 압력)
* **Core PCE (YoY):** {pce_val}% (연준 목표 2%와 괴리: {pce_gap})
* **Headline CPI (YoY):** {cpi_val}% (추세: {cpi_trend})
* **기대 인플레이션(BEI 10Y):** {exp_inf}%

### 3. Liquidity & Fed Policy (유동성 환경)
* **금리 커브 (10Y-2Y):** {yc_val}bp (상태: {yc_status})
* **SOMA (연준 자산):** {soma_val}B$ (QT 진행 속도: {qt_speed})
* **Net Liquidity (순유동성):** {nl_val}B$ ({nl_text})
* **하이일드 스프레드:** {hy_val}% (평가: {hy_eval})

### 4. Sentiment & Volatility (심리)
* **VIX (주식 공포지수):** {vix}
* **금융 스트레스 지수 (STLFSI4):** {stlfsi_val} (설명: MOVE 대체재. 0보다 크면 시장 긴장, 0 이하면 평온. 최신 버전 사용)
* **CNN Fear & Greed Index:** {cnn_val} (상태: {cnn_status})
"""
    return fred_summary


def _format_economic_news_data(economic_news: Dict) -> str:
    """경제 뉴스 데이터 포맷팅 (공통 함수)"""
    news_summary = "### 5. Key News Context \n"
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
    
    return news_summary


def create_mp_analysis_prompt(fred_signals: Dict, economic_news: Dict, previous_mp_id: Optional[str] = None) -> str:
    # FRED 데이터 포맷팅
    fred_summary = _format_fred_dashboard_data(fred_signals)
    
    # 경제 뉴스 포맷팅
    news_summary = _format_economic_news_data(economic_news)
    
    # 이전 MP 정보
    previous_mp_info = ""
    if previous_mp_id:
        portfolios = get_model_portfolios()
        previous_mp = portfolios.get(previous_mp_id)
        if previous_mp:
            previous_mp_info = f"\n=== 이전 MP 정보 ===\n"
            previous_mp_info += f"이전에 선택된 MP: {previous_mp_id} - {previous_mp['name']}\n"
            previous_mp_info += f"이전 MP 특징: {previous_mp['description']}\n\n"
            previous_mp_info += "**중요:** 경제 상황이 크게 달라지지 않은 경우, 이전 MP를 유지하는 것이 좋습니다.\n"
            previous_mp_info += "경제 지표의 변화가 명확하고 지속적인 경우에만 MP를 변경하세요.\n\n"
    
    # MP 시나리오 정보를 프롬프트에 포함
    mp_info = "\n=== 모델 포트폴리오 (MP) 시나리오 ===\n"
    mp_info += "현재 거시경제 국면을 분석하여 다음 5가지 모델 포트폴리오 중 하나를 선택하세요:\n\n"
    portfolios = get_model_portfolios()
    for mp_id, mp in portfolios.items():
        mp_info += f"{mp_id}: {mp['name']}\n"
        mp_info += f"  - 특징: {mp['description']}\n"
        mp_info += f"  - 핵심 전략: {mp['strategy']}\n"
        mp_info += f"  - 자산 배분: 주식 {mp['allocation']['Stocks']}% / 채권 {mp['allocation']['Bonds']}% / 대체투자 {mp['allocation']['Alternatives']}% / 현금 {mp['allocation']['Cash']}%\n\n"
    
    prompt = f"""당신은 거시경제 전문가입니다. 다음 데이터를 분석하여 현재 거시경제 국면에 가장 적합한 모델 포트폴리오(MP)를 선택하세요.

{mp_info}

{previous_mp_info}

{fred_summary}

{news_summary}

## 분석 지침:
1. **정량 데이터(FRED) 절대 우선:** 뉴스 텍스트(심리)와 FRED 데이터(수치)가 상충할 경우(예: 뉴스에서는 실업률 하락을 강조하나, 데이터 추세는 상승인 경우), 반드시 **FRED 데이터의 수치와 추세**를 기준으로 판단하세요.
2. **금리 커브(Yield Curve) 심층 해석:**
   - **Bear Steepening (장기 금리 상승 주도)** 현상이 관측될 경우, 이를 단순한 경기 회복 신호로 해석하지 말고 **'재정 건전성 우려' 또는 '인플레이션 고착화' 리스크**로 해석하여 보수적인 MP(MP-4 등) 선택의 근거로 삼으세요.
3. **유동성 지표 간 괴리 해결:**
   - SOMA(연준 자산)와 Net Liquidity(순유동성)의 방향이 다를 경우, 시장에 즉각적인 영향을 미치는 **Net Liquidity(순유동성)**의 추세를 우선하여 판단하세요.
4. **현재 거시경제 국면을 종합 판단**하여 5가지 MP 시나리오 중 하나를 선택하세요.
   - 단, MP-4(Defensive)는 금리 인하 기대뿐만 아니라, **'금리 변동성 확대에 따른 방어적 태세'**가 필요할 때도 선택 가능합니다.
5. **이전 MP 고려사항 (Whipsaw 방지):**
   - 경제 상황이 구조적으로 달라지지 않았다면 이전 MP를 유지하세요. 지표의 변화가 일시적 노이즈가 아닌 '추세적 전환'일 때만 변경하세요.
6. MP 선택 시 핵심 체크리스트:
   - 성장률 및 선행지표 (Philly Fed 신규주문 등)의 방향성
   - 물가(PCE/CPI)와 기대인플레이션(BEI)의 괴리
   - 하이일드 스프레드 급등 여부 (신용 위험 감지)
   - 실업률의 '3개월 이동평균' 추세 변화 (샴의 법칙 전조)

## 출력 형식 (JSON):
{{
    "analysis_summary": "분석 요약 (한국어, 400-500자)",
    "mp_id": "MP-4",
    "reasoning": "판단 근거 (한국어, 500-700자) - 1) [변화 감지] 이전 MP 대비 경제 지표의 유의미한 변화가 있었는지 평가 (예: 실업률 추세 전환 등). 2) [데이터 상충 해결] 뉴스(실업률 하락)와 데이터(3개월 추세 상승) 간 괴리 발생 시 데이터 우선 판단 근거 서술. 3) [최종 선택] MP를 선택한 논리적 근거 서술."
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
        previous_sub_mp: 이전 Sub-MP 정보 ({"stocks": "Eq-A", "bonds": "Bnd-L", "alternatives": "Alt-I", "cash": "Cash-N"} 형태)
    """
    
    # FRED 데이터 포맷팅 (공통 함수 사용)
    fred_summary = _format_fred_dashboard_data(fred_signals)
    
    # 경제 뉴스 포맷팅 (공통 함수 사용)
    news_summary = _format_economic_news_data(economic_news)
    
    # 선택된 MP 정보
    portfolios = get_model_portfolios()
    selected_mp = portfolios.get(mp_id, {})
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
        sub_portfolios = get_sub_model_portfolios()
        if previous_sub_mp.get('stocks'):
            prev_stocks = sub_portfolios.get(previous_sub_mp['stocks'], {})
            previous_sub_mp_info += f"이전 주식 Sub-MP: {previous_sub_mp['stocks']} - {prev_stocks.get('name', 'N/A')}\n"
        if previous_sub_mp.get('bonds'):
            prev_bonds = sub_portfolios.get(previous_sub_mp['bonds'], {})
            previous_sub_mp_info += f"이전 채권 Sub-MP: {previous_sub_mp['bonds']} - {prev_bonds.get('name', 'N/A')}\n"
        if previous_sub_mp.get('alternatives'):
            prev_alt = sub_portfolios.get(previous_sub_mp['alternatives'], {})
            previous_sub_mp_info += f"이전 대체자산 Sub-MP: {previous_sub_mp['alternatives']} - {prev_alt.get('name', 'N/A')}\n"
        if previous_sub_mp.get('cash'):
            prev_cash = sub_portfolios.get(previous_sub_mp['cash'], {})
            previous_sub_mp_info += f"이전 현금 Sub-MP: {previous_sub_mp['cash']} - {prev_cash.get('name', 'N/A')}\n"
        previous_sub_mp_info += "\n**중요:** 경제 상황이 크게 달라지지 않은 경우, 이전 Sub-MP를 유지하는 것이 좋습니다.\n"
        previous_sub_mp_info += "경제 지표의 변화가 명확하고 지속적인 경우에만 Sub-MP를 변경하세요.\n\n"
    
    # Sub-MP 시나리오 정보
    sub_mp_info = "\n=== Sub-MP (자산군별 세부 모델) 시나리오 ===\n"
    
    # 주식 Sub-MP
    sub_mp_info += "\n### 주식 (Equity) Sub-Models:\n"
    sub_portfolios = get_sub_model_portfolios()
    for sub_mp_id in ["Eq-A", "Eq-N", "Eq-D"]:
        sub_mp = sub_portfolios.get(sub_mp_id, {})
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
        sub_mp = sub_portfolios.get(sub_mp_id, {})
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
        sub_mp = sub_portfolios.get(sub_mp_id, {})
        if sub_mp:
            sub_mp_info += f"{sub_mp_id}: {sub_mp.get('name', 'N/A')}\n"
            sub_mp_info += f"  - 상황: {sub_mp.get('description', 'N/A')}\n"
            etf_details = sub_mp.get('etf_details', [])
            if etf_details:
                sub_mp_info += f"  - 세부 종목:\n"
                for etf in etf_details:
                    sub_mp_info += f"    * {etf.get('ticker', 'N/A')} ({etf.get('name', 'N/A')}): {etf.get('weight', 0)*100:.0f}%\n"
            sub_mp_info += "\n"

    # 현금 Sub-MP (DB에 정의된 Cash 자산군 모델)
    cash_models = {k: v for k, v in sub_portfolios.items() if str(v.get('asset_class', '')).lower() == 'cash'}
    if cash_models:
        sub_mp_info += "\n### 현금 (Cash) Sub-Models:\n"
        # 현금성은 Cash-N 하나만 선택지라는 비즈니스 룰을 안내
        for sub_mp_id, sub_mp in cash_models.items():
            sub_mp_info += f"{sub_mp_id} (현금성): {sub_mp.get('name', 'N/A')}\n"
            sub_mp_info += f"  - 상황: {sub_mp.get('description', 'N/A')}\n"
            etf_details = sub_mp.get('etf_details', [])
            if etf_details:
                sub_mp_info += f"  - 세부 종목:\n"
                for etf in etf_details:
                    sub_mp_info += f"    * {etf.get('ticker', 'N/A')} ({etf.get('name', 'N/A')}): {etf.get('weight', 0)*100:.0f}%\n"
            sub_mp_info += "\n"
    
    prompt = f"""당신은 거시경제 전문가입니다. 선택된 MP({mp_id})에 기반하여 각 자산군별 Sub-MP를 선택하세요.

{mp_info}

{sub_mp_info}

{previous_sub_mp_info}

{fred_summary}

{news_summary}

## 분석 지침:
1. **선택된 MP의 논리**를 바탕으로, 현재의 특수한 시장 상황(Curve, Valuation 등)을 반영하여 Sub-MP를 선택하세요.
2. **주식 Sub-MP 선택 기준:**
   - 금리 인하기, 유동성 풍부, Risk-On → Eq-A (성장 공격형)
   - 방향성 불확실, 박스권 장세 → Eq-N (시장 중립형)
   - 고금리 장기화, 밸류에이션 부담, 경기 침체 우려 → Eq-D (방어형)
3. **채권 Sub-MP 선택 기준 (듀레이션 관리):**
   - 금리 인하 사이클 진입 확실시 → Bnd-L (장기채 베팅)
   - 금리 방향성 탐색 구간 → Bnd-N (균형)
   - **금리 인상기, 인플레이션 쇼크, 또는 'Bear Steepening(장기 금리 급등)'으로 인한 장기채 평가손실 위험 구간** → **Bnd-S (단기채 방어)**
4. **대체자산 Sub-MP 선택 기준:**
   - 스태그플레이션, **재정 적자 우려, 화폐 가치 신뢰 하락(Debasement)** → **Alt-I (인플레 방어 - 금 선호)**
   - 금융 시스템 위기, 신용 경색(Credit Crunch), 주식 폭락 → Alt-C (위기 방어 - 달러 선호)
5. **현금 Sub-MP 선택 기준:**
   - 현금/단기 MMF 등 유동성 확보 및 변동성 회피 목적: Cash-N 선택
   - 자산군 비중이 0%이면 null
6. **이전 Sub-MP 고려사항:**
   - 급격한 포트폴리오 변경을 지양하고, 논리적 근거가 확실할 때만 변경하세요.
7. **데이터 충돌 시:**
   - 매크로 데이터와 뉴스가 상충할 경우, **Sub-MP 선택에서는 '가격 변수(금리 커브, 하이일드 스프레드)'**를 최우선 기준으로 삼으세요.

## 출력 형식 (JSON):
{{
    "stocks_sub_mp": "Eq-A" 또는 "Eq-N" 또는 "Eq-D" 또는 null,
    "bonds_sub_mp": "Bnd-L" 또는 "Bnd-N" 또는 "Bnd-S" 또는 null,
    "alternatives_sub_mp": "Alt-I" 또는 "Alt-C" 또는 null,
    "cash_sub_mp": "Cash-N" 또는 null,
    "reasoning": "Sub-MP 선택 근거 (한국어, 300-500자) - 1) [변화 감지] 이전 MP/Sub-MP 대비 경제 지표의 유의미한 변화가 있었는지 평가 (예: 실업률 추세 전환 등). 2) [데이터 상충 해결] 뉴스(실업률 하락)와 데이터(3개월 추세 상승) 간 괴리 발생 시 데이터 우선 판단 근거 서술. 3) [최종 선택] Sub-MP 선택한 논리적 근거 서술."
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
        
    Returns:
        Optional[AIStrategyDecision]: AI 전략 결정 결과
        
    Raises:
        ValueError: 포트폴리오 데이터를 로드할 수 없는 경우 (LLM 분석 중단)
    """
    try:
        logger.info("AI 전략 분석 시작 (MP + Sub-MP 분리 분석)")
        
        # 포트폴리오 데이터 검증 (분석 전에 필수)
        try:
            portfolios = get_model_portfolios()
            if not portfolios:
                raise ValueError("모델 포트폴리오 데이터가 없습니다. LLM 분석을 수행할 수 없습니다.")
            logger.info(f"모델 포트폴리오 로드 완료: {len(portfolios)}개")
            
            sub_portfolios = get_sub_model_portfolios()
            if not sub_portfolios:
                raise ValueError("Sub-MP 포트폴리오 데이터가 없습니다. LLM 분석을 수행할 수 없습니다.")
            logger.info(f"Sub-MP 포트폴리오 로드 완료: {len(sub_portfolios)}개")
        except ValueError as e:
            logger.error(f"포트폴리오 데이터 로드 실패: {e}")
            raise  # ValueError는 그대로 전파하여 분석 중단
        except Exception as e:
            error_msg = f"포트폴리오 데이터 로드 중 예상치 못한 오류 발생: {e}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e
        
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
        portfolios = get_model_portfolios()
        if not mp_id or mp_id not in portfolios:
            # portfolios.keys()가 정수일 수 있으므로 문자열로 변환
            valid_mp_ids = ', '.join(str(k) for k in portfolios.keys())
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
            
            # with 블록이 끝나면 __exit__가 호출되어 로그가 저장되어야 함
            logger.info("Sub-MP LLM 호출 컨텍스트 종료 (로그 저장 예상)")
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
        cash_sub_mp = sub_mp_decision_data.get('cash_sub_mp')
        
        # 자산군 비중 확인
        target_allocation = get_model_portfolio_allocation(mp_id)
        if target_allocation:
            if target_allocation.get('Stocks', 0) == 0:
                stocks_sub_mp = None
            if target_allocation.get('Bonds', 0) == 0:
                bonds_sub_mp = None
            if target_allocation.get('Alternatives', 0) == 0:
                alternatives_sub_mp = None
            if target_allocation.get('Cash', 0) == 0:
                cash_sub_mp = None
        
        # Sub-MP 유효성 검증
        valid_stocks_sub_mp = ["Eq-A", "Eq-N", "Eq-D"]
        valid_bonds_sub_mp = ["Bnd-L", "Bnd-N", "Bnd-S"]
        valid_alternatives_sub_mp = ["Alt-I", "Alt-C"]
        valid_cash_sub_mp = ["Cash-N"]
        
        if stocks_sub_mp and stocks_sub_mp not in valid_stocks_sub_mp:
            logger.warning(f"유효하지 않은 주식 Sub-MP: {stocks_sub_mp}, None으로 설정")
            stocks_sub_mp = None
        if bonds_sub_mp and bonds_sub_mp not in valid_bonds_sub_mp:
            logger.warning(f"유효하지 않은 채권 Sub-MP: {bonds_sub_mp}, None으로 설정")
            bonds_sub_mp = None
        if alternatives_sub_mp and alternatives_sub_mp not in valid_alternatives_sub_mp:
            logger.warning(f"유효하지 않은 대체자산 Sub-MP: {alternatives_sub_mp}, None으로 설정")
            alternatives_sub_mp = None
        if cash_sub_mp and valid_cash_sub_mp and cash_sub_mp not in valid_cash_sub_mp:
            logger.warning(f"유효하지 않은 현금 Sub-MP: {cash_sub_mp}, None으로 설정")
            cash_sub_mp = None
        
        logger.info(f"Sub-MP 분석 완료: Stocks={stocks_sub_mp}, Bonds={bonds_sub_mp}, Alternatives={alternatives_sub_mp}, Cash={cash_sub_mp}")
        
        # ===== 최종 결정 생성 =====
        sub_mp_decision = SubMPDecision(
            stocks_sub_mp=stocks_sub_mp,
            bonds_sub_mp=bonds_sub_mp,
            alternatives_sub_mp=alternatives_sub_mp,
            cash_sub_mp=cash_sub_mp,
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
        # include_summary=True로 변경하여 collect_economic_news 내부의 캐싱/요약 로직 사용
        economic_news = collect_economic_news(days=20, include_summary=True)
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
        
        # 이미 요약된 정보가 있으면 스킵 (collect_economic_news에서 수행됨)
        if economic_news and economic_news.get("news_summary"):
            logger.info("✅ 이미 생성된 뉴스 요약이 있어 LLM 요약 과정을 생략합니다.")
            return {
                **state,
                "news_summary": economic_news.get("news_summary")
            }

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
    except ValueError as e:
        # 포트폴리오 데이터 로드 실패는 심각한 오류로 처리
        error_msg = f"포트폴리오 데이터 부재로 인한 AI 분석 중단: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            **state,
            "decision": None,
            "error": error_msg,
            "success": False
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
        error = state.get("error")
        
        # 포트폴리오 데이터 부재로 인한 오류인 경우 저장하지 않음
        if error and "포트폴리오 데이터" in error:
            logger.error(f"포트폴리오 데이터 부재로 인해 결과를 저장하지 않습니다: {error}")
            return {
                **state,
                "success": False,
                "error": error
            }
        
        if not decision:
            logger.error("저장할 결정이 없습니다.")
            return {
                **state,
                "success": False,
                "error": error or "저장할 결정이 없습니다."
            }
        
        success = save_strategy_decision(decision, fred_signals, economic_news)
        
        if success:
            target_allocation = decision.get_target_allocation()
            portfolios = get_model_portfolios()
            mp_info = portfolios.get(decision.mp_id, {})
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
                    "cash": decision.sub_mp.cash_sub_mp,
                    "reasoning": decision.sub_mp.reasoning
                }
            
            cursor.execute("""
                INSERT INTO ai_strategy_decisions (
                    decision_date,
                    analysis_summary,
                    target_allocation,
                    recommended_stocks,
                    quant_signals,
                    account_pnl
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                analysis_summary_with_reasoning,
                json.dumps(save_data),  # mp_id와 target_allocation을 함께 저장
                json.dumps(decision.recommended_stocks.model_dump()) if decision.recommended_stocks else None,
                json.dumps(fred_signals) if fred_signals else None,
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
