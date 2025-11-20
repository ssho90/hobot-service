#!/bin/bash

# Python 캐시 삭제 및 서버 재시작 스크립트
# 사용법: ./clear_cache_and_restart.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🧹 Python 캐시 파일 삭제 중..."

# 현재 디렉토리와 하위 디렉토리의 모든 __pycache__ 삭제
find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true

# .pyc 파일 삭제
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# .pyo 파일 삭제
find . -type f -name "*.pyo" -delete 2>/dev/null || true

echo "✅ 캐시 파일 삭제 완료"
echo ""
echo "🔄 서버 재시작 중..."

# systemd 서비스 재시작
if systemctl is-active --quiet hobot.service 2>/dev/null; then
    echo "systemd 서비스 재시작 중..."
    sudo systemctl restart hobot.service
    sleep 3
    if systemctl is-active --quiet hobot.service 2>/dev/null; then
        echo "✅ 서버 재시작 완료"
        echo ""
        echo "📊 서버 상태:"
        sudo systemctl status hobot.service --no-pager -l | head -20
    else
        echo "❌ 서버 재시작 실패"
        echo ""
        echo "📊 서버 상태 (전체):"
        sudo systemctl status hobot.service --no-pager -l
    fi
else
    echo "⚠️  systemd 서비스가 실행 중이 아닙니다."
    echo ""
    echo "gunicorn 프로세스 확인 중..."
    GUNICORN_PIDS=$(pgrep -f "gunicorn.*asgi:asgi_app" || true)
    if [ ! -z "$GUNICORN_PIDS" ]; then
        echo "실행 중인 gunicorn 프로세스: $GUNICORN_PIDS"
        echo "프로세스를 종료하고 재시작하세요:"
        echo "  pkill -f 'gunicorn.*asgi:asgi_app'"
        echo "  cd /home/ec2-user/hobot-service/hobot"
        echo "  source venv/bin/activate"
        echo "  gunicorn -c gunicorn.conf.py asgi:asgi_app"
    else
        echo "gunicorn 프로세스가 실행 중이 아닙니다."
    fi
fi

echo ""
echo "💡 참고: gunicorn은 preload_app=True로 설정되어 있어"
echo "   코드 변경 후 반드시 재시작해야 새 코드가 적용됩니다."

