from dotenv import load_dotenv
import os

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
logging.basicConfig(filename=log_file_path, level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Pydantic 모델
class StrategyRequest(BaseModel):
    strategy: str

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
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
    """뉴스 파일에서 뉴스를 읽어옵니다. (브라우저용)"""
    try:
        result = news_manager.get_news_with_date()
        
        if result["news"]:
            return result
        else:
            raise HTTPException(status_code=404, detail="No news available")
    except Exception as e:
        logging.error(f"Error getting daily news: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/news-update")
async def update_daily_news(force: bool = Query(default=False, description="강제 업데이트 여부")):
    """뉴스를 새로 수집하고 저장합니다. (스케줄러/수동 업데이트용 - Tavily API 호출)"""
    try:
        return news_manager.update_news_with_tavily(compiled, force_update=force)
    except Exception as e:
        logging.error(f"Error updating daily news: {e}")
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
        from service.kis.kis import health_check as kis_health_check_func
        result = kis_health_check_func()
        logging.info(f"KIS health check result: {result}")
        return result
    except Exception as e:
        logging.error(f"Error in KIS health check: {e}")
        return {"status": "error", "message": str(e)}

@api_router.get("/kis/healthcheck")
async def kis_health_check_old():
    """기존 엔드포인트 (하위 호환성 유지)"""
    from service.kis import connection_test
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
            email=request.email,
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
        
        return {
            "status": "success",
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"]
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
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "email": current_user["email"],
        "role": current_user["role"]
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

# 로그 조회 API (admin 전용)
@api_router.get("/admin/logs")
async def get_logs(
    log_type: str = Query(..., description="로그 타입: backend, frontend, nginx"),
    lines: int = Query(100, description="읽을 줄 수"),
    admin_user: dict = Depends(require_admin)
):
    """로그 조회 (admin 전용)"""
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        log_content = ""
        log_file = ""
        
        if log_type == "backend":
            # 백엔드 로그: log.txt 우선, 없으면 error.log
            log_file = os.path.join(base_path, "log.txt")
            if not os.path.exists(log_file):
                # error.log 시도
                error_log = os.path.join(base_path, "logs", "error.log")
                if os.path.exists(error_log):
                    log_file = error_log
                else:
                    # access.log 시도
                    access_log = os.path.join(base_path, "logs", "access.log")
                    if os.path.exists(access_log):
                        log_file = access_log
                    else:
                        return {"status": "success", "log_type": log_type, "content": "No backend log file found", "file": ""}
        elif log_type == "frontend":
            # 프론트엔드 빌드 로그
            log_file = os.path.join(base_path, "..", "hobot-ui", "build", "asset-manifest.json")
            # 실제로는 빌드 로그가 없을 수 있으므로, logs 디렉토리 확인
            frontend_log = os.path.join(base_path, "logs", "frontend-build.log")
            if os.path.exists(frontend_log):
                log_file = frontend_log
            else:
                return {"status": "success", "log_type": log_type, "content": "No frontend build log available", "file": ""}
        elif log_type == "nginx":
            # nginx 로그
            nginx_logs = [
                "/var/log/nginx/access.log",
                "/var/log/nginx/error.log",
                "/var/log/nginx/hobot-access.log",
                "/var/log/nginx/hobot-error.log"
            ]
            log_file = None
            for nginx_log in nginx_logs:
                if os.path.exists(nginx_log):
                    log_file = nginx_log
                    break
            
            if not log_file:
                return {"status": "success", "log_type": log_type, "content": "No nginx log available", "file": ""}
        else:
            raise HTTPException(status_code=400, detail="Invalid log_type. Must be: backend, frontend, or nginx")
        
        if log_file and os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    all_lines = f.readlines()
                    # 최근 N줄만 반환
                    log_content = ''.join(all_lines[-lines:])
            except Exception as e:
                logging.error(f"Error reading log file {log_file}: {e}")
                return {"status": "error", "message": f"Error reading log file: {str(e)}", "file": log_file}
        else:
            return {"status": "success", "log_type": log_type, "content": "Log file not found", "file": log_file or "unknown"}
        
        return {
            "status": "success",
            "log_type": log_type,
            "content": log_content,
            "file": log_file,
            "lines": len(log_content.split('\n'))
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# API 라우터를 앱에 포함
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8991)