from dotenv import load_dotenv
import os
import json

load_dotenv(override=True)

from fastapi import FastAPI, HTTPException, Query, APIRouter, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
import logging
from service.slack_bot import post_message
from app import daily_news_summary
from service.news.daily_news_agent import compiled
from service.news import news_manager
from service import auth
# 서비스 시작 시 데이터베이스 초기화 (지연 초기화)
# 실제 사용 시점에 자동으로 초기화됨
from typing import Optional

app = FastAPI(title="Hobot API", version="1.0.0")

# API 라우터 생성
api_router = APIRouter(prefix="/api")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log.txt')
# 로깅 설정 (기존 설정이 있어도 덮어쓰기)
logging.basicConfig(
    filename=log_file_path, 
    level=logging.DEBUG,  # DEBUG 레벨로 변경하여 모든 로그 출력
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True  # 기존 핸들러가 있어도 재설정
)

# Pydantic 모델
class StrategyRequest(BaseModel):
    strategy: str

class RegisterRequest(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None

# JWT 인증
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보 가져오기"""
    token = credentials.credentials
    payload = auth.verify_token(token)
    user = auth.get_user_by_username(payload.get("username"))
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

@api_router.get("/upbit/trading")
async def upbit_trading():
    import time
    from service.upbit import upbit
    
    res = upbit.control_tower()
    post_message(f"upbit_trading result: {res}", channel="#auto-trading-logs")
    logging.info(f"upbit_trading result: {res}")
    return res

@api_router.get("/kis/health")
async def kis_health_check():
    """한국투자증권 API 헬스체크"""
    try:
        from service.macro_trading.kis.kis import health_check as kis_health_check_func
        result = kis_health_check_func()
        logging.info(f"KIS health check result: {result}")
        return result
    except Exception as e:
        logging.error(f"Error in KIS health check: {e}")
        return {"status": "error", "message": str(e)}

@api_router.get("/kis/balance")
async def kis_get_balance():
    """한국투자증권 계좌 잔액조회"""
    try:
        from service.macro_trading.kis.kis import get_balance_info_api
        result = get_balance_info_api()
        logging.info(f"KIS balance check result: {result.get('status')}")
        return result
    except Exception as e:
        logging.error(f"Error in KIS balance check: {e}")
        return {"status": "error", "message": str(e)}

@api_router.get("/kis/healthcheck")
async def kis_health_check_old():
    """기존 엔드포인트 (하위 호환성 유지)"""
    from service.macro_trading.kis import connection_test
    res = connection_test.run_connection_test()
    logging.info(f"kis health check result: {res}")
    return res

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

# Macro Trading API
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

@api_router.get("/macro-trading/account-snapshots")
async def get_account_snapshots(
    days: int = Query(default=30, description="조회할 일수 (기본값: 30일)"),
    admin_user: dict = Depends(require_admin)
):
    """계좌 스냅샷 조회 API (admin 전용)"""
    try:
        from service.database.db import get_db_connection
        from datetime import datetime, timedelta
        
        end_date = datetime.now().date()
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
                WHERE snapshot_date >= %s AND snapshot_date <= %s
                ORDER BY snapshot_date DESC
            """, (start_date, end_date))
            
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

# 자산군 상세 설정 관련 Pydantic 모델
class AssetClassDetailItem(BaseModel):
    ticker: str
    name: str
    weight: float  # 0-1 사이 값
    currency: Optional[str] = None  # 현금 자산군의 경우 통화 (KRW, USD)

class AssetClassDetailsRequest(BaseModel):
    asset_class: str  # stocks, bonds, alternatives, cash
    items: list[AssetClassDetailItem]

@api_router.get("/macro-trading/asset-class-details")
async def get_asset_class_details():
    """자산군별 상세 종목 및 비율 조회"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    asset_class,
                    ticker,
                    name,
                    weight,
                    currency,
                    is_active,
                    created_at,
                    updated_at
                FROM asset_class_details
                WHERE is_active = TRUE
                ORDER BY asset_class, weight DESC
            """)
            
            rows = cursor.fetchall()
            
            # 자산군별로 그룹화
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
                        "weight": float(row["weight"]),
                        "currency": row.get("currency"),
                        "is_active": bool(row["is_active"]),
                        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row["created_at"] else None,
                        "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S") if row["updated_at"] else None
                    })
            
            return {
                "status": "success",
                "data": result
            }
    except Exception as e:
        logging.error(f"Error fetching asset class details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/macro-trading/asset-class-details")
async def save_asset_class_details(
    request: AssetClassDetailsRequest,
    admin_user: dict = Depends(require_admin)
):
    """자산군별 상세 종목 및 비율 저장 (admin 전용)"""
    try:
        from service.database.db import get_db_connection
        from datetime import datetime
        
        # 자산군 유효성 검사
        valid_asset_classes = ["stocks", "bonds", "alternatives", "cash"]
        if request.asset_class not in valid_asset_classes:
            raise HTTPException(status_code=400, detail=f"Invalid asset_class. Must be one of: {', '.join(valid_asset_classes)}")
        
        # 비중 합계 검증 (0.99 ~ 1.01 사이 허용, 부동소수점 오차 고려)
        total_weight = sum(item.weight for item in request.items)
        if not (0.99 <= total_weight <= 1.01):
            raise HTTPException(status_code=400, detail=f"Total weight must be 1.0 (current: {total_weight:.4f})")
        
        # 각 항목의 비중 검증
        for item in request.items:
            if not (0 <= item.weight <= 1):
                raise HTTPException(status_code=400, detail=f"Item weight must be between 0 and 1 (ticker: {item.ticker}, weight: {item.weight})")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 기존 항목들을 비활성화
            cursor.execute("""
                UPDATE asset_class_details
                SET is_active = FALSE
                WHERE asset_class = %s
            """, (request.asset_class,))
            
            # 새 항목들 저장
            now = datetime.now()
            for item in request.items:
                cursor.execute("""
                    INSERT INTO asset_class_details 
                    (asset_class, ticker, name, weight, currency, is_active, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        name = VALUES(name),
                        weight = VALUES(weight),
                        currency = VALUES(currency),
                        is_active = TRUE,
                        updated_at = VALUES(updated_at)
                """, (request.asset_class, item.ticker, item.name, item.weight, item.currency, now, now))
            
            conn.commit()
            
            return {
                "status": "success",
                "message": f"Asset class details saved for {request.asset_class}",
                "asset_class": request.asset_class,
                "items_count": len(request.items)
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error saving asset class details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/macro-trading/rebalance")
async def manual_rebalance(
    admin_user: dict = Depends(require_admin)
):
    """수동 리밸런싱 실행 (admin 전용)"""
    try:
        from datetime import datetime
        # TODO: 실제 리밸런싱 로직 구현 (Phase 4에서 구현 예정)
        # 현재는 플레이스홀더 응답
        return {
            "status": "success",
            "message": "리밸런싱이 요청되었습니다. (실제 구현은 Phase 4에서 완료 예정)",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logging.error(f"Error executing manual rebalance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/search-stocks")
async def search_stocks(
    keyword: str = Query(..., description="검색 키워드 (종목명 일부)"),
    limit: int = Query(default=20, ge=1, le=100, description="최대 검색 결과 수")
):
    """종목명으로 티커 검색"""
    try:
        from service.macro_trading.kis.stock_collector import search_stock_tickers
        
        if not keyword or len(keyword.strip()) < 1:
            return {
                "status": "success",
                "data": [],
                "count": 0
            }
        
        results = search_stock_tickers(keyword.strip(), limit=limit)
        
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
    """AI 분석 Overview 조회"""
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
                    recommended_stocks,
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
                    "message": "AI 분석 결과가 아직 없습니다."
                }
            
            # JSON 필드 파싱
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
                from service.macro_trading.ai_strategist import (
                    SUB_MODEL_PORTFOLIOS,
                    get_sub_mp_etf_details
                )
                
                sub_mp_details = {}
                # 각 자산군별 Sub-MP 세부 종목 정보
                if sub_mp_data.get('stocks'):
                    stocks_sub_mp_id = sub_mp_data['stocks']
                    stocks_etf_details = get_sub_mp_etf_details(stocks_sub_mp_id)
                    if stocks_etf_details:
                        sub_mp_details['stocks'] = {
                            'sub_mp_id': stocks_sub_mp_id,
                            'sub_mp_name': SUB_MODEL_PORTFOLIOS.get(stocks_sub_mp_id, {}).get('name', ''),
                            'etf_details': stocks_etf_details
                        }
                
                if sub_mp_data.get('bonds'):
                    bonds_sub_mp_id = sub_mp_data['bonds']
                    bonds_etf_details = get_sub_mp_etf_details(bonds_sub_mp_id)
                    if bonds_etf_details:
                        sub_mp_details['bonds'] = {
                            'sub_mp_id': bonds_sub_mp_id,
                            'sub_mp_name': SUB_MODEL_PORTFOLIOS.get(bonds_sub_mp_id, {}).get('name', ''),
                            'etf_details': bonds_etf_details
                        }
                
                if sub_mp_data.get('alternatives'):
                    alternatives_sub_mp_id = sub_mp_data['alternatives']
                    alternatives_etf_details = get_sub_mp_etf_details(alternatives_sub_mp_id)
                    if alternatives_etf_details:
                        sub_mp_details['alternatives'] = {
                            'sub_mp_id': alternatives_sub_mp_id,
                            'sub_mp_name': SUB_MODEL_PORTFOLIOS.get(alternatives_sub_mp_id, {}).get('name', ''),
                            'etf_details': alternatives_etf_details
                        }
            
            recommended_stocks = row.get('recommended_stocks')
            if recommended_stocks:
                if isinstance(recommended_stocks, str):
                    recommended_stocks = json.loads(recommended_stocks)
            else:
                recommended_stocks = None
            
            # analysis_summary에서 reasoning 추출 (판단 근거: 이후 텍스트)
            analysis_summary = row['analysis_summary'] or ''
            reasoning = ''
            if '판단 근거:' in analysis_summary:
                parts = analysis_summary.split('판단 근거:')
                if len(parts) > 1:
                    reasoning = parts[1].strip()
                    analysis_summary = parts[0].strip()
            
            # Sub-MP reasoning 추출 (recommended_stocks에서 sub_mp reasoning이 있을 수 있음)
            sub_mp_reasoning = None
            if sub_mp_data and isinstance(sub_mp_data, dict):
                sub_mp_reasoning = sub_mp_data.get('reasoning')
            
            return {
                "status": "success",
                "data": {
                    "decision_date": row['decision_date'].strftime('%Y-%m-%d %H:%M:%S') if row['decision_date'] else None,
                    "analysis_summary": analysis_summary,
                    "reasoning": reasoning,
                    "mp_id": mp_id,
                    "target_allocation": target_allocation,
                    "sub_mp": sub_mp_details,
                    "sub_mp_reasoning": sub_mp_reasoning,
                    "recommended_stocks": recommended_stocks,
                    "created_at": row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if row['created_at'] else None
                }
            }
            
    except Exception as e:
        logging.error(f"Error getting AI overview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/macro-trading/run-ai-analysis")
async def run_ai_analysis_manual(admin_user: dict = Depends(require_admin)):
    """수동 AI 분석 실행 (Admin 전용)"""
    try:
        from service.macro_trading.ai_strategist import run_ai_analysis
        
        logging.info(f"수동 AI 분석 실행 요청: {admin_user.get('username')}")
        
        success = run_ai_analysis()
        
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
                    qual_sentiment,
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
            
            qual_sentiment = row.get('qual_sentiment')
            if qual_sentiment and isinstance(qual_sentiment, str):
                qual_sentiment = json.loads(qual_sentiment)
            
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
                    "qual_sentiment": qual_sentiment,
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
                    from service.macro_trading.ai_strategist import (
                        SUB_MODEL_PORTFOLIOS,
                        get_sub_mp_etf_details
                    )
                    
                    sub_mp_details = {}
                    if sub_mp_data.get('stocks'):
                        stocks_sub_mp_id = sub_mp_data['stocks']
                        stocks_etf_details = get_sub_mp_etf_details(stocks_sub_mp_id)
                        if stocks_etf_details:
                            sub_mp_details['stocks'] = {
                                'sub_mp_id': stocks_sub_mp_id,
                                'sub_mp_name': SUB_MODEL_PORTFOLIOS.get(stocks_sub_mp_id, {}).get('name', ''),
                                'etf_details': stocks_etf_details
                            }
                    
                    if sub_mp_data.get('bonds'):
                        bonds_sub_mp_id = sub_mp_data['bonds']
                        bonds_etf_details = get_sub_mp_etf_details(bonds_sub_mp_id)
                        if bonds_etf_details:
                            sub_mp_details['bonds'] = {
                                'sub_mp_id': bonds_sub_mp_id,
                                'sub_mp_name': SUB_MODEL_PORTFOLIOS.get(bonds_sub_mp_id, {}).get('name', ''),
                                'etf_details': bonds_etf_details
                            }
                    
                    if sub_mp_data.get('alternatives'):
                        alternatives_sub_mp_id = sub_mp_data['alternatives']
                        alternatives_etf_details = get_sub_mp_etf_details(alternatives_sub_mp_id)
                        if alternatives_etf_details:
                            sub_mp_details['alternatives'] = {
                                'sub_mp_id': alternatives_sub_mp_id,
                                'sub_mp_name': SUB_MODEL_PORTFOLIOS.get(alternatives_sub_mp_id, {}).get('name', ''),
                                'etf_details': alternatives_etf_details
                            }
                
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


@api_router.get("/macro-trading/rebalancing-history")
async def get_rebalancing_history(
    days: int = Query(default=30, description="조회할 일수 (기본값: 30일)"),
    admin_user: dict = Depends(require_admin)
):
    """리밸런싱 실행 이력 조회 API (admin 전용)"""
    try:
        from service.database.db import get_db_connection
        from datetime import datetime, timedelta
        import json
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id,
                    execution_date,
                    threshold_used,
                    drift_before,
                    drift_after,
                    trades_executed,
                    total_cost,
                    status,
                    error_message,
                    created_at
                FROM rebalancing_history
                WHERE execution_date >= %s AND execution_date <= %s
                ORDER BY execution_date DESC
            """, (start_date, end_date))
            
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                result.append({
                    "id": row["id"],
                    "execution_date": row["execution_date"].strftime("%Y-%m-%d %H:%M:%S") if row["execution_date"] else None,
                    "threshold_used": float(row["threshold_used"]) if row["threshold_used"] else 0,
                    "drift_before": row["drift_before"] if isinstance(row["drift_before"], dict) else (json.loads(row["drift_before"]) if row["drift_before"] else {}),
                    "drift_after": row["drift_after"] if isinstance(row["drift_after"], dict) else (json.loads(row["drift_after"]) if row["drift_after"] else {}),
                    "trades_executed": row["trades_executed"] if isinstance(row["trades_executed"], dict) else (json.loads(row["trades_executed"]) if row["trades_executed"] else {}),
                    "total_cost": float(row["total_cost"]) if row["total_cost"] else 0,
                    "status": row["status"],
                    "error_message": row["error_message"],
                    "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row["created_at"] else None
                })
            
            return {
                "status": "success",
                "data": result,
                "count": len(result)
            }
    except Exception as e:
        logging.error(f"Error fetching rebalancing history: {e}", exc_info=True)
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


@api_router.get("/macro-trading/economic-news")
async def get_economic_news(
    hours: int = Query(default=24, ge=1, le=168, description="조회할 시간 범위 (시간, 기본값: 24시간, 최대: 168시간)")
):
    """최근 경제 뉴스 조회 API
    
    economic_news 테이블에서 최근 N시간 내의 뉴스를 조회하여 반환합니다.
    
    Args:
        hours: 조회할 시간 범위 (기본값: 24시간)
    
    Returns:
        {
            "status": "success",
            "timestamp": "2024-12-19 10:30:00",
            "hours": 24,
            "total_count": 10,
            "news": [
                {
                    "id": 1,
                    "title": "US Stocks Rebound, Still Post Weekly Losses",
                    "link": "https://tradingeconomics.com/united-states/stock-market",
                    "country": "United States",
                    "category": "Stock Market",
                    "description": "US stocks sharply rebounded...",
                    "published_at": "2024-12-19 08:00:00",
                    "collected_at": "2024-12-19 10:00:00",
                    "source": "TradingEconomics Stream"
                },
                ...
            ]
        }
    """
    try:
        from service.database.db import get_db_connection
        from datetime import datetime, timedelta
        
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
                    source,
                    created_at
                FROM economic_news
                WHERE published_at >= %s
                ORDER BY published_at DESC
            """, (cutoff_time,))
            
            rows = cursor.fetchall()
            
            news_list = []
            for row in rows:
                news_item = {
                    "id": row.get("id"),
                    "title": row.get("title"),
                    "title_ko": row.get("title_ko"),
                    "link": row.get("link"),
                    "country": row.get("country"),
                    "country_ko": row.get("country_ko"),
                    "category": row.get("category"),
                    "category_ko": row.get("category_ko"),
                    "description": row.get("description"),
                    "description_ko": row.get("description_ko"),
                    "published_at": row.get("published_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("published_at") else None,
                    "collected_at": row.get("collected_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("collected_at") else None,
                    "source": row.get("source"),
                    "created_at": row.get("created_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("created_at") else None
                }
                news_list.append(news_item)
            
            return {
                "status": "success",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "hours": hours,
                "total_count": len(news_list),
                "news": news_list
            }
            
    except Exception as e:
        logging.error(f"Error fetching economic news: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "ko"  # "ko" or "en"
    news_id: Optional[int] = None  # 뉴스 ID (DB 저장용)
    field_type: Optional[str] = None  # 필드 타입: "title", "description", "country", "category"

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
        # 이메일이 없으면 사용자명@hobot.local로 설정
        email = request.email or f"{request.username}@hobot.local"
        user = auth.create_user(
            username=request.username,
            email=email,
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
async def login(request: LoginRequest):
    """로그인"""
    try:
        user = auth.get_user_by_username(request.username)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        if not auth.verify_password(request.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        # JWT 토큰 생성
        token = auth.create_access_token({
            "username": user["username"],
            "role": user["role"]
        })
        
        # admin role을 가진 사용자인지 확인
        is_sys_admin = user.get("role") == "admin"
        
        return {
            "status": "success",
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
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
        "username": current_user["username"],
        "email": current_user["email"],
        "role": current_user["role"],
        "is_system_admin": is_sys_admin
    }

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
async def update_user(user_id: int, request: UserUpdateRequest, admin_user: dict = Depends(require_admin)):
    """사용자 정보 업데이트 (admin 전용)"""
    try:
        user = auth.update_user(
            user_id=user_id,
            username=request.username,
            email=request.email,
            role=request.role
        )
        return {"status": "success", "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, admin_user: dict = Depends(require_admin)):
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

# 포트폴리오 관리 API (admin 전용)
@api_router.get("/admin/portfolios/model-portfolios")
async def get_model_portfolios(admin_user: dict = Depends(require_admin)):
    """모델 포트폴리오 목록 조회 (admin 전용)"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, description, strategy, 
                       allocation_stocks, allocation_bonds, 
                       allocation_alternatives, allocation_cash,
                       display_order, is_active, created_at, updated_at
                FROM model_portfolios
                ORDER BY display_order, id
            """)
            rows = cursor.fetchall()
            
            portfolios = []
            for row in rows:
                # NULL 값 처리 및 타입 변환
                allocation_stocks = row.get("allocation_stocks") or 0
                allocation_bonds = row.get("allocation_bonds") or 0
                allocation_alternatives = row.get("allocation_alternatives") or 0
                allocation_cash = row.get("allocation_cash") or 0
                
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
            cursor.execute("""
                UPDATE model_portfolios
                SET name = %s, description = %s, strategy = %s,
                    allocation_stocks = %s, allocation_bonds = %s,
                    allocation_alternatives = %s, allocation_cash = %s,
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
                # 외래키 컬럼 이름 확인 (여러 가능한 컬럼 이름 시도)
                etf_rows = []
                try:
                    # model_id로 시도
                    cursor.execute("""
                        SELECT category, ticker, name, weight, display_order
                        FROM sub_portfolio_compositions
                        WHERE model_id = %s
                        ORDER BY display_order
                    """, (row["id"],))
                    etf_rows = cursor.fetchall()
                except Exception:
                    try:
                        # portfolio_id로 시도
                        cursor.execute("""
                            SELECT category, ticker, name, weight, display_order
                            FROM sub_portfolio_compositions
                            WHERE portfolio_id = %s
                            ORDER BY display_order
                        """, (row["id"],))
                        etf_rows = cursor.fetchall()
                    except Exception:
                        try:
                            # sub_mp_id로 시도
                            cursor.execute("""
                                SELECT category, ticker, name, weight, display_order
                                FROM sub_portfolio_compositions
                                WHERE sub_mp_id = %s
                                ORDER BY display_order
                            """, (row["id"],))
                            etf_rows = cursor.fetchall()
                        except Exception as e:
                            logging.warning(f"ETF 상세 정보 조회 실패 (model_id/portfolio_id/sub_mp_id 모두 시도): {e}")
                            # 테이블 구조 확인을 위해 컬럼 정보 조회
                            try:
                                cursor.execute("SHOW COLUMNS FROM sub_portfolio_compositions")
                                columns = cursor.fetchall()
                                column_names = [col[0] for col in columns]
                                logging.info(f"sub_portfolio_compositions 컬럼: {column_names}")
                            except:
                                pass
                
                etf_details = []
                allocation = {}
                for etf_row in etf_rows:
                    # NULL 값 처리
                    category = etf_row.get("category") or ""
                    ticker = etf_row.get("ticker") or ""
                    name = etf_row.get("name") or ""
                    weight = etf_row.get("weight") or 0
                    
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
            # sub_portfolio_compositions 테이블의 외래키 컬럼 이름 확인
            # 여러 가능한 컬럼 이름 시도
            deleted = False
            try:
                cursor.execute("DELETE FROM sub_portfolio_compositions WHERE model_id = %s", (sub_mp_id,))
                deleted = True
            except Exception:
                try:
                    cursor.execute("DELETE FROM sub_portfolio_compositions WHERE portfolio_id = %s", (sub_mp_id,))
                    deleted = True
                except Exception:
                    try:
                        cursor.execute("DELETE FROM sub_portfolio_compositions WHERE sub_mp_id = %s", (sub_mp_id,))
                        deleted = True
                    except Exception as e:
                        logging.warning(f"ETF 상세 정보 삭제 실패: {e}")
            
            if not deleted:
                logging.warning(f"sub_portfolio_compositions 테이블에서 ETF 상세 정보를 삭제할 수 없습니다. 외래키 컬럼 이름을 확인해주세요.")
            
            # ETF 상세 정보 삽입
            etf_details = request.get("etf_details", [])
            for idx, etf in enumerate(etf_details):
                # 외래키 컬럼 이름에 따라 INSERT 쿼리 변경
                try:
                    cursor.execute("""
                        INSERT INTO sub_portfolio_compositions 
                        (model_id, category, ticker, name, weight, display_order)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        sub_mp_id,
                        etf.get("category", ""),
                        etf.get("ticker", ""),
                        etf.get("name", ""),
                        etf.get("weight", 0),
                        idx
                    ))
                except Exception:
                    try:
                        cursor.execute("""
                            INSERT INTO sub_portfolio_compositions 
                            (portfolio_id, category, ticker, name, weight, display_order)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            sub_mp_id,
                            etf.get("category", ""),
                            etf.get("ticker", ""),
                            etf.get("name", ""),
                            etf.get("weight", 0),
                            idx
                        ))
                    except Exception:
                        try:
                            cursor.execute("""
                                INSERT INTO sub_portfolio_compositions 
                                (sub_mp_id, category, ticker, name, weight, display_order)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """, (
                                sub_mp_id,
                                etf.get("category", ""),
                                etf.get("ticker", ""),
                                etf.get("name", ""),
                                etf.get("weight", 0),
                                idx
                            ))
                        except Exception as e:
                            logging.error(f"ETF 상세 정보 삽입 실패: {e}")
                            raise
            
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
                "log.txt": os.path.join(base_path, "log.txt"),
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
# Overview 추천 섹터 관리 API (Admin 전용)
# ============================================

class OverviewSectorItem(BaseModel):
    sector_group: str
    ticker: str
    name: str
    display_order: int = 0
    is_active: bool = True

class OverviewSectorRequest(BaseModel):
    asset_class: str  # stocks, bonds, alternatives, cash
    items: list[OverviewSectorItem]

@api_router.get("/admin/overview-recommended-sectors")
async def get_overview_recommended_sectors(
    admin_user: dict = Depends(require_admin)
):
    """Overview 추천 섹터/그룹 리스트 조회 (Admin 전용)"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id,
                    asset_class,
                    sector_group,
                    ticker,
                    name,
                    display_order,
                    is_active,
                    created_at,
                    updated_at
                FROM overview_recommended_sectors
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
                        "id": row["id"],
                        "ticker": row["ticker"],
                        "name": row["name"],
                        "display_order": row["display_order"],
                        "is_active": bool(row["is_active"]),
                        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row["created_at"] else None,
                        "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S") if row["updated_at"] else None
                    })
            
            return {
                "status": "success",
                "data": result
            }
    except Exception as e:
        logging.error(f"Error fetching overview recommended sectors: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/overview-recommended-sectors")
async def save_overview_recommended_sectors(
    request: OverviewSectorRequest,
    admin_user: dict = Depends(require_admin)
):
    """Overview 추천 섹터/그룹 리스트 저장 (Admin 전용)"""
    try:
        from service.database.db import get_db_connection
        from datetime import datetime
        
        # 자산군 유효성 검사
        valid_asset_classes = ["stocks", "bonds", "alternatives", "cash"]
        if request.asset_class not in valid_asset_classes:
            raise HTTPException(status_code=400, detail=f"Invalid asset_class. Must be one of: {', '.join(valid_asset_classes)}")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 기존 항목들을 비활성화
            cursor.execute("""
                UPDATE overview_recommended_sectors
                SET is_active = FALSE
                WHERE asset_class = %s
            """, (request.asset_class,))
            
            # 새 항목들 저장
            now = datetime.now()
            for item in request.items:
                cursor.execute("""
                    INSERT INTO overview_recommended_sectors 
                    (asset_class, sector_group, ticker, name, display_order, is_active, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        name = VALUES(name),
                        display_order = VALUES(display_order),
                        is_active = VALUES(is_active),
                        updated_at = VALUES(updated_at)
                """, (request.asset_class, item.sector_group, item.ticker, item.name, item.display_order, item.is_active, now, now))
            
            conn.commit()
            
            return {
                "status": "success",
                "message": f"Overview recommended sectors saved for {request.asset_class}",
                "asset_class": request.asset_class,
                "items_count": len(request.items)
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error saving overview recommended sectors: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/admin/overview-recommended-sectors/{sector_id}")
async def delete_overview_recommended_sector(
    sector_id: int,
    admin_user: dict = Depends(require_admin)
):
    """Overview 추천 섹터/그룹 삭제 (Admin 전용)"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM overview_recommended_sectors
                WHERE id = %s
            """, (sector_id,))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Sector not found")
            
            conn.commit()
            
            return {
                "status": "success",
                "message": f"Sector {sector_id} deleted"
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting overview recommended sector: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
            total = cursor.fetchone()['total']
            
            # 로그 조회
            query = f"""
                SELECT 
                    id,
                    model_name,
                    provider,
                    service_name,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    duration_ms,
                    request_prompt,
                    response_prompt,
                    created_at
                FROM llm_usage_logs
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])
            cursor.execute(query, params)
            
            logs = cursor.fetchall()
            
            # datetime 객체를 문자열로 변환
            for log in logs:
                if log.get('created_at'):
                    log['created_at'] = log['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            
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
    uvicorn.run(app, host="0.0.0.0", port=8991)