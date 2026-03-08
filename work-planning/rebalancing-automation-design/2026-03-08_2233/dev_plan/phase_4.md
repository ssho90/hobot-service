# Phase 4. 스케줄러 연결 및 사용자 Fan-out

## 목표
- 전략 프로필별 signal confirmation 스케줄과 사용자별 rebalancing execution fan-out을 연결한다.
- 동시 실행 방지와 사용자 간 격리를 확보한다.

## 대상 파일
- `hobot/service/macro_trading/scheduler.py`
- `hobot/service/macro_trading/rebalancing/rebalancing_engine.py`
- 신규 `hobot/service/macro_trading/rebalancing/auto_rebalance_service.py`

## 구현 포인트
- `08:35` signal confirmation
- `09:40` user fan-out execution
- user isolation
- idempotency lock
- job tags / job status

## 체크리스트

### To-Do
- [ ] 전략 프로필별 signal confirmation job 추가
- [ ] 자동 실행 대상 사용자 조회 함수 구현
- [ ] `auto_rebalance_enabled` 필터 구현
- [ ] 사용자별 threshold override 적용
- [ ] fan-out execution 루프 구현
- [ ] 사용자 실패가 전체 job 실패로 전파되지 않게 분리
- [ ] 중복 실행 방지 lock 구현

### In Progress
- [ ] scheduler job naming / tagging 규칙 설계
- [ ] retry 정책 설계

### Done
- [ ] 사용자별 리밸런싱 관리 원칙 문서화

## 완료 기준
- 스케줄러가 자동으로 signal confirmation과 user fan-out execution을 수행한다.
- 한 사용자의 주문 실패가 다른 사용자의 실행을 막지 않는다.
- 동일 날짜/동일 phase 중복 실행 시 lock이 동작한다.

## 리스크
- fan-out 규모가 커지면 API rate limit 또는 DB connection 압박이 생길 수 있다.
- job lock 범위를 잘못 잡으면 중복 주문 또는 전체 정지가 발생할 수 있다.
