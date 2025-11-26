#!/bin/bash
set -e

# 배포 스크립트 - Hobot 서비스 배포 자동화
# 사용법: ./deploy.sh <DEPLOY_PATH> <GITHUB_REPO> <GH_TOKEN> [환경변수들...]

DEPLOY_PATH="${1:-/home/ec2-user/hobot-service}"
GITHUB_REPO="${2}"
GH_TOKEN="${3}"

# 환경 변수 (export된 값 사용)
export SL_TOKEN="${SL_TOKEN}"
export UP_ACCESS_KEY="${UP_ACCESS_KEY}"
export UP_SECRET_KEY="${UP_SECRET_KEY}"
export HT_API_KEY="${HT_API_KEY}"
export HT_SECRET_KEY="${HT_SECRET_KEY}"
export HT_ACCOUNT="${HT_ACCOUNT}"
export HT_ID="${HT_ID}"
export OPENAI_API_KEY="${OPENAI_API_KEY}"
export GOOGLE_API_KEY="${GOOGLE_API_KEY}"
export TAVILY_API_KEY="${TAVILY_API_KEY}"
export FRED_API_KEY="${FRED_API_KEY}"
export DOMAIN_NAME="${DOMAIN_NAME}"
# MySQL Database Configuration
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-3306}"
export DB_USER="${DB_USER}"
export DB_PASSWORD="${DB_PASSWORD}"
export DB_NAME="${DB_NAME:-hobot}"
export DB_CHARSET="${DB_CHARSET:-utf8mb4}"
# JWT Secret Key
export JWT_SECRET_KEY="${JWT_SECRET_KEY}"

# 유틸리티 함수 (stderr로 출력하여 stdout과 분리)
log_info() { echo "ℹ️  $*" >&2; }
log_success() { echo "✅ $*" >&2; }
log_error() { echo "❌ $*" >&2; exit 1; }
log_warn() { echo "⚠️  $*" >&2; }

# Git 업데이트
update_repository() {
  log_info "Updating repository..."
  cd "${DEPLOY_PATH}" || {
    log_warn "Deploy directory not found. Creating..."
    mkdir -p "${DEPLOY_PATH}"
    cd "${DEPLOY_PATH}"
  }
  
  if [ -d ".git" ]; then
    # 로컬 변경사항 처리
    git fetch "https://${GH_TOKEN}@github.com/${GITHUB_REPO}.git" main || true
    
    # 로컬 변경사항이 있으면 stash 또는 reset
    if ! git diff-index --quiet HEAD --; then
      log_warn "Local changes detected, stashing..."
      git stash || true
    fi
    
    # untracked 파일 중 merge를 방해하는 파일 제거
    if [ -f "hobot/service/database/users.json" ]; then
      log_warn "Removing untracked users.json file..."
      rm -f "hobot/service/database/users.json" || true
    fi
    
    # package-lock.json 변경사항 무시
    if [ -f "hobot-ui/package-lock.json" ]; then
      git checkout -- "hobot-ui/package-lock.json" 2>/dev/null || true
    fi
    
    # 강제로 pull (로컬 변경사항 덮어쓰기)
    git reset --hard "origin/main" 2>/dev/null || git reset --hard "main" 2>/dev/null || true
    git pull "https://${GH_TOKEN}@github.com/${GITHUB_REPO}.git" main || {
      log_warn "Git pull failed, trying reset and pull..."
      git fetch "https://${GH_TOKEN}@github.com/${GITHUB_REPO}.git" main
      git reset --hard "origin/main" || git reset --hard "main"
    }
  else
    if [ "$(ls -A . 2>/dev/null)" ]; then
      log_warn "Directory is not empty, backing up..."
      cd ..
      BACKUP_NAME="${DEPLOY_PATH}.backup.$(date +%s)"
      mv "${DEPLOY_PATH}" "${BACKUP_NAME}"
      mkdir -p "${DEPLOY_PATH}"
      cd "${DEPLOY_PATH}"
    fi
    git clone "https://${GH_TOKEN}@github.com/${GITHUB_REPO}.git" .
  fi
  log_success "Repository updated"
}

# Python 환경 설정
setup_python_env() {
  log_info "Setting up Python environment..."
  cd "${DEPLOY_PATH}/hobot"
  
  # Python 3.12 확인
  if ! command -v python3.12 &> /dev/null; then
    log_error "Python 3.12 is not installed"
  fi
  
  # 가상환경 생성
  if [ ! -d "venv" ]; then
    # uv 설치
    if ! command -v uv &> /dev/null; then
      log_info "Installing uv..."
      curl -LsSf https://astral.sh/uv/install.sh | sh
      export PATH="$HOME/.cargo/bin:$PATH"
    fi
    
    # 가상환경 생성
    uv venv venv --python 3.12 || log_error "Failed to create virtual environment"
    chmod +x venv/bin/* 2>/dev/null || true
    
    # pip 설치
    if [ -f "venv/bin/python" ]; then
      venv/bin/python -m ensurepip --upgrade --default-pip 2>&1 || {
        curl -s https://bootstrap.pypa.io/get-pip.py | venv/bin/python
      }
    fi
  fi
  
  # Python 실행 파일 확인
  if [ ! -f "venv/bin/python" ] || [ ! -x "venv/bin/python" ]; then
    log_error "Python executable not found or not executable"
  fi
  
  PYTHON_CMD="venv/bin/python"
  
  # 의존성 설치
  log_info "Installing dependencies..."
  ${PYTHON_CMD} -m pip install --upgrade pip >/dev/null 2>&1 || true
  ${PYTHON_CMD} -m pip install -r requirements.txt >/dev/null 2>&1
  
  # gunicorn 확인
  if ! ${PYTHON_CMD} -m gunicorn --version &>/dev/null; then
    ${PYTHON_CMD} -m pip install gunicorn[gevent] >/dev/null 2>&1 || ${PYTHON_CMD} -m pip install gunicorn >/dev/null 2>&1
  fi
  
  log_success "Python environment ready"
  echo "${PYTHON_CMD}"
}

# .env 파일 생성
create_env_file() {
  log_info "Creating .env file..."
  cat > "${DEPLOY_PATH}/hobot/.env" << EOF
# Environment variables for Hobot service
# Generated automatically during deployment from GitHub Actions secrets/variables

# API Keys
SL_TOKEN=${SL_TOKEN}
UP_ACCESS_KEY=${UP_ACCESS_KEY}
UP_SECRET_KEY=${UP_SECRET_KEY}
HT_API_KEY=${HT_API_KEY}
HT_SECRET_KEY=${HT_SECRET_KEY}
HT_ACCOUNT=${HT_ACCOUNT}
HT_ID=${HT_ID}
OPENAI_API_KEY=${OPENAI_API_KEY}
GOOGLE_API_KEY=${GOOGLE_API_KEY}
TAVILY_API_KEY=${TAVILY_API_KEY}
FRED_API_KEY=${FRED_API_KEY}

# MySQL Database Configuration
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DB_NAME=${DB_NAME}
DB_CHARSET=${DB_CHARSET}

# JWT Secret Key
JWT_SECRET_KEY=${JWT_SECRET_KEY}
EOF
  chmod 600 "${DEPLOY_PATH}/hobot/.env"
  log_success ".env file created"
}

# 백엔드 배포
deploy_backend() {
  log_info "Deploying backend..."
  cd "${DEPLOY_PATH}/hobot"
  
  PYTHON_CMD=$(setup_python_env)
  create_env_file
  
  # Python 캐시 삭제 (이전 코드가 메모리에 남지 않도록)
  log_info "Clearing Python cache files..."
  find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
  find . -type f -name "*.pyc" -delete 2>/dev/null || true
  find . -type f -name "*.pyo" -delete 2>/dev/null || true
  log_success "Python cache cleared"
  
  # 전략 초기화
  log_info "Initializing strategies..."
  ${PYTHON_CMD} service/utils/init_strategy_pause.py >/tmp/init_strategy.log 2>&1 || {
    cat /tmp/init_strategy.log >&2
    log_error "Failed to initialize strategies"
  }
  rm -f /tmp/init_strategy.log
  
  mkdir -p logs
  
  # Systemd 서비스 설정
  if [ -f "../.github/deploy/hobot.service" ]; then
    log_info "Setting up systemd service..."
    sudo cp ../.github/deploy/hobot.service /etc/systemd/system/hobot.service
    sudo sed -i "s|/home/ec2-user/hobot-service|${DEPLOY_PATH}|g" /etc/systemd/system/hobot.service
    sudo sed -i "s|User=ec2-user|User=$(whoami)|g" /etc/systemd/system/hobot.service
    
    PYTHON_PATH="${DEPLOY_PATH}/hobot/venv/bin/python"
    sudo sed -i "s|/home/ec2-user/hobot-service/hobot/venv/bin/python|${PYTHON_PATH}|g" /etc/systemd/system/hobot.service
    
    sudo mkdir -p "${DEPLOY_PATH}/hobot/logs"
    sudo chown -R "$(whoami):$(whoami)" "${DEPLOY_PATH}/hobot/logs"
    
    sudo systemctl daemon-reload
    sudo systemctl enable hobot.service
    
    # 서비스 중지 (캐시 정리를 위해)
    log_info "Stopping backend service for clean restart..."
    sudo systemctl stop hobot.service 2>/dev/null || true
    sleep 2
    
    # gunicorn 프로세스가 남아있으면 강제 종료
    GUNICORN_PIDS=$(pgrep -f "gunicorn.*asgi:asgi_app" 2>/dev/null || true)
    if [ ! -z "${GUNICORN_PIDS}" ]; then
      log_info "Killing remaining gunicorn processes: ${GUNICORN_PIDS}"
      sudo pkill -f "gunicorn.*asgi:asgi_app" 2>/dev/null || true
      sleep 2
    fi
    
    # 서비스 재시작
    log_info "Starting backend service..."
    sudo systemctl start hobot.service
    sleep 5
    
    if sudo systemctl is-active --quiet hobot.service; then
      log_success "Backend service is running"
    else
      log_error "Backend service failed to start"
      log_info "Service status:"
      sudo systemctl status hobot.service --no-pager -l | head -30 >&2
    fi
  else
    # 직접 실행
    PORT=8991
    EXISTING_PIDS=$(lsof -ti :${PORT} 2>/dev/null || true)
    [ ! -z "${EXISTING_PIDS}" ] && kill -9 ${EXISTING_PIDS} 2>/dev/null || true
    
    nohup ${PYTHON_CMD} -m gunicorn -c gunicorn.conf.py asgi:asgi_app > logs/gunicorn.log 2>&1 &
    sleep 2
    log_success "Backend started"
  fi
}

# Node.js 버전 확인 및 업그레이드
setup_nodejs() {
  log_info "Checking Node.js version..."
  
  # 현재 Node.js 버전 확인
  CURRENT_NODE_VERSION=$(node --version 2>/dev/null || echo "")
  if [ -n "${CURRENT_NODE_VERSION}" ]; then
    CURRENT_NODE_MAJOR=$(echo "${CURRENT_NODE_VERSION}" | cut -d'v' -f2 | cut -d'.' -f1)
    if [ "${CURRENT_NODE_MAJOR}" -ge 18 ]; then
      log_info "Node.js version is sufficient: ${CURRENT_NODE_VERSION}"
      return
    fi
  fi
  
  # nvm 설치 확인
  export NVM_DIR="$HOME/.nvm"
  if [ ! -d "$NVM_DIR" ]; then
    log_info "Installing nvm..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash || {
      log_warn "Failed to install nvm, using system Node.js"
      if ! command -v node &>/dev/null; then
        log_error "Node.js is not installed and nvm installation failed"
      fi
      return
    }
  fi
  
  # nvm 로드
  [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
  [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
  
  # Node.js 18 이상 설치
  if type nvm &>/dev/null; then
    log_info "Installing Node.js 18 via nvm..."
    nvm install 18 || nvm install 20 || {
      log_warn "Failed to install Node.js 18/20 via nvm, trying system Node.js"
      if ! command -v node &>/dev/null; then
        log_error "Node.js is not installed"
      fi
      return
    }
    nvm use 18 || nvm use 20 || true
    nvm alias default 18 || nvm alias default 20 || true
  fi
  
  # Node.js 버전 확인
  NODE_VERSION=$(node --version 2>/dev/null || echo "unknown")
  log_info "Node.js version: ${NODE_VERSION}"
  
  if ! command -v node &>/dev/null; then
    log_error "Node.js is not installed"
  fi
}

# 프론트엔드 빌드
build_frontend() {
  log_info "Building frontend..."
  cd "${DEPLOY_PATH}/hobot-ui"
  
  # Node.js 설정
  setup_nodejs
  
  # nvm이 설치되어 있으면 사용
  export NVM_DIR="$HOME/.nvm"
  [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
  [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
  
  # npm 캐시 정리
  npm cache clean --force 2>/dev/null || true
  
  log_info "Installing dependencies..."
  npm install || log_error "Failed to install npm dependencies"
  
  export NODE_OPTIONS="--max-old-space-size=1536"
  
  # 백그라운드 빌드
  rm -f ../hobot/logs/frontend-build-*.flag
  nohup bash -c "export NVM_DIR=\"\$HOME/.nvm\" && [ -s \"\$NVM_DIR/nvm.sh\" ] && \. \"\$NVM_DIR/nvm.sh\" && export NODE_OPTIONS='--max-old-space-size=1536' && npm run build && touch ../hobot/logs/frontend-build-complete.flag || (echo 'Build failed' && cat ../hobot/logs/frontend-build.log && touch ../hobot/logs/frontend-build-failed.flag)" > ../hobot/logs/frontend-build.log 2>&1 &
  
  # 빌드 완료 대기
  BUILD_TIMEOUT=600
  ELAPSED=0
  while [ ${ELAPSED} -lt ${BUILD_TIMEOUT} ]; do
    [ -f "../hobot/logs/frontend-build-complete.flag" ] && break
    if [ -f "../hobot/logs/frontend-build-failed.flag" ]; then
      log_error "Frontend build failed. Check logs:"
      tail -50 ../hobot/logs/frontend-build.log >&2
      exit 1
    fi
    sleep 10
    ELAPSED=$((ELAPSED + 10))
    [ $((ELAPSED % 60)) -eq 0 ] && log_info "Build in progress... (${ELAPSED}s)"
  done
  
  if [ ! -f "../hobot/logs/frontend-build-complete.flag" ]; then
    log_error "Frontend build timeout. Check logs:"
    tail -50 ../hobot/logs/frontend-build.log >&2
    exit 1
  fi
  
  [ ! -d "build" ] && log_error "Frontend build directory not found"
  
  # 빌드 디렉토리를 /var/www/hobot로 복사 (nginx가 접근하기 쉬운 표준 위치)
  log_info "Copying build directory to /var/www/hobot..."
  sudo mkdir -p /var/www/hobot
  sudo rm -rf /var/www/hobot/*
  sudo cp -r build/* /var/www/hobot/
  
  # nginx 사용자/그룹으로 소유권 변경
  if id nginx &>/dev/null; then
    sudo chown -R nginx:nginx /var/www/hobot
  else
    # nginx 사용자가 없으면 www-data 사용 (Ubuntu/Debian)
    if id www-data &>/dev/null; then
      sudo chown -R www-data:www-data /var/www/hobot
    else
      # 둘 다 없으면 root 소유로 설정하고 기타 사용자 읽기 권한 부여
      sudo chown -R root:root /var/www/hobot
      sudo chmod -R 755 /var/www/hobot
    fi
  fi
  
  # 권한 설정
  sudo chmod -R 755 /var/www/hobot
  sudo find /var/www/hobot -type f -exec chmod 644 {} \;
  sudo find /var/www/hobot -type d -exec chmod 755 {} \;
  
  log_success "Frontend build completed and copied to /var/www/hobot"
}

# nginx 설정 비활성화 스크립트
disable_default_nginx_config() {
  cat > /tmp/disable_nginx_server.py << 'PYEOF'
import re
import sys

try:
    with open('/etc/nginx/nginx.conf', 'r') as f:
        lines = f.readlines()
    
    in_http = False
    http_depth = 0
    in_server = False
    server_depth = 0
    result = []
    modified = False
    
    for line in lines:
        stripped = line.lstrip()
        
        if re.match(r'^\s*http\s*{', line):
            in_http = True
            http_depth = line.count('{') - line.count('}')
            result.append(line)
            continue
        
        if in_http:
            http_depth += line.count('{') - line.count('}')
            
            if re.match(r'^\s*server\s*{', line) and not stripped.startswith('#'):
                in_server = True
                server_depth = 1
                result.append('    # DISABLED BY DEPLOYMENT: ' + line.lstrip())
                modified = True
                continue
            
            if in_server:
                server_depth += line.count('{') - line.count('}')
                if not stripped.startswith('#'):
                    result.append('    # ' + line)
                else:
                    result.append(line)
                if server_depth == 0:
                    in_server = False
                continue
            
            if http_depth == 0 and stripped.startswith('}'):
                in_http = False
            
            result.append(line)
        else:
            result.append(line)
    
    if modified:
        with open('/etc/nginx/nginx.conf', 'w') as f:
            f.writelines(result)
        print("✅ Disabled default server block")
        sys.exit(0)
    else:
        print("ℹ️  No default server block found")
        sys.exit(0)
        
except Exception as e:
    print(f"⚠️  Error: {e}")
    sys.exit(1)
PYEOF
  sudo python3 /tmp/disable_nginx_server.py
  rm -f /tmp/disable_nginx_server.py
}

# nginx 설정
setup_nginx() {
  log_info "Setting up nginx..."
  
  # nginx 설치
  if ! command -v nginx &> /dev/null; then
    log_info "Installing nginx..."
    sudo yum install -y nginx 2>/dev/null || sudo apt-get update && sudo apt-get install -y nginx
  fi
  
  # sites-available, sites-enabled 디렉토리 생성 (없는 경우)
  sudo mkdir -p /etc/nginx/sites-available
  sudo mkdir -p /etc/nginx/sites-enabled
  
  # nginx.conf에 sites-enabled include 추가 (없는 경우)
  if [ -f "/etc/nginx/nginx.conf" ]; then
    [ ! -f "/etc/nginx/nginx.conf.backup" ] && sudo cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.backup
    
    # sites-enabled include가 없으면 추가
    if ! sudo grep -q "include.*sites-enabled" /etc/nginx/nginx.conf; then
      log_info "Adding sites-enabled include to nginx.conf..."
      # Python으로 안전하게 추가
      cat > /tmp/add_nginx_include.py << 'PYEOF'
import re
import sys

try:
    with open('/etc/nginx/nginx.conf', 'r') as f:
        lines = f.readlines()
    
    # 이미 include가 있는지 확인
    for line in lines:
        if 'include /etc/nginx/sites-enabled' in line:
            print("ℹ️  sites-enabled include already exists")
            sys.exit(0)
    
    # http 블록 찾기
    in_http = False
    http_brace_count = 0
    insert_pos = -1
    
    for i, line in enumerate(lines):
        if re.match(r'^\s*http\s*{', line):
            in_http = True
            http_brace_count = line.count('{') - line.count('}')
            insert_pos = i + 1
            continue
        
        if in_http:
            http_brace_count += line.count('{') - line.count('}')
            if http_brace_count == 0:
                # http 블록이 닫히기 전에 추가
                insert_pos = i
                break
    
    if insert_pos > 0:
        # include 문 추가
        indent = '    '  # 4 spaces
        include_line = indent + 'include /etc/nginx/sites-enabled/*;\n'
        lines.insert(insert_pos, include_line)
        
        with open('/etc/nginx/nginx.conf', 'w') as f:
            f.writelines(lines)
        print("✅ Added sites-enabled include to nginx.conf")
        sys.exit(0)
    else:
        print("⚠️  Could not find http block in nginx.conf")
        sys.exit(1)
        
except Exception as e:
    print(f"⚠️  Error: {e}")
    sys.exit(1)
PYEOF
      sudo python3 /tmp/add_nginx_include.py || log_warn "Failed to add sites-enabled include (may already exist)"
      rm -f /tmp/add_nginx_include.py
    fi
    
    # nginx.conf의 기본 server 블록 비활성화
    sudo grep -q "^\s*server\s*{" /etc/nginx/nginx.conf && disable_default_nginx_config || true
  fi
  
  # 기본 설정 비활성화 (conf.d의 기본 설정들)
  for conf_file in /etc/nginx/conf.d/*.conf; do
    [ -f "$conf_file" ] && sudo mv "$conf_file" "${conf_file}.disabled" 2>/dev/null || true
  done
  
  # sites-enabled의 default 설정 삭제 (가이드 3단계 A)
  if [ -f "/etc/nginx/sites-enabled/default" ]; then
    log_info "Removing default site from sites-enabled..."
    sudo rm -f /etc/nginx/sites-enabled/default
  fi
  
  # 우리 설정을 sites-available에 복사 (가이드 2단계 A)
  log_info "Creating nginx configuration in sites-available..."
  
  # 기존 설정이 있고 Certbot이 설정한 SSL 부분이 있으면 백업
  CERTBOT_CONFIGURED=false
  if [ -f "/etc/nginx/sites-available/hobot" ] && sudo grep -q "managed by Certbot" /etc/nginx/sites-available/hobot; then
    log_info "Certbot SSL configuration detected, will preserve it..."
    sudo cp /etc/nginx/sites-available/hobot /etc/nginx/sites-available/hobot.certbot-backup
    CERTBOT_CONFIGURED=true
  fi
  
  # 새 설정 파일 복사
  sudo cp "${DEPLOY_PATH}/.github/deploy/nginx.conf" /etc/nginx/sites-available/hobot
  sudo sed -i "s|/home/ec2-user/hobot-service|${DEPLOY_PATH}|g" /etc/nginx/sites-available/hobot
  
  # 도메인 이름 설정 (가이드 3단계)
  if [ -n "${DOMAIN_NAME}" ] && [ "${DOMAIN_NAME}" != "" ]; then
    log_info "Setting server_name to domain: ${DOMAIN_NAME} www.${DOMAIN_NAME}"
    # server_name _; 를 도메인으로 변경
    sudo sed -i "s|server_name _;|server_name ${DOMAIN_NAME} www.${DOMAIN_NAME};|g" /etc/nginx/sites-available/hobot
  else
    log_info "No domain name provided, using default server_name (_)"
  fi
  
  # Certbot이 이미 설정한 경우 SSL 설정 자동 복원
  if [ "$CERTBOT_CONFIGURED" = true ] && command -v certbot &>/dev/null; then
    log_info "Restoring Certbot SSL configuration using certbot..."
    # Certbot의 --nginx 옵션을 사용하여 SSL 설정을 다시 적용 (기존 인증서 사용, non-interactive)
    # --reinstall 옵션은 설정만 다시 적용하고 인증서는 갱신하지 않음
    sudo certbot --nginx --reinstall --cert-name stockoverflow.org -d stockoverflow.org -d www.stockoverflow.org --non-interactive --keep-until-expiring 2>/dev/null && {
      log_success "Certbot SSL configuration restored"
    } || {
      log_warn "Certbot reinstall failed, SSL may need manual configuration"
    }
  fi
  
  sudo chmod 644 /etc/nginx/sites-available/hobot
  
  # sites-enabled에 심볼릭 링크 생성 (가이드 3단계 A)
  log_info "Enabling hobot site..."
  sudo ln -sf /etc/nginx/sites-available/hobot /etc/nginx/sites-enabled/hobot
  
  # 프론트엔드 빌드 디렉토리 권한 확인 및 설정
  FRONTEND_BUILD_DIR="/var/www/hobot"
  if [ -d "${FRONTEND_BUILD_DIR}" ]; then
    log_info "Verifying frontend build directory permissions..."
    # nginx 사용자/그룹으로 소유권 확인
    if id nginx &>/dev/null; then
      sudo chown -R nginx:nginx "${FRONTEND_BUILD_DIR}" 2>/dev/null || true
    elif id www-data &>/dev/null; then
      sudo chown -R www-data:www-data "${FRONTEND_BUILD_DIR}" 2>/dev/null || true
    fi
    # 권한 설정
    sudo chmod -R 755 "${FRONTEND_BUILD_DIR}" 2>/dev/null || true
    sudo find "${FRONTEND_BUILD_DIR}" -type f -exec chmod 644 {} \; 2>/dev/null || true
    sudo find "${FRONTEND_BUILD_DIR}" -type d -exec chmod 755 {} \; 2>/dev/null || true
  fi
  
  # SELinux 설정 (있는 경우)
  if command -v getenforce &>/dev/null && [ "$(getenforce)" = "Enforcing" ]; then
    log_info "SELinux is enabled, setting context for web files..."
    sudo setsebool -P httpd_can_network_connect 1 2>/dev/null || true
    sudo setsebool -P httpd_can_network_relay 1 2>/dev/null || true
    # nginx가 /var/www/hobot에 접근할 수 있도록 설정
    sudo chcon -R -t httpd_sys_content_t /var/www/hobot 2>/dev/null || true
  fi
  
  # 설정 테스트 (가이드 3단계 B)
  log_info "Testing nginx configuration..."
  sudo nginx -t || log_error "Nginx configuration test failed"
  
  # Nginx 재시작 (가이드 3단계 C)
  log_info "Restarting nginx..."
  sudo systemctl enable nginx
  sudo systemctl restart nginx
  sleep 3
  
  sudo systemctl is-active --quiet nginx || log_error "Nginx failed to start"
  log_success "Nginx configured and running"
}

# 프론트엔드 배포
deploy_frontend() {
  if [ ! -d "${DEPLOY_PATH}/hobot-ui" ]; then
    log_warn "Frontend directory not found, skipping..."
    return
  fi
  
  if ! command -v node &> /dev/null; then
    log_warn "Node.js not found, skipping frontend deployment"
    return
  fi
  
  build_frontend
  setup_nginx
}

# 메인 실행
main() {
  log_info "Starting deployment..."
  log_info "Deploy path: ${DEPLOY_PATH}"
  
  update_repository
  deploy_backend
  deploy_frontend
  
  log_success "Deployment completed successfully!"
}

main "$@"

