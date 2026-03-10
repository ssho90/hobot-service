# 05. Phase 3 Run State Machine Foundation

## 목적
- 사용자별 5일 분할집행 run 상태머신의 기초를 구현한다.
- `PAPER_TIME_TRAVEL` 테스트에서 day-by-day slice 주문과 run 상태를 확인할 수 있게 한다.

## 수행 내용
- `db.py`
  - `rebalancing_runs`
  - `rebalancing_run_snapshots`
- 신규 `run_repository.py`
  - run 생성/조회
  - same target 재사용
  - 다른 target 등장 시 supersede + parent-child 연결
  - planning/execution/state transition snapshot 저장
  - pause/resume helper
  - `ceil(remaining_qty / remaining_execution_days)` 기반 당일 slice 계산
- `target_retriever.py`
  - `target_signature`
  - `target_payload`
  - `mp_signature`
  - `sub_mp_signatures`
  - current target metadata 반환 보강
- `rebalancing_engine.py`
  - `execute_rebalancing_for_user()` 추가
  - 현재 snapshot 기준 full net trade 계산
  - active run의 `remaining_execution_days` 기준 당일 slice 생성
  - phase 5 실행 시 run 생성/재사용/완료 처리
  - execution result에 `run`, `full_net_trades`, `net_trades`, `target_signature` 포함
- `paper_broker_adapter.py`
  - `strategy_profile_id`, `business_date`를 실행 엔진으로 전달
- `test_session_service.py`
  - test session의 `strategy_profile_id`, `next_business_date`를 paper execution에 전달
- `main.py`
  - `/api/test/rebalancing-runs/{run_id}`
  - `/api/test/rebalancing-runs/{run_id}/snapshots`
- 테스트
  - `test_rebalancing_run_repository.py` 추가

## 검증
- 수정 파일 AST parse 성공
- `run_repository.calculate_today_slice_quantity()`
  - `9 / 5 -> 2`
  - `1 / 5 -> 1`
- `run_repository.build_daily_sliced_trades()`
  - BUY/SELL action 유지
  - SELL diff 음수 유지
- `rebalancing_engine.execute_rebalancing_for_user(max_phase=3)` 직접 로드 검증
  - active run이 없을 때 `PREVIEW` run 반환
  - `QQQ 9주 -> 2주`, `TLT 5주 -> 1주` 당일 slice 반환 확인

## 남은 범위
- partial fill을 주문 응답/체결 이벤트 기준으로 더 정밀하게 반영
- completion tolerance 정의
- run별 화면/리포트 정리
- MP/Sub-MP 충돌 시 pause/defer/absorb 정책을 실제 상태 전이에 연결

## 이슈/메모
- 현재 partial fill 반영은 “다음 거래일 snapshot 재계산” 방식으로 1차 대응한다.
- 현재 run 완료는 `remaining_execution_days == 0` 또는 drift 해소 시점 기준으로만 처리한다.
- 체결 이벤트 단위의 잔량 보정은 다음 단계에서 `OrderExecutor` 확장이 필요하다.
