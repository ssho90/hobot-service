#!/bin/bash

# Hobot 통합 실행 스크립트 (Backend + Frontend)

BACKEND_PORT=8991
FRONTEND_PORT=3000
PROJECT_ROOT="/Users/ssho/project/hobot-service"

echo "🚀 Starting Hobot Full Stack Application..."
echo "Backend: http://localhost:$BACKEND_PORT"
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "================================================"

# 함수: 포트 사용 중인 프로세스 종료
kill_port_processes() {
    local port=$1
    local service_name=$2
    
    echo "🔍 Checking for existing $service_name processes on port $port..."
    EXISTING_PIDS=$(lsof -ti :$port 2>/dev/null)
    
    if [ ! -z "$EXISTING_PIDS" ]; then
        echo "⚠️  Found existing $service_name processes on port $port: $EXISTING_PIDS"
        echo "🔄 Killing existing processes..."
        kill -9 $EXISTING_PIDS 2>/dev/null
        sleep 2
        
        # 프로세스가 정말 종료되었는지 확인
        REMAINING_PIDS=$(lsof -ti :$port 2>/dev/null)
        if [ ! -z "$REMAINING_PIDS" ]; then
            echo "⚠️  Warning: Some $service_name processes may still be running on port $port"
        else
            echo "✅ Existing $service_name processes terminated successfully."
        fi
    else
        echo "✅ No existing $service_name processes found on port $port."
    fi
}

# 함수: 백엔드 시작
start_backend() {
    echo ""
    echo "🔧 Starting Backend (FastAPI)..."
    echo "================================================"
    
    cd "$PROJECT_ROOT/hobot"
    
    # 가상환경 활성화 (있는 경우)
    if [ -d "venv" ]; then
        source venv/bin/activate
        echo "🐍 Virtual environment activated"
    fi
    
    # 의존성 설치
    echo "📦 Installing backend dependencies..."
    python3 -m pip install -r requirements.txt > /dev/null 2>&1
    
    # 백엔드 서버 시작 (백그라운드)
    echo "🚀 Starting FastAPI server..."
    python3 -m uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT --reload > backend.log 2>&1 &
    BACKEND_PID=$!
    
    echo "✅ Backend started with PID: $BACKEND_PID"
    echo "📝 Backend logs:"
    echo "   Access: $PROJECT_ROOT/hobot/logs/access.log"
    echo "   Error:  $PROJECT_ROOT/hobot/logs/error.log"
    echo "   App:    $PROJECT_ROOT/hobot/log.txt"
}

# 함수: 프론트엔드 시작
start_frontend() {
    echo ""
    echo "🎨 Starting Frontend (React)..."
    echo "================================================"
    
    cd "$PROJECT_ROOT/hobot-ui"
    
    # Node.js 설치 확인
    if ! command -v node &> /dev/null; then
        echo "❌ Node.js is not installed. Please install Node.js first."
        echo "   Visit: https://nodejs.org/"
        exit 1
    fi
    
    # npm 설치 확인
    if ! command -v npm &> /dev/null; then
        echo "❌ npm is not installed. Please install npm first."
        exit 1
    fi
    
    # 의존성 설치
    echo "📦 Installing frontend dependencies..."
    npm install > /dev/null 2>&1
    
    # 프론트엔드 서버 시작 (백그라운드)
    echo "🚀 Starting React development server..."
    npm start > frontend.log 2>&1 &
    FRONTEND_PID=$!
    
    echo "✅ Frontend started with PID: $FRONTEND_PID"
    echo "📝 Frontend logs: $PROJECT_ROOT/hobot-ui/frontend.log"
}

# 함수: 서버 상태 확인
check_servers() {
    echo ""
    echo "🔍 Checking server status..."
    echo "================================================"
    
    sleep 5  # 서버 시작 대기
    
    # 백엔드 상태 확인
    if curl -s http://localhost:$BACKEND_PORT/ > /dev/null 2>&1; then
        echo "✅ Backend is running on http://localhost:$BACKEND_PORT"
    else
        echo "❌ Backend failed to start"
    fi
    
    # 프론트엔드 상태 확인
    if curl -s http://localhost:$FRONTEND_PORT/ > /dev/null 2>&1; then
        echo "✅ Frontend is running on http://localhost:$FRONTEND_PORT"
    else
        echo "❌ Frontend failed to start"
    fi
}

# 함수: 정리 (Ctrl+C 시 실행)
cleanup() {
    echo ""
    echo "🛑 Shutting down servers..."
    echo "================================================"
    
    if [ ! -z "$BACKEND_PID" ]; then
        echo "🔄 Stopping backend (PID: $BACKEND_PID)..."
        kill $BACKEND_PID 2>/dev/null
    fi
    
    if [ ! -z "$FRONTEND_PID" ]; then
        echo "🔄 Stopping frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID 2>/dev/null
    fi
    
    # 포트 정리
    kill_port_processes $BACKEND_PORT "backend"
    kill_port_processes $FRONTEND_PORT "frontend"
    
    echo "✅ All servers stopped."
    exit 0
}

# Ctrl+C 신호 처리
trap cleanup SIGINT

# 메인 실행
main() {
    # 포트 정리
    kill_port_processes $BACKEND_PORT "backend"
    kill_port_processes $FRONTEND_PORT "frontend"
    
    # 서버 시작
    start_backend
    start_frontend
    
    # 서버 상태 확인
    check_servers
    
    echo ""
    echo "🎉 Hobot Full Stack Application is running!"
    echo "================================================"
    echo "🌐 Frontend: http://localhost:$FRONTEND_PORT"
    echo "🔧 Backend API: http://localhost:$BACKEND_PORT"
    echo "📚 API Docs: http://localhost:$BACKEND_PORT/docs"
    echo ""
    echo "📝 Logs:"
    echo "   Backend:  tail -f $PROJECT_ROOT/hobot/backend.log"
    echo "   Frontend: tail -f $PROJECT_ROOT/hobot-ui/frontend.log"
    echo ""
    echo "⏹️  Press Ctrl+C to stop all servers"
    echo "================================================"
    
    # 서버가 실행 중인 동안 대기
    wait
}

# 스크립트 실행
main
