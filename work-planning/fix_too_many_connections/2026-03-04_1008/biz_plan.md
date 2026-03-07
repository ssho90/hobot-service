# 작업 계획: Too Many Connections 수정

## 문제 요약
MySQL `(1040, 'Too many connections')` 에러 발생

## 근본 원인
1. `ensure_database_initialized()` 초기화 실패 시 `_db_initialized = True`에 도달 못함
   → 모든 API 요청마다 `init_database()` 재시도 → 커넥션 낭비
2. `_init_lock` 없음 → 멀티스레드 동시 초기화 시도 가능

## 수정 계획
### [1] `threading.Lock` 추가 (동시 초기화 레이스 컨디션 방지)
### [2] 초기화 실패 시 Cool-down 로직 추가 (60초 내 재시도 차단)
### [3] 초기화 성공 여부와 무관하게 `_db_initialized = True` 설정 제거 → 대신 retry 관리

## 대상 파일
- `hobot/service/database/db.py` (880~908번째 줄)
