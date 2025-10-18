#!/bin/bash

# Hobot 간단 실행 스크립트 (Backend + Frontend)

echo "🚀 Starting Hobot Full Stack..."

# 포트 정리
echo "🧹 Cleaning up ports..."
lsof -ti :8991 | xargs kill -9 2>/dev/null
lsof -ti :3000 | xargs kill -9 2>/dev/null
sleep 2

# 백엔드 시작
echo "🔧 Starting Backend..."
cd hobot
python3 -m uvicorn main:app --host 0.0.0.0 --port 8991 --reload &
BACKEND_PID=$!

# 프론트엔드 시작
echo "🎨 Starting Frontend..."
cd ../hobot-ui
npm start &
FRONTEND_PID=$!

echo ""
echo "✅ Both servers started!"
echo "🌐 Frontend: http://localhost:3000"
echo "🔧 Backend: http://localhost:8991"
echo "📚 API Docs: http://localhost:8991/docs"
echo ""
echo "⏹️  Press Ctrl+C to stop"

# 정리 함수
cleanup() {
    echo "🛑 Stopping servers..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT
wait
