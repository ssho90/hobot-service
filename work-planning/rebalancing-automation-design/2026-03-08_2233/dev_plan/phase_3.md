# Phase 3. 멀티데이 Run 상태머신

## 목표
- 5회 실행일 기준의 분할집행 상태머신을 구현한다.
- 사용자별 run 생성, pause/resume, supersede, completion을 관리한다.

## 대상 파일
- `hobot/service/database/db.py`
- `hobot/main.py`
- `hobot/service/macro_trading/rebalancing/test_session_service.py`
- `hobot/service/macro_trading/rebalancing/paper_broker_adapter.py`
- `hobot/service/macro_trading/rebalancing/rebalancing_engine.py`
- `hobot/service/macro_trading/rebalancing/order_executor.py`
- 신규 `hobot/service/macro_trading/rebalancing/run_repository.py`

## 구현 포인트
- `rebalancing_runs`
- `rebalancing_run_snapshots`
- `executed_days`
- `remaining_execution_days`
- `today_slice`
- `GLOBAL preemption`
- `GLOBAL absorb / LOCAL defer`

## 체크리스트

### To-Do
- [ ] completion tolerance 규칙 구현
- [ ] partial fill 상세 체결 반영 로직 구현
  - 주문 응답 기반 잔량 계산
  - 미체결/부분체결 주문 정산
- [ ] run별 UI/리포트 조회 화면 정리

### In Progress
- [ ] `OrderExecutor` 일자별 결과 저장 방식 설계
  - 실제 체결 이벤트 단위로 snapshot 세분화 필요

### Done
- [x] run 상태 enum 확정
  - `ACTIVE`
  - `PAUSED`
  - `COMPLETED`
  - `CANCELLED`
  - `SUPERSEDED`
  - `FAILED`
- [x] 당일 slice 계산 함수 구현
- [x] `execute_rebalancing_for_user()` 기반 멀티데이 run foundation 구현
- [x] `rebalancing_runs` / `rebalancing_run_snapshots` 테이블 정의
- [x] pause/resume 상태 전이 helper 구현
- [x] supersede 시 parent-child 관계 저장 구현
- [x] 테스트용 run 조회 API 추가
- [x] 충돌 정책 정의
  - MP 우선
  - Sub-MP는 defer/absorb 가능

## 완료 기준
- 사용자별 active run이 생성된다.
- 매 실행일마다 `남은 수량 / 남은 실행일 수`로 당일 주문이 계산된다.
- partial fill과 잔량 이월이 동작한다.
- 충돌 케이스에서 pause/supersede/재개가 재현된다.

## 리스크
- 상태 전이를 DB에 느슨하게 저장하면 재시도나 복구 시 중복 주문 위험이 커진다.
- run과 실제 주문 결과의 동기화가 깨지면 잔량 계산이 틀어질 수 있다.
