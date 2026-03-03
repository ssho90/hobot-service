#!/bin/bash

# Hobot FastAPI 서버 개발용 실행 스크립트 (Uvicorn)

PORT=8991
PYTHON312_BIN=""
PYTHON_BIN="python3"

resolve_python312() {
    if command -v python3.12 >/dev/null 2>&1; then
        PYTHON312_BIN=$(command -v python3.12)
        return 0
    fi

    if command -v python3 >/dev/null 2>&1; then
        if python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1; then
            PYTHON312_BIN=$(command -v python3)
            return 0
        fi
    fi

    return 1
}

run_with_sudo() {
    if command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        "$@"
    fi
}

ensure_python312() {
    if resolve_python312; then
        echo "Python 3.12 detected: $($PYTHON312_BIN --version)"
        return 0
    fi

    echo "Python 3.12 not found. Installing Python 3.12..."

    if [[ "$OSTYPE" == "darwin"* ]]; then
        if ! command -v brew >/dev/null 2>&1; then
            echo "Homebrew is required to install Python 3.12 on macOS."
            echo "Install Homebrew first: https://brew.sh"
            exit 1
        fi

        if brew list python@3.12 >/dev/null 2>&1; then
            echo "python@3.12 is already installed via Homebrew."
        else
            brew install python@3.12
        fi

        if [ -d "/opt/homebrew/opt/python@3.12/bin" ]; then
            export PATH="/opt/homebrew/opt/python@3.12/bin:$PATH"
        elif [ -d "/usr/local/opt/python@3.12/bin" ]; then
            export PATH="/usr/local/opt/python@3.12/bin:$PATH"
        fi
    elif command -v apt-get >/dev/null 2>&1; then
        run_with_sudo apt-get update
        run_with_sudo apt-get install -y software-properties-common
        run_with_sudo add-apt-repository -y ppa:deadsnakes/ppa
        run_with_sudo apt-get update
        run_with_sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
    else
        echo "Unsupported environment. Install Python 3.12 manually and rerun this script."
        exit 1
    fi

    if ! resolve_python312; then
        echo "Python 3.12 installation failed. Please install it manually."
        exit 1
    fi

    echo "Python 3.12 installed successfully: $($PYTHON312_BIN --version)"
}

echo "Starting Hobot FastAPI server in development mode on port $PORT..."

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

ensure_python312

# 가상환경 활성화/생성
if [ -d "../.venv" ]; then
    # shellcheck disable=SC1091
    source ../.venv/bin/activate
    echo "Virtual environment activated from ../.venv"
elif [ -d "venv" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
    echo "Virtual environment activated from venv"
else
    echo "No virtual environment found. Creating ../.venv with Python 3.12..."
    "$PYTHON312_BIN" -m venv ../.venv
    # shellcheck disable=SC1091
    source ../.venv/bin/activate
    echo "Virtual environment created and activated from ../.venv"
fi

if ! python -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 12) else 1)' >/dev/null 2>&1; then
    echo "Current virtual environment is not using Python 3.12+."
    echo "Recreate venv with Python 3.12 and rerun the script."
    exit 1
fi

PYTHON_BIN="python"
echo "Using Python runtime: $($PYTHON_BIN --version)"

# 의존성 설치
echo "Installing dependencies..."
"$PYTHON_BIN" -m pip install -r requirements.txt

# Uvicorn으로 개발 서버 실행
echo "Starting development server on 0.0.0.0:$PORT"
"$PYTHON_BIN" -m uvicorn main:app --host 0.0.0.0 --port $PORT --reload
