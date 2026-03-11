# KIS SSL 번들 충돌 수정 계획서

## 목적

로컬 개발 환경에서 `REQUESTS_CA_BUNDLE` 또는 `SSL_CERT_FILE`이 잡혀 있어도 KIS OpenAPI HTTPS 호출이 깨지지 않도록 `kis_api.py`를 국소적으로 보완한다.

## 범위

- `hobot/service/macro_trading/kis/kis_api.py`
- KIS API 요청 경로의 SSL 검증 번들 처리
- 로컬/EC2 환경 차이를 고려한 호환성 확보

## 완료 조건

1. KIS 요청이 전역 `requests` 환경변수에 직접 종속되지 않는다.
2. 기본 공인 루트 번들은 유지한다.
3. 추가 CA가 있는 환경에서는 기본 루트 + 추가 CA를 함께 신뢰한다.
4. EC2처럼 추가 CA가 없는 환경의 기존 동작은 유지한다.
