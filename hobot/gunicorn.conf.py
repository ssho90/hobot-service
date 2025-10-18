# Gunicorn 설정 파일
import os

bind = "0.0.0.0:8991"
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 30
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
