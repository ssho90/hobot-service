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
        
@api_router.post("/update-strategy")
async def update_strategy(request: StrategyRequest, platform: str = Query(default="upbit"), current_user: dict = Depends(require_admin)):
    """플랫폼별 현재 전략을 업데이트합니다. (Admin 전용)"""
    try:
        from service import strategy_manager
        strategy_manager.write_strategy(platform, request.strategy)
        return {"status": "success", "message": f"{platform} strategy updated"}
    except Exception as e:
        logging.error(f"Error updating strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/register")
async def register(request: RegisterRequest):
    """사용자 회원가입"""
    try:
        user_id = auth.create_user(request.username, request.password, request.email)
        return {"status": "success", "message": "User created successfully", "user_id": user_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Register error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@api_router.post("/login")
async def login(request: LoginRequest):
    """사용자 로그인"""
    user = auth.authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = auth.create_access_token(
        data={"sub": str(user["id"]), "username": user["username"], "role": user.get("role", "user")}
    )
    return {"access_token": access_token, "token_type": "bearer", "role": user.get("role", "user")}

@api_router.get("/users/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """현재 로그인한 사용자 정보 조회"""
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "email": current_user["email"],
        "role": current_user.get("role", "user")
    }

@api_router.get("/users")
async def read_users(current_user: dict = Depends(require_admin)):
    """사용자 목록 조회 (Admin 전용)"""
    users = auth.get_all_users()
    # 비밀번호 해시 제외
    for user in users:
        if "password_hash" in user:
            del user["password_hash"]
    return users

@api_router.put("/users/{user_id}")
async def update_user(user_id: int, request: UserUpdateRequest, current_user: dict = Depends(require_admin)):
    """사용자 정보 수정 (Admin 전용)"""
    try:
        auth.update_user(user_id, request.username, request.email, request.role)
        return {"status": "success", "message": "User updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Update user error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@api_router.delete("/users/{user_id}")
async def delete_user(user_id: int, current_user: dict = Depends(require_admin)):
    """사용자 삭제 (Admin 전용)"""
    try:
        auth.delete_user(user_id)
        return {"status": "success", "message": "User deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Delete user error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@api_router.get("/llm/logs")
async def get_llm_logs(
    page: int = 1, 
    limit: int = 20, 
    model: Optional[str] = None,
    current_user: dict = Depends(require_admin)
):
    """LLM 사용 로그 조회 (Admin 전용)"""
    try:
        from service.llm_monitoring import get_logs
        result = get_logs(page=page, limit=limit, model_filter=model)
        return result
    except Exception as e:
        logging.error(f"Error fetching LLM logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/llm/stats")
async def get_llm_stats(
    days: int = 7,
    current_user: dict = Depends(require_admin)
):
    """LLM 사용 통계 조회 (Admin 전용)"""
    try:
        from service.llm_monitoring import get_stats
        result = get_stats(days=days)
        return result
    except Exception as e:
        logging.error(f"Error fetching LLM stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/macro-trading/run-ai-analysis")
async def run_ai_analysis_endpoint(current_user: dict = Depends(require_admin)):
    """거시경제 AI 분석 실행 (Admin 전용)"""
    try:
        # 백그라운드 태스크로 실행하면 좋겠지만, 일단 동기적으로 실행
        from service.macro_trading.ai_strategist import run_ai_analysis
        success = run_ai_analysis()
        if success:
            return {"status": "success", "message": "AI analysis completed successfully"}
        else:
            return {"status": "error", "message": "AI analysis failed"}
    except Exception as e:
        logging.error(f"Error running AI analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/overview")
async def get_macro_overview():
    """거시경제 AI 분석 개요 조회"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 최신 AI 결정 가져오기
            cursor.execute("""
                SELECT * FROM ai_strategy_decisions 
                ORDER BY created_at DESC LIMIT 1
            """)
            decision = cursor.fetchone()
            
            if not decision:
                return {"status": "success", "data": None}
            
            # JSON 필드 파싱
            for key in ['target_allocation', 'quant_signals', 'qual_sentiment', 'account_pnl', 'recommended_stocks']:
                if decision.get(key) and isinstance(decision[key], str):
                    try:
                        decision[key] = json.loads(decision[key])
                    except json.JSONDecodeError:
                        pass
            
            return {"status": "success", "data": decision}
    except Exception as e:
        logging.error(f"Error fetching macro overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro/latest-news-summary")
async def get_latest_news_summary():
    """DB에 저장된 최신 경제 뉴스 요약을 반환합니다."""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 최신 AI 전략 결정 결과에서 뉴스 요약 추출
            cursor.execute("""
                SELECT qual_sentiment, created_at
                FROM ai_strategy_decisions
                ORDER BY created_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if not row:
                 return {"summary": "저장된 뉴스 요약이 없습니다."}
            
            qual_sentiment = row.get("qual_sentiment")
            if not qual_sentiment:
                return {"summary": "저장된 뉴스 요약이 없습니다. (데이터 없음)"}
                
            # JSON 파싱
            if isinstance(qual_sentiment, str):
                try:
                    qual_sentiment = json.loads(qual_sentiment)
                except:
                    return {"summary": "데이터 형식 오류"}
            
            # economic_news 구조 내의 news_summary 추출
            news_summary = qual_sentiment.get("news_summary")
            
            if not news_summary:
                 return {"summary": "뉴스 요약 데이터가 없습니다."}
                 
            return {"summary": news_summary, "created_at": row["created_at"]}
            
    except Exception as e:
        logging.error(f"Error fetching latest news summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/strategy-decisions-history")
async def get_strategy_decisions_history(page: int = 1, limit: int = 10):
    """과거 AI 전략 결정 이력 조회"""
    try:
        from service.database.db import get_db_connection
        
        offset = (page - 1) * limit
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 전체 카운트
            cursor.execute("SELECT COUNT(*) as count FROM ai_strategy_decisions")
            total_count = cursor.fetchone()['count']
            total_pages = (total_count + limit - 1) // limit
            
            # 이력 조회
            cursor.execute("""
                SELECT * FROM ai_strategy_decisions 
                ORDER BY created_at DESC 
                LIMIT %s OFFSET %s
            """, (limit, offset))
            decisions = cursor.fetchall()
            
            # JSON 필드 파싱
            for decision in decisions:
                for key in ['target_allocation', 'quant_signals', 'qual_sentiment', 'account_pnl', 'recommended_stocks']:
                    if decision.get(key) and isinstance(decision[key], str):
                        try:
                            decision[key] = json.loads(decision[key])
                        except json.JSONDecodeError:
                            pass
            
            return {
                "status": "success", 
                "data": decisions,
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "total_pages": total_pages
            }
    except Exception as e:
        logging.error(f"Error fetching strategy history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/macro-trading/translate")
async def translate_text_endpoint(
    request: dict,
    current_user: dict = Depends(require_admin)
):
    """텍스트 번역 및 DB 저장"""
    try:
        text = request.get("text")
        target_lang = request.get("target_lang", "ko")
        news_id = request.get("news_id")
        field_type = request.get("field_type") # title, description
        
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
            
        from service.llm_service import translate_text_with_llm
        translated_text = translate_text_with_llm(text, target_lang)
        
        # DB에 저장
        if news_id and field_type in ['title', 'description']:
            from service.database.db import get_db_connection
            with get_db_connection() as conn:
                cursor = conn.cursor()
                if field_type == 'title':
                    cursor.execute("UPDATE economic_news SET title_ko = %s WHERE id = %s", (translated_text, news_id))
                elif field_type == 'description':
                    cursor.execute("UPDATE economic_news SET description_ko = %s WHERE id = %s", (translated_text, news_id))
                conn.commit()
        
        return {"status": "success", "translated_text": translated_text}
    except Exception as e:
        logging.error(f"Translation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/sectors")
async def get_macro_sectors(asset_class: str = Query(None)):
    """Overview AI 추천 섹터/그룹 조회"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM overview_recommended_sectors WHERE is_active = TRUE"
            params = []
            
            if asset_class:
                query += " AND asset_class = %s"
                params.append(asset_class)
                
            query += " ORDER BY asset_class, display_order"
            
            cursor.execute(query, tuple(params))
            sectors = cursor.fetchall()
            
            return {"status": "success", "data": sectors}
    except Exception as e:
        logging.error(f"Error fetching sectors: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/macro-trading/sectors")
async def add_macro_sector(sector_data: dict, current_user: dict = Depends(require_admin)):
    """Overview AI 추천 섹터/그룹 추가"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO overview_recommended_sectors 
                (asset_class, sector_group, ticker, name, display_order, is_active)
                VALUES (%s, %s, %s, %s, %s, TRUE)
            """, (
                sector_data.get('asset_class'),
                sector_data.get('sector_group'),
                sector_data.get('ticker'),
                sector_data.get('name'),
                sector_data.get('display_order', 0)
            ))
            conn.commit()
            
            return {"status": "success", "message": "Sector added successfully"}
    except Exception as e:
        logging.error(f"Error adding sector: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/macro-trading/sectors/{sector_id}")
async def delete_macro_sector(sector_id: int, current_user: dict = Depends(require_admin)):
    """Overview AI 추천 섹터/그룹 삭제 (비활성화)"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("UPDATE overview_recommended_sectors SET is_active = FALSE WHERE id = %s", (sector_id,))
            conn.commit()
            
            return {"status": "success", "message": "Sector deleted successfully"}
    except Exception as e:
        logging.error(f"Error deleting sector: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/macro-trading/sectors/options")
async def get_sector_options():
    """자산군 및 섹터 그룹 옵션 목록 조회"""
    try:
        from service.database.db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 유니크한 자산군 조회
            cursor.execute("SELECT DISTINCT asset_class FROM overview_recommended_sectors ORDER BY asset_class")
            asset_classes = [row['asset_class'] for row in cursor.fetchall()]
            
            # 유니크한 섹터 그룹 조회
            cursor.execute("SELECT DISTINCT sector_group FROM overview_recommended_sectors ORDER BY sector_group")
            sector_groups = [row['sector_group'] for row in cursor.fetchall()]
            
            return {
                "status": "success", 
                "data": {
                    "asset_classes": asset_classes,
                    "sector_groups": sector_groups
                }
            }
    except Exception as e:
        logging.error(f"Error fetching sector options: {e}")
        raise HTTPException(status_code=500, detail=str(e))

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
