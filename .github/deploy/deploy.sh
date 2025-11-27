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
export GEMINI_API_KEY="${GEMINI_API_KEY}"
export TAVILY_API_KEY="${TAVILY_API_KEY}"

# 유틸리티 함수
log_info() { echo "ℹ️  $*"; }
log_success() { echo "✅ $*"; }
log_error() { echo "❌ $*"; exit 1; }
log_warn() { echo "⚠️  $*"; }

# Git 업데이트
update_repository() {
  log_info "Updating repository..."
  cd "${DEPLOY_PATH}" || {
    log_warn "Deploy directory not found. Creating..."
    mkdir -p "${DEPLOY_PATH}"
    cd "${DEPLOY_PATH}"
  }
  
  if [ -d ".git" ]; then
    git pull "https://${GH_TOKEN}@github.com/${GITHUB_REPO}.git" main || true
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
  ${PYTHON_CMD} -m pip install --upgrade pip || true
  ${PYTHON_CMD} -m pip install -r requirements.txt
  
  # gunicorn 확인
  if ! ${PYTHON_CMD} -m gunicorn --version &>/dev/null; then
    ${PYTHON_CMD} -m pip install gunicorn[gevent] || ${PYTHON_CMD} -m pip install gunicorn
  fi
  
  log_success "Python environment ready"
  echo "${PYTHON_CMD}"
}

# .env 파일 생성
create_env_file() {
  log_info "Creating .env file..."
  cat > "${DEPLOY_PATH}/hobot/.env" << EOF
# Environment variables for Hobot service
# Generated automatically during deployment

SL_TOKEN=${SL_TOKEN}
UP_ACCESS_KEY=${UP_ACCESS_KEY}
UP_SECRET_KEY=${UP_SECRET_KEY}
HT_API_KEY=${HT_API_KEY}
HT_SECRET_KEY=${HT_SECRET_KEY}
HT_ACCOUNT=${HT_ACCOUNT}
HT_ID=${HT_ID}
OPENAI_API_KEY=${OPENAI_API_KEY}
GEMINI_API_KEY=${GEMINI_API_KEY}
TAVILY_API_KEY=${TAVILY_API_KEY}
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
  
  # 전략 초기화
  log_info "Initializing strategies..."
  ${PYTHON_CMD} service/utils/init_strategy_pause.py
  
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
    sudo systemctl restart hobot.service
    sleep 3
    
    if sudo systemctl is-active --quiet hobot.service; then
      log_success "Backend service is running"
    else
      log_error "Backend service failed to start"
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

# 프론트엔드 빌드
build_frontend() {
  log_info "Building frontend..."
  cd "${DEPLOY_PATH}/hobot-ui"
  
  npm install
  export NODE_OPTIONS="--max-old-space-size=1536"
  
  # 백그라운드 빌드
  rm -f ../hobot/logs/frontend-build-*.flag
  nohup bash -c "export NODE_OPTIONS='--max-old-space-size=1536' && npm run build && touch ../hobot/logs/frontend-build-complete.flag || touch ../hobot/logs/frontend-build-failed.flag" > ../hobot/logs/frontend-build.log 2>&1 &
  
  # 빌드 완료 대기
  BUILD_TIMEOUT=600
  ELAPSED=0
  while [ ${ELAPSED} -lt ${BUILD_TIMEOUT} ]; do
    [ -f "../hobot/logs/frontend-build-complete.flag" ] && break
    [ -f "../hobot/logs/frontend-build-failed.flag" ] && log_error "Frontend build failed"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
    [ $((ELAPSED % 60)) -eq 0 ] && log_info "Build in progress... (${ELAPSED}s)"
  done
  
  [ ! -d "build" ] && log_error "Frontend build directory not found"
  
  # 권한 설정
  sudo chown -R "$(whoami):$(whoami)" build
  sudo chmod -R 755 build
  sudo chmod -R o+rX build 2>/dev/null || true
  id nginx &>/dev/null && sudo usermod -a -G "$(whoami)" nginx 2>/dev/null || true
  
  log_success "Frontend build completed"
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

# certbot 인증서 발급/갱신
setup_ssl_certificates() {
  log_info "Setting up SSL certificates for Langfuse proxy..."
  
  # certbot 설치 확인
  if ! command -v certbot &> /dev/null; then
    log_info "Installing certbot..."
    sudo yum install -y certbot python3-certbot-nginx 2>/dev/null || \
      (sudo apt-get update && sudo apt-get install -y certbot python3-certbot-nginx)
  fi
  
  # certbot 웹루트 디렉토리 생성
  sudo mkdir -p /var/www/certbot
  sudo chown -R nginx:nginx /var/www/certbot 2>/dev/null || true
  
  # 기존 certbot 이메일 확인 (있는 경우 사용)
  CERTBOT_EMAIL=$(sudo cat /etc/letsencrypt/renewal/*.conf 2>/dev/null | grep -oP 'email = \K[^\s]+' | head -1 || echo "admin@stockoverflow.com")
  
  # Langfuse 인증서 발급/갱신 (certonly 사용하여 nginx 설정은 수동 관리)
  if [ ! -f "/etc/letsencrypt/live/langfuse.stockoverflow.com/fullchain.pem" ]; then
    log_info "Requesting SSL certificate for langfuse.stockoverflow.com..."
    # certbot certonly를 사용하여 인증서만 발급 (nginx 설정은 우리가 관리)
    sudo certbot certonly --webroot \
      -w /var/www/certbot \
      -d langfuse.stockoverflow.com \
      --non-interactive --agree-tos \
      --email "${CERTBOT_EMAIL}" \
      --preferred-challenges http || log_warn "Failed to get certificate for langfuse.stockoverflow.com (check DNS and try again)"
  else
    log_info "Certificate for langfuse.stockoverflow.com already exists, renewing if needed..."
    sudo certbot renew --cert-name langfuse.stockoverflow.com --quiet --no-random-sleep-on-renew || true
  fi
  
  # Langfuse US 인증서 발급/갱신
  if [ ! -f "/etc/letsencrypt/live/langfuse-us.stockoverflow.com/fullchain.pem" ]; then
    log_info "Requesting SSL certificate for langfuse-us.stockoverflow.com..."
    sudo certbot certonly --webroot \
      -w /var/www/certbot \
      -d langfuse-us.stockoverflow.com \
      --non-interactive --agree-tos \
      --email "${CERTBOT_EMAIL}" \
      --preferred-challenges http || log_warn "Failed to get certificate for langfuse-us.stockoverflow.com (check DNS and try again)"
  else
    log_info "Certificate for langfuse-us.stockoverflow.com already exists, renewing if needed..."
    sudo certbot renew --cert-name langfuse-us.stockoverflow.com --quiet --no-random-sleep-on-renew || true
  fi
  
  log_success "SSL certificates configured"
}

# nginx 설정
setup_nginx() {
  log_info "Setting up nginx..."
  
  # nginx 설치
  if ! command -v nginx &> /dev/null; then
    log_info "Installing nginx..."
    sudo yum install -y nginx 2>/dev/null || sudo apt-get update && sudo apt-get install -y nginx
  fi
  
  # 기본 설정 비활성화
  for conf_file in /etc/nginx/conf.d/*.conf; do
    [ -f "$conf_file" ] && sudo mv "$conf_file" "${conf_file}.disabled" 2>/dev/null || true
  done
  
  # 우리 설정 복사
  sudo cp "${DEPLOY_PATH}/.github/deploy/nginx.conf" /etc/nginx/conf.d/00-hobot.conf
  sudo sed -i "s|/home/ec2-user/hobot-service|${DEPLOY_PATH}|g" /etc/nginx/conf.d/00-hobot.conf
  sudo chmod 644 /etc/nginx/conf.d/00-hobot.conf
  
  # nginx.conf의 기본 server 블록 비활성화
  if [ -f "/etc/nginx/nginx.conf" ]; then
    [ ! -f "/etc/nginx/nginx.conf.backup" ] && sudo cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.backup
    sudo grep -q "^\s*server\s*{" /etc/nginx/nginx.conf && disable_default_nginx_config || true
  fi
  
  # SSL 인증서가 있는지 확인하고 nginx 설정 조정
  LANGFUSE_CERT="/etc/letsencrypt/live/langfuse.stockoverflow.com/fullchain.pem"
  LANGFUSE_US_CERT="/etc/letsencrypt/live/langfuse-us.stockoverflow.com/fullchain.pem"
  
  # 인증서가 없으면 SSL 블록을 제거하는 Python 스크립트 실행
  if [ ! -f "$LANGFUSE_CERT" ] || [ ! -f "$LANGFUSE_US_CERT" ]; then
    log_info "SSL certificates not found, removing HTTPS blocks temporarily..."
    cat > /tmp/remove_ssl_blocks.py << 'PYEOF'
import re
import sys

try:
    with open('/etc/nginx/conf.d/00-hobot.conf', 'r') as f:
        lines = f.readlines()
    
    result = []
    in_ssl_server = False
    ssl_server_depth = 0
    skip_ssl_block = False
    
    for line in lines:
        # SSL server 블록 시작 감지 (listen 443)
        if re.search(r'listen\s+443\s+ssl', line):
            in_ssl_server = True
            ssl_server_depth = 1
            skip_ssl_block = True
            continue
        
        if in_ssl_server:
            ssl_server_depth += line.count('{') - line.count('}')
            if ssl_server_depth == 0:
                in_ssl_server = False
                skip_ssl_block = False
            continue
        
        result.append(line)
    
    with open('/etc/nginx/conf.d/00-hobot.conf', 'w') as f:
        f.writelines(result)
    print("✅ Removed SSL blocks")
    sys.exit(0)
        
except Exception as e:
    print(f"⚠️  Error: {e}")
    sys.exit(1)
PYEOF
    sudo python3 /tmp/remove_ssl_blocks.py
    rm -f /tmp/remove_ssl_blocks.py
  fi
  
  # nginx 설정 테스트
  if ! sudo nginx -t 2>&1 | grep -q "test is successful"; then
    log_error "Nginx configuration test failed"
    sudo nginx -t
  fi
  
  # nginx 시작
  sudo systemctl enable nginx
  sudo systemctl restart nginx
  sleep 3
  
  sudo systemctl is-active --quiet nginx || log_error "Nginx failed to start"
  
  # SSL 인증서 설정 (nginx가 실행 중이어야 함)
  setup_ssl_certificates
  
  # 인증서가 발급되었으면 SSL 블록 복원 및 nginx 재시작
  if [ -f "$LANGFUSE_CERT" ] && [ -f "$LANGFUSE_US_CERT" ]; then
    log_info "SSL certificates found, restoring HTTPS blocks..."
    # 설정 파일을 다시 복사하여 SSL 블록 포함
    sudo cp "${DEPLOY_PATH}/.github/deploy/nginx.conf" /etc/nginx/conf.d/00-hobot.conf
    sudo sed -i "s|/home/ec2-user/hobot-service|${DEPLOY_PATH}|g" /etc/nginx/conf.d/00-hobot.conf
    
    if sudo nginx -t; then
      sudo systemctl reload nginx
      log_success "HTTPS enabled for Langfuse proxy"
    else
      log_warn "Nginx configuration test failed after adding SSL blocks"
      sudo nginx -t
    fi
  else
    log_warn "SSL certificates not available yet. HTTP-only mode active."
    log_info "After DNS propagation, run deployment again to enable HTTPS."
  fi
  
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

