from dotenv import load_dotenv
import os
import json
import time
import schedule
from datetime import date, datetime

load_dotenv(override=True)

from fastapi import FastAPI, HTTPException, Query, APIRouter, Depends, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import logging
import uuid
from service.slack_bot import post_message
from app import daily_news_summary
from service.news.daily_news_agent import compiled
from service.news import news_manager
from service import auth
from service import file_service
from service.core.time_provider import TimeProvider
from service import llm as llm_service
from service.graph.rag.context_api import router as graph_rag_router
from service.graph.rag.response_generator import router as graph_rag_answer_router
from service.graph.monitoring.graphrag_metrics import router as graph_rag_metrics_router
from service.graph.strategy.strategy_api import router as strategy_api_router
from service.macro_trading.real_estate_api import router as real_estate_api_router
from service.kakao.skill_api import router as kakao_skill_router
# 서비스 시작 시 데이터베이스 초기화 (지연 초기화)
# 실제 사용 시점에 자동으로 초기화됨
from typing import Any, Dict, List, Optional

app = FastAPI(title="Hobot API", version="1.0.0")

# API 라우터 생성
api_router = APIRouter(prefix="/api")
api_router.include_router(graph_rag_router)
api_router.include_router(graph_rag_answer_router)
api_router.include_router(graph_rag_metrics_router)
api_router.include_router(strategy_api_router)
api_router.include_router(real_estate_api_router)
api_router.include_router(kakao_skill_router)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
# Configure logging
# EC2 배포 위치 기준: /home/ec2-user/hobot-service/hobot/logs/log.txt
current_dir = os.path.dirname(os.path.abspath(__file__))
log_dir = os.path.join(current_dir, 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, 'log.txt')

# 로깅 설정 (기존 설정이 있어도 덮어쓰기)
# FileHandler와 StreamHandler(콘솔) 모두 추가
logging.basicConfig(
    level=logging.DEBUG,  # DEBUG 레벨로 변경하여 모든 로그 출력
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True,  # 기존 핸들러가 있어도 재설정
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Reduce noise from Neo4j driver
logging.getLogger("neo4j").setLevel(logging.WARNING)

# Pydantic 모델
class StrategyRequest(BaseModel):
    strategy: str

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

class KISCredentialRequest(BaseModel):
    kis_id: str
    account_no: str
    app_key: str
    app_secret: str
    is_simulation: bool = False

class UpbitCredentialRequest(BaseModel):
    access_key: str
    secret_key: str

class MFAVerifySetupRequest(BaseModel):
    secret: str
    code: str

class MFADisableRequest(BaseModel):
    password: str

class MFARegenerateBackupCodesRequest(BaseModel):
    password: str

class MFALoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: Optional[str] = None


class RebalancingConfigRequest(BaseModel):
    mp_threshold_percent: float
    sub_mp_threshold_percent: float

# 비트코인 반감기 사이클 정적 데이터
BITCOIN_CYCLE_DATA = [
    {"date": "2012-11", "price": 12, "type": "history", "event": "1st Halving"},
    {"date": "2013-12", "price": 1209, "type": "history", "event": "Peak"},
    {"date": "2015-01", "price": 180, "type": "history", "event": "Bottom"},
    {"date": "2016-07", "price": 650, "type": "history", "event": "2nd Halving"},
    {"date": "2017-12", "price": 19328, "type": "history", "event": "Peak"},
    {"date": "2018-12", "price": 3222, "type": "history", "event": "Bottom"},
    {"date": "2020-05", "price": 8600, "type": "history", "event": "3rd Halving"},
    {"date": "2021-11", "price": 66459, "type": "history", "event": "Peak"},
    {"date": "2022-11", "price": 15653, "type": "history", "event": "Bottom"},
    {"date": "2024-04", "price": 63000, "type": "history", "event": "4th Halving"},
    {"date": "2025-08", "price": 125000, "type": "history", "event": "Peak"},
    {"date": "2026-10", "price": 45000, "type": "prediction", "event": "Bottom (Exp)"},
    {"date": "2028-04", "price": 70000, "type": "prediction", "event": "5th Halving"},
    {"date": "2029-08", "price": 200000, "type": "prediction", "event": "Peak (Exp)"}
]

# JWT 인증
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보 가져오기"""
    token = credentials.credentials
    payload = auth.verify_token(token)
    user = auth.get_user_by_id(payload.get("id"))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_admin(current_user: dict = Depends(get_current_user)):
    """Admin 권한 확인"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

def is_system_admin(current_user: dict = Depends(get_current_user)) -> bool:
    """시스템 어드민 여부 확인 (admin role을 가진 사용자)"""
    return current_user.get("role") == "admin"

# 기본 페이지 (루트)
@app.get("/", response_class=HTMLResponse)
async def hello_world():
    return "<p>Hello, World!</p>"

# API 엔드포인트들을 /api 라우터에 추가
@api_router.get("/health")
async def health_check():
    from service.upbit.upbit import health_check
    res = health_check()
    return res

@api_router.get("/news-sentiment")
async def daily_news(query: str = Query(default="오늘의 뉴스 중 중요한 뉴스들을 알려줘. 경제 > 정치 > 과학(기술) > 사회 > 기타 순서로 중요도를 판단하면 돼")):
    """기존 뉴스 시감 분석 (슬랙 전송용)"""
    news = daily_news_summary(query)
    res = post_message(news)
    return res

@app.get("/about", response_class=HTMLResponse)
async def about_page():
    """About 페이지 (서비스 소개)"""
    with open(os.path.join(current_dir, "about.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/admin/test", response_class=HTMLResponse)
async def admin_test_dashboard():
    """테스트 관리자 대시보드 (페이지 로드 자체는 인증 불필요, API 호출 시 인증)"""
    try:
        with open(os.path.join(current_dir, "admin_dashboard.html"), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Dashboard file not found."

@api_router.get("/news")
async def get_daily_news():
    """뉴스 파일에서 뉴스를 읽어옵니다. (브라우저용) - 자동 업데이트 없음"""
    logging.info("=== GET /api/news - Starting news retrieval ===")
    try:
        logging.info("Step 1: Calling news_manager.get_news_with_date()...")
        result = news_manager.get_news_with_date()
        logging.info(f"Step 1 Result: news exists={result['news'] is not None}, date={result.get('date')}, is_today={result.get('is_today')}")
        
        # 뉴스가 없어도 결과 반환 (프론트엔드에서 처리)
        logging.info("Step 2: Returning news result (may be empty)")
        return result
    except Exception as e:
        logging.error(f"Step 3: Unexpected error getting daily news: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/news-update")
async def update_daily_news(force: bool = Query(default=False, description="강제 업데이트 여부")):
    """뉴스를 새로 수집하고 저장합니다. (스케줄러/수동 업데이트용 - Tavily API 호출)"""
    logging.info(f"=== GET /api/news-update - Starting news update (force={force}) ===")
    try:
        logging.info("Step 1: Calling news_manager.update_news_with_tavily()...")
        result = news_manager.update_news_with_tavily(compiled, force_update=force)
        logging.info(f"Step 1 Result: status={result.get('status')}, message={result.get('message')}")
        return result
    except Exception as e:
        logging.error(f"Step 2: Error updating daily news: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/bitcoin-cycle")
async def get_bitcoin_cycle():
    """비트코인 반감기 사이클 데이터와 현재 가격을 반환합니다."""
    current_price = None
    error_message = None
    
    # 1. 현재 가격 조회 (Binance API 사용 - Rate limit이 더 넉넉함)
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        import requests
        # Binance API
        try:
            response = requests.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": "BTCUSDT"},
                timeout=5,
                verify=False # SSL 인증서 오류 우회
            )
            response.raise_for_status()
            data = response.json()
            price = float(data["price"])
            
            current_price = {
                "price": price,
                "timestamp": f"{datetime.utcnow().isoformat()}Z",
                "source": "binance"
            }
        except Exception as binance_err:
             logging.warning(f"Binance fetch failed: {binance_err}. Trying fallback...")
             raise binance_err # Trigger fallback

    except Exception as exc:
        # Fallback to CoinGecko if Binance fails
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "bitcoin", "vs_currencies": "usd"},
                timeout=5,
                verify=False # SSL 인증서 오류 우회
            )
            response.raise_for_status()
            payload = response.json()
            price = payload.get("bitcoin", {}).get("usd")
            if price:
                current_price = {
                    "price": price,
                    "timestamp": f"{datetime.utcnow().isoformat()}Z",
                    "source": "coingecko"
                }
            else:
                 error_message = "current price missing"
        except Exception as e2:
             logging.warning(f"All price fetch attempts failed. Using mock data for demo. Error: {e2}")
             # Final Fallback: Mock Data to prevent UI text missing
             # 2026년 기준 적절한 가상 가격 리턴
             current_price = {
                 "price": 95000 + (datetime.now().minute * 100), # 약간의 변동성
                 "timestamp": f"{datetime.utcnow().isoformat()}Z",
                 "source": "simulation"
             }
             error_message = f"Real-time update failed ({str(exc)}). Using simulation data."

    # 2. 날짜 기반으로 history/prediction 동적 할당
    processed_cycle_data = []
    now = datetime.now()
    
    for item in BITCOIN_CYCLE_DATA:
        # 날짜 파싱 ("YYYY-MM")
        try:
            item_date = datetime.strptime(item["date"], "%Y-%m")
            # 현재 날짜보다 이전이거나 같으면 history, 미래면 prediction
            # 단, 현재 월도 포함하여 history로 처리
            if item_date <= now:
                new_type = "history"
                # Prediction 이벤트명에서 (Exp) 제거
                new_event = item["event"].replace(" (Exp)", "")
            else:
                new_type = "prediction"
                new_event = item["event"]
                
            processed_cycle_data.append({
                **item,
                "type": new_type,
                "event": new_event
            })
        except ValueError:
            # 날짜 형식이 안맞으면 그대로 유지
            processed_cycle_data.append(item)
            
    # Debug Logging
    logging.info(f"Cycle Data Debug: First item date: {processed_cycle_data[0]['date']}, Last item date: {processed_cycle_data[-1]['date']}, Total: {len(processed_cycle_data)}")

    return {
        "cycle_data": processed_cycle_data,
        "current_price": current_price,
        "error": error_message
    }

@api_router.get("/upbit/trading")
async def upbit_trading():
    import time
    from service.upbit import upbit
    
    res = upbit.control_tower()
    post_message(f"upbit_trading result: {res}", channel="#auto-trading-logs")
    logging.info(f"upbit_trading result: {res}")
    return res

@api_router.get("/kis/health")
async def kis_health_check(current_user: dict = Depends(get_current_user)):
    """한국투자증권 API 헬스체크 (로그인 사용자별)"""
    try:
        from service.macro_trading.kis.kis import health_check as kis_health_check_func
        result = kis_health_check_func(user_id=current_user["id"])
        logging.info(f"KIS health check result: {result}")
        return result
    except Exception as e:
        logging.error(f"Error in KIS health check: {e}")
        return {"status": "error", "message": str(e)}

@api_router.get("/kis/balance")
async def kis_get_balance(current_user: dict = Depends(get_current_user)):
    """한국투자증권 계좌 잔액조회 (로그인 사용자별)"""
    try:
        from service.macro_trading.kis.kis import get_balance_info_api
        logging.info(f"KIS balance API 호출 - user_id: {current_user['id']}")
        result = get_balance_info_api(user_id=current_user["id"])
        status = result.get('status')
        message = result.get('message', '')
        logging.info(f"KIS balance check result - status: {status}, message: {message}")
        if status == "error":
            logging.warning(f"KIS balance check 실패 상세 - result: {json.dumps(result, ensure_ascii=False)}")
        return result
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logging.error(f"KIS balance check 예외 발생 - error: {str(e)}, trace: {error_trace}")
        return {"status": "error", "message": str(e), "trace": error_trace}


@api_router.get("/upbit/test2")
async def upbit_bbrsi_test2():
    from service.upbit import upbit
    from service.upbit.upbit_utils import read_current_strategy
    
    current_st = read_current_strategy()
    res = upbit.strategy_ema("STRATEGY_NULL")
    logging.info(f"upbit_trading result: {res}")
    return {"res": res}

@api_router.get("/current-strategy")
async def get_current_strategy(platform: str = Query(default="upbit", description="플랫폼 (upbit, binance, kis)")):
    """플랫폼별 현재 전략을 반환합니다."""
    try:
        from service import strategy_manager
        strategy = strategy_manager.read_strategy(platform)
        return {"platform": platform, "strategy": strategy}
    except Exception as e:
        logging.error(f"Error reading current strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/current-strategy/{platform}", response_class=PlainTextResponse)
async def get_current_strategy_platform(platform: str):
    """플랫폼별 현재 전략을 텍스트로 반환합니다. (하위 호환성)"""
    try:
        from service import strategy_manager
        strategy = strategy_manager.read_strategy(platform)
        return strategy
    except Exception as e:
        logging.error(f"Error reading current strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/upbit/account-summary")
async def get_upbit_account_summary_api():
    """업비트 계좌 요약 정보 조회 (자산, 평가금액, 수익률, 전략 등)"""
    try:
        from service.upbit.account_service import get_upbit_account_summary
        result = get_upbit_account_summary()
        return result
    except Exception as e:
        logging.error(f"Error fetching upbit account summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/upbit/strategy/current")
async def get_upbit_current_strategy():
    """업비트 현재 전략 상태 및 시장 분석 결과 조회 (Simulation)"""
    try:
        from service.upbit.upbit import analyze_market_condition
        analysis_result = analyze_market_condition()
        return {"status": "success", "strategy": analysis_result}
    except Exception as e:
        logging.error(f"Error analyzing upbit strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/upbit/operation/start")
async def start_upbit_trading():
    """트레이딩 시작 (Resume)"""
    try:
        from service.upbit.upbit_utils import write_current_strategy, get_resume_strategy
        
        # Resume 전략 가져오기
        resume_strategy = get_resume_strategy()
        
        # DB에 기록
        write_current_strategy(resume_strategy)
        
        return {"status": "success", "message": f"Trading resumed with strategy: {resume_strategy}", "strategy": resume_strategy}
    except Exception as e:
        logging.error(f"Error starting trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/upbit/operation/pause")
async def pause_upbit_trading():
    """트레이딩 일시정지 (Pause)"""
    try:
        from service.upbit.upbit_utils import write_current_strategy
        
        # Pause 기록
        write_current_strategy("STRATEGY_PAUSE")
        
        return {"status": "success", "message": "Trading paused", "strategy": "STRATEGY_PAUSE"}
    except Exception as e:
        logging.error(f"Error pausing trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/fred-data")
async def get_fred_data(
    indicator_code: str = Query(..., description="지표 코드 (DGS10, DGS2, FEDFUNDS, CPIAUCSL, PCEPI, GDP, UNRATE, PAYEMS, WALCL, WTREGEN, RRPONTSYD, BAMLH0A0HYM2, DFII10)"),
    days: int = Query(default=365, description="조회할 일수 (기본값: 365일)")
):
    """FRED 데이터 조회 API"""
    try:
        from service.macro_trading.collectors.fred_collector import (
            get_fred_collector, RateLimitError, FREDAPIError, DataInsufficientError
        )
        from service.macro_trading.validators.data_validator import FREDDataValidator
        from datetime import date, timedelta
        
        collector = get_fred_collector()
        validator = FREDDataValidator()
        
        # 최근 N일간 데이터 조회
        try:
            data = collector.get_latest_data(indicator_code, days=days)
        except DataInsufficientError as e:
            logging.warning(f"Data insufficient: {e}")
            return {
                "indicator_code": indicator_code,
                "data": [],
                "error": {
                    "type": "data_insufficient",
                    "message": str(e),
                    "severity": "warning"
                },
                "message": "데이터가 부족합니다."
            }
        except (RateLimitError, FREDAPIError) as e:
            logging.error(f"FRED API error: {e}", exc_info=True)
            return {
                "indicator_code": indicator_code,
                "data": [],
                "error": {
                    "type": "api_error",
                    "message": str(e),
                    "severity": "critical"
                },
                "message": "FRED API 오류가 발생했습니다."
            }
        
        if len(data) == 0:
            return {
                "indicator_code": indicator_code,
                "data": [],
                "error": {
                    "type": "no_data",
                    "message": "데이터가 없습니다.",
                    "severity": "warning"
                },
                "message": "데이터가 없습니다."
            }
        
        # 데이터 품질 검증
        quality_summary = validator.get_data_quality_summary(indicator_code, data)
        issues = validator.validate_data_quality(indicator_code, data)
        
        # 날짜와 값을 리스트로 변환
        result_data = [
            {
                "date": date_idx.strftime("%Y-%m-%d") if hasattr(date_idx, 'strftime') else str(date_idx),
                "value": float(value)
            }
            for date_idx, value in data.items()
        ]
        
        response = {
            "indicator_code": indicator_code,
            "data": result_data,
            "count": len(result_data),
            "quality": quality_summary
        }
        
        # 심각한 이슈가 있으면 경고 추가
        critical_issues = [issue for issue in issues if issue.severity == 'critical']
        if critical_issues:
            response["warning"] = {
                "message": f"{len(critical_issues)}개의 심각한 데이터 품질 이슈가 발견되었습니다.",
                "issues": [issue.to_dict() for issue in critical_issues]
            }
        
        return response
    except Exception as e:
        logging.error(f"Error fetching FRED data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/yield-curve-spread")
async def get_yield_curve_spread_data(
    days: int = Query(default=365, description="조회할 일수 (기본값: 365일)")
):
    """장단기 금리차 데이터 조회 API (DGS10 - DGS2)"""
    try:
        from service.macro_trading.collectors.fred_collector import (
            get_fred_collector, RateLimitError, FREDAPIError, DataInsufficientError
        )
        from service.macro_trading.validators.data_validator import FREDDataValidator
        from datetime import date, timedelta
        import pandas as pd
        
        collector = get_fred_collector()
        validator = FREDDataValidator()
        
        # DGS10과 DGS2 데이터 조회
        api_errors = []
        try:
            dgs10_data = collector.get_latest_data("DGS10", days=days)
        except (RateLimitError, FREDAPIError, DataInsufficientError) as e:
            api_errors.append(f"DGS10: {str(e)}")
            dgs10_data = pd.Series(dtype=float)
        
        try:
            dgs2_data = collector.get_latest_data("DGS2", days=days)
        except (RateLimitError, FREDAPIError, DataInsufficientError) as e:
            api_errors.append(f"DGS2: {str(e)}")
            dgs2_data = pd.Series(dtype=float)
        
        if len(dgs10_data) == 0 or len(dgs2_data) == 0:
            return {
                "spread_data": [],
                "dgs10_data": [],
                "dgs2_data": [],
                "error": {
                    "type": "data_insufficient",
                    "message": "데이터가 부족합니다.",
                    "details": api_errors,
                    "severity": "critical" if api_errors else "warning"
                },
                "message": "데이터가 부족합니다."
            }
        
        # 공통 날짜로 정렬하여 스프레드 계산
        common_dates = dgs10_data.index.intersection(dgs2_data.index)
        
        spread_data = []
        dgs10_list = []
        dgs2_list = []
        
        for date_idx in common_dates:
            dgs10_val = dgs10_data[date_idx]
            dgs2_val = dgs2_data[date_idx]
            
            # numpy 타입을 Python 기본 타입으로 변환
            if hasattr(dgs10_val, 'item'):
                dgs10_val = float(dgs10_val.item())
            else:
                dgs10_val = float(dgs10_val)
            
            if hasattr(dgs2_val, 'item'):
                dgs2_val = float(dgs2_val.item())
            else:
                dgs2_val = float(dgs2_val)
            
            spread = dgs10_val - dgs2_val
            
            # 날짜 변환
            if isinstance(date_idx, pd.Timestamp):
                date_str = date_idx.strftime("%Y-%m-%d")
            elif hasattr(date_idx, 'strftime'):
                date_str = date_idx.strftime("%Y-%m-%d")
            else:
                date_str = str(date_idx)
            
            spread_data.append({
                "date": date_str,
                "value": float(spread)
            })
            dgs10_list.append({
                "date": date_str,
                "value": float(dgs10_val)
            })
            dgs2_list.append({
                "date": date_str,
                "value": float(dgs2_val)
            })
        
        # 이동평균 계산 (20일, 120일)
        if len(spread_data) >= 20:
            spread_values = [item["value"] for item in spread_data]
            ma20_values = []
            ma120_values = []
            
            for i in range(len(spread_values)):
                if i >= 19:
                    ma20 = sum(spread_values[i-19:i+1]) / 20
                    ma20_values.append({"date": spread_data[i]["date"], "value": float(ma20)})
                else:
                    ma20_values.append({"date": spread_data[i]["date"], "value": None})
                
                if i >= 119:
                    ma120 = sum(spread_values[i-119:i+1]) / 120
                    ma120_values.append({"date": spread_data[i]["date"], "value": float(ma120)})
                else:
                    ma120_values.append({"date": spread_data[i]["date"], "value": None})
        else:
            ma20_values = []
            ma120_values = []
        
        response = {
            "spread_data": spread_data,
            "dgs10_data": dgs10_list,
            "dgs2_data": dgs2_list,
            "ma20": ma20_values,
            "ma120": ma120_values,
            "count": len(spread_data)
        }
        
        # API 오류가 있으면 추가
        if api_errors:
            response["error"] = {
                "type": "api_error",
                "message": "일부 데이터 수집 중 오류가 발생했습니다.",
                "details": api_errors,
                "severity": "warning"
            }
        
        # 데이터 품질 검증 (스프레드 데이터)
        if len(spread_data) > 0:
            spread_series = pd.Series(
                [item["value"] for item in spread_data],
                index=[pd.to_datetime(item["date"]) for item in spread_data]
            )
            quality_summary = validator.get_data_quality_summary("YIELD_SPREAD", spread_series)
            response["quality"] = quality_summary
        
        # numpy 타입 변환 (모든 응답 데이터에 적용)
        response = convert_numpy_types(response)
        
        return response
    except Exception as e:
        logging.error(f"Error fetching yield curve spread data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/real-interest-rate")
async def get_real_interest_rate_data(
    days: int = Query(default=365, description="조회할 일수 (기본값: 365일)")
):
    """실질 금리 시계열 데이터 조회 API (DFII10)"""
    try:
        from service.macro_trading.collectors.fred_collector import (
            get_fred_collector, RateLimitError, FREDAPIError, DataInsufficientError
        )
        from datetime import date, timedelta
        import pandas as pd
        
        collector = get_fred_collector()
        
        # DFII10 데이터 직접 조회
        try:
            dfii10_data = collector.get_latest_data("DFII10", days=days)
        except (RateLimitError, FREDAPIError, DataInsufficientError) as e:
            logging.warning(f"DFII10 데이터 조회 실패: {e}")
            return {
                "data": [],
                "error": {
                    "type": "api_error",
                    "message": str(e),
                    "severity": "warning"
                },
                "message": "데이터 조회에 실패했습니다."
            }
        
        if len(dfii10_data) == 0:
            return {
                "data": [],
                "error": {
                    "type": "data_insufficient",
                    "message": "데이터가 부족합니다.",
                    "severity": "warning"
                },
                "message": "데이터가 부족합니다."
            }
        
        # 날짜와 값을 리스트로 변환
        result_data = [
            {
                "date": date_idx.strftime("%Y-%m-%d") if hasattr(date_idx, 'strftime') else str(date_idx),
                "value": float(value)
            }
            for date_idx, value in dfii10_data.items()
        ]
        
        return {
            "data": result_data,
            "count": len(result_data),
            "unit": "%",
            "description": "실질 금리 (DFII10 - 10-Year Treasury Inflation-Indexed Security)"
        }
        
    except Exception as e:
        logging.error(f"Error fetching real interest rate data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/net-liquidity")
async def get_net_liquidity_data(
    days: int = Query(default=365, description="조회할 일수 (기본값: 365일)")
):
    """연준 순유동성 시계열 데이터 조회 API"""
    try:
        from service.macro_trading.signals.quant_signals import QuantSignalCalculator
        from datetime import date, timedelta
        import pandas as pd
        
        calculator = QuantSignalCalculator()
        
        # 순유동성 시계열 데이터 계산
        net_liquidity_series = calculator.get_net_liquidity_series(days=days)
        
        if net_liquidity_series is None or len(net_liquidity_series) == 0:
            return {
                "data": [],
                "error": {
                    "type": "data_insufficient",
                    "message": "데이터가 부족합니다.",
                    "severity": "warning"
                },
                "message": "데이터가 부족합니다."
            }
        
        # 날짜와 값을 리스트로 변환
        result_data = [
            {
                "date": date_idx.strftime("%Y-%m-%d") if hasattr(date_idx, 'strftime') else str(date_idx),
                "value": float(value)
            }
            for date_idx, value in net_liquidity_series.items()
        ]
        
        return {
            "data": result_data,
            "count": len(result_data),
            "unit": "Millions of Dollars",
            "description": "연준 순유동성 (WALCL - WTREGEN - RRPONTSYD)"
        }
        
    except Exception as e:
        logging.error(f"Error fetching net liquidity data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/fred-indicators")
async def get_fred_indicators_status():
    """FRED 지표 목록 및 상태 조회 API"""
    try:
        from service.macro_trading.collectors.fred_collector import get_fred_collector
        from datetime import date, datetime
        
        collector = get_fred_collector()
        indicators = collector.get_indicators_status()
        
        # Serialize date/datetime objects to strings
        for ind in indicators:
            if isinstance(ind.get('last_updated'), (date, datetime)):
                ind['last_updated'] = ind['last_updated'].isoformat()
            if isinstance(ind.get('last_collected_at'), (date, datetime)):
                ind['last_collected_at'] = ind['last_collected_at'].isoformat()
            
            # Sparkline date serialization
            if 'sparkline' in ind and isinstance(ind['sparkline'], list):
                for point in ind['sparkline']:
                    if isinstance(point.get('date'), (date, datetime)):
                        point['date'] = point['date'].isoformat()
                
        return {"data": indicators, "count": len(indicators)}
        
    except Exception as e:
        logging.error(f"Error fetching FRED indicators status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/account-snapshots")
async def get_account_snapshots(
    days: int = Query(default=30, description="조회할 일수 (기본값: 30일)"),
    current_user: dict = Depends(get_current_user)
):
    """계좌 스냅샷 조회 API (본인 데이터)"""
    try:
        from service.database.db import get_db_connection
        from datetime import datetime, timedelta, timezone

        try:
            from zoneinfo import ZoneInfo
            end_date = datetime.now(ZoneInfo("Asia/Seoul")).date()
        except Exception:
            end_date = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9))).date()
        start_date = end_date - timedelta(days=days)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id,
                    snapshot_date,
                    total_value,
                    cash_balance,
                    allocation_actual,
                    pnl_by_asset,
                    pnl_total,
                    created_at,
                    updated_at
                FROM account_snapshots
                WHERE snapshot_date >= %s AND snapshot_date <= %s AND user_id = %s
                ORDER BY snapshot_date ASC
            """, (start_date, end_date, current_user['id']))
            # Chart drawing is easier with ASC order
            
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                result.append({
                    "id": row["id"],
                    "snapshot_date": row["snapshot_date"].strftime("%Y-%m-%d") if row["snapshot_date"] else None,
                    "total_value": float(row["total_value"]) if row["total_value"] else 0,
                    "cash_balance": float(row["cash_balance"]) if row["cash_balance"] else 0,
                    "allocation_actual": row["allocation_actual"] if isinstance(row["allocation_actual"], dict) else (json.loads(row["allocation_actual"]) if row["allocation_actual"] else {}),
                    "pnl_by_asset": row["pnl_by_asset"] if isinstance(row["pnl_by_asset"], dict) else (json.loads(row["pnl_by_asset"]) if row["pnl_by_asset"] else {}),
                    "pnl_total": float(row["pnl_total"]) if row["pnl_total"] else 0,
                    "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row["created_at"] else None,
                    "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S") if row["updated_at"] else None
                })
            
            return {
                "status": "success",
                "data": result,
                "count": len(result)
            }
    except Exception as e:
        logging.error(f"Error fetching account snapshots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/macro-trading/rebalancing-status")
async def get_rebalancing_status(current_user: dict = Depends(get_current_user)):
    """MP / Sub-MP 목표 vs 실제 현황 조회"""
    try:
        from service.database.db import get_db_connection
        import json
        from service.macro_trading.kis.kis import get_balance_info_api
        from service.macro_trading.ai_strategist import (
            get_model_portfolio_allocation,
            get_sub_mp_details,
            get_model_portfolios,
        )

        def normalize_alloc(alloc: dict) -> dict:
            if not alloc:
                return {"stocks": 0, "bonds": 0, "alternatives": 0, "cash": 0}
            return {
                "stocks": float(alloc.get("stocks") or alloc.get("Stocks") or 0),
                "bonds": float(alloc.get("bonds") or alloc.get("Bonds") or 0),
                "alternatives": float(alloc.get("alternatives") or alloc.get("Alternatives") or 0),
                "cash": float(alloc.get("cash") or alloc.get("Cash") or 0),
            }

        # 1) 최신 AI 결정에서 MP/ Sub-MP 목표 조회
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    target_allocation,
                    decision_date
                FROM ai_strategy_decisions
                ORDER BY decision_date DESC
                LIMIT 1
                """
            )
            decision_row = cursor.fetchone()

        if not decision_row:
            return {
                "status": "success",
                "data": None,
                "message": "AI 전략 결정이 아직 없습니다.",
            }
        
        # decision_date 저장 (현재 MP의 마지막 결정 시점)
        current_decision_date = decision_row["decision_date"]

        target_allocation_raw = decision_row["target_allocation"]
        if isinstance(target_allocation_raw, str):
            target_allocation_raw = json.loads(target_allocation_raw)

        mp_id = None
        target_alloc = None
        sub_mp_data = None
        mp_info = {}

        if isinstance(target_allocation_raw, dict):
            if "mp_id" in target_allocation_raw:
                mp_id = target_allocation_raw["mp_id"]
                
                # MP 정보 및 할당량 조회
                all_mps = get_model_portfolios()
                mp_data = all_mps.get(mp_id)
                allocation_from_mp = None
                
                if mp_data:
                    allocation_from_mp = mp_data.get("allocation")
                    
                    # 현재 MP가 연속으로 적용된 첫 날짜(started_at) 찾기
                    # 가장 최근부터 역순으로 탐색하여 mp_id가 달라지는 시점 직후가 started_at
                    mp_started_at = None
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT decision_date, target_allocation
                            FROM ai_strategy_decisions
                            ORDER BY decision_date DESC
                            LIMIT 100
                            """
                        )
                        history_rows = cursor.fetchall()
                    
                    if history_rows:
                        for row in history_rows:
                            row_alloc = row["target_allocation"]
                            if isinstance(row_alloc, str):
                                row_alloc = json.loads(row_alloc)
                            row_mp_id = row_alloc.get("mp_id") if isinstance(row_alloc, dict) else None
                            if row_mp_id == mp_id:
                                mp_started_at = row["decision_date"]
                            else:
                                # mp_id가 달라지면 중단 (이전까지가 현재 MP의 연속 적용 기간)
                                break
                    
                    mp_info = {
                        "name": mp_data.get("name"),
                        "description": mp_data.get("description"),
                        "updated_at": mp_data.get("updated_at"),
                        "started_at": mp_started_at.strftime("%Y-%m-%d %H:%M:%S") if mp_started_at else None,
                        "decision_date": current_decision_date.strftime("%Y-%m-%d %H:%M:%S") if current_decision_date else None
                    }
                
                target_alloc = allocation_from_mp or target_allocation_raw.get("target_allocation", target_allocation_raw)
                sub_mp_data = target_allocation_raw.get("sub_mp")
            else:
                target_alloc = target_allocation_raw
        else:
            target_alloc = target_allocation_raw

        target_alloc_norm = normalize_alloc(target_alloc)

        sub_mp_details = None
        if sub_mp_data and mp_id:
            sub_mp_details = get_sub_mp_details(sub_mp_data)

        # 2) 실제 자산 비중: KIS balance 기반
        balance = get_balance_info_api(current_user.get("id"))
        if not balance or balance.get("status") != "success":
            return {
                "status": "error",
                "message": balance.get("message", "KIS 잔고 조회에 실패했습니다.") if balance else "KIS 잔고 조회에 실패했습니다.",
            }

        asset_class_info = balance.get("asset_class_info") or {}
        total_eval_amount = float(balance.get("total_eval_amount") or 0)

        def get_class_total(key: str) -> float:
            info = asset_class_info.get(key) or {}
            return float(info.get("total_eval_amount") or 0)

        actual_alloc = {"stocks": 0, "bonds": 0, "alternatives": 0, "cash": 0}
        if total_eval_amount > 0:
            actual_alloc["stocks"] = round(get_class_total("stocks") / total_eval_amount * 100, 2)
            actual_alloc["bonds"] = round(get_class_total("bonds") / total_eval_amount * 100, 2)
            actual_alloc["alternatives"] = round(get_class_total("alternatives") / total_eval_amount * 100, 2)
            cash_total = get_class_total("cash") or float(balance.get("cash_balance") or 0)
            actual_alloc["cash"] = round(cash_total / total_eval_amount * 100, 2)

        def build_target_items(asset_key: str):
            items = []
            detail = (sub_mp_details or {}).get(asset_key) if sub_mp_details else None
            if not detail:
                return items
            for etf in detail.get("etf_details", []):
                weight = etf.get("weight") or etf.get("weight_percent") or 0
                weight_percent = weight * 100 if weight <= 1 else weight
                items.append(
                    {
                        "name": etf.get("name") or etf.get("ticker") or "",
                        "ticker": etf.get("ticker") or "",
                        "weight_percent": round(float(weight_percent), 2),
                    }
                )
            return items

        def build_actual_items(asset_key: str):
            items = []
            info = asset_class_info.get(asset_key) or {}
            class_total = float(info.get("total_eval_amount") or 0)
            holdings = info.get("holdings") or []
            if class_total <= 0:
                return items

            holdings_sum = 0
            for h in holdings:
                eval_amount = float(h.get("eval_amount") or 0)
                holdings_sum += eval_amount
                weight_percent = round(eval_amount / class_total * 100, 2) if class_total > 0 else 0
                items.append(
                    {
                        "name": h.get("stock_name") or "",
                        "ticker": h.get("stock_code") or "",
                        "weight_percent": weight_percent,
                    }
                )
            
            # Cash 자산군의 경우 holdings에 포함되지 않은 예수금(Cash Balance)을 항목으로 추가
            if asset_key == "cash":
                # 역산하는 대신, KIS API로 직접 조회된 정확한 현금 잔고(cash_balance)를 사용
                cash_balance = float(balance.get("cash_balance") or 0)
                
                # 부동소수점 오차 등을 고려하여 일정 금액 이상일 때만 표시 (예: 10원)
                if cash_balance > 10:
                    weight_percent = round(cash_balance / class_total * 100, 2) if class_total > 0 else 0
                    items.append(
                        {
                            "name": "현금 (예수금)",
                            "ticker": "CASH",
                            "weight_percent": weight_percent,
                        }
                    )
            return items

        asset_order = ["stocks", "bonds", "alternatives", "cash"]
        sub_mp_payload = []
        for key in asset_order:
            detail = (sub_mp_details or {}).get(key)
            item = {
                "asset_class": key,
                "target": build_target_items(key),
                "actual": build_actual_items(key),
            }
            if detail:
                item["sub_mp_name"] = detail.get("sub_mp_name")
                item["sub_mp_description"] = detail.get("sub_mp_description")
                item["updated_at"] = detail.get("updated_at")
            
            sub_mp_payload.append(item)

        # ... (previous code)

        # 3) 리밸런싱 필요 여부 판단 (Drift Calculation)
        # rebalancing_engine의 check_rebalancing_needed 사용
        from service.macro_trading.rebalancing.rebalancing_engine import check_rebalancing_needed
        from service.macro_trading.rebalancing.config_retriever import get_rebalancing_config
        
        config = get_rebalancing_config()
        # 기본값 로드
        thresholds = {"mp": float(config.get("mp", 3.0)), "sub_mp": float(config.get("sub_mp", 5.0))}
        
        # 현재 상태 객체 구성 (rebalancing_engine에서 사용하는 형식으로 맞춤)
        # get_balance_info_api 결과(balance)를 그대로 사용할 수 있는지 확인 필요
        # rebalancing_engine의 asset_retriever.get_current_portfolio_state()는 balance 정보를 가공함
        # 여기서는 효율성을 위해 asset_retriever를 직접 호출하거나 balance 결과를 변환해야 함.
        # 중복 호출을 피하기 위해 asset_retriever를 사용하는 것이 가장 깔끔함.
        
        from service.macro_trading.rebalancing.asset_retriever import get_current_portfolio_state
        current_state_for_engine = get_current_portfolio_state(current_user.get("id"))
        
        # Target MP/Sub-MP 포맷 맞춤
        # rebalancing_engine은 target_retriever 형식을 따름.
        # 여기서 구한 target_alloc_norm, sub_mp_details를 engine이 원하는 대로 변환하거나
        # engine 내부 함수를 호출하는 것이 나음.
        
        # 간단하게 engine의 로직을 재사용하기 위해 필요한 데이터만 넘김
        # 하지만 engine.check_rebalancing_needed는 특정 포맷을 원함.
        # 가장 확실한 방법은 engine 내부 로직을 통해 Drift만 계산하는 것.
        
        rebalancing_needed = False
        drift_info = {}
        
        if current_state_for_engine:
            # target_retriever 형식으로 변환이 필요할 수 있으나, 
            # engine의 check_rebalancing_needed 인자를 보면: 
            # check_rebalancing_needed(current_state, target_mp, target_sub_mp, thresholds)
            # target_mp: {"stocks": 50.0, ...} (퍼센트 단위) -> target_alloc_norm 와 동일
            # target_sub_mp: {"stocks": {"etf_details": [...]}} -> sub_mp_details 와 거의 유사?
            # get_sub_mp_details 반환값 구조: {"stocks": {"etf_details": [{"ticker":..., "weight":...}]}}
            
            # target_alloc_norm의 키는 소문자여야 함 (이미 처리됨)
            
            # sub_mp_details 구조 확인 필요. 
            # get_sub_mp_details는 {"stocks": {"etf_details": [...]}} 형태 반환 예상.
            
            rebalancing_needed, drift_info = check_rebalancing_needed(
                current_state_for_engine, 
                target_alloc_norm, 
                sub_mp_details or {}, 
                thresholds
            )

        return {
            "status": "success",
            "data": {
                "mp": {
                    "target_allocation": target_alloc_norm,
                    "actual_allocation": actual_alloc,
                    **mp_info,
                },
                "sub_mp": sub_mp_payload,
                "rebalancing_status": {
                    "needed": rebalancing_needed,
                    "reasons": drift_info.get("reasons", []),
                    "drift_details": drift_info,
                    "thresholds": thresholds
                }
            },
        }
    except Exception as e:
        logging.error(f"Error fetching rebalancing status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class RebalanceTestRequest(BaseModel):
    max_phase: int = 5 # 2: Drift Check, 4: Plan & Validate, 5: Full Execution

@api_router.post("/macro-trading/rebalance/test")
async def test_rebalancing(
    req: RebalanceTestRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    리밸런싱 프로세스 테스트 실행
    max_phase에 따라 실행 범위 제어 가능
    """
    try:
        from service.macro_trading.rebalancing.rebalancing_engine import execute_rebalancing
        result = await execute_rebalancing(current_user.get("id"), max_phase=req.max_phase)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/search-stocks")
async def search_stocks(
    keyword: str = Query(..., description="검색 키워드 (종목명 일부)"),
    limit: int = Query(default=20, ge=1, le=100, description="최대 검색 결과 수")
):
    """종목명으로 티커 검색"""
    try:
        if not keyword or len(keyword.strip()) < 1:
            return {
                "status": "success",
                "data": [],
                "count": 0
            }

        from service.database.db import get_db_connection
        kw = f"%{keyword.strip()}%"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ticker, stock_name, market_type, last_updated
                FROM stock_tickers
                WHERE ticker LIKE %s OR stock_name LIKE %s
                ORDER BY stock_name
                LIMIT %s
            """, (kw, kw, limit))
            rows = cursor.fetchall()
            results = [
                {
                    "ticker": row.get("ticker"),
                    "stock_name": row.get("stock_name"),
                    "market_type": row.get("market_type"),
                    "last_updated": row.get("last_updated").isoformat() if row.get("last_updated") else None
                }
                for row in rows
            ]

        return {
            "status": "success",
            "data": results,
            "count": len(results)
        }
    except Exception as e:
        logging.error(f"Error searching stocks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/overview")
async def get_ai_overview():
    """AI 분석 Overview 조회 (Graph DB 기반)"""
    try:
        from service.macro_trading.overview_service import get_overview_data
        
        result = await get_overview_data()
        
        if not result or not result.get("data"):
            return {
                "status": "success",
                "data": None,
                "message": "AI 분석 결과가 아직 없습니다."
            }
            
        return result
            
    except Exception as e:
        logging.error(f"Error getting AI overview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/macro-trading/run-ai-analysis")
async def run_ai_analysis_manual(admin_user: dict = Depends(require_admin)):
    """수동 AI 분석 실행 (Admin 전용)"""
    try:
        from service.macro_trading.ai_strategist import run_ai_analysis
        
        logging.info(f"수동 AI 분석 실행 요청: {admin_user.get('username')}")
        
        trigger_user_id = admin_user.get("id") or admin_user.get("username")
        success = run_ai_analysis(triggered_by_user_id=trigger_user_id)
        
        if success:
            return {
                "status": "success",
                "message": "AI 분석이 완료되었습니다."
            }
        else:
            raise HTTPException(status_code=500, detail="AI 분석 실행에 실패했습니다.")
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error running AI analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/macro-trading/latest-strategy-decision")
async def get_latest_strategy_decision():
    """최신 AI 전략 결정 조회"""
    try:
        from service.database.db import get_db_connection
        import json
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id,
                    decision_date,
                    analysis_summary,
                    target_allocation,
                    quant_signals,
                    account_pnl,
                    created_at
                FROM ai_strategy_decisions
                ORDER BY decision_date DESC
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            
            if not row:
                return {
                    "status": "success",
                    "data": None,
                    "message": "AI 전략 결정이 아직 없습니다."
                }
            
            # JSON 필드 파싱
            target_allocation_raw = row['target_allocation']
            if isinstance(target_allocation_raw, str):
                target_allocation_raw = json.loads(target_allocation_raw)
            
            # MP 기반 저장 형식 처리
            mp_id = None
            target_allocation = None
            if isinstance(target_allocation_raw, dict):
                if "mp_id" in target_allocation_raw:
                    mp_id = target_allocation_raw["mp_id"]
                    target_allocation = target_allocation_raw.get("target_allocation", target_allocation_raw)
                else:
                    target_allocation = target_allocation_raw
            else:
                target_allocation = target_allocation_raw
            
            quant_signals = row.get('quant_signals')
            if quant_signals and isinstance(quant_signals, str):
                quant_signals = json.loads(quant_signals)
            

            
            account_pnl = row.get('account_pnl')
            if account_pnl and isinstance(account_pnl, str):
                account_pnl = json.loads(account_pnl)
            
            return {
                "status": "success",
                "data": {
                    "id": row['id'],
                    "decision_date": row['decision_date'].strftime("%Y-%m-%d %H:%M:%S") if row['decision_date'] else None,
                    "analysis_summary": row.get('analysis_summary'),
                    "mp_id": mp_id,
                    "target_allocation": target_allocation,
                    "quant_signals": quant_signals,

                    "account_pnl": account_pnl,
                    "created_at": row['created_at'].strftime("%Y-%m-%d %H:%M:%S") if row['created_at'] else None
                }
            }
    except Exception as e:
        logging.error(f"Error fetching latest strategy decision: {e}", exc_info=True)
        # AI 전략 결정이 없어도 에러가 아닌 빈 응답 반환
        return {
            "status": "success",
            "data": None,
            "message": "AI 전략 결정을 조회할 수 없습니다."
        }

@api_router.get("/macro-trading/strategy-decisions-history")
async def get_strategy_decisions_history(
    page: int = Query(default=1, ge=1, description="페이지 번호"),
    limit: int = Query(default=1, ge=1, le=100, description="페이지당 항목 수")
):
    """AI 전략 결정 이력 조회 (페이지네이션)"""
    try:
        from service.database.db import get_db_connection
        import json
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 전체 개수 조회
            cursor.execute("SELECT COUNT(*) as total FROM ai_strategy_decisions")
            total_count = cursor.fetchone()['total']
            
            # 페이지네이션 계산
            total_pages = (total_count + limit - 1) // limit
            offset = (page - 1) * limit
            
            # 데이터 조회
            cursor.execute("""
                SELECT 
                    id,
                    decision_date,
                    analysis_summary,
                    target_allocation,
                    recommended_stocks,
                    created_at
                FROM ai_strategy_decisions
                ORDER BY decision_date DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            
            rows = cursor.fetchall()
            
            # JSON 필드 파싱 및 데이터 변환
            result = []
            for row in rows:
                # target_allocation 파싱
                target_allocation_raw = row['target_allocation']
                if isinstance(target_allocation_raw, str):
                    target_allocation_raw = json.loads(target_allocation_raw)
                
                # MP 기반 저장 형식 처리 (mp_id와 target_allocation이 함께 저장됨)
                mp_id = None
                target_allocation = None
                sub_mp_data = None
                if isinstance(target_allocation_raw, dict):
                    # 새로운 형식: {"mp_id": "MP-4", "target_allocation": {...}, "sub_mp": {...}}
                    if "mp_id" in target_allocation_raw:
                        mp_id = target_allocation_raw["mp_id"]
                        # mp_id가 있으면 get_model_portfolio_allocation을 사용하여 실제 allocation 가져오기
                        from service.macro_trading.ai_strategist import get_model_portfolio_allocation
                        allocation_from_mp = get_model_portfolio_allocation(mp_id)
                        if allocation_from_mp:
                            target_allocation = allocation_from_mp
                        else:
                            # MP ID가 유효하지 않으면 저장된 target_allocation 사용
                            target_allocation = target_allocation_raw.get("target_allocation", target_allocation_raw)
                        
                        # Sub-MP 정보 추출
                        sub_mp_data = target_allocation_raw.get("sub_mp")
                    else:
                        # 기존 형식: 직접 target_allocation만 있음
                        target_allocation = target_allocation_raw
                else:
                    target_allocation = target_allocation_raw
                
                # Sub-MP 세부 종목 정보 가져오기
                sub_mp_details = None
                if sub_mp_data and mp_id:
                    from service.macro_trading.ai_strategist import get_sub_mp_details

                    sub_mp_details = get_sub_mp_details(sub_mp_data)
                
                recommended_stocks = row.get('recommended_stocks')
                if recommended_stocks:
                    if isinstance(recommended_stocks, str):
                        recommended_stocks = json.loads(recommended_stocks)
                else:
                    recommended_stocks = None
                
                # analysis_summary에서 reasoning 추출
                analysis_summary = row['analysis_summary'] or ''
                reasoning = ''
                if '판단 근거:' in analysis_summary:
                    parts = analysis_summary.split('판단 근거:')
                    if len(parts) > 1:
                        reasoning = parts[1].strip()
                        analysis_summary = parts[0].strip()
                
                # Sub-MP reasoning 추출
                sub_mp_reasoning = None
                if sub_mp_data and isinstance(sub_mp_data, dict):
                    sub_mp_reasoning = sub_mp_data.get('reasoning')
                
                result.append({
                    "id": row['id'],
                    "decision_date": row['decision_date'].strftime('%Y-%m-%d %H:%M:%S') if row['decision_date'] else None,
                    "analysis_summary": analysis_summary,
                    "reasoning": reasoning,
                    "mp_id": mp_id,
                    "target_allocation": target_allocation,
                    "sub_mp": sub_mp_details,
                    "sub_mp_reasoning": sub_mp_reasoning,
                    "recommended_stocks": recommended_stocks,
                    "created_at": row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if row['created_at'] else None
                })
            
            return {
                "status": "success",
                "data": result,
                "page": page,
                "limit": limit,
                "total": total_count,
                "total_pages": total_pages
            }
    except Exception as e:
        logging.error(f"Error fetching strategy decisions history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def convert_numpy_types(obj):
    """
    numpy 타입을 Python 기본 타입으로 변환하는 재귀 함수
    """
    import numpy as np
    
    if isinstance(obj, (np.integer, np.int_, np.intc, np.intp, np.int8,
                        np.int16, np.int32, np.int64, np.uint8, np.uint16,
                        np.uint32, np.uint64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return [convert_numpy_types(item) for item in obj.tolist()]
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj


@api_router.get("/macro-trading/quantitative-signals")
async def get_quantitative_signals(
    natural_rate: float = Query(default=2.0, description="자연 이자율 (%)"),
    target_inflation: float = Query(default=2.0, description="목표 인플레이션율 (%)"),
    liquidity_ma_weeks: Optional[int] = Query(default=None, description="유동성 이동평균 기간 (주, None이면 설정 파일에서 가져옴)")
):
    """AI 판단용 정량 시그널 조회 API
    
    모든 정량 시그널을 계산하여 반환합니다:
    - yield_curve_spread_trend: 장단기 금리차 추세 추종 전략
    - real_interest_rate: 실질 금리 (DFII10)
    - taylor_rule_signal: 테일러 준칙 신호
    - net_liquidity: 연준 순유동성
    - high_yield_spread: 하이일드 스프레드
    - additional_indicators: 추가 지표 (실업률, 고용 등)
    """
    try:
        from service.macro_trading.signals.quant_signals import QuantSignalCalculator
        from datetime import datetime
        
        calculator = QuantSignalCalculator()
        
        # 모든 정량 시그널 계산
        signals = calculator.calculate_all_signals(
            natural_rate=natural_rate,
            target_inflation=target_inflation,
            liquidity_ma_weeks=liquidity_ma_weeks
        )
        
        # 추가 지표 계산
        additional_indicators = calculator.get_additional_indicators()
        
        # 결과 구성
        result = {
            "status": "success",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "signals": {
                "yield_curve_spread_trend": signals.get("yield_curve_spread_trend"),
                "real_interest_rate": signals.get("real_interest_rate"),
                "taylor_rule_signal": signals.get("taylor_rule_signal"),
                "net_liquidity": signals.get("net_liquidity"),
                "high_yield_spread": signals.get("high_yield_spread"),
                "additional_indicators": additional_indicators
            },
            "parameters": {
                "natural_rate": natural_rate,
                "target_inflation": target_inflation,
                "liquidity_ma_weeks": liquidity_ma_weeks
            }
        }
        
        # None 값이 있는 시그널 확인
        missing_signals = [key for key, value in signals.items() if value is None]
        if missing_signals:
            result["warnings"] = {
                "message": f"{len(missing_signals)}개의 시그널을 계산할 수 없습니다.",
                "missing_signals": missing_signals
            }
        
        # numpy 타입을 Python 기본 타입으로 변환
        result = convert_numpy_types(result)
        
        return result
        
    except Exception as e:
        logging.error(f"Error calculating quantitative signals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))





class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "ko"  # "ko" or "en"
    news_id: Optional[int] = None  # 뉴스 ID (DB 저장용)
    field_type: Optional[str] = None  # 필드 타입: "title", "description", "country", "category"

@api_router.get("/macro-trading/briefing")
async def get_market_briefing():
    """최신 Market Briefing 조회 (Headlines 포함)"""
    try:
        from service.database.db import get_db_connection
        from service.macro_trading.ai_strategist import normalize_market_briefing_text
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, briefing_text, summary_text, created_at 
                FROM market_news_summaries 
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            # Headlines 조회 (최신 3개)
            cursor.execute("""
                SELECT title, link, published_at, source
                FROM economic_news
                ORDER BY published_at DESC
                LIMIT 3
            """)
            headlines = []
            for h in cursor.fetchall():
                 headlines.append({
                     "title": h['title'],
                     "link": h['link'],
                     "published_at": h['published_at'].strftime("%Y-%m-%d %H:%M:%S") if h['published_at'] else None,
                     "source": h['source']
                 })
            
            if row and row.get('briefing_text'):
                raw_briefing = row.get('briefing_text') or ""
                normalized_briefing = normalize_market_briefing_text(raw_briefing)
                normalized_summary = normalize_market_briefing_text(row.get('summary_text') or "")

                # 기존에 저장된 직렬화 문자열이 있으면 조회 시점에 정리 저장
                if normalized_briefing and normalized_briefing != raw_briefing and row.get('id'):
                    try:
                        cursor.execute("""
                            UPDATE market_news_summaries
                            SET briefing_text = %s
                            WHERE id = %s
                        """, (normalized_briefing, row['id']))
                    except Exception as update_err:
                        logging.warning(f"Market Briefing 정규화 저장 실패(id={row.get('id')}): {update_err}")

                return {
                    "status": "success",
                    "briefing": normalized_briefing,
                    "summary_text": normalized_summary,
                    "created_at": row['created_at'].strftime("%Y-%m-%d %H:%M:%S"),
                    "headlines": headlines
                }
            return {
                "status": "success",
                "briefing": None,
                "headlines": headlines,
                "message": "생성된 브리핑이 없습니다."
            }
    except Exception as e:
        import logging
        logging.error(f"Market Briefing 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/macro-trading/economic-news")
async def get_economic_news(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100)):
    """경제 뉴스 목록 조회 (페이지네이션)"""
    try:
        from service.database.db import get_db_connection
        
        offset = (page - 1) * limit
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 총 개수 조회
            cursor.execute("SELECT COUNT(*) as count FROM economic_news")
            total_count = cursor.fetchone()['count']
            
            # 뉴스 조회
            cursor.execute("""
                SELECT id, title, link, description, published_at, source, title_ko, description_ko
                FROM economic_news
                ORDER BY published_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            
            rows = cursor.fetchall()
            news_list = []
            for row in rows:
                news_list.append({
                    "id": row['id'],
                    "title": row.get('title_ko') or row['title'],
                    "original_title": row['title'],
                    "link": row.get('link'),
                    "description": row.get('description_ko') or row.get('description'),
                    "published_at": row['published_at'].strftime("%Y-%m-%d %H:%M:%S") if row['published_at'] else None,
                    "source": row.get('source')
                })
            
            import math
            total_pages = math.ceil(total_count / limit)
            
            return {
                "status": "success",
                "data": news_list,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total_count": total_count,
                    "total_pages": total_pages
                }
            }
            
    except Exception as e:
        import logging
        logging.error(f"경제 뉴스 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/macro-trading/translate")
async def translate_text(request: TranslateRequest):
    """텍스트 번역 API (DB 캐싱 지원)
    
    Args:
        request: TranslateRequest 객체 (text, target_lang, news_id, field_type)
    
    Returns:
        {
            "status": "success",
            "original_text": "...",
            "translated_text": "...",
            "target_lang": "ko",
            "from_cache": true/false
        }
    """
    logging.info(f"Translation request received: news_id={request.news_id}, field_type={request.field_type}, text_length={len(request.text) if request.text else 0}")
    
    try:
        from service.database.db import get_db_connection
        
        text = request.text
        target_lang = request.target_lang
        news_id = request.news_id
        field_type = request.field_type
        
        # country, category는 번역하지 않음
        if field_type in ["country", "category"]:
            logging.info(f"Skipping translation for field_type: {field_type}")
            return {
                "status": "success",
                "original_text": text,
                "translated_text": text,
                "target_lang": target_lang,
                "from_cache": False
            }
        
        # 한글 번역만 지원 (영어는 원문 반환)
        if target_lang != "ko":
            return {
                "status": "success",
                "original_text": text,
                "translated_text": text,
                "target_lang": target_lang,
                "from_cache": False
            }
        
        # 필드 타입에 따라 적절한 컬럼명 결정 (title, description만)
        field_map = {
            "title": "title_ko",
            "description": "description_ko"
        }
        
        # DB에서 번역 확인 (news_id와 field_type이 제공된 경우)
        if news_id and field_type and field_type in field_map:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                column_name = field_map[field_type]
                cursor.execute(f"""
                    SELECT {column_name}
                    FROM economic_news
                    WHERE id = %s AND {column_name} IS NOT NULL AND {column_name} != ''
                """, (news_id,))
                
                row = cursor.fetchone()
                if row and row.get(column_name):
                    logging.info(f"Translation found in cache: news_id={news_id}, field_type={field_type}")
                    return {
                        "status": "success",
                        "original_text": text,
                        "translated_text": row.get(column_name),
                        "target_lang": target_lang,
                        "from_cache": True
                    }
        
        # DB에 없으면 LLM으로 번역
        logging.info(f"Translating with LLM: news_id={news_id}, field_type={field_type}")
        from service.llm import llm_gemini_flash
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser
        
        prompt_text = f"다음 영어 텍스트를 자연스러운 한국어로 번역해주세요. 전문 용어는 그대로 유지하되, 문맥에 맞게 번역해주세요:\n\n{text}"
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a professional translator. Translate the given text accurately and naturally."),
            ("user", "{text}")
        ])
        
        llm = llm_gemini_flash()
        chain = prompt | llm | StrOutputParser()
        
        translated_text = chain.invoke({"text": prompt_text}).strip()
        logging.info(f"Translation completed: news_id={news_id}, field_type={field_type}, translated_length={len(translated_text)}")
        
        # 번역 결과를 DB에 저장 (news_id와 field_type이 제공된 경우)
        if news_id and field_type and field_type in field_map:
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    column_name = field_map[field_type]
                    cursor.execute(f"""
                        UPDATE economic_news
                        SET {column_name} = %s
                        WHERE id = %s
                    """, (translated_text, news_id))
                    conn.commit()
                    logging.info(f"Translation saved to DB: news_id={news_id}, field_type={field_type}")
            except Exception as e:
                logging.error(f"Failed to save translation to DB: {e}", exc_info=True)
        
        return {
            "status": "success",
            "original_text": text,
            "translated_text": translated_text,
            "target_lang": target_lang,
            "from_cache": False
        }
    except Exception as e:
        logging.error(f"Translation error: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "original_text": request.text,
            "translated_text": request.text,  # 에러 시 원문 반환
            "from_cache": False
        }

@api_router.get("/macro-trading/economic-news-data")
async def get_economic_news_data(
    hours: int = Query(default=24, ge=1, le=168, description="조회할 시간 범위 (시간, 기본값: 24시간, 최대: 168시간)"),
    group_by: str = Query(default="hour", description="그룹화 단위: 'hour' (1시간), '6hour' (6시간), 'day' (1일)", regex="^(hour|6hour|day)$")
):
    """경제 뉴스 데이터 조회 API (시간 단위 그룹화)
    
    FRED 데이터 API와 유사한 형식으로 시간 단위로 그룹화된 뉴스 데이터를 반환합니다.
    
    Args:
        hours: 조회할 시간 범위 (기본값: 24시간)
        group_by: 그룹화 단위 ('hour', '6hour', 'day')
    
    Returns:
        {
            "data": [
                {
                    "time": "2024-12-19 10:00:00",
                    "count": 5,
                    "news": [
                        {
                            "id": 1,
                            "title": "...",
                            "country": "United States",
                            "category": "Stock Market",
                            "published_at": "2024-12-19 10:15:00"
                        },
                        ...
                    ]
                },
                ...
            ],
            "count": 10,
            "hours": 24,
            "group_by": "hour",
            "summary": {
                "total_news": 10,
                "unique_countries": 5,
                "unique_categories": 8
            }
        }
    """
    try:
        from service.database.db import get_db_connection
        from datetime import datetime, timedelta
        from collections import defaultdict
        
        # 시간 범위 계산
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # 그룹화 단위에 따른 시간 포맷 결정
        if group_by == "hour":
            time_format = "%Y-%m-%d %H:00:00"
            time_truncate = "DATE_FORMAT(published_at, '%Y-%m-%d %H:00:00')"
        elif group_by == "6hour":
            # 6시간 단위: 0-5시, 6-11시, 12-17시, 18-23시
            time_format = "%Y-%m-%d %H:00:00"
            time_truncate = "DATE_FORMAT(DATE_SUB(published_at, INTERVAL HOUR(published_at) MOD 6 HOUR), '%Y-%m-%d %H:00:00')"
        else:  # day
            time_format = "%Y-%m-%d 00:00:00"
            time_truncate = "DATE_FORMAT(published_at, '%Y-%m-%d 00:00:00')"
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 시간 단위로 그룹화하여 뉴스 개수 조회
            cursor.execute(f"""
                SELECT 
                    {time_truncate} as time_group,
                    COUNT(*) as count
                FROM economic_news
                WHERE published_at >= %s
                GROUP BY time_group
                ORDER BY time_group DESC
            """, (cutoff_time,))
            
            grouped_counts = cursor.fetchall()
            
            # 각 시간 그룹별 상세 뉴스 조회
            data = []
            all_news = []
            countries = set()
            categories = set()
            
            for row in grouped_counts:
                time_group_str = row.get("time_group")
                count = row.get("count")
                
                # 해당 시간 그룹의 뉴스 상세 조회
                if group_by == "hour":
                    time_start = datetime.strptime(time_group_str, "%Y-%m-%d %H:00:00")
                    time_end = time_start + timedelta(hours=1)
                elif group_by == "6hour":
                    time_start = datetime.strptime(time_group_str, "%Y-%m-%d %H:00:00")
                    time_end = time_start + timedelta(hours=6)
                else:  # day
                    time_start = datetime.strptime(time_group_str, "%Y-%m-%d 00:00:00")
                    time_end = time_start + timedelta(days=1)
                
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
                        published_at
                    FROM economic_news
                    WHERE published_at >= %s AND published_at < %s
                    ORDER BY published_at DESC
                """, (time_start, time_end))
                
                news_items = cursor.fetchall()
                
                # 뉴스 리스트 구성
                news_list = []
                for news_row in news_items:
                    news_item = {
                        "id": news_row.get("id"),
                        "title": news_row.get("title"),
                        "title_ko": news_row.get("title_ko"),
                        "link": news_row.get("link"),
                        "country": news_row.get("country"),
                        "country_ko": news_row.get("country_ko"),
                        "category": news_row.get("category"),
                        "category_ko": news_row.get("category_ko"),
                        "description": news_row.get("description"),
                        "description_ko": news_row.get("description_ko"),
                        "published_at": news_row.get("published_at").strftime("%Y-%m-%d %H:%M:%S") if news_row.get("published_at") else None
                    }
                    news_list.append(news_item)
                    all_news.append(news_item)
                    
                    # 통계 수집
                    if news_row.get("country"):
                        countries.add(news_row.get("country"))
                    if news_row.get("category"):
                        categories.add(news_row.get("category"))
                
                data.append({
                    "time": time_group_str,
                    "count": count,
                    "news": news_list
                })
            
            # 요약 통계
            summary = {
                "total_news": len(all_news),
                "unique_countries": len(countries),
                "unique_categories": len(categories)
            }
            
            result = {
                "data": data,
                "count": len(data),
                "hours": hours,
                "group_by": group_by,
                "summary": summary
            }
            
            return result
            
    except Exception as e:
        logging.error(f"Error fetching economic news data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/current-strategy")
async def update_current_strategy(request: StrategyRequest):
    """전략을 업데이트합니다. (기본값은 upbit, 하위 호환성 유지)"""
    try:
        from service import strategy_manager
        strategy_manager.write_strategy('upbit', request.strategy)
        logging.info(f"Current strategy updated (upbit): {request.strategy}")
        return {"status": "success", "platform": "upbit", "strategy": request.strategy}
    except Exception as e:
        logging.error(f"Error updating current strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/current-strategy/{platform}")
async def update_current_strategy_platform(platform: str, request: StrategyRequest):
    """플랫폼별 전략을 업데이트합니다."""
    try:
        from service import strategy_manager
        strategy_manager.write_strategy(platform, request.strategy)
        logging.info(f"Current strategy updated ({platform}): {request.strategy}")
        return {"status": "success", "platform": platform, "strategy": request.strategy}
    except Exception as e:
        logging.error(f"Error updating current strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 인증 관련 API
@api_router.post("/auth/register")
async def register(request: RegisterRequest):
    """회원가입"""
    try:
        user = auth.create_user(
            username=request.username,
            password=request.password,
            role="user"
        )
        return {"status": "success", "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error registering user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/auth/login")
async def login(request: MFALoginRequest):
    """로그인 (MFA 지원)"""
    try:
        user = auth.get_user_by_id(request.username)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        if not auth.verify_password(request.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        # MFA 활성화 여부 확인
        mfa_enabled = user.get("mfa_enabled", False)
        
        if mfa_enabled:
            # MFA 코드가 제공되지 않았으면 MFA 코드 요청 응답
            if not request.mfa_code:
                return {
                    "status": "mfa_required",
                    "message": "MFA code is required",
                    "mfa_enabled": True
                }
            
            # MFA 코드 검증
            if not auth.verify_user_mfa(user["id"], request.mfa_code):
                raise HTTPException(status_code=401, detail="Invalid MFA code")
        
        # JWT 토큰 생성
        token = auth.create_access_token({
            "id": user["id"],
            "role": user["role"]
        })
        
        # admin role을 가진 사용자인지 확인
        is_sys_admin = user.get("role") == "admin"
        
        return {
            "status": "success",
            "token": token,
            "user": {
                "id": user["id"],
                "role": user["role"],
                "is_system_admin": is_sys_admin
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error logging in: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """현재 로그인한 사용자 정보 조회"""
    # admin role을 가진 사용자인지 확인
    is_sys_admin = current_user.get("role") == "admin"
    
    return {
        "id": current_user["id"],
        "role": current_user["role"],
        "is_system_admin": is_sys_admin
    }

# 사용자별 KIS Credential API
@api_router.get("/user/kis-credentials")
async def get_user_kis_credentials(current_user: dict = Depends(get_current_user)):
    """사용자별 KIS API 인증 정보 조회"""
    try:
        from service.database.db import get_db_connection
        from service.utils.encryption import decrypt_data
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT kis_id, account_no, is_simulation
                FROM user_kis_credentials
                WHERE user_id = %s
            """, (current_user["id"],))
            row = cursor.fetchone()
            
            if not row:
                return {
                    "status": "success",
                    "has_credentials": False,
                    "data": None
                }
            
            # 민감정보(app_key, app_secret)는 절대 반환하지 않는다.
            return {
                "status": "success",
                "has_credentials": True,
                "data": {
                    "kis_id": row["kis_id"],
                    "account_no": row["account_no"],
                    "is_simulation": bool(row.get("is_simulation", False))
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting KIS credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/user/kis-credentials")
async def save_user_kis_credentials(
    request: KISCredentialRequest,
    current_user: dict = Depends(get_current_user)
):
    """사용자별 KIS API 인증 정보 저장/업데이트"""
    try:
        from service.database.db import get_db_connection
        from service.utils.encryption import encrypt_data
        
        # 암호화
        app_key_encrypted = encrypt_data(request.app_key)
        app_secret_encrypted = encrypt_data(request.app_secret)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 기존 데이터 확인
            cursor.execute("""
                SELECT id FROM user_kis_credentials WHERE user_id = %s
            """, (current_user["id"],))
            existing = cursor.fetchone()
            
            if existing:
                # 업데이트
                cursor.execute("""
                    UPDATE user_kis_credentials
                    SET kis_id = %s,
                        account_no = %s,
                        app_key_encrypted = %s,
                        app_secret_encrypted = %s,
                        is_simulation = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                """, (
                    request.kis_id,
                    request.account_no,
                    app_key_encrypted,
                    app_secret_encrypted,
                    request.is_simulation,
                    current_user["id"]
                ))
            else:
                # 새로 생성
                cursor.execute("""
                    INSERT INTO user_kis_credentials
                    (user_id, kis_id, account_no, app_key_encrypted, app_secret_encrypted, is_simulation)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    current_user["id"],
                    request.kis_id,
                    request.account_no,
                    app_key_encrypted,
                    app_secret_encrypted,
                    request.is_simulation
                ))
            
            conn.commit()
            
            return {
                "status": "success",
                "message": "KIS 인증 정보가 저장되었습니다."
            }
    except Exception as e:
        logging.error(f"Error saving KIS credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 사용자별 Upbit Credential API
@api_router.get("/user/upbit-credentials")
async def get_user_upbit_credentials(current_user: dict = Depends(get_current_user)):
    """사용자별 Upbit API 인증 정보 조회"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id
                FROM user_upbit_credentials
                WHERE user_id = %s
            """, (current_user["id"],))
            row = cursor.fetchone()
            
            if not row:
                return {
                    "status": "success",
                    "has_credentials": False,
                    "data": None
                }
            
            # 민감정보(access_key, secret_key)는 절대 반환하지 않는다.
            return {
                "status": "success",
                "has_credentials": True,
                "data": {
                    "user_id": row["user_id"]
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting Upbit credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/user/upbit-credentials")
async def save_user_upbit_credentials(
    request: UpbitCredentialRequest,
    current_user: dict = Depends(get_current_user)
):
    """사용자별 Upbit API 인증 정보 저장/업데이트"""
    try:
        from service.database.db import get_db_connection
        from service.utils.encryption import encrypt_data
        import hashlib
        
        # 암호화
        access_key_encrypted = encrypt_data(request.access_key)
        secret_key_encrypted = encrypt_data(request.secret_key)
        
        # 해시 기반 ID 생성
        id_str = f"{current_user['id']}_upbit"
        id_hash = hashlib.sha256(id_str.encode()).hexdigest()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 기존 데이터 확인
            cursor.execute("""
                SELECT id FROM user_upbit_credentials WHERE user_id = %s
            """, (current_user["id"],))
            existing = cursor.fetchone()
            
            if existing:
                # 업데이트
                cursor.execute("""
                    UPDATE user_upbit_credentials
                    SET access_key = %s,
                        secret_key = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                """, (
                    access_key_encrypted,
                    secret_key_encrypted,
                    current_user["id"]
                ))
            else:
                # 새로 생성
                cursor.execute("""
                    INSERT INTO user_upbit_credentials
                    (id, user_id, access_key, secret_key)
                    VALUES (%s, %s, %s, %s)
                """, (
                    id_hash,
                    current_user["id"],
                    access_key_encrypted,
                    secret_key_encrypted
                ))
            
            conn.commit()
            
            return {
                "status": "success",
                "message": "Upbit 인증 정보가 저장되었습니다."
            }
    except Exception as e:
        logging.error(f"Error saving Upbit credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# MFA 관련 API
@api_router.get("/user/mfa/status")
async def get_mfa_status(current_user: dict = Depends(get_current_user)):
    """MFA 상태 조회"""
    try:
        status_data = auth.get_user_mfa_status(current_user["id"])
        return {
            "status": "success",
            "data": status_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting MFA status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/user/mfa/setup")
async def setup_mfa(current_user: dict = Depends(get_current_user)):
    """MFA 설정 시작 (QR 코드 생성)"""
    try:
        result = auth.setup_mfa(current_user["id"])
        return {
            "status": "success",
            "data": {
                "secret": result["secret"],  # 임시 Secret (설정 완료 전까지만 사용)
                "qr_code": result["qr_code"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error setting up MFA: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/user/mfa/verify-setup")
async def verify_mfa_setup(
    request: MFAVerifySetupRequest,
    current_user: dict = Depends(get_current_user)
):
    """MFA 설정 완료 (코드 검증)"""
    try:
        result = auth.verify_mfa_setup(
            current_user["id"],
            request.secret,
            request.code
        )
        return {
            "status": "success",
            "message": "MFA가 활성화되었습니다.",
            "data": {
                "backup_codes": result["backup_codes"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error verifying MFA setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/user/mfa/disable")
async def disable_mfa(
    request: MFADisableRequest,
    current_user: dict = Depends(get_current_user)
):
    """MFA 비활성화"""
    try:
        auth.disable_mfa(current_user["id"], request.password)
        return {
            "status": "success",
            "message": "MFA가 비활성화되었습니다."
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error disabling MFA: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/user/mfa/regenerate-backup-codes")
async def regenerate_backup_codes(
    request: MFARegenerateBackupCodesRequest,
    current_user: dict = Depends(get_current_user)
):
    """백업 코드 재생성"""
    try:
        backup_codes = auth.regenerate_backup_codes(
            current_user["id"],
            request.password
        )
        return {
            "status": "success",
            "message": "백업 코드가 재생성되었습니다.",
            "data": {
                "backup_codes": backup_codes
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error regenerating backup codes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Admin 전용 API
@api_router.get("/admin/users")
async def get_all_users(admin_user: dict = Depends(require_admin)):
    """모든 사용자 조회 (admin 전용)"""
    try:
        users = auth.get_all_users()
        return {"status": "success", "users": users}
    except Exception as e:
        logging.error(f"Error getting users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/admin/users/{user_id}")
async def update_user(user_id: str, request: UserUpdateRequest, admin_user: dict = Depends(require_admin)):
    """사용자 정보 업데이트 (admin 전용)"""
    try:
        user = auth.update_user(
            user_id=user_id,
            new_user_id=request.username,
            role=request.role
        )
        return {"status": "success", "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, admin_user: dict = Depends(require_admin)):
    """사용자 삭제 (admin 전용)"""
    try:
        # 자기 자신은 삭제 불가
        if user_id == admin_user["id"]:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")
        
        deleted = auth.delete_user(user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {"status": "success", "message": "User deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/macro-indicators/status")
async def get_macro_indicator_status(admin_user: dict = Depends(require_admin)):
    """미국/한국 경제지표 수집 상태 조회 (admin 전용)"""
    try:
        from service.macro_trading.indicator_health import get_macro_indicator_health_snapshot

        snapshot = get_macro_indicator_health_snapshot()
        return {"status": "success", **snapshot}
    except Exception as e:
        logging.error(f"Error getting macro indicator status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _to_iso_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _record_to_dict(record: Any) -> Dict[str, Any]:
    if record is None:
        return {}
    if hasattr(record, "data"):
        return record.data()
    try:
        return dict(record)
    except Exception:
        return {}


def _build_neo4j_db_summary(database: str) -> Dict[str, Any]:
    started_at = time.perf_counter()
    try:
        driver = get_neo4j_driver(database)
        with driver.session() as session:
            session.run("RETURN 1 AS ok").single()
            node_row = _record_to_dict(session.run("MATCH (n) RETURN count(n) AS count").single())
            rel_row = _record_to_dict(session.run("MATCH ()-[r]->() RETURN count(r) AS count").single())

            label_rows = session.run(
                """
                UNWIND ['Document', 'Event', 'Fact', 'Claim', 'Evidence', 'Entity', 'EconomicIndicator', 'MacroTheme'] AS label
                CALL {
                  WITH label
                  MATCH (n)
                  WHERE label IN labels(n)
                  RETURN count(n) AS cnt
                }
                RETURN label, cnt
                """
            )
            relationship_rows = session.run(
                """
                UNWIND ['MENTIONS', 'ABOUT_THEME', 'AFFECTS', 'HAS_EVIDENCE', 'SUPPORTS', 'CAUSES', 'ABOUT', 'BELONGS_TO'] AS rel_type
                CALL {
                  WITH rel_type
                  MATCH ()-[r]->()
                  WHERE type(r) = rel_type
                  RETURN count(r) AS cnt
                }
                RETURN rel_type, cnt
                """
            )

            label_counts: Dict[str, int] = {}
            for row in label_rows:
                label_name = row.get("label")
                label_counts[label_name] = _safe_int(row.get("cnt"))

            relationship_counts: Dict[str, int] = {}
            for row in relationship_rows:
                rel_type = row.get("rel_type")
                relationship_counts[rel_type] = _safe_int(row.get("cnt"))

        return {
            "database": database,
            "status": "success",
            "message": "connected",
            "response_ms": round((time.perf_counter() - started_at) * 1000, 1),
            "node_count": _safe_int(node_row.get("count")),
            "relationship_count": _safe_int(rel_row.get("count")),
            "label_counts": label_counts,
            "relationship_type_counts": relationship_counts,
        }
    except Exception as exc:
        logging.error("Neo4j summary failed (%s): %s", database, exc, exc_info=True)
        return {
            "database": database,
            "status": "error",
            "message": str(exc),
            "response_ms": round((time.perf_counter() - started_at) * 1000, 1),
            "node_count": 0,
            "relationship_count": 0,
            "label_counts": {},
            "relationship_type_counts": {},
        }


def _collect_macro_graph_extraction_summary() -> Dict[str, Any]:
    try:
        driver = get_neo4j_driver("macro")
        with driver.session() as session:
            summary_row = _record_to_dict(
                session.run(
                    """
                    MATCH (d:Document)
                    RETURN count(d) AS total_documents,
                           count(CASE WHEN d.extraction_status = 'success' THEN 1 END) AS success_documents,
                           count(CASE WHEN d.extraction_status = 'failed' THEN 1 END) AS failed_documents,
                           count(CASE WHEN d.extraction_status = 'pending' THEN 1 END) AS pending_status_documents,
                           count(CASE WHEN d.extraction_status IS NULL THEN 1 END) AS null_status_documents,
                           count(CASE
                                  WHEN d.extraction_status = 'failed'
                                       AND (
                                         d.extraction_updated_at IS NULL
                                         OR d.extraction_updated_at <= datetime() - duration({minutes: 180})
                                       )
                                  THEN 1 END
                           ) AS retryable_failed_documents,
                           count(CASE
                                  WHEN d.extraction_status IS NULL OR d.extraction_status = 'pending'
                                  THEN 1 END
                           ) AS pending_candidates,
                           count(CASE
                                  WHEN d.extraction_updated_at >= datetime() - duration({hours: 24})
                                  THEN 1 END
                           ) AS extracted_last_24h,
                           max(d.published_at) AS latest_published_at,
                           max(d.extraction_updated_at) AS latest_extraction_updated_at
                    """
                ).single()
            )

            recent_rows = []
            for row in session.run(
                """
                MATCH (d:Document)
                RETURN d.doc_id AS doc_id,
                       d.title AS title,
                       d.country_code AS country_code,
                       d.category AS category,
                       d.extraction_status AS extraction_status,
                       d.extraction_last_error AS extraction_last_error,
                       d.published_at AS published_at,
                       d.extraction_updated_at AS extraction_updated_at
                ORDER BY coalesce(d.extraction_updated_at, d.published_at) DESC
                LIMIT 20
                """
            ):
                recent_rows.append(
                    {
                        "doc_id": row.get("doc_id"),
                        "title": row.get("title"),
                        "country_code": row.get("country_code"),
                        "category": row.get("category"),
                        "extraction_status": row.get("extraction_status") or "unknown",
                        "extraction_last_error": row.get("extraction_last_error"),
                        "published_at": _to_iso_or_none(row.get("published_at")),
                        "extraction_updated_at": _to_iso_or_none(row.get("extraction_updated_at")),
                    }
                )

            failed_rows = []
            for row in session.run(
                """
                MATCH (d:Document)
                WHERE d.extraction_status = 'failed'
                RETURN d.doc_id AS doc_id,
                       d.title AS title,
                       d.extraction_last_error AS extraction_last_error,
                       d.extraction_updated_at AS extraction_updated_at
                ORDER BY d.extraction_updated_at DESC
                LIMIT 10
                """
            ):
                failed_rows.append(
                    {
                        "doc_id": row.get("doc_id"),
                        "title": row.get("title"),
                        "extraction_last_error": row.get("extraction_last_error"),
                        "extraction_updated_at": _to_iso_or_none(row.get("extraction_updated_at")),
                    }
                )

        return {
            "status": "success",
            "total_documents": _safe_int(summary_row.get("total_documents")),
            "success_documents": _safe_int(summary_row.get("success_documents")),
            "failed_documents": _safe_int(summary_row.get("failed_documents")),
            "pending_status_documents": _safe_int(summary_row.get("pending_status_documents")),
            "null_status_documents": _safe_int(summary_row.get("null_status_documents")),
            "pending_candidates": _safe_int(summary_row.get("pending_candidates")),
            "retryable_failed_documents": _safe_int(summary_row.get("retryable_failed_documents")),
            "extracted_last_24h": _safe_int(summary_row.get("extracted_last_24h")),
            "latest_published_at": _to_iso_or_none(summary_row.get("latest_published_at")),
            "latest_extraction_updated_at": _to_iso_or_none(summary_row.get("latest_extraction_updated_at")),
            "recent_documents": recent_rows,
            "recent_failed_documents": failed_rows,
        }
    except Exception as exc:
        logging.error("Macro graph extraction summary failed: %s", exc, exc_info=True)
        return {
            "status": "error",
            "message": str(exc),
            "total_documents": 0,
            "success_documents": 0,
            "failed_documents": 0,
            "pending_status_documents": 0,
            "null_status_documents": 0,
            "pending_candidates": 0,
            "retryable_failed_documents": 0,
            "extracted_last_24h": 0,
            "latest_published_at": None,
            "latest_extraction_updated_at": None,
            "recent_documents": [],
            "recent_failed_documents": [],
        }


@api_router.get("/admin/neo4j-monitoring")
async def get_admin_neo4j_monitoring(admin_user: dict = Depends(require_admin)):
    """
    Admin Neo4j/수집 파이프라인 모니터링 스냅샷.
    """
    try:
        from service.database.db import get_db_connection
        from service.macro_trading.indicator_health import get_macro_indicator_health_snapshot

        news_summary: Dict[str, Any] = {
            "total_news": 0,
            "news_last_24h": 0,
            "news_last_7d": 0,
            "collected_last_24h": 0,
            "last_published_at": None,
            "last_collected_at": None,
            "by_country_last_7d": [],
        }
        fred_summary: Dict[str, Any] = {
            "total_rows": 0,
            "indicator_count": 0,
            "rows_last_24h": 0,
            "rows_last_7d": 0,
            "last_observation_date": None,
            "last_collected_at": None,
            "daily_rows_last_7d": [],
        }

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT count(*) AS total_news,
                           sum(CASE WHEN published_at >= NOW() - INTERVAL 1 DAY THEN 1 ELSE 0 END) AS news_last_24h,
                           sum(CASE WHEN published_at >= NOW() - INTERVAL 7 DAY THEN 1 ELSE 0 END) AS news_last_7d,
                           sum(CASE WHEN collected_at >= NOW() - INTERVAL 1 DAY THEN 1 ELSE 0 END) AS collected_last_24h,
                           max(published_at) AS last_published_at,
                           max(collected_at) AS last_collected_at
                    FROM economic_news
                    """
                )
                row = cursor.fetchone() or {}
                news_summary.update(
                    {
                        "total_news": _safe_int(row.get("total_news")),
                        "news_last_24h": _safe_int(row.get("news_last_24h")),
                        "news_last_7d": _safe_int(row.get("news_last_7d")),
                        "collected_last_24h": _safe_int(row.get("collected_last_24h")),
                        "last_published_at": _to_iso_or_none(row.get("last_published_at")),
                        "last_collected_at": _to_iso_or_none(row.get("last_collected_at")),
                    }
                )

                cursor.execute(
                    """
                    SELECT COALESCE(country, 'Unknown') AS country,
                           count(*) AS count
                    FROM economic_news
                    WHERE published_at >= NOW() - INTERVAL 7 DAY
                    GROUP BY COALESCE(country, 'Unknown')
                    ORDER BY count DESC
                    LIMIT 12
                    """
                )
                news_summary["by_country_last_7d"] = [
                    {"country": row.get("country"), "count": _safe_int(row.get("count"))}
                    for row in cursor.fetchall()
                ]

                cursor.execute(
                    """
                    SELECT count(*) AS total_rows,
                           count(DISTINCT indicator_code) AS indicator_count,
                           sum(CASE WHEN created_at >= NOW() - INTERVAL 1 DAY THEN 1 ELSE 0 END) AS rows_last_24h,
                           sum(CASE WHEN created_at >= NOW() - INTERVAL 7 DAY THEN 1 ELSE 0 END) AS rows_last_7d,
                           max(date) AS last_observation_date,
                           max(created_at) AS last_collected_at
                    FROM fred_data
                    """
                )
                row = cursor.fetchone() or {}
                fred_summary.update(
                    {
                        "total_rows": _safe_int(row.get("total_rows")),
                        "indicator_count": _safe_int(row.get("indicator_count")),
                        "rows_last_24h": _safe_int(row.get("rows_last_24h")),
                        "rows_last_7d": _safe_int(row.get("rows_last_7d")),
                        "last_observation_date": _to_iso_or_none(row.get("last_observation_date")),
                        "last_collected_at": _to_iso_or_none(row.get("last_collected_at")),
                    }
                )

                cursor.execute(
                    """
                    SELECT DATE(created_at) AS day, count(*) AS rows
                    FROM fred_data
                    WHERE created_at >= NOW() - INTERVAL 7 DAY
                    GROUP BY DATE(created_at)
                    ORDER BY day DESC
                    """
                )
                fred_summary["daily_rows_last_7d"] = [
                    {"day": _to_iso_or_none(row.get("day")), "rows": _safe_int(row.get("rows"))}
                    for row in cursor.fetchall()
                ]
        except Exception as db_exc:
            logging.error("Admin monitoring DB summary failed: %s", db_exc, exc_info=True)
            news_summary["status"] = "error"
            news_summary["message"] = str(db_exc)
            fred_summary["status"] = "error"
            fred_summary["message"] = str(db_exc)

        indicator_snapshot = get_macro_indicator_health_snapshot()
        stale_or_missing_indicators = [
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "country": item.get("country"),
                "health": item.get("health"),
                "lag_hours": item.get("lag_hours"),
                "expected_interval_hours": item.get("expected_interval_hours"),
                "last_collected_at": item.get("last_collected_at"),
                "note": item.get("note"),
            }
            for item in indicator_snapshot.get("indicators", [])
            if item.get("health") in {"stale", "missing"}
        ]
        stale_or_missing_indicators.sort(
            key=lambda item: (
                0 if item.get("health") == "stale" else 1,
                -(item.get("lag_hours") or 0),
                item.get("code") or "",
            )
        )

        neo4j_architecture = _build_neo4j_db_summary("architecture")
        neo4j_macro = _build_neo4j_db_summary("macro")
        macro_extraction = _collect_macro_graph_extraction_summary()

        scheduler_jobs: List[Dict[str, Any]] = []
        try:
            for job in schedule.get_jobs():
                scheduler_jobs.append(
                    {
                        "tags": sorted(list(job.tags)) if job.tags else [],
                        "interval": _safe_int(getattr(job, "interval", 0)),
                        "unit": str(getattr(job, "unit", "")),
                        "next_run": _to_iso_or_none(getattr(job, "next_run", None)),
                        "last_run": _to_iso_or_none(getattr(job, "last_run", None)),
                        "at_time": str(getattr(job, "at_time", "")) if getattr(job, "at_time", None) else None,
                    }
                )
        except Exception as schedule_exc:
            logging.warning("Scheduler job snapshot failed: %s", schedule_exc)

        flow_status_news = "healthy" if news_summary.get("news_last_24h", 0) > 0 else "warning"
        flow_status_graph = (
            "error"
            if macro_extraction.get("status") == "error"
            else ("warning" if macro_extraction.get("pending_candidates", 0) > 0 else "healthy")
        )
        flow_status_fred = "healthy" if fred_summary.get("rows_last_24h", 0) > 0 else "warning"
        stale_count = len([x for x in stale_or_missing_indicators if x.get("health") == "stale"])
        missing_count = len([x for x in stale_or_missing_indicators if x.get("health") == "missing"])
        flow_status_indicator = "warning" if (stale_count + missing_count) > 0 else "healthy"
        flow_status_neo4j = (
            "healthy"
            if neo4j_architecture.get("status") == "success" and neo4j_macro.get("status") == "success"
            else "error"
        )

        news_reason = None
        if flow_status_news != "healthy":
            news_reason = (
                "최근 24시간 기준 발행 뉴스 수가 0건입니다. "
                f"(24h={news_summary.get('news_last_24h', 0)}, 7d={news_summary.get('news_last_7d', 0)})"
            )

        graph_sync_reason = None
        if flow_status_graph == "error":
            graph_sync_reason = (
                f"Macro Graph 추출 상태 오류: {macro_extraction.get('message') or 'unknown error'}"
            )
        elif flow_status_graph == "warning":
            graph_sync_reason = (
                "미처리/재시도 대상 문서가 남아 있습니다. "
                f"(pending={macro_extraction.get('pending_candidates', 0)}, "
                f"retryable_failed={macro_extraction.get('retryable_failed_documents', 0)})"
            )

        llm_extraction_reason = None
        if flow_status_graph == "error":
            llm_extraction_reason = (
                f"LLM 추출 파이프라인 오류: {macro_extraction.get('message') or 'unknown error'}"
            )
        elif flow_status_graph == "warning":
            llm_extraction_reason = (
                "백로그 추출이 아직 완료되지 않았습니다. "
                f"(success={macro_extraction.get('success_documents', 0)}, "
                f"failed={macro_extraction.get('failed_documents', 0)}, "
                f"pending={macro_extraction.get('pending_candidates', 0)})"
            )

        fred_reason = None
        if flow_status_fred != "healthy":
            fred_reason = (
                "최근 24시간 fred_data 적재 행이 0건입니다. "
                f"(24h={fred_summary.get('rows_last_24h', 0)}, 7d={fred_summary.get('rows_last_7d', 0)})"
            )

        indicator_reason = None
        if flow_status_indicator != "healthy":
            indicator_reason = (
                "수집 주기 대비 지연/미수집 지표가 존재합니다. "
                f"(stale={stale_count}, missing={missing_count})"
            )

        neo4j_reason = None
        if flow_status_neo4j != "healthy":
            neo4j_reason = (
                "Neo4j 연결/쿼리 점검 필요. "
                f"(macro={neo4j_macro.get('status')}:{neo4j_macro.get('message')}, "
                f"architecture={neo4j_architecture.get('status')}:{neo4j_architecture.get('message')})"
            )

        pipeline_flow = [
            {
                "id": "news_collection",
                "title": "뉴스 수집",
                "description": "TradingEconomics Stream -> MySQL economic_news",
                "schedule": "매 1시간",
                "status": flow_status_news,
                "metric": f"24h {news_summary.get('news_last_24h', 0)}건 / 7d {news_summary.get('news_last_7d', 0)}건",
                "reason": news_reason,
            },
            {
                "id": "graph_sync",
                "title": "문서 그래프 동기화",
                "description": "MySQL news -> Neo4j Document + ABOUT_THEME + MENTIONS",
                "schedule": "매 2시간",
                "status": flow_status_graph,
                "metric": f"Document {macro_extraction.get('total_documents', 0)}개",
                "reason": graph_sync_reason,
            },
            {
                "id": "llm_extraction",
                "title": "LLM 추출 적재",
                "description": "Document -> Event/Fact/Claim/Evidence/AFFECTS",
                "schedule": "백로그 배치",
                "status": flow_status_graph,
                "metric": f"pending {macro_extraction.get('pending_candidates', 0)} / retryable_failed {macro_extraction.get('retryable_failed_documents', 0)}",
                "reason": llm_extraction_reason,
            },
            {
                "id": "fred_ingestion",
                "title": "FRED 정량 수집",
                "description": "FRED API -> MySQL fred_data",
                "schedule": "일별 스케줄",
                "status": flow_status_fred,
                "metric": f"24h {fred_summary.get('rows_last_24h', 0)}행 / indicator {fred_summary.get('indicator_count', 0)}개",
                "reason": fred_reason,
            },
            {
                "id": "indicator_health",
                "title": "지표 상태 평가",
                "description": "수집 주기 대비 지연/미수집 감시",
                "schedule": "조회 시 실시간",
                "status": flow_status_indicator,
                "metric": f"stale {stale_count} / missing {missing_count}",
                "reason": indicator_reason,
            },
            {
                "id": "graph_serving",
                "title": "Graph 질의 제공",
                "description": "Ontology/Macro Graph 질의 처리",
                "schedule": "API 요청 시",
                "status": flow_status_neo4j,
                "metric": f"macro {neo4j_macro.get('status')} / architecture {neo4j_architecture.get('status')}",
                "reason": neo4j_reason,
            },
        ]

        return {
            "status": "success",
            "generated_at": datetime.now().isoformat(),
            "neo4j": {
                "architecture": neo4j_architecture,
                "macro": neo4j_macro,
            },
            "macro_graph": {
                "extraction": macro_extraction,
            },
            "ingestion": {
                "news": news_summary,
                "fred": fred_summary,
                "indicators": {
                    "summary": indicator_snapshot.get("summary", {}),
                    "stale_or_missing_count": len(stale_or_missing_indicators),
                    "stale_or_missing_indicators": stale_or_missing_indicators[:20],
                },
            },
            "scheduler": {
                "jobs": scheduler_jobs,
                "pipeline_flow": pipeline_flow,
            },
        }
    except Exception as exc:
        logging.error("Error getting admin neo4j monitoring snapshot: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# 포트폴리오 관리 API (admin 전용)
@api_router.get("/admin/portfolios/model-portfolios")
async def get_model_portfolios(admin_user: dict = Depends(require_admin)):
    """모델 포트폴리오 목록 조회 (admin 전용)"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # stocks_allocation, bonds_allocation, alternatives_allocation, cash_allocation 컬럼 사용
            cursor.execute("""
                SELECT id, name, description, strategy, 
                       stocks_allocation, bonds_allocation, 
                       alternatives_allocation, cash_allocation,
                       display_order, is_active, created_at, updated_at
                FROM model_portfolios
                ORDER BY display_order, id
            """)
            rows = cursor.fetchall()
            
            portfolios = []
            for row in rows:
                # NULL 값 처리 및 타입 변환
                allocation_stocks = row.get("stocks_allocation") or 0
                allocation_bonds = row.get("bonds_allocation") or 0
                allocation_alternatives = row.get("alternatives_allocation") or 0
                allocation_cash = row.get("cash_allocation") or 0
                
                portfolios.append({
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "strategy": row["strategy"],
                    "allocation": {
                        "Stocks": float(allocation_stocks) if allocation_stocks is not None else 0.0,
                        "Bonds": float(allocation_bonds) if allocation_bonds is not None else 0.0,
                        "Alternatives": float(allocation_alternatives) if allocation_alternatives is not None else 0.0,
                        "Cash": float(allocation_cash) if allocation_cash is not None else 0.0
                    },
                    "display_order": row["display_order"],
                    "is_active": bool(row["is_active"]),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
                })
            
            return {"status": "success", "portfolios": portfolios}
    except Exception as e:
        logging.error(f"Error getting model portfolios: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/portfolios/model-portfolios/{mp_id}")
async def update_model_portfolio(
    mp_id: str,
    request: dict,
    admin_user: dict = Depends(require_admin)
):
    """모델 포트폴리오 업데이트 (admin 전용)"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            allocation = request.get("allocation", {})
            # stocks_allocation, bonds_allocation, alternatives_allocation, cash_allocation 컬럼 사용
            cursor.execute("""
                UPDATE model_portfolios
                SET name = %s, description = %s, strategy = %s,
                    stocks_allocation = %s, bonds_allocation = %s,
                    alternatives_allocation = %s, cash_allocation = %s,
                    display_order = %s, is_active = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                request.get("name"),
                request.get("description"),
                request.get("strategy"),
                allocation.get("Stocks", 0),
                allocation.get("Bonds", 0),
                allocation.get("Alternatives", 0),
                allocation.get("Cash", 0),
                request.get("display_order", 0),
                request.get("is_active", True),
                mp_id
            ))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Model portfolio not found")
            
            conn.commit()
            
            # 캐시 갱신
            from service.macro_trading.ai_strategist import refresh_portfolio_cache
            refresh_portfolio_cache()
            
            return {"status": "success", "message": "Model portfolio updated"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating model portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/portfolios/sub-model-portfolios")
async def get_sub_model_portfolios(admin_user: dict = Depends(require_admin)):
    """Sub-MP 포트폴리오 목록 조회 (admin 전용)"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 사용하는 테이블: sub_portfolio_models / sub_portfolio_compositions
            # sub_portfolio_models 테이블 확인
            try:
                cursor.execute("SELECT 1 FROM sub_portfolio_models LIMIT 1")
            except Exception:
                logging.error("sub_portfolio_models 테이블을 찾을 수 없습니다.")
                return {"status": "success", "portfolios": []}
            
            # Sub-MP 포트폴리오 조회
            cursor.execute("""
                SELECT id, name, description, asset_class,
                       display_order, is_active, created_at, updated_at
                FROM sub_portfolio_models
                ORDER BY asset_class, display_order, id
            """)
            
            rows = cursor.fetchall()
            
            portfolios = []
            for row in rows:
                # ETF 상세 정보 조회 (sub_portfolio_compositions 테이블)
                # 외래키 컬럼: sub_portfolio_model_id
                # category 컬럼이 없을 수 있으므로 ticker나 name을 category로 사용
                cursor.execute("""
                    SELECT ticker, name, weight, display_order
                    FROM sub_portfolio_compositions
                    WHERE sub_portfolio_model_id = %s
                    ORDER BY display_order
                """, (row["id"],))
                etf_rows = cursor.fetchall()
                
                etf_details = []
                allocation = {}
                for etf_row in etf_rows:
                    # NULL 값 처리
                    ticker = etf_row.get("ticker") or ""
                    name = etf_row.get("name") or ""
                    weight = etf_row.get("weight") or 0
                    
                    # category 컬럼이 없으므로 name을 category로 사용하거나 빈 문자열
                    # 또는 ticker를 기반으로 category 추출 (예: ETF 이름에서 카테고리 추출)
                    category = name.split()[0] if name else ""  # 이름의 첫 단어를 category로 사용
                    
                    etf_details.append({
                        "category": category,
                        "ticker": ticker,
                        "name": name,
                        "weight": float(weight) if weight is not None else 0.0
                    })
                    if category:
                        allocation[category] = float(weight) if weight is not None else 0.0
                
                portfolios.append({
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "asset_class": row["asset_class"],
                    "allocation": allocation,
                    "etf_details": etf_details,
                    "display_order": row["display_order"],
                    "is_active": bool(row["is_active"]),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
                })
            
            return {"status": "success", "portfolios": portfolios}
    except Exception as e:
        logging.error(f"Error getting sub-model portfolios: {e}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/portfolios/sub-model-portfolios/{sub_mp_id}")
async def update_sub_model_portfolio(
    sub_mp_id: str,
    request: dict,
    admin_user: dict = Depends(require_admin)
):
    """Sub-MP 포트폴리오 업데이트 (admin 전용)"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Sub-MP 정보 업데이트 (sub_portfolio_models 테이블 사용)
            cursor.execute("""
                UPDATE sub_portfolio_models
                SET name = %s, description = %s, asset_class = %s,
                    display_order = %s, is_active = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                request.get("name"),
                request.get("description"),
                request.get("asset_class"),
                request.get("display_order", 0),
                request.get("is_active", True),
                sub_mp_id
            ))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Sub-model portfolio not found")
            
            # ETF 상세 정보 업데이트 (기존 삭제 후 재생성)
            # sub_portfolio_compositions 테이블의 외래키 컬럼: sub_portfolio_model_id
            # category 컬럼이 없으므로 제외
            cursor.execute("DELETE FROM sub_portfolio_compositions WHERE sub_portfolio_model_id = %s", (sub_mp_id,))
            
            # ETF 상세 정보 삽입
            etf_details = request.get("etf_details", [])
            for idx, etf in enumerate(etf_details):
                # category 컬럼이 없으므로 제외하고 삽입
                cursor.execute("""
                    INSERT INTO sub_portfolio_compositions 
                    (sub_portfolio_model_id, ticker, name, weight, display_order)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    sub_mp_id,
                    etf.get("ticker", ""),
                    etf.get("name", ""),
                    etf.get("weight", 0),
                    idx
                ))
            
            conn.commit()
            
            # 캐시 갱신
            from service.macro_trading.ai_strategist import refresh_portfolio_cache
            refresh_portfolio_cache()
            
            return {"status": "success", "message": "Sub-model portfolio updated"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating sub-model portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 리밸런싱 임계값 설정 (admin 전용)
@api_router.get("/macro-trading/rebalancing/config")
async def get_rebalancing_config(admin_user: dict = Depends(require_admin)):
    """리밸런싱 임계값 설정 조회"""
    try:
        from service.database.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, mp_threshold_percent, sub_mp_threshold_percent, updated_at
                FROM rebalancing_config
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if not row:
                return {
                    "status": "success",
                    "data": {
                        "mp_threshold_percent": 3.0,
                        "sub_mp_threshold_percent": 5.0,
                        "updated_at": None
                    }
                }
            return {
                "status": "success",
                "data": {
                    "mp_threshold_percent": float(row.get("mp_threshold_percent", 3.0)),
                    "sub_mp_threshold_percent": float(row.get("sub_mp_threshold_percent", 5.0)),
                    "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting rebalancing config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/macro-trading/rebalancing/replay-report")
async def get_rebalancing_replay_report(
    days: int = Query(90, ge=30, le=365, description="리플레이 조회 기간(일)"),
    admin_user: dict = Depends(require_admin),
):
    """리밸런싱 회귀 리포트 조회 (admin 전용)"""
    try:
        from service.macro_trading.replay_regression import generate_historical_replay_report

        report = generate_historical_replay_report(days=days)
        return {"status": "success", "data": report}
    except Exception as e:
        logging.error(f"Error getting rebalancing replay report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/macro-trading/rebalancing/config")
async def upsert_rebalancing_config(
    request: RebalancingConfigRequest,
    admin_user: dict = Depends(require_admin)
):
    """리밸런싱 임계값 설정 저장/업데이트"""
    try:
        from service.database.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 새로운 해시 ID로 설정 저장
            new_id = uuid.uuid4().hex
            cursor.execute("""
                INSERT INTO rebalancing_config (id, mp_threshold_percent, sub_mp_threshold_percent)
                VALUES (%s, %s, %s)
            """, (
                new_id,
                request.mp_threshold_percent,
                request.sub_mp_threshold_percent
            ))
            conn.commit()
            return {"status": "success", "message": "Rebalancing config saved"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error saving rebalancing config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Crypto 설정 (admin 전용)
class CryptoConfigRequest(BaseModel):
    market_status: str

@api_router.get("/macro-trading/crypto-config")
async def get_crypto_config(admin_user: dict = Depends(require_admin)):
    """가상화폐 매매 설정 조회"""
    try:
        from service.database.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, market_status, strategy, updated_at
                FROM crypto_config
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if not row:
                # 데이터가 없으면 기본값 반환
                return {
                    "status": "success",
                    "data": {
                        "market_status": "BULL",
                        "strategy": "STRATEGY_NULL",
                        "updated_at": None
                    }
                }
            return {
                "status": "success",
                "data": {
                    "market_status": row["market_status"],
                    "strategy": row["strategy"],
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
                }
            }
    except Exception as e:
        logging.error(f"Error getting crypto config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/macro-trading/crypto-config")
async def update_crypto_config(
    request: CryptoConfigRequest,
    admin_user: dict = Depends(require_admin)
):
    """가상화폐 매매 설정 업데이트 (시장 상태 변경)"""
    try:
        from service.database.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 최신 전략 조회 (History 유지를 위해)
            cursor.execute("SELECT strategy FROM crypto_config ORDER BY updated_at DESC LIMIT 1")
            row = cursor.fetchone()
            current_strategy = row["strategy"] if row else 'STRATEGY_NULL'

            # 항상 새로운 row 생성 (History 관리)
            new_id = uuid.uuid4().hex
            cursor.execute("""
                INSERT INTO crypto_config (id, market_status, strategy)
                VALUES (%s, %s, %s)
            """, (new_id, request.market_status, current_strategy))
                
            conn.commit()
            return {"status": "success", "message": "Crypto config updated"}
    except Exception as e:
        logging.error(f"Error updating crypto config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 로그 조회 API (admin 전용)
@api_router.get("/admin/logs")
async def get_logs(
    log_type: str = Query(..., description="로그 타입: backend, frontend, nginx"),
    lines: int = Query(100, description="읽을 줄 수"),
    log_file: Optional[str] = Query(None, description="백엔드 로그 파일명 (log.txt, error.log, access.log)"),
    start_time: Optional[str] = Query(None, description="시작 시간 (YYYY-MM-DDTHH:MM 형식)"),
    end_time: Optional[str] = Query(None, description="종료 시간 (YYYY-MM-DDTHH:MM 형식)"),
    admin_user: dict = Depends(require_admin)
):
    """로그 조회 (admin 전용)"""
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        log_content = ""
        log_file_name = ""
        
        # nginx 로그는 별도로 처리
        if log_type == "nginx":
            import subprocess
            try:
                # journalctl을 사용하여 nginx 로그 읽기
                result = subprocess.run(
                    ['journalctl', '-u', 'nginx', '-n', str(lines), '--no-pager'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    return {
                        "status": "success",
                        "log_type": log_type,
                        "content": result.stdout,
                        "file": "journalctl -u nginx",
                        "lines": len(result.stdout.split('\n'))
                    }
                else:
                    # journalctl 실패 시 파일 직접 읽기 시도
                    nginx_logs = [
                        "/var/log/nginx/hobot-access.log",
                        "/var/log/nginx/hobot-error.log",
                        "/var/log/nginx/access.log",
                        "/var/log/nginx/error.log"
                    ]
                    for nginx_log in nginx_logs:
                        if os.path.exists(nginx_log):
                            try:
                                with open(nginx_log, 'r', encoding='utf-8', errors='ignore') as f:
                                    all_lines = f.readlines()
                                    log_content = ''.join(all_lines[-lines:])
                                    return {
                                        "status": "success",
                                        "log_type": log_type,
                                        "content": log_content,
                                        "file": nginx_log,
                                        "lines": len(log_content.split('\n'))
                                    }
                            except PermissionError:
                                continue
                            except Exception:
                                continue
                    
                    return {
                        "status": "error",
                        "message": "nginx 로그를 읽을 수 없습니다. 권한이 필요합니다. 서버에서 다음 명령어로 확인하세요: sudo journalctl -u nginx -n 100",
                        "file": "",
                        "log_type": log_type
                    }
            except FileNotFoundError:
                # journalctl이 없는 경우 파일 직접 읽기 시도
                nginx_logs = [
                    "/var/log/nginx/hobot-access.log",
                    "/var/log/nginx/hobot-error.log",
                    "/var/log/nginx/access.log",
                    "/var/log/nginx/error.log"
                ]
                for nginx_log in nginx_logs:
                    if os.path.exists(nginx_log):
                        try:
                            with open(nginx_log, 'r', encoding='utf-8', errors='ignore') as f:
                                all_lines = f.readlines()
                                log_content = ''.join(all_lines[-lines:])
                                return {
                                    "status": "success",
                                    "log_type": log_type,
                                    "content": log_content,
                                    "file": nginx_log,
                                    "lines": len(log_content.split('\n'))
                                }
                        except PermissionError:
                            continue
                        except Exception:
                            continue
                
                return {
                    "status": "error",
                    "message": "nginx 로그를 읽을 수 없습니다. 권한이 필요합니다. 서버에서 다음 명령어로 확인하세요: sudo tail -n 100 /var/log/nginx/access.log",
                    "file": "",
                    "log_type": log_type
                }
            except subprocess.TimeoutExpired:
                return {
                    "status": "error",
                    "message": "nginx 로그 읽기 시간 초과",
                    "file": "",
                    "log_type": log_type
                }
            except Exception as e:
                logging.error(f"Error reading nginx logs: {e}")
                return {
                    "status": "error",
                    "message": f"nginx 로그를 읽는 중 오류가 발생했습니다: {str(e)}",
                    "file": "",
                    "log_type": log_type
                }
        
        if log_type == "backend":
            # 백엔드 로그 파일 매핑
            backend_log_map = {
                "log.txt": os.path.join(base_path, "logs", "log.txt"),
                "error.log": os.path.join(base_path, "logs", "error.log"),
                "access.log": os.path.join(base_path, "logs", "access.log")
            }
            
            # 특정 파일이 지정된 경우 해당 파일만 읽기
            if log_file and log_file in backend_log_map:
                log_path = backend_log_map[log_file]
                log_name = log_file
            else:
                # 기본값: log.txt
                log_path = backend_log_map.get("log.txt")
                log_name = "log.txt"
            
            if not log_path or not os.path.exists(log_path):
                return {"status": "success", "log_type": log_type, "content": f"Log file {log_name} not found", "file": log_name}
            
            import re
            from datetime import datetime
            
            # 타임스탬프 파싱을 위한 정규식
            # log.txt 형식: 2025-11-01 21:51:25,255 - INFO - ...
            timestamp_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d+)?)')
            # access.log/error.log 형식 (Gunicorn): IP - - [01/Nov/2025:21:51:25 +0000] ...
            gunicorn_timestamp_pattern = re.compile(r'\[(\d{2}/\w+/\d{4}:\d{2}:\d{2}:\d{2})')
            
            def parse_timestamp(line):
                """로그 라인에서 타임스탬프를 파싱하여 datetime 객체로 반환"""
                try:
                    # log.txt 형식: 2025-11-01 21:51:25,255
                    match = timestamp_pattern.match(line)
                    if match:
                        ts_str = match.group(1).replace(',', '.')
                        return datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S.%f')
                    
                    # Gunicorn access.log/error.log 형식: [01/Nov/2025:21:51:25:00]
                    match = gunicorn_timestamp_pattern.search(line)
                    if match:
                        ts_str = match.group(1)
                        return datetime.strptime(ts_str, '%d/%b/%Y:%H:%M:%S')
                    
                    # 타임스탬프를 찾을 수 없으면 현재 시간 반환 (맨 뒤로 정렬)
                    return datetime.now()
                except:
                    # 파싱 실패 시 현재 시간 반환
                    return datetime.now()
            
            # 로그 파일 읽기
            # 시간 필터가 없으면 파일 끝에서 최근 N줄만 읽기 (tail과 동일하게)
            # 시간 필터가 있으면 전체 파일을 읽어서 필터링
            all_log_entries = []  # (timestamp, log_line) 튜플 리스트
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    if start_time or end_time:
                        # 시간 필터가 있으면 전체 파일 읽기
                        file_lines = f.readlines()
                    else:
                        # 시간 필터가 없으면 파일 끝에서 최근 N줄만 읽기 (효율적이고 정확함)
                        # 파일 크기가 크면 seek로 끝부분만 읽기
                        try:
                            # 파일 크기 확인
                            f.seek(0, 2)  # 파일 끝으로 이동
                            file_size = f.tell()
                            
                            # 최근 대략 N줄을 읽기 위해 (평균 라인 길이 * N * 2)만큼만 읽기
                            # 안전하게 더 많이 읽기 위해 * 3
                            read_size = min(lines * 200 * 3, file_size)  # 평균 라인 길이 200자 가정
                            f.seek(max(0, file_size - read_size))
                            file_lines = f.readlines()
                            # 실제로는 마지막 N줄만 사용 (Traceback 등 여러 줄 에러 포함)
                            file_lines = file_lines[-lines * 2:]  # 여유있게 2배로
                        except:
                            # seek 실패 시 전체 파일 읽기
                            f.seek(0)
                            file_lines = f.readlines()
                            file_lines = file_lines[-lines * 2:]
                    
                    if file_lines:
                        # 타임스탬프가 없는 줄(예: Traceback의 일부)을 처리하기 위해
                        # 이전 줄의 타임스탬프를 상속받도록 처리
                        last_timestamp = None
                        for line in file_lines:
                            line = line.rstrip('\n\r')
                            if not line.strip():  # 빈 줄은 건너뛰기
                                continue
                            
                            # 타임스탬프 패턴이 있는지 먼저 확인
                            has_timestamp = bool(timestamp_pattern.match(line) or gunicorn_timestamp_pattern.search(line))
                            
                            if has_timestamp:
                                # 타임스탬프가 있으면 파싱
                                timestamp = parse_timestamp(line)
                                last_timestamp = timestamp
                            else:
                                # 타임스탬프가 없으면 이전 줄의 타임스탬프 상속
                                if last_timestamp is not None:
                                    timestamp = last_timestamp
                                else:
                                    # 첫 줄이 타임스탬프가 없으면 건너뛰기
                                    continue
                            
                            all_log_entries.append((timestamp, line))
            except Exception as e:
                logging.warning(f"Could not read {log_path}: {e}")
                return {"status": "error", "message": f"Error reading log file: {str(e)}", "file": log_name}
            
            if all_log_entries:
                # 타임스탬프 기준으로 정렬 (오래된 것부터 최신 순)
                all_log_entries.sort(key=lambda x: x[0])
                
                # 시간 필터 적용
                # 프론트엔드에서 UTC+9 시간을 보내므로, 로그 타임스탬프와 직접 비교
                # 로그 타임스탬프는 서버의 로컬 시간대(UTC+9)로 저장되어 있다고 가정
                filtered_entries = all_log_entries
                if start_time or end_time:
                    try:
                        if start_time:
                            # UTC+9 시간대를 naive datetime으로 파싱 (로그와 동일한 시간대)
                            start_dt = datetime.strptime(start_time, '%Y-%m-%dT%H:%M')
                            filtered_entries = [entry for entry in filtered_entries if entry[0] >= start_dt]
                        if end_time:
                            # UTC+9 시간대를 naive datetime으로 파싱 (로그와 동일한 시간대)
                            end_dt = datetime.strptime(end_time, '%Y-%m-%dT%H:%M')
                            # 종료 시간에 59초 59밀리초 추가하여 해당 시간대까지 포함
                            end_dt = end_dt.replace(second=59, microsecond=999999)
                            filtered_entries = [entry for entry in filtered_entries if entry[0] <= end_dt]
                    except ValueError as e:
                        logging.warning(f"Invalid time format: {e}")
                        # 시간 파싱 실패 시 필터링하지 않음
                
                # 최근 N줄만 선택 (시간 필터 적용 후)
                recent_entries = filtered_entries[-lines:] if len(filtered_entries) > lines else filtered_entries
                
                # 로그 내용 구성
                log_content = '\n'.join([line for _, line in recent_entries])
                
                # 파일 정보 구성
                file_info = log_name
                file_info += f" (Total: {len(all_log_entries)} lines"
                if start_time or end_time:
                    file_info += f", Filtered: {len(filtered_entries)} lines"
                file_info += f", Showing: {len(recent_entries)} lines)"
                if start_time or end_time:
                    file_info += f" | Time Range: {start_time or 'N/A'} ~ {end_time or 'N/A'}"
                
                log_file_name = file_info
                
                return {
                    "status": "success",
                    "log_type": log_type,
                    "content": log_content,
                    "file": log_file_name,
                    "lines": len(recent_entries)
                }
            else:
                return {"status": "success", "log_type": log_type, "content": f"No content in {log_name}", "file": log_name}
        elif log_type == "frontend":
            # 프론트엔드 빌드 로그
            frontend_log = os.path.join(base_path, "logs", "frontend-build.log")
            if os.path.exists(frontend_log):
                log_file = frontend_log
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        all_lines = f.readlines()
                        # 최근 N줄만 반환
                        log_content = ''.join(all_lines[-lines:])
                    return {
                        "status": "success",
                        "log_type": log_type,
                        "content": log_content,
                        "file": log_file,
                        "lines": len(log_content.split('\n'))
                    }
                except Exception as e:
                    logging.error(f"Error reading log file {log_file}: {e}")
                    return {"status": "error", "message": f"Error reading log file: {str(e)}", "file": log_file}
            else:
                return {"status": "success", "log_type": log_type, "content": "No frontend build log available", "file": ""}
        else:
            raise HTTPException(status_code=400, detail="Invalid log_type. Must be: backend, frontend, or nginx")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================


# ============================================
# LLM 모니터링 API
# ============================================

@api_router.get("/llm-monitoring/options")
async def get_llm_monitoring_options():
    """LLM 모니터링 필터 옵션 조회 (모델명, 서비스명 목록)"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 모델명 목록 조회
            cursor.execute("""
                SELECT DISTINCT model_name
                FROM llm_usage_logs
                WHERE model_name IS NOT NULL
                ORDER BY model_name
            """)
            models = [row['model_name'] for row in cursor.fetchall()]
            
            # 서비스명 목록 조회
            cursor.execute("""
                SELECT DISTINCT service_name
                FROM llm_usage_logs
                WHERE service_name IS NOT NULL
                ORDER BY service_name
            """)
            services = [row['service_name'] for row in cursor.fetchall()]
            
            return {
                "status": "success",
                "models": models,
                "services": services
            }
    except Exception as e:
        logging.error(f"LLM 모니터링 옵션 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/llm-monitoring/logs")
async def get_llm_monitoring_logs(
    limit: int = Query(default=100, ge=1, le=1000, description="조회할 로그 수"),
    offset: int = Query(default=0, ge=0, description="오프셋"),
    model_name: Optional[str] = Query(default=None, description="모델명 필터 (All 또는 특정 모델명)"),
    service_name: Optional[str] = Query(default=None, description="서비스명 필터 (All 또는 특정 서비스명)"),
    start_date: Optional[str] = Query(default=None, description="시작 날짜 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(default=None, description="종료 날짜 (YYYY-MM-DD)")
):
    """LLM 사용 로그 조회"""
    try:
        from service.database.db import get_db_connection
        from datetime import datetime
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # WHERE 조건 구성
            conditions = []
            params = []
            
            if model_name and model_name.lower() != 'all':
                conditions.append("model_name = %s")
                params.append(model_name)
            
            if service_name and service_name.lower() != 'all':
                conditions.append("service_name = %s")
                params.append(service_name)
            
            if start_date:
                # 날짜 형식이 시간까지 포함되어 있는지 확인
                if ' ' in start_date or 'T' in start_date:
                    conditions.append("created_at >= %s")
                else:
                    conditions.append("DATE(created_at) >= %s")
                params.append(start_date)
            
            if end_date:
                # 날짜 형식이 시간까지 포함되어 있는지 확인
                if ' ' in end_date or 'T' in end_date:
                    conditions.append("created_at <= %s")
                else:
                    conditions.append("DATE(created_at) <= %s")
                params.append(end_date)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            # 전체 개수 조회
            count_query = f"SELECT COUNT(*) as total FROM llm_usage_logs {where_clause}"
            cursor.execute(count_query, params)
            count_result = cursor.fetchone()
            total = count_result['total'] if count_result else 0
            
            # 로그 조회
            # created_at을 문자열로 직접 가져와서 시간대 변환 없이 그대로 사용
            query = f"""
                SELECT 
                    id,
                    model_name,
                    provider,
                    service_name,
                    user_id,
                    flow_type,
                    flow_run_id,
                    agent_name,
                    trace_order,
                    metadata_json,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    duration_ms,
                    request_prompt,
                    response_prompt,
                    DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i:%%S') as created_at
                FROM llm_usage_logs
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])
            cursor.execute(query, params)
            
            logs = cursor.fetchall()
            
            # created_at은 이미 문자열로 반환되므로 추가 변환 불필요
            
            return {
                "status": "success",
                "total": total,
                "limit": limit,
                "offset": offset,
                "logs": logs,
                "data": logs  # 호환성을 위해 둘 다 반환
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"LLM 사용 로그 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/llm-monitoring/token-usage")
async def get_llm_token_usage(
    group_by: str = Query(default="day", description="그룹화 기준 (day, model, service)"),
    start_date: Optional[str] = Query(default=None, description="시작 날짜 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(default=None, description="종료 날짜 (YYYY-MM-DD)"),
    model_name: Optional[str] = Query(default=None, description="모델명 필터"),
    service_name: Optional[str] = Query(default=None, description="서비스명 필터")
):
    """LLM 토큰 사용량 조회"""
    try:
        from service.database.db import get_db_connection
        from datetime import datetime
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # WHERE 조건 구성
            conditions = []
            params = []
            
            if start_date:
                if ' ' in start_date or 'T' in start_date:
                    conditions.append("created_at >= %s")
                else:
                    conditions.append("DATE(created_at) >= %s")
                params.append(start_date)
            
            if end_date:
                if ' ' in end_date or 'T' in end_date:
                    conditions.append("created_at <= %s")
                else:
                    conditions.append("DATE(created_at) <= %s")
                params.append(end_date)
            
            if model_name:
                conditions.append("model_name = %s")
                params.append(model_name)
            
            if service_name:
                conditions.append("service_name = %s")
                params.append(service_name)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            # 그룹화 기준에 따라 쿼리 구성
            if group_by == "day":
                group_by_clause = "DATE(created_at)"
                select_fields = "DATE(created_at) as date"
            elif group_by == "model":
                group_by_clause = "model_name, provider"
                select_fields = "model_name, provider"
            elif group_by == "service":
                group_by_clause = "service_name"
                select_fields = "service_name"
            else:
                raise HTTPException(status_code=400, detail="Invalid group_by. Must be: day, model, or service")
            
            query = f"""
                SELECT 
                    {select_fields},
                    SUM(prompt_tokens) as prompt_tokens,
                    SUM(completion_tokens) as completion_tokens,
                    SUM(total_tokens) as total_tokens,
                    COUNT(*) as request_count
                FROM llm_usage_logs
                {where_clause}
                GROUP BY {group_by_clause}
                ORDER BY {group_by_clause} DESC
            """
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            # datetime 객체를 문자열로 변환
            for result in results:
                if result.get('date'):
                    result['date'] = result['date'].isoformat() if hasattr(result['date'], 'isoformat') else str(result['date'])
            
            return {
                "status": "success",
                "group_by": group_by,
                "start_date": start_date,
                "end_date": end_date,
                "data": results
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"LLM 토큰 사용량 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/llm-monitoring/user-usage")
async def get_llm_user_usage(
    start_date: Optional[str] = Query(default=None, description="시작 날짜 (YYYY-MM-DD 또는 YYYY-MM-DD HH:MM:SS)"),
    end_date: Optional[str] = Query(default=None, description="종료 날짜 (YYYY-MM-DD 또는 YYYY-MM-DD HH:MM:SS)"),
    user_id: Optional[str] = Query(default=None, description="특정 사용자 ID 필터"),
    admin_user: dict = Depends(require_admin)
):
    """사용자별 LLM 사용량 조회 (Admin 전용)"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # WHERE 조건 구성
            conditions = ["user_id IS NOT NULL"]  # 사용자 ID가 있는 것만
            params = []
            
            if start_date:
                if ' ' in start_date or 'T' in start_date:
                    conditions.append("created_at >= %s")
                else:
                    conditions.append("DATE(created_at) >= %s")
                params.append(start_date)
            
            if end_date:
                if ' ' in end_date or 'T' in end_date:
                    conditions.append("created_at <= %s")
                else:
                    conditions.append("DATE(created_at) <= %s")
                params.append(end_date)
            
            if user_id:
                conditions.append("user_id = %s")
                params.append(user_id)
            
            where_clause = "WHERE " + " AND ".join(conditions)
            
            # 사용자별 집계 쿼리
            query = f"""
                SELECT 
                    user_id,
                    COUNT(*) as request_count,
                    SUM(prompt_tokens) as total_prompt_tokens,
                    SUM(completion_tokens) as total_completion_tokens,
                    SUM(total_tokens) as total_tokens,
                    AVG(duration_ms) as avg_duration_ms,
                    MAX(created_at) as last_used_at,
                    MIN(created_at) as first_used_at
                FROM llm_usage_logs
                {where_clause}
                GROUP BY user_id
                ORDER BY total_tokens DESC
            """
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            # datetime 객체를 문자열로 변환
            for result in results:
                if result.get('last_used_at'):
                    result['last_used_at'] = result['last_used_at'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(result['last_used_at'], 'strftime') else str(result['last_used_at'])
                if result.get('first_used_at'):
                    result['first_used_at'] = result['first_used_at'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(result['first_used_at'], 'strftime') else str(result['first_used_at'])
                if result.get('avg_duration_ms'):
                    result['avg_duration_ms'] = round(float(result['avg_duration_ms']), 2)
            
            # 전체 요약 통계
            summary_query = f"""
                SELECT 
                    COUNT(DISTINCT user_id) as total_users,
                    COUNT(*) as total_requests,
                    SUM(total_tokens) as total_tokens_used
                FROM llm_usage_logs
                {where_clause}
            """
            cursor.execute(summary_query, params)
            summary = cursor.fetchone()
            
            return {
                "status": "success",
                "start_date": start_date,
                "end_date": end_date,
                "summary": {
                    "total_users": summary.get('total_users', 0) if summary else 0,
                    "total_requests": summary.get('total_requests', 0) if summary else 0,
                    "total_tokens_used": summary.get('total_tokens_used', 0) if summary else 0
                },
                "data": results
            }
    except Exception as e:
        logging.error(f"사용자별 LLM 사용량 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/llm-monitoring/users")
async def get_llm_users(admin_user: dict = Depends(require_admin)):
    """LLM을 사용한 사용자 목록 조회 (Admin 전용)"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT user_id 
                FROM llm_usage_logs 
                WHERE user_id IS NOT NULL 
                ORDER BY user_id
            """)
            results = cursor.fetchall()
            users = [r['user_id'] for r in results]
            
            return {
                "status": "success",
                "users": users
            }
    except Exception as e:
        logging.error(f"LLM 사용자 목록 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/multi-agent-monitoring/options")
async def get_multi_agent_monitoring_options(admin_user: dict = Depends(require_admin)):
    """멀티에이전트 모니터링 필터 옵션 조회"""
    try:
        from service.database.db import get_db_connection

        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT DISTINCT flow_type
                FROM llm_usage_logs
                WHERE flow_type IS NOT NULL AND flow_type != ''
                ORDER BY flow_type
                """
            )
            flow_types = [row["flow_type"] for row in cursor.fetchall()]
            if not flow_types:
                flow_types = ["chatbot", "dashboard_ai_analysis"]

            cursor.execute(
                """
                SELECT DISTINCT COALESCE(NULLIF(user_id, ''), 'system') AS user_id
                FROM llm_usage_logs
                WHERE flow_type IS NOT NULL AND flow_type != ''
                ORDER BY user_id
                """
            )
            users = [row["user_id"] for row in cursor.fetchall()]

            return {
                "status": "success",
                "flow_types": flow_types,
                "users": users,
            }
    except Exception as e:
        logging.error(f"멀티에이전트 옵션 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/multi-agent-monitoring/flows")
async def get_multi_agent_flow_runs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    flow_type: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    admin_user: dict = Depends(require_admin),
):
    """멀티에이전트 run 목록(요청 단위) 조회"""
    try:
        from service.database.db import get_db_connection

        conditions = [
            "flow_run_id IS NOT NULL",
            "flow_run_id != ''",
            "flow_type IS NOT NULL",
            "flow_type != ''",
        ]
        params: List[Any] = []

        if flow_type and flow_type.lower() != "all":
            conditions.append("flow_type = %s")
            params.append(flow_type)

        if user_id and user_id.lower() != "all":
            if user_id == "system":
                conditions.append("COALESCE(NULLIF(user_id, ''), 'system') = 'system'")
            else:
                conditions.append("user_id = %s")
                params.append(user_id)

        if start_date:
            if " " in start_date or "T" in start_date:
                conditions.append("created_at >= %s")
            else:
                conditions.append("DATE(created_at) >= %s")
            params.append(start_date)

        if end_date:
            if " " in end_date or "T" in end_date:
                conditions.append("created_at <= %s")
            else:
                conditions.append("DATE(created_at) <= %s")
            params.append(end_date)

        where_clause = "WHERE " + " AND ".join(conditions)

        with get_db_connection() as conn:
            cursor = conn.cursor()

            count_query = f"""
                SELECT COUNT(*) AS total
                FROM (
                    SELECT flow_run_id
                    FROM llm_usage_logs
                    {where_clause}
                    GROUP BY flow_run_id
                ) AS run_counts
            """
            cursor.execute(count_query, params)
            total_result = cursor.fetchone() or {}
            total = int(total_result.get("total") or 0)

            flow_query = f"""
                SELECT
                    flow_run_id,
                    flow_type,
                    COALESCE(NULLIF(user_id, ''), 'system') AS user_id,
                    MIN(created_at) AS started_at,
                    MAX(created_at) AS ended_at,
                    ROUND(TIMESTAMPDIFF(MICROSECOND, MIN(created_at), MAX(created_at)) / 1000, 0) AS flow_duration_ms,
                    COUNT(*) AS call_count,
                    SUM(prompt_tokens) AS total_prompt_tokens,
                    SUM(completion_tokens) AS total_completion_tokens,
                    SUM(total_tokens) AS total_tokens,
                    SUM(COALESCE(duration_ms, 0)) AS llm_duration_ms,
                    GROUP_CONCAT(DISTINCT service_name ORDER BY service_name SEPARATOR ', ') AS services,
                    GROUP_CONCAT(DISTINCT model_name ORDER BY model_name SEPARATOR ', ') AS models
                FROM llm_usage_logs
                {where_clause}
                GROUP BY flow_run_id, flow_type, COALESCE(NULLIF(user_id, ''), 'system')
                ORDER BY started_at DESC
                LIMIT %s OFFSET %s
            """
            flow_params = list(params) + [limit, offset]
            cursor.execute(flow_query, flow_params)
            rows = cursor.fetchall()

            flows = []
            for row in rows:
                started_at = row.get("started_at")
                ended_at = row.get("ended_at")
                flows.append(
                    {
                        "flow_run_id": row.get("flow_run_id"),
                        "flow_type": row.get("flow_type"),
                        "user_id": row.get("user_id"),
                        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(started_at, "strftime") else str(started_at),
                        "ended_at": ended_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ended_at, "strftime") else str(ended_at),
                        "flow_duration_ms": int(row.get("flow_duration_ms") or 0),
                        "call_count": int(row.get("call_count") or 0),
                        "total_prompt_tokens": int(row.get("total_prompt_tokens") or 0),
                        "total_completion_tokens": int(row.get("total_completion_tokens") or 0),
                        "total_tokens": int(row.get("total_tokens") or 0),
                        "llm_duration_ms": int(row.get("llm_duration_ms") or 0),
                        "services": row.get("services") or "",
                        "models": row.get("models") or "",
                    }
                )

            return {
                "status": "success",
                "total": total,
                "limit": limit,
                "offset": offset,
                "flows": flows,
                "data": flows,
            }
    except Exception as e:
        logging.error(f"멀티에이전트 run 목록 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/multi-agent-monitoring/calls")
async def get_multi_agent_flow_calls(
    flow_run_id: str = Query(..., min_length=1),
    admin_user: dict = Depends(require_admin),
):
    """특정 run의 LLM 호출 상세 조회"""
    try:
        from service.database.db import get_db_connection

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id,
                    flow_run_id,
                    flow_type,
                    COALESCE(NULLIF(user_id, ''), 'system') AS user_id,
                    service_name,
                    agent_name,
                    model_name,
                    provider,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    duration_ms,
                    trace_order,
                    metadata_json,
                    request_prompt,
                    response_prompt,
                    created_at
                FROM llm_usage_logs
                WHERE flow_run_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (flow_run_id,),
            )
            rows = cursor.fetchall()

            calls = []
            for row in rows:
                metadata_payload = row.get("metadata_json")
                if isinstance(metadata_payload, str) and metadata_payload:
                    try:
                        metadata_payload = json.loads(metadata_payload)
                    except Exception:
                        metadata_payload = {"raw": metadata_payload}

                created_at = row.get("created_at")
                calls.append(
                    {
                        "id": row.get("id"),
                        "flow_run_id": row.get("flow_run_id"),
                        "flow_type": row.get("flow_type"),
                        "user_id": row.get("user_id"),
                        "service_name": row.get("service_name"),
                        "agent_name": row.get("agent_name"),
                        "model_name": row.get("model_name"),
                        "provider": row.get("provider"),
                        "prompt_tokens": int(row.get("prompt_tokens") or 0),
                        "completion_tokens": int(row.get("completion_tokens") or 0),
                        "total_tokens": int(row.get("total_tokens") or 0),
                        "duration_ms": int(row.get("duration_ms") or 0),
                        "trace_order": row.get("trace_order"),
                        "metadata_json": metadata_payload,
                        "request_prompt": row.get("request_prompt"),
                        "response_prompt": row.get("response_prompt"),
                        "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created_at, "strftime") else str(created_at),
                    }
                )

            return {
                "status": "success",
                "flow_run_id": flow_run_id,
                "call_count": len(calls),
                "calls": calls,
                "data": calls,
            }
    except Exception as e:
        logging.error(f"멀티에이전트 호출 상세 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_admin)
):
    """관리자 파일 업로드"""
    try:
        return file_service.save_file(file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/files")
async def list_files(
    current_user: dict = Depends(require_admin)
):
    """업로드된 파일 목록 조회"""
    try:
        return {"files": file_service.list_files()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/admin/files/{file_id}")
async def delete_file(
    file_id: str,
    current_user: dict = Depends(require_admin)
):
    """파일 삭제"""
    try:
        return file_service.delete_file(file_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/files/{file_id}")
async def download_file(
    file_id: str,
    current_user: dict = Depends(require_admin)
):
    """파일 다운로드"""
    try:
        file_info = file_service.get_file_info(file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found")
        
        # 파일명을 URL 인코딩하여 Content-Disposition 헤더 설정
        from urllib.parse import quote
        encoded_filename = quote(file_info['original_name'].encode('utf-8'))
        
        return FileResponse(
            path=file_info['path'],
            filename=file_info['original_name'], # 기본 filename
            media_type='application/octet-stream',
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ============================================
# Shared View API (File Upload Sync)
# ============================================

class SharedViewRequest(BaseModel):
    type: str  # 'text' or 'image'
    content: str # text content or image URL

# Simple in-memory storage
shared_view_state = {
    "type": None,
    "content": None,
    "updated_at": None
}

@api_router.get("/admin/shared-view")
async def get_shared_view(current_user: dict = Depends(require_admin)):
    """공유된 화면 상태 조회"""
    return shared_view_state

@api_router.post("/admin/shared-view")
async def update_shared_view(
    req: SharedViewRequest,
    current_user: dict = Depends(require_admin)
):
    """공유된 화면 상태 업데이트"""
    global shared_view_state
    from datetime import datetime
    shared_view_state = {
        "type": req.type,
        "content": req.content,
        "updated_at": datetime.now().isoformat()
    }
    return {"status": "success", "data": shared_view_state}


# --- Test Environment API (Phase 1) ---

class TimeTravelRequest(BaseModel):
    date: str  # YYYY-MM-DD
    time: str = "08:00" # HH:MM

class TestPromptRequest(BaseModel):
    prompt: str
    model: str = "gemini-3-pro-preview" # Default model

@api_router.get("/test/status")
async def get_test_status(current_user: dict = Depends(require_admin)):
    """테스트 환경 상태 조회 (가상 시간, 리밸런싱 진행 상태)"""
    try:
        current_time = TimeProvider.get_current_time()
        
        # 최근 리밸런싱 상태 조회
        from service.database.db import get_db_connection
        rebalancing_logs = []
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM rebalancing_state 
                ORDER BY created_at DESC LIMIT 5
            """)
            rows = cursor.fetchall()
            for row in rows:
                if row.get('details'):
                    if isinstance(row['details'], str):
                        try:
                            row['details'] = json.loads(row['details'])
                        except:
                            pass
                else:
                    row['details'] = {}
                    
                row['created_at'] = row['created_at'].isoformat() if row['created_at'] else None
                row['updated_at'] = row['updated_at'].isoformat() if row['updated_at'] else None
                row['target_date'] = row['target_date'].isoformat() if row['target_date'] else None
                rebalancing_logs.append(row)

        return {
            "virtual_time": current_time.isoformat(),
            "is_virtual": abs((current_time - datetime.now()).total_seconds()) > 5,
            "rebalancing_logs": rebalancing_logs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/test/time-travel")
async def set_virtual_time(
    req: TimeTravelRequest,
    current_user: dict = Depends(require_admin)
):
    """가상 시간 설정 (Time Travel)"""
    try:
        target_dt = datetime.strptime(f"{req.date} {req.time}", "%Y-%m-%d %H:%M")
        TimeProvider.set_virtual_time(target_dt)
        return {"status": "success", "current_time": target_dt.isoformat()}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format code. Use YYYY-MM-DD and HH:MM")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/test/time-travel/next-day")
async def next_day_time_travel(
    current_user: dict = Depends(require_admin)
):
    """다음 날 08:00로 시간 이동 (+1 Day)"""
    try:
        target_dt = TimeProvider.add_days(1, default_time="08:00")
        return {"status": "success", "current_time": target_dt.isoformat(), "message": "Moved to next day 08:00"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/test/time-travel/reset")
async def reset_virtual_time(
    current_user: dict = Depends(require_admin)
):
    """실제 시간으로 복귀 (Reset)"""
    try:
        TimeProvider.reset_to_real_time()
        return {"status": "success", "message": "Reset to real time", "current_time": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/test/macro-prompt")
async def test_macro_prompt(
    req: TestPromptRequest,
    current_user: dict = Depends(require_admin)
):
    """LLM 프롬프트 테스트 (Macro Prompt Lab)"""
    try:
        # 모델 선택
        llm = None
        if "gpt-4" in req.model:
            llm = llm_service.llm_gpt4o()
        else:
            llm = llm_service.llm_gemini_pro(model=req.model)
            
        # 실행
        response = llm.invoke(req.prompt)
        
        return {
            "status": "success",
            "model": req.model,
            "response": response.content
        }
    except Exception as e:
        logging.error(f"Macro Prompt Test Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# Gemini API Proxy (Frontend에서 사용)
# ============================================
class GeminiMarketAnalysisRequest(BaseModel):
    query: str

class GeminiCypherRequest(BaseModel):
    question: str
    database: Optional[str] = "architecture"  # "architecture" or "macro" (legacy: "news")
    schema_override: Optional[str] = None

class GeminiExplainRequest(BaseModel):
    question: str
    cypher: str
    results: list

# Default Graph DB schema for Cypher generation
GRAPH_SCHEMA = """
Graph Database Schema:
- Node Labels: Resource, VNet, Subnet, Subscription, Environment
- Relationships: 
  - (Resource)-[:BELONGS_TO]->(Subscription)
  - (VNet)-[:BELONGS_TO]->(Subscription)
  - (Subnet)-[:PART_OF]->(VNet)
  - (Resource)-[:DEPLOYED_IN]->(Subnet)
  - (Resource)-[:IN_ENVIRONMENT]->(Environment)
  - (VNet)-[:IN_ENVIRONMENT]->(Environment)
- Common Node Properties: name, id, type, status, region, createdAt
- Resource types may include: VM, Storage, Database, LoadBalancer, etc.
- Resource types may include: VM, Storage, Database, LoadBalancer, etc.
"""

MACRO_GRAPH_SCHEMA = """
Macro Knowledge Graph Schema:
- Node Labels:
  - Document (doc_id, title, url, source, published_at, country, category, lang)
  - Event (event_id, type, summary, event_time, country)
  - MacroTheme (theme_id, name, description)
  - EconomicIndicator (indicator_code, name, unit, frequency, source, country)
  - IndicatorObservation (indicator_code, obs_date, value, vintage_date?)
  - DerivedFeature (indicator_code, feature_name, obs_date)
  - Entity (canonical_id, name, entity_type)
  - EntityAlias (canonical_id, alias, lang)
  - Fact (metric, value, unit, period, prev_value?)
  - Claim (polarity, confidence)
  - Evidence (text, lang, offset_start?, offset_end?)
  - Story (story_id, window_days, method)
  - MacroState (date)
  - AnalysisRun (run_id, created_at, question, model, as_of_date)

- Relationships:
  - (Document)-[:MENTIONS]->(Event|Fact|Entity|EconomicIndicator|MacroTheme)
  - (Document)-[:HAS_EVIDENCE]->(Evidence)
  - (Evidence)-[:SUPPORTS]->(Fact|Claim)
  - (Entity)-[:HAS_ALIAS]->(EntityAlias)
  - (Event)-[:ABOUT_THEME]->(MacroTheme)
  - (EconomicIndicator)-[:BELONGS_TO]->(MacroTheme)
  - (Event)-[:AFFECTS]->(EconomicIndicator|MacroTheme)
  - (Event)-[:CAUSES]->(Event)
  - (Claim)-[:ABOUT]->(Event|EconomicIndicator|MacroTheme)
  - (EconomicIndicator)-[:HAS_OBSERVATION]->(IndicatorObservation)
  - (IndicatorObservation)-[:HAS_FEATURE]->(DerivedFeature)
  - (Story)-[:CONTAINS]->(Document)
  - (Story)-[:ABOUT_THEME]->(MacroTheme)
  - (Story)-[:AFFECTS]->(EconomicIndicator)
  - (MacroState)-[:HAS_SIGNAL]->(DerivedFeature)
  - (MacroState)-[:DOMINANT_THEME]->(MacroTheme)
  - (MacroState)-[:EXPLAINED_BY]->(Event|Story)
  - (AnalysisRun)-[:USED_EVIDENCE]->(Evidence)
  - (AnalysisRun)-[:USED_NODE]->(Event|EconomicIndicator|MacroTheme|Story|Document)
"""

# Rate limiting for ontology queries (DB-based)
ONTOLOGY_DAILY_LIMIT = 20  # Regular users can make 20 queries per day

def check_ontology_rate_limit(user: dict) -> tuple[bool, int]:
    """Check if user has exceeded their daily query limit using DB logs. Returns (is_allowed, remaining_count)"""
    # Admin users have no limit
    if user.get("role") == "admin":
        return True, -1  # -1 means unlimited
    
    user_id = user.get("id") or user.get("username")
    
    try:
        from service.database.db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT COUNT(*) as count 
                FROM llm_usage_logs 
                WHERE user_id = %s 
                AND DATE(created_at) = CURRENT_DATE()
                AND service_name IN ('architecture_graph_cypher', 'macro_graph_cypher', 'news_graph_cypher', 'ontology_generate_cypher')
            """
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            count = result['count'] if result else 0
            
            remaining = max(0, ONTOLOGY_DAILY_LIMIT - count)
            
            if count >= ONTOLOGY_DAILY_LIMIT:
                return False, 0
                
            return True, remaining
    except Exception as e:
        logging.error(f"Rate limit check failed: {e}")
        # DB 에러 시 일단 허용하되 로그 남김 (또는 차단)
        # 여기서는 보수적으로 0 리턴하여 차단할 수도 있지만, 장애 시 서비스 가용성을 위해 허용할 수도 있음.
        # 요구사항이 '제한'이므로 에러 시 차단하는 것이 안전할 수 있으나, DB connection fail일 경우 사용자 경험 저하.
        # Fallback to allow if DB fails? Or deny?
        # Deny for now as strict requirement.
        return False, 0

def increment_ontology_query_count(user: dict):
    """
    Increment count is no longer needed as we count directly from llm_usage_logs.
    This function is kept for backward compatibility if needed, or removed.
    For this implementation, the usage log IS the count increment.
    """
    pass

@api_router.get("/ontology/query-limit")
async def get_ontology_query_limit(current_user: dict = Depends(get_current_user)):
    """Get remaining query count for the current user"""
    is_allowed, remaining = check_ontology_rate_limit(current_user)
    is_admin = current_user.get("role") == "admin"
    
    return {
        "status": "success",
        "data": {
            "daily_limit": ONTOLOGY_DAILY_LIMIT if not is_admin else -1,
            "remaining": remaining,
            "is_unlimited": is_admin
        }
    }

@api_router.post("/gemini/generate-cypher")
async def gemini_generate_cypher(request: GeminiCypherRequest, current_user: dict = Depends(get_current_user)):
    """Gemini API를 통한 Cypher 쿼리 생성 (인증 필요, 일반 사용자 하루 20회 제한)"""
    import time
    from service.llm_monitoring import log_llm_usage
    
    # Check rate limit
    is_allowed, remaining = check_ontology_rate_limit(current_user)
    if not is_allowed:
        raise HTTPException(
            status_code=429, 
            detail=f"일일 질의 한도({ONTOLOGY_DAILY_LIMIT}회)를 초과했습니다. 내일 다시 시도해주세요."
        )
    
    start_time = time.time()
    user_id = current_user.get("id") or current_user.get("username")
    
    try:
        from google import genai
        from google.genai import types
        
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="GOOGLE_API_KEY is not configured")
        
        client = genai.Client(api_key=api_key)
        database = (request.database or "architecture").lower()
        if database == "news":
            database = "macro"

        if database == "macro":
            schema = request.schema_override or MACRO_GRAPH_SCHEMA
        else:
            schema = request.schema_override or GRAPH_SCHEMA
        
        prompt = f"""{schema}

User Question: {request.question}

Generate a Cypher query to answer this question. 
IMPORTANT: 
- Return ONLY the Cypher query, no explanation
- Use LIMIT 50 for safety unless specific count is requested
- Match the schema labels and relationships exactly"""
        
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a Cypher query expert. Generate only valid Neo4j Cypher queries based on the given schema. Return ONLY the query, no markdown formatting, no explanations.",
            ),
        )
        
        cypher = response.text.strip() if response.text else ""
        # Clean up markdown formatting if present
        cypher = cypher.replace('```cypher\n', '').replace('```\n', '').replace('```', '').strip()
        
        # Log LLM usage with user_id
        duration_ms = int((time.time() - start_time) * 1000)
        try:
            # Extract token usage if available
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                prompt_tokens = getattr(usage, 'prompt_token_count', 0) or 0
                completion_tokens = getattr(usage, 'candidates_token_count', 0) or 0
                total_tokens = getattr(usage, 'total_token_count', 0) or (prompt_tokens + completion_tokens)
            
            log_llm_usage(
                model_name='gemini-2.0-flash',
                provider='Google',
                request_prompt=prompt[:2000],  # Truncate for storage
                response_prompt=cypher[:2000],
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                service_name=f'{database}_graph_cypher', # 'architecture_graph_cypher' or 'macro_graph_cypher'
                duration_ms=duration_ms,
                user_id=user_id
            )
        except Exception as log_err:
            logging.warning(f"Failed to log LLM usage: {log_err}")
        
        # Query count is tracked via usage logs now
        # increment_ontology_query_count(current_user)
        _, new_remaining = check_ontology_rate_limit(current_user)
        
        return {
            "status": "success",
            "data": {
                "cypher": cypher,
                "remaining_queries": new_remaining
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Gemini Cypher generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/gemini/explain-results")
async def gemini_explain_results(request: GeminiExplainRequest, current_user: dict = Depends(get_current_user)):
    """Gemini API를 통한 쿼리 결과 설명 (인증 필요)"""
    import time
    from service.llm_monitoring import log_llm_usage
    
    start_time = time.time()
    user_id = current_user.get("id") or current_user.get("username")
    
    try:
        from google import genai
        from google.genai import types
        
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="GOOGLE_API_KEY is not configured")
        
        client = genai.Client(api_key=api_key)
        results_str = json.dumps(request.results[:20], indent=2, ensure_ascii=False)
        
        prompt = f"""User asked: "{request.question}"

Cypher query used: {request.cypher}

Query results (JSON):
{results_str}

Please provide a clear, human-readable answer to the user's question based on these results. 
- Be concise but informative
- Highlight key findings
- Use bullet points for multiple items if appropriate
- If no results, say so clearly
- 한국어로 답변해줘"""
        
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a helpful assistant that explains graph database query results in plain language. Be concise and focus on answering the user's original question.",
            ),
        )
        
        explanation = response.text if response.text else "결과를 설명할 수 없습니다."
        
        # Log LLM usage with user_id
        duration_ms = int((time.time() - start_time) * 1000)
        try:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                prompt_tokens = getattr(usage, 'prompt_token_count', 0) or 0
                completion_tokens = getattr(usage, 'candidates_token_count', 0) or 0
                total_tokens = getattr(usage, 'total_token_count', 0) or (prompt_tokens + completion_tokens)
            
            log_llm_usage(
                model_name='gemini-2.0-flash',
                provider='Google',
                request_prompt=prompt[:2000],
                response_prompt=explanation[:2000],
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                service_name='ontology_explain_results',
                duration_ms=duration_ms,
                user_id=user_id
            )
        except Exception as log_err:
            logging.warning(f"Failed to log LLM usage: {log_err}")
        
        return {
            "status": "success",
            "data": {
                "explanation": explanation
            }
        }
    except Exception as e:
        logging.error(f"Gemini explain results error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/gemini/market-analysis")
async def gemini_market_analysis(request: GeminiMarketAnalysisRequest):
    """Gemini API를 통한 시장 분석 - Google Search Grounding 사용"""
    try:
        from google import genai
        from google.genai import types
        
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="GOOGLE_API_KEY is not configured")
        
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=request.query,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                system_instruction="You are a senior financial market analyst for 'StockOverflow'. Provide concise, data-backed insights. When asked about specific stocks or market trends, use Google Search to find the latest information. Summarize key reasons for price movements. Keep the tone professional but accessible. 한국어로 답변해줘.",
            ),
        )
        
        text = response.text if response.text else "분석을 생성할 수 없습니다."
        
        # Extract grounding chunks for sources
        sources = []
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                grounding_metadata = candidate.grounding_metadata
                if hasattr(grounding_metadata, 'grounding_chunks') and grounding_metadata.grounding_chunks:
                    for chunk in grounding_metadata.grounding_chunks:
                        if hasattr(chunk, 'web') and chunk.web:
                            web = chunk.web
                            if hasattr(web, 'uri') and hasattr(web, 'title'):
                                sources.append({
                                    "uri": web.uri,
                                    "title": web.title
                                })
        
        return {
            "status": "success",
            "data": {
                "text": text,
                "sources": sources
            }
        }
    except Exception as e:
        logging.error(f"Gemini market analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Neo4j API Proxy (Frontend에서 사용)
# ============================================
class Neo4jQueryRequest(BaseModel):
    query: str
    params: Optional[dict] = None
    database: Optional[str] = "architecture"  # "architecture" or "macro" (legacy: "news")

# Neo4j driver singletons
_neo4j_driver = None
_neo4j_macro_driver = None

def get_neo4j_driver(database: str = "architecture"):
    global _neo4j_driver, _neo4j_macro_driver
    
    # Common credentials
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")

    database = (database or "architecture").lower()
    if database == "news":
        database = "macro"

    if database == "macro":
        if _neo4j_macro_driver is None:
            from neo4j import GraphDatabase
            # Macro Graph URL
            uri = os.getenv("NEO4J_MACRO_URI")
            logging.info(f"[Neo4j] Initializing Macro Graph Driver. URI: {uri}")
            
            if not uri:
                 # Fallback/Log or Error if critical, but for now log warning
                 logging.warning("NEO4J_MACRO_URI not set. Macro Graph logic might fail.")
                 # Default to localhost if not set in dev, but in prod it should be set
                 uri = "bolt://localhost:7687" 

            _neo4j_macro_driver = GraphDatabase.driver(uri, auth=(user, password))
        return _neo4j_macro_driver
    else:
        # Default / Architecture
        if _neo4j_driver is None:
            from neo4j import GraphDatabase
            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            logging.info(f"[Neo4j] Initializing Architecture Graph Driver. URI: {uri}")
            _neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
        return _neo4j_driver

@api_router.post("/neo4j/query")
async def neo4j_run_query(request: Neo4jQueryRequest):
    """Neo4j Cypher 쿼리 실행"""
    try:
        driver = get_neo4j_driver(request.database)
        
        with driver.session() as session:
            result = session.run(request.query, request.params or {})
            
            nodes = []
            links = []
            node_ids = set()
            link_ids = set()
            raw_records = []
            
            for record in result:
                # Store raw record data
                raw_record = {}
                for key in record.keys():
                    value = record[key]
                    if hasattr(value, 'items'):
                        raw_record[key] = dict(value.items()) if hasattr(value, 'items') else str(value)
                    else:
                        raw_record[key] = value
                raw_records.append(raw_record)
                
                # Process for graph visualization
                for key in record.keys():
                    value = record[key]
                    
                    if value is None:
                        continue
                    
                    # Check if it's a Node
                    if hasattr(value, 'labels') and hasattr(value, 'element_id'):
                        node_id = value.element_id
                        if node_id not in node_ids:
                            nodes.append({
                                "id": node_id,
                                "labels": list(value.labels),
                                "properties": dict(value.items()) if hasattr(value, 'items') else {},
                                "val": 1
                            })
                            node_ids.add(node_id)
                    
                    # Check if it's a Relationship
                    elif hasattr(value, 'type') and hasattr(value, 'element_id'):
                        link_id = value.element_id
                        if link_id not in link_ids:
                            # Get start and end node IDs
                            start_id = value.start_node.element_id if hasattr(value, 'start_node') else None
                            end_id = value.end_node.element_id if hasattr(value, 'end_node') else None
                            
                            if start_id and end_id:
                                link_data = {
                                    "source": start_id,
                                    "target": end_id,
                                    "type": value.type
                                }
                                # Add relationship properties
                                if hasattr(value, 'items'):
                                    link_data.update(dict(value.items()))
                                links.append(link_data)
                                link_ids.add(link_id)
            
            return {
                "status": "success",
                "data": {
                    "nodes": nodes,
                    "links": links,
                    "raw": raw_records
                }
            }
    except Exception as e:
        logging.error(f"Neo4j query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/neo4j/health")
async def neo4j_health_check(database: str = Query("architecture")):
    """Neo4j 연결 상태 확인"""
    try:
        driver = get_neo4j_driver(database)
        with driver.session() as session:
            result = session.run("RETURN 1 as test")
            result.single()
        return {"status": "success", "message": f"Neo4j ({database}) connection is healthy"}
    except Exception as e:
        logging.error(f"Neo4j health check error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# API 라우터를 앱에 포함
app.include_router(api_router)


# ============================================
# 애플리케이션 시작 시 초기화
# ============================================
@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 실행되는 이벤트"""
    import os
    
    logging.info("Hobot 애플리케이션 시작 중...")
    
    # Gunicorn 환경 감지: GUNICORN_WORKER_ID 환경 변수가 있으면 워커 프로세스
    # Gunicorn 환경에서는 when_ready 훅에서 스케줄러가 시작되므로 여기서는 시작하지 않음
    # Uvicorn 개발 환경에서만 여기서 스케줄러 시작
    is_gunicorn_worker = os.getenv('GUNICORN_WORKER_ID') is not None
    
    if not is_gunicorn_worker:
        # Uvicorn 개발 환경에서만 스케줄러 시작
        try:
            from service.macro_trading.scheduler import start_all_schedulers
            threads = start_all_schedulers()
            logging.info(f"[Uvicorn] 모든 스케줄러가 시작되었습니다. (총 {len(threads)}개 스레드)")
        except Exception as e:
            logging.error(f"[Uvicorn] 스케줄러 시작 실패: {e}", exc_info=True)
            # 스케줄러 실패해도 애플리케이션은 계속 실행
    else:
        logging.info("[Gunicorn Worker] 스케줄러는 메인 프로세스의 when_ready 훅에서 시작됩니다.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
