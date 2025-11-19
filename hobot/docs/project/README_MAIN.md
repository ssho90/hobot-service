# Hobot Trading System

Hobot 자동 트레이딩 시스템의 풀스택 애플리케이션입니다.

## 🏗️ 프로젝트 구조

```
hobot-service/
├── hobot/                 # Backend (FastAPI)
│   ├── main.py           # FastAPI 애플리케이션
│   ├── app.py            # 뉴스 요약 기능
│   ├── service/          # 비즈니스 로직
│   │   ├── upbit/        # Upbit API 연동
│   │   ├── kis/          # KIS API 연동
│   │   ├── slack_bot.py  # Slack 알림
│   │   └── CurrentStrategy.txt  # 현재 전략 상태
│   ├── requirements.txt  # Python 의존성
│   ├── start_dev.sh      # 개발 서버 실행
│   └── start_server.sh   # 프로덕션 서버 실행
├── hobot-ui/             # Frontend (React)
│   ├── src/
│   │   ├── components/   # React 컴포넌트
│   │   ├── App.js        # 메인 앱
│   │   └── index.js      # 진입점
│   ├── package.json      # Node.js 의존성
│   └── README.md         # 프론트엔드 문서
└── README.md            # 이 파일
```

## 🚀 빠른 시작

### 1. 전체 스택 한번에 실행

```bash
# 프로젝트 루트로 이동
cd hobot-service

# 백엔드와 프론트엔드 동시 실행
./start_all.sh
```

### 2. 개별 실행

#### 백엔드만 실행
```bash
cd hobot-service/hobot
./start_dev.sh    # 개발 모드
# 또는
./start_server.sh # 프로덕션 모드
```

#### 프론트엔드만 실행
```bash
cd hobot-service/hobot-ui
npm install
npm start
```

## 🌐 접속 주소

- **프론트엔드**: http://localhost:3000
- **백엔드 API**: http://localhost:8991
- **API 문서**: http://localhost:8991/docs

## 🚢 배포

AWS EC2에 자동 배포하는 방법은 [DEPLOYMENT.md](./DEPLOYMENT.md)를 참고하세요.

GitHub Actions를 통해 `main` 브랜치에 푸시하면 자동으로 EC2에 배포됩니다.

## 🔐 로그인 정보

- **사용자명**: `admin`
- **비밀번호**: `admin`

## 📋 주요 기능

### Frontend (React)
- 🔐 로그인 페이지
- 📊 Hobot 상태 모니터링 (30초마다 헬스체크)
- 📈 현재 포지션 표시 (1분마다 업데이트)
- ⏸️ Pause/Start 기능
- 🎨 모던한 UI/UX

### Backend (FastAPI)
- 🔍 Hobot 헬스체크 API
- 📰 뉴스 요약 기능
- 💰 Upbit/KIS 트레이딩 API
- 📝 전략 상태 관리
- 🔔 Slack 알림

## 🛠️ 기술 스택

### Backend
- **FastAPI**: 현대적이고 빠른 웹 프레임워크
- **Uvicorn**: ASGI 서버 (개발용)
- **Gunicorn**: WSGI/ASGI 서버 (프로덕션용)
- **Python 3.9+**: 프로그래밍 언어

### Frontend
- **React 18**: 사용자 인터페이스 라이브러리
- **React Router**: 클라이언트 사이드 라우팅
- **Axios**: HTTP 클라이언트
- **CSS3**: 스타일링

### External APIs
- **Upbit API**: 암호화폐 거래
- **KIS API**: 한국투자증권 API
- **Slack API**: 알림 시스템

## 📦 설치 요구사항

### 시스템 요구사항
- **Python 3.9+**
- **Node.js 16+**
- **npm 8+**

### Python 패키지
```bash
cd hobot-service/hobot
pip install -r requirements.txt
```

### Node.js 패키지
```bash
cd hobot-service/hobot-ui
npm install
```

## 🔧 개발 환경 설정

### 1. 환경 변수 설정
```bash
cd hobot-service/hobot
cp .env.example .env
# .env 파일을 편집하여 필요한 API 키 설정
```

### 2. 가상환경 설정 (선택사항)
```bash
cd hobot-service/hobot
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 또는
venv\Scripts\activate     # Windows
```

## 📝 API 엔드포인트

모든 API 엔드포인트는 `/api` 경로를 기본으로 사용합니다.

### 기본 엔드포인트
- `GET /` - 기본 페이지

### API 엔드포인트
- `GET /api/health` - Hobot 헬스체크
- `GET /api/news` - 뉴스 요약
- `GET /api/upbit/trading` - Upbit 트레이딩
- `GET /api/kis/healthcheck` - KIS 헬스체크
- `GET /api/upbit/test2` - Upbit 테스트
- `GET /api/current-strategy` - 현재 전략 상태 조회
- `POST /api/current-strategy` - 현재 전략 상태 변경

### API 문서
- `GET /docs` - Swagger UI
- `GET /redoc` - ReDoc

## 🐛 문제 해결

### 포트 충돌 에러
```bash
# 포트 사용 중인 프로세스 확인
lsof -i :8991  # 백엔드 포트
lsof -i :3000  # 프론트엔드 포트

# 프로세스 종료
kill -9 <PID>
```

### 의존성 설치 에러
```bash
# Python 의존성 재설치
cd hobot-service/hobot
pip install --upgrade pip
pip install -r requirements.txt

# Node.js 의존성 재설치
cd hobot-service/hobot-ui
rm -rf node_modules package-lock.json
npm install
```

### 서버 시작 실패
1. 포트가 사용 중인지 확인
2. 의존성이 모두 설치되었는지 확인
3. 환경 변수가 올바르게 설정되었는지 확인

## 📊 모니터링

### 로그 확인

#### 백엔드 로그 (Gunicorn)
```bash
cd hobot-service/hobot

# 로그 모니터링 스크립트 (대화형)
./log_monitor.sh

# 최근 로그 보기
./view_logs.sh

# 실시간 로그 모니터링
tail -f logs/access.log    # 접근 로그
tail -f logs/error.log     # 에러 로그
tail -f log.txt           # 애플리케이션 로그

# 모든 로그 동시 모니터링
tail -f logs/access.log logs/error.log log.txt
```

#### 프론트엔드 로그
```bash
# 프론트엔드 로그
tail -f hobot-service/hobot-ui/frontend.log
```

### 서버 상태 확인
```bash
# 백엔드 상태
curl http://localhost:8991/api/health

# 프론트엔드 상태
curl http://localhost:3000
```

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 📞 지원

문제가 발생하거나 질문이 있으시면 이슈를 생성해주세요.

---

**Happy Trading! 🚀**
