# AWS EC2 배포 가이드

GitHub Actions를 사용하여 AWS EC2에 자동 배포하는 방법입니다.

## 사전 준비

### 1. EC2 인스턴스 설정

- EC2 인스턴스가 실행 중이어야 합니다 (IP: 3.34.13.230)
- SSH 접속이 가능해야 합니다
- Python 3, pip가 설치되어 있어야 합니다
- (선택) Node.js가 설치되어 있으면 프론트엔드도 배포됩니다

### 2. GitHub Secrets 및 Variables 설정

GitHub 저장소의 Settings > Secrets and variables > Actions에서 설정하세요:

#### 필수 Secrets (민감한 정보)

- `EC2_SSH_PRIVATE_KEY`: EC2 접속용 SSH 개인키 (전체 내용)
- `GH_TOKEN`: GitHub Personal Access Token (private repository 접근용)

#### 필수 Variables (일반 설정값)

- `EC2_HOST`: EC2 Public IP (예: `3.34.13.230`)
- `EC2_USER`: EC2 사용자명 (일반적으로 `ubuntu` 또는 `ec2-user`)

#### 선택 Variables (일반 설정값)

- `EC2_DEPLOYMENT_PATH`: 배포 경로 (기본값: `/home/ec2-user/hobot-service`)

### 3. SSH 키 생성 및 설정

#### EC2에서 SSH 키 생성 (처음 한 번만)

```bash
# EC2에 접속
ssh ubuntu@3.34.13.230

# 배포용 SSH 키 생성
ssh-keygen -t rsa -b 4096 -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
```

#### GitHub Secrets에 개인키 추가

```bash
# EC2에서 개인키 내용 복사
cat ~/.ssh/github_deploy
```

복사한 내용을 GitHub Secrets의 `EC2_SSH_PRIVATE_KEY`에 추가하세요.

> **참고**: Secrets는 암호화되어 저장되며, Variables는 일반 텍스트로 저장됩니다. 민감한 정보는 반드시 Secrets에 저장하세요.

#### GitHub Personal Access Token 생성 및 설정

Private repository를 사용하는 경우 GitHub Personal Access Token이 필요합니다:

1. GitHub에서 Settings > Developer settings > Personal access tokens > Tokens (classic) 이동
2. "Generate new token (classic)" 클릭
3. 다음 권한 선택:
   - `repo` (전체 권한) - private repository 접근용
4. 토큰 생성 후 복사
5. GitHub Secrets의 `GH_TOKEN`에 추가

### 4. Variables 설정

일반 설정값들은 Variables에 추가하세요:

1. GitHub 저장소의 Settings > Secrets and variables > Actions 이동
2. "Variables" 탭 클릭
3. "New repository variable" 버튼 클릭
4. 다음 변수들을 추가:
   - `EC2_HOST`: EC2 Public IP 주소
   - `EC2_USER`: EC2 사용자명
   - `EC2_DEPLOYMENT_PATH`: (선택) 배포 경로

## 배포 방법

### 자동 배포

`main` 브랜치에 push하면 자동으로 배포됩니다:

```bash
git push origin main
```

### 수동 배포

GitHub Actions 탭에서 "Deploy to AWS EC2" workflow를 선택하고 "Run workflow"를 클릭하세요.

## 배포 프로세스

1. **코드 체크아웃**: GitHub에서 최신 코드를 가져옵니다
2. **SSH 연결**: EC2에 SSH로 접속합니다
3. **코드 업데이트**: Git pull 또는 clone으로 코드를 업데이트합니다
4. **의존성 설치**: Python 패키지를 설치합니다
5. **서비스 재시작**: 기존 서비스를 종료하고 새로 시작합니다
6. **헬스 체크**: 서버가 정상적으로 응답하는지 확인합니다

## 서비스 관리

### Systemd 서비스 사용 (권장)

배포 시 `.github/deploy/hobot.service` 파일이 있으면 systemd 서비스로 관리됩니다:

```bash
# 서비스 상태 확인
sudo systemctl status hobot

# 서비스 재시작
sudo systemctl restart hobot

# 로그 확인
sudo journalctl -u hobot -f
```

### 수동 관리

Systemd 서비스가 없으면 프로세스로 직접 실행됩니다:

```bash
# 프로세스 확인
lsof -ti :8991

# 프로세스 종료
kill -9 $(lsof -ti :8991)

# 수동 시작
cd /home/ubuntu/hobot-service/hobot
source venv/bin/activate
python3 -m gunicorn -c gunicorn.conf.py asgi:asgi_app
```

## 로그 확인

```bash
# 애플리케이션 로그
tail -f /home/ubuntu/hobot-service/hobot/log.txt

# Gunicorn 액세스 로그
tail -f /home/ubuntu/hobot-service/hobot/logs/access.log

# Gunicorn 에러 로그
tail -f /home/ubuntu/hobot-service/hobot/logs/error.log

# Systemd 서비스 로그 (systemd 사용 시)
sudo journalctl -u hobot -f
```

## 문제 해결

### 배포 실패 시

1. GitHub Actions 로그 확인
2. EC2에 직접 접속하여 수동으로 확인:
   ```bash
   ssh ubuntu@3.34.13.230
   cd /home/ubuntu/hobot-service
   ```

### 서비스가 시작되지 않는 경우

1. 포트 충돌 확인:
   ```bash
   lsof -ti :8991
   ```

2. 의존성 확인:
   ```bash
   cd /home/ubuntu/hobot-service/hobot
   source venv/bin/activate
   pip list
   ```

3. 환경 변수 확인:
   ```bash
   # .env 파일이 있는지 확인
   ls -la /home/ubuntu/hobot-service/hobot/.env
   ```

### SSH 연결 실패 시

1. EC2 Security Group에서 SSH 포트(22)가 열려있는지 확인
2. SSH 키가 올바른지 확인
3. EC2 인스턴스가 실행 중인지 확인

## 보안 주의사항

- `.env` 파일은 Git에 커밋하지 마세요 (`.gitignore`에 포함됨)
- `access_token.json`은 `.gitignore`에 포함되어 있습니다
- EC2 Security Group에서 필요한 포트만 열어두세요
- 정기적으로 SSH 키를 교체하세요
- **`.github` 폴더의 파일들은 형상관리되어야 합니다** (workflow, 배포 설정, 문서 등)

