# Gunicorn 설정 파일
import os

bind = "0.0.0.0:8991"
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 300  # 5분 (300초) - 뉴스 API가 Tavily + LLM 요약, Rebalacing 등 오래 걸리는 작업 대비
keepalive = 2
preload_app = True

# 로그 설정
loglevel = "info"
accesslog = os.path.join(os.path.dirname(__file__), "logs", "access.log")
errorlog = os.path.join(os.path.dirname(__file__), "logs", "error.log")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 로그 파일 디렉토리 생성
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

# 프로세스 ID 파일
pidfile = os.path.join(log_dir, "gunicorn.pid")

# 데몬 모드 비활성화 (터미널에서 실행)
daemon = False

# 로그 로테이션 설정
logconfig = None

# Gunicorn 훅: 워커가 준비되었을 때 호출 (메인 프로세스에서만 실행)
def when_ready(server):
    """Gunicorn이 준비되었을 때 호출되는 훅 (메인 프로세스에서만 실행)"""
    import logging
    import sys
    import os
    
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # 스케줄러 시작 (메인 프로세스에서만 실행)
    try:
        # 프로젝트 루트를 Python 경로에 추가
        project_root = os.path.dirname(os.path.abspath(__file__))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        from service.macro_trading.scheduler import start_all_schedulers
        threads = start_all_schedulers()
        logger.info(f"[Gunicorn when_ready] 모든 스케줄러가 시작되었습니다. (총 {len(threads)}개 스레드)")
    except Exception as e:
        logger.error(f"[Gunicorn when_ready] 스케줄러 시작 실패: {e}", exc_info=True)
        # 스케줄러 실패해도 애플리케이션은 계속 실행
