# Hobot UI - React Frontend

Hobot 서비스의 React 기반 프론트엔드 애플리케이션입니다.

## 기능

- 로그인 페이지
- Hobot 상태 모니터링 (Health Check API 연동)
- 현재 포지션 표시 (CurrentStrategy.txt 파일 연동)
- Pause/Start 기능 (CurrentStrategy.txt 파일 수정)

## 설치 및 실행

### 🚀 통합 실행 (권장)

#### 전체 스택 한번에 실행
```bash
cd hobot-service
./start_all.sh
```

#### 간단한 실행
```bash
cd hobot-service
./start_simple.sh
```

### 🔧 개별 실행

#### 백엔드 (FastAPI) 실행

##### 프로덕션 환경 (Gunicorn)
```bash
cd hobot-service/hobot
./start_server.sh
```

##### 개발 환경 (Uvicorn)
```bash
cd hobot-service/hobot
./start_dev.sh
```

또는 수동 실행:
```bash
cd hobot-service/hobot
pip install -r requirements.txt
gunicorn -c gunicorn.conf.py asgi:asgi_app  # 프로덕션
# 또는
uvicorn main:app --host 0.0.0.0 --port 8991 --reload  # 개발
```

백엔드는 `http://localhost:8991`에서 실행됩니다.

#### 프론트엔드 (React) 실행

```bash
cd hobot-service/hobot-ui
npm install
npm start
```

프론트엔드는 `http://localhost:3000`에서 실행됩니다.

## 로그인 정보

- 사용자명: `admin`
- 비밀번호: `admin`

## API 엔드포인트

모든 API 엔드포인트는 `/api` 경로를 기본으로 사용합니다.

- `GET /api/health` - Hobot 헬스체크
- `GET /api/news` - 뉴스 요약
- `GET /api/upbit/trading` - Upbit 트레이딩
- `GET /api/kis/healthcheck` - KIS 헬스체크
- `GET /api/upbit/test2` - Upbit 테스트
- `GET /api/current-strategy` - 현재 전략 상태 조회
- `POST /api/current-strategy` - 현재 전략 상태 변경

## 프로젝트 구조

```
src/
├── components/
│   ├── LoginPage.js      # 로그인 페이지
│   ├── Dashboard.js      # 메인 대시보드
│   ├── HobotStatus.js    # Hobot 상태 컴포넌트
│   ├── CurrentPosition.js # 현재 포지션 컴포넌트
│   └── Tools.js          # 도구 버튼 컴포넌트
├── App.js               # 메인 앱 컴포넌트
├── index.js             # 앱 진입점
└── index.css            # 전역 스타일
```
