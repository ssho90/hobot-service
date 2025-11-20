# 환경 변수 설정 가이드

## 📋 개요

이 프로젝트는 환경 변수를 다음과 같이 관리합니다:
- **로컬 개발**: `.env` 파일 사용
- **EC2 서버**: GitHub Actions의 secrets/variables 사용

## 🏠 로컬 개발 환경 설정

### 1. .env 파일 생성

프로젝트 루트의 `hobot/` 디렉토리에 `.env` 파일을 생성하세요:

```bash
cd hobot
cp .env.example .env
```

### 2. .env 파일 편집

`.env` 파일을 열어 필요한 값들을 설정하세요:

```bash
# MySQL Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password_here
DB_NAME=hobot
DB_CHARSET=utf8mb4

# JWT Secret Key
JWT_SECRET_KEY=your_jwt_secret_key_here

# API Keys
OPENAI_API_KEY=your_openai_api_key
GEMINI_API_KEY=your_gemini_api_key
TAVILY_API_KEY=your_tavily_api_key
FRED_API_KEY=your_fred_api_key

# Trading API Keys
ENV_UP_ACCESS_KEY=your_upbit_access_key
ENV_UP_SECRET_KEY=your_upbit_secret_key
ENV_HT_API_KEY=your_ht_api_key
ENV_HT_SECRET_KEY=your_ht_secret_key
ENV_HT_ACCOUNT=your_ht_account
ENV_HT_ID=your_ht_id

# Slack Token
ENV_SL_TOKEN=your_slack_token
```

### 3. .env 파일 보안

⚠️ **중요**: `.env` 파일은 Git에 커밋하지 마세요. 이미 `.gitignore`에 포함되어 있습니다.

## ☁️ EC2 서버 환경 설정 (GitHub Actions)

EC2 서버에서는 GitHub Actions의 secrets와 variables를 사용합니다.

### 1. GitHub Repository 설정

1. GitHub 저장소로 이동
2. **Settings** → **Secrets and variables** → **Actions** 클릭

### 2. Variables 설정 (공개 가능한 값)

**Variables** 탭에서 다음 변수들을 추가하세요:

| 변수명 | 값 | 설명 |
|--------|-----|------|
| `DB_HOST` | `localhost` 또는 MySQL 호스트 | MySQL 서버 호스트 |
| `DB_PORT` | `3306` | MySQL 포트 (기본값: 3306) |
| `DB_NAME` | `hobot` | 데이터베이스 이름 (기본값: hobot) |
| `DB_CHARSET` | `utf8mb4` | 문자셋 (기본값: utf8mb4) |
| `EC2_HOST` | `your-ec2-ip-or-domain` | EC2 인스턴스 호스트 |
| `EC2_USER` | `ec2-user` | EC2 사용자명 |
| `DOMAIN_NAME` | `your-domain.com` | 도메인 이름 (선택사항) |

### 3. Secrets 설정 (민감한 정보)

**Secrets** 탭에서 다음 시크릿들을 추가하세요:

| 시크릿명 | 설명 |
|---------|------|
| `DB_USER` | MySQL 사용자명 |
| `DB_PASSWORD` | MySQL 비밀번호 |
| `JWT_SECRET_KEY` | JWT 토큰 서명용 시크릿 키 |
| `ENV_OPENAI_API_KEY` | OpenAI API 키 |
| `ENV_GEMINI_API_KEY` | Gemini API 키 |
| `ENV_TAVILY_API_KEY` | Tavily API 키 |
| `FRED_API_KEY` | FRED API 키 (거시경제 데이터 수집용) |
| `ENV_UP_ACCESS_KEY` | Upbit Access Key |
| `ENV_UP_SECRET_KEY` | Upbit Secret Key |
| `ENV_HT_API_KEY` | HT API Key |
| `ENV_HT_SECRET_KEY` | HT Secret Key |
| `ENV_HT_ACCOUNT` | HT Account |
| `ENV_HT_ID` | HT ID |
| `ENV_SL_TOKEN` | Slack Token |
| `EC2_SSH_PRIVATE_KEY` | EC2 SSH 개인 키 |
| `GH_TOKEN` | GitHub Personal Access Token |

### 4. GitHub Actions Workflow 확인

`.github/workflows/deploy.yml` 파일에서 환경 변수가 올바르게 설정되어 있는지 확인하세요.

## 🔄 환경 변수 로드 순서

애플리케이션은 다음 순서로 환경 변수를 로드합니다:

1. **시스템 환경 변수** (최우선)
2. **.env 파일** (로컬 개발 시)
3. **기본값** (코드에 정의된 기본값)

## 📝 환경 변수 목록

### 필수 환경 변수

#### MySQL 데이터베이스
- `DB_HOST`: MySQL 호스트 (기본값: localhost)
- `DB_PORT`: MySQL 포트 (기본값: 3306)
- `DB_USER`: MySQL 사용자명
- `DB_PASSWORD`: MySQL 비밀번호
- `DB_NAME`: 데이터베이스 이름 (기본값: hobot)
- `DB_CHARSET`: 문자셋 (기본값: utf8mb4)

#### 인증
- `JWT_SECRET_KEY`: JWT 토큰 서명용 시크릿 키

### 선택적 환경 변수

#### API Keys
- `OPENAI_API_KEY`: OpenAI API 키
- `GEMINI_API_KEY`: Google Gemini API 키
- `TAVILY_API_KEY`: Tavily API 키
- `FRED_API_KEY`: FRED API 키 (거시경제 데이터 수집용)

#### 거래소 API
- `ENV_UP_ACCESS_KEY`: Upbit Access Key
- `ENV_UP_SECRET_KEY`: Upbit Secret Key
- `ENV_HT_API_KEY`: HT API Key
- `ENV_HT_SECRET_KEY`: HT Secret Key
- `ENV_HT_ACCOUNT`: HT Account
- `ENV_HT_ID`: HT ID

#### 기타
- `ENV_SL_TOKEN`: Slack Bot Token
- `DOMAIN_NAME`: 도메인 이름 (nginx 설정용)

## 🔍 환경 변수 확인

### 로컬에서 확인

```bash
# .env 파일 확인
cat hobot/.env

# Python에서 확인
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('DB_HOST'))"
```

### EC2에서 확인

```bash
# .env 파일 확인 (배포 후 자동 생성됨)
cat /home/ec2-user/hobot-service/hobot/.env

# 환경 변수 확인
env | grep DB_
```

## ⚠️ 주의사항

1. **.env 파일은 Git에 커밋하지 마세요**
   - 이미 `.gitignore`에 포함되어 있습니다
   - `.env.example` 파일만 커밋하세요

2. **GitHub Secrets는 민감한 정보만 저장**
   - 비밀번호, API 키 등은 Secrets에 저장
   - 공개 가능한 값은 Variables에 저장

3. **환경 변수 이름 일관성**
   - 로컬과 서버에서 동일한 변수명 사용
   - 일부 변수는 `ENV_` 접두사 사용 (기존 코드와의 호환성)

4. **보안**
   - JWT_SECRET_KEY는 강력한 랜덤 문자열 사용
   - 데이터베이스 비밀번호는 복잡한 비밀번호 사용

## 🆘 문제 해결

### 환경 변수가 로드되지 않는 경우

1. `.env` 파일 위치 확인: `hobot/.env` (프로젝트 루트가 아님)
2. `load_dotenv()` 호출 확인: 코드에서 `load_dotenv()`가 호출되는지 확인
3. 파일 권한 확인: `.env` 파일 읽기 권한 확인

### GitHub Actions 배포 실패

1. Secrets/Variables 설정 확인
2. 변수명 오타 확인
3. GitHub Actions 로그 확인

## 📚 관련 문서

- [MySQL 설정 가이드](./MYSQL_SETUP.md)
- [배포 가이드](../.github/DEPLOY.md)

