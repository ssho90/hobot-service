# 04_execution_attempt

## 실제 적재 실행 시도
- KR/US collector의 `collect_top50_daily_ohlcv(...)` 직접 호출 시도

## 결과
- 두 경로 모두 DB 연결 실패로 중단
- 에러:
  - `OperationalError (2003, "Can't connect to MySQL server on '127.0.0.1' ([Errno 1] Operation not permitted)")`

## 해석
- 샌드박스/실행 환경에서 MySQL 연결이 제한되어 있어 실제 INSERT까지 진행 불가
- 코드 구현/테스트는 완료되어, DB 접근 가능한 런타임에서는 즉시 실행 가능
