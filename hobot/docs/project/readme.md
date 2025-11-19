# Hobot Backend - FastAPI

Hobot 서비스의 FastAPI 기반 백엔드 애플리케이션입니다.

## 기술 스택

- **FastAPI**: 현대적이고 빠른 웹 프레임워크
- **Uvicorn**: ASGI 서버 (개발용)
- **Gunicorn**: WSGI/ASGI 서버 (프로덕션용)
- **Pydantic**: 데이터 검증 및 직렬화

## 설치 및 실행

### 의존성 설치
```bash
pip install -r requirements.txt
```

### 개발 환경 실행
```bash
./start_dev.sh
# 또는
uvicorn main:app --host 0.0.0.0 --port 8991 --reload
```

### 프로덕션 환경 실행
```bash
./start_server.sh
# 또는
gunicorn -c gunicorn.conf.py asgi:asgi_app
```

## API 엔드포인트

### 기본 엔드포인트
- `GET /` - 기본 페이지

### API 엔드포인트 (모두 `/api` 경로 사용)
- `GET /api/health` - Hobot 헬스체크
- `GET /api/news` - 뉴스 요약
- `GET /api/upbit/trading` - Upbit 트레이딩
- `GET /api/kis/healthcheck` - KIS 헬스체크
- `GET /api/upbit/test2` - Upbit 테스트
- `GET /api/current-strategy` - 현재 전략 상태 조회
- `POST /api/current-strategy` - 현재 전략 상태 변경

### API 문서
- `GET /docs` - Swagger UI (자동 생성된 API 문서)
- `GET /redoc` - ReDoc (대체 API 문서)

## 설정

### Gunicorn 설정 (gunicorn.conf.py)
- **Workers**: 4개
- **Worker Class**: UvicornWorker
- **Port**: 8991
- **Timeout**: 30초
- **Keepalive**: 2초

### 환경 변수
`.env` 파일에서 환경 변수를 설정할 수 있습니다.

## 로깅

로그는 `log.txt` 파일에 기록됩니다.

## CORS

프론트엔드와의 통신을 위해 CORS가 활성화되어 있습니다.
프로덕션 환경에서는 특정 도메인으로 제한하는 것을 권장합니다.