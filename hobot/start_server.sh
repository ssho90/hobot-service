#!/bin/bash

# Hobot FastAPI 서버 실행 스크립트

PORT=8991
echo "Starting Hobot FastAPI server with Gunicorn on port $PORT..."

# 포트 사용 중인 프로세스 확인 및 종료
echo "Checking for existing processes on port $PORT..."
EXISTING_PIDS=$(lsof -ti :$PORT 2>/dev/null)

if [ ! -z "$EXISTING_PIDS" ]; then
    echo "Found existing processes on port $PORT: $EXISTING_PIDS"
    echo "Killing existing processes..."
    kill -9 $EXISTING_PIDS 2>/dev/null
    sleep 2
    
    # 프로세스가 정말 종료되었는지 확인
    REMAINING_PIDS=$(lsof -ti :$PORT 2>/dev/null)
    if [ ! -z "$REMAINING_PIDS" ]; then
        echo "Warning: Some processes may still be running on port $PORT"
    else
        echo "Existing processes terminated successfully."
    fi
else
    echo "No existing processes found on port $PORT."
fi

# 가상환경 활성화 (있는 경우)
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "Virtual environment activated"
fi

# 의존성 설치
echo "Installing dependencies..."
python3 -m pip install -r requirements.txt

# Gunicorn으로 서버 실행
echo "Starting server on 0.0.0.0:$PORT"
echo "📝 Logs will be saved to:"
echo "   Access: $PROJECT_ROOT/hobot/logs/access.log"
echo "   Error:  $PROJECT_ROOT/hobot/logs/error.log"
echo "   App:    $PROJECT_ROOT/hobot/log.txt"
echo ""
echo "🔍 To view logs:"
echo "   ./view_logs.sh     - View recent logs"
echo "   ./log_monitor.sh   - Interactive log monitor"
echo "   tail -f logs/access.log - Real-time access logs"
echo "   tail -f logs/error.log  - Real-time error logs"
echo ""

python3 -m gunicorn -c gunicorn.conf.py asgi:asgi_app
