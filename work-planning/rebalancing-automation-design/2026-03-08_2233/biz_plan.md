# 자동 리밸런싱 전환 설계서

## 문서 목적

본 문서는 [원본 설계 문서](/Users/ssho/project/hobot-service/hobot/docs/macro-trading/20260308_auto_rebalancing_design.md)를 `work-planning` 형식으로 옮긴 실행용 계획 문서다.

- 원본 위치: `/Users/ssho/project/hobot-service/hobot/docs/macro-trading/20260308_auto_rebalancing_design.md`
- 목적: 자동 리밸런싱 구현 작업을 `work-planning` 트리 안에서 추적 가능하게 한다.
- 범위: 신호 확정, 5일 분할집행, 멀티유저 상태 관리, 모의투자 + time-travel 테스트

## 핵심 요구사항

1. MP 또는 Sub-MP가 변경되면 3거래일 연속 동일할 때만 리밸런싱을 시작한다.
2. 리밸런싱은 5회 실행일 기준으로 분할 매수/매도한다.
3. 첫날에 5일치 주문을 고정하지 않고, 매일 최신 스냅샷 기준으로 남은 수량을 재계산한다.
4. MP/Sub-MP 변경 충돌, drift 임계치 충돌, 체결/시세/현금 예외를 상태머신으로 처리한다.
5. 리밸런싱 상태와 실행 결과는 사용자별로 독립 관리한다.
6. 공식 테스트는 모의투자 계좌로 수행하되, `+1 business day`로 날짜를 압축 진행할 수 있어야 한다.

## 현재 상태 요약

### 이미 있는 것

- AI 분석 자동 스케줄
  - `hobot/service/macro_trading/scheduler.py`
  - 매일 `08:30` `run_ai_analysis()` 실행
- 사용자별 계좌/주문 실행 경로
  - `get_balance_info_api(user_id)`
  - `get_user_kis_credentials(user_id)`
  - `execute_rebalancing(user_id)`

### 아직 없는 것

- 3거래일 신호 확정기
- 5회 분할집행 상태머신
- active target / pending candidate / run 상태 분리
- 사용자별 자동 리밸런싱 설정
- paper trading + time travel 테스트 세션 관리

## 설계 원칙

### 1. 신호와 실행을 분리한다

- `Observed Signal`
- `Pending Candidate`
- `Effective Target`

최신 `ai_strategy_decisions`를 즉시 매매에 사용하지 않는다.

### 2. 실행은 적응형으로 계산한다

매 실행일마다 아래를 다시 계산한다.

1. 현재 보유 수량/현금/시세 스냅샷 취득
2. 현재 시점 기준 목표 수량 재계산
3. 남은 목표 수량 계산
4. `오늘 주문 수량 = 남은 수량 / 남은 실행일 수`
5. 체결 결과 반영

### 3. 멀티유저 구조를 강제한다

- 전략 신호와 확정 target은 `strategy_profile_id` 단위로 공유 가능
- drift 판단, active run, 주문, 체결, 예외, 재시도는 `user_id` 단위로 분리

즉, 같은 전략 프로필을 여러 사용자가 공유하더라도 리밸런싱 실행 상태는 절대로 공유하지 않는다.

### 4. 테스트는 실전 전 Paper Trading으로 검증한다

- 공식 테스트 모드: `PAPER_TIME_TRAVEL`
- 보조 로직 테스트 모드: `DUMMY_UNIT`

## To-Be 운영 모델

### 일일 배치

| 시간(KST) | 배치 | 설명 |
| --- | --- | --- |
| 08:30 | AI Analysis Job | 전략 분석 또는 fixture input |
| 08:35 | Signal Confirmation Job | 전략 프로필별 3거래일 연속 여부 판정 |
| 09:40 | Auto Rebalancing Job | 사용자별 drift 점검 및 당일 분할주문 실행 |
| 장 마감 후 | Reconciliation Job | 체결/잔량/예외 정리 |

### 우선순위 규칙

1. `CONFIRMED MP CHANGE`
2. `MP DRIFT BREACH`
3. `CONFIRMED SUB-MP CHANGE`
4. `SUB-MP DRIFT BREACH`

정책:

- 높은 우선순위는 낮은 우선순위 run을 supersede 가능
- 낮은 우선순위는 높은 우선순위 run을 끊지 않고 absorb 또는 defer

## 핵심 충돌 처리 정책

### 1. 리밸런싱 도중 MP 또는 Sub-MP가 변경되는 경우

- 미확정 후보(1~2일차)는 즉시 전환하지 않음
- MP 후보 발생 시 전체 run pause
- Sub-MP 후보 발생 시 해당 자산군 scope만 pause
- 3거래일 뒤 확정되면 새 target으로 Day 1부터 재시작
- 후보가 취소되면 pause된 run 재개

### 2. Sub-MP 리밸런싱 중 MP 임계치 초과 발생

- `GLOBAL preemption`
- local run은 `superseded`
- 새 global run을 현재 보유 상태 기준으로 다시 생성

### 3. MP 리밸런싱 중 Sub-MP 임계치 초과 발생

- `GLOBAL absorb, LOCAL defer`
- global run이 우선
- 필요하면 global 완료 후 follow-up local run 생성

## 권장 상태/데이터 모델

### 전략/설정

- `strategy_profiles`
- `user_rebalancing_settings`

### 신호 계층

- `rebalancing_signal_observations`
- `rebalancing_signal_candidates`
- `effective_rebalancing_targets`

### 실행 계층

- `rebalancing_runs`
- `rebalancing_run_snapshots`

### 테스트 계층

- `rebalancing_test_sessions`
- `rebalancing_test_day_results`
- `rebalancing_test_assertions`

## 테스트 전략

### 공식 테스트 모드

- `PAPER_TIME_TRAVEL`
- 모의투자 계좌 사용
- `virtual_business_date` 기반으로 날짜 진행
- `+1 business day`를 누르면 해당 날짜 배치를 즉시 실행

### 중요한 의미

`+1 business day`는 브로커 날짜를 바꾸는 기능이 아니다.

1. 내부 `virtual_business_date`를 다음 거래일로 이동
2. 해당 날짜 fixture를 적용
3. 그 날짜의 signal confirmation + rebalancing execution 수행
4. 결과를 테스트 세션에 저장
5. UI에서 일별 결과 확인

주의:

- 모의투자 주문은 실제 주문 가능한 시장 시간에만 실행 가능
- 시장 시간이 아니면 해당 테스트 일차를 `planned` 상태로 저장하고, 가능한 시간에 실행하도록 제한하는 것이 안전함

### 최소 테스트 시나리오

1. MP 변경 2일 유지 후 취소
2. MP 변경 3거래일 유지 후 confirm
3. 리밸런싱 2일차에 Sub-MP 후보 발생 후 취소
4. local run 도중 MP drift breach
5. global run 도중 sub-mp breach
6. 사용자 2명 성공, 1명 credential 없음
7. 한 사용자는 partial fill, 다른 사용자는 full fill
8. 수동 매매 반영
9. `+1 business day` 5회 진행 시 분할집행 완료

## 구현 포인트

### 스케줄러

대상:

- `hobot/service/macro_trading/scheduler.py`

필요 함수:

- `run_signal_confirmation_job()`
- `run_auto_rebalancing_job()`
- `setup_signal_confirmation_scheduler()`
- `setup_auto_rebalancing_scheduler()`

### 타겟 조회

대상:

- `hobot/service/macro_trading/rebalancing/target_retriever.py`

필요 함수:

- `get_effective_target()`
- `build_target_signature()`
- `get_target_by_signature()`

### 실행 엔진

대상:

- `hobot/service/macro_trading/rebalancing/rebalancing_engine.py`

필요 함수:

- `detect_rebalancing_events()`
- `start_run_if_needed()`
- `pause_impacted_runs()`
- `resume_runs_if_candidate_reverted()`
- `execute_run_for_today()`
- `plan_today_slice()`
- `reconcile_run_after_execution()`
- `execute_rebalancing_for_user(user_id, strategy_profile_id)`

### 주문 실행

대상:

- `hobot/service/macro_trading/rebalancing/order_executor.py`

필요사항:

- 주문별 idempotency key
- partial fill / timeout / cancel 저장
- sell 이후 buy 수량 재보정

### 테스트 인프라

대상:

- `hobot/service/macro_trading/rebalancing/`
- `hobot/service/core/time_provider.py`
- `hobot/main.py`

필요 컴포넌트:

- `ScenarioFixtureLoader`
- `PaperTradingBrokerAdapter`
- `TimeTravelScenarioRunner`
- `TestSessionManager`
- `TestResultRecorder`
- 선택적 `FakeBrokerAdapter`

## 구현 순서

### Phase 1. 신호 안정화 계층

- signature 계산
- observation/candidate/effective target 저장

### Phase 2. 모의투자 + Time Travel 테스트 인프라

- `PAPER_TIME_TRAVEL` 모드
- 테스트 세션 관리
- `+1 business day` 실행
- 결과 화면/리포트

### Phase 3. 멀티데이 run 상태머신

- `rebalancing_runs`
- `rebalancing_run_snapshots`
- pause/resume/supersede

### Phase 4. 스케줄러 연결

- `08:35` 전략 프로필별 signal confirmation
- `09:40` 사용자별 auto execution fan-out

### Phase 5. 예외 및 운영 툴링

- 관리자 대시보드
- kill switch
- retry/restart 제어

## 완료 기준

다음을 만족하면 본 계획 완료로 본다.

1. MP/Sub-MP 3거래일 확정이 자동으로 동작한다.
2. 사용자별 5회 분할집행이 상태 저장과 함께 동작한다.
3. MP/Sub-MP 충돌 케이스가 상태머신에서 재현 가능하다.
4. `PAPER_TIME_TRAVEL` 모드에서 `+1 business day`로 시나리오를 진행할 수 있다.
5. 사용자별 테스트 결과와 주문/체결 로그를 화면에서 확인할 수 있다.
