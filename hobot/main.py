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
logging.basicConfig(filename=log_file_path, level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

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
    """시스템 어드민 여부 확인 (ssho, admin 사용자)"""
    username = current_user.get("username", "")
    return auth.is_system_admin(username)

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
        
        username = user["username"]
        is_sys_admin = auth.is_system_admin(username)
        
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
    username = current_user.get("username", "")
    is_sys_admin = auth.is_system_admin(username)
    
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
            all_log_entries = []  # (timestamp, log_line) 튜플 리스트
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    file_lines = f.readlines()
                    if file_lines:
                        for line in file_lines:
                            line = line.rstrip('\n\r')
                            if line.strip():  # 빈 줄 제외
                                timestamp = parse_timestamp(line)
                                all_log_entries.append((timestamp, line))
            except Exception as e:
                logging.warning(f"Could not read {log_path}: {e}")
                return {"status": "error", "message": f"Error reading log file: {str(e)}", "file": log_name}
            
            if all_log_entries:
                # 타임스탬프 기준으로 정렬 (오래된 것부터 최신 순)
                all_log_entries.sort(key=lambda x: x[0])
                
                # 시간 필터 적용
                filtered_entries = all_log_entries
                if start_time or end_time:
                    try:
                        if start_time:
                            start_dt = datetime.strptime(start_time, '%Y-%m-%dT%H:%M')
                            filtered_entries = [entry for entry in filtered_entries if entry[0] >= start_dt]
                        if end_time:
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

# API 라우터를 앱에 포함
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8991)