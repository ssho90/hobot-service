# Daily History

## 2026-03-08
- 세션: [01_dev_plan_init.md](./01_dev_plan_init.md)
- 핵심 요약: `biz_plan.md`를 기반으로 `dev_plan/phase_1.md` ~ `phase_5.md` 구현 계획 문서를 생성했다.
- 이슈/해결: `workflow/`와 `dev_plan/` 용도를 혼동했으나, 규칙 재확인 후 `dev_plan/`에 단계별 계획을 분리하고 `workflow/`에는 작업 이력만 기록하도록 정리했다.
- 다음 목표: `phase_1.md` 기준으로 신호 안정화 계층부터 실제 구현 시작

## 2026-03-09
- 세션: [02_phase1_signal_foundation.md](./02_phase1_signal_foundation.md)
- 핵심 요약: 자동 리밸런싱 Phase 1 기반으로 전략 프로필, 신호 observation/candidate/effective target 테이블과 조회 경로를 구현했다.
- 이슈/해결: 기본 `unittest`는 Python 3.9에서 `service.macro_trading.__init__`의 eager import 때문에 실패하여, 수정 파일 직접 로드 방식으로 AST 및 핵심 함수 검증을 수행했다.
- 다음 목표: `PAPER_TIME_TRAVEL` 세션과 `+1 business day` 테스트 경로 구현

## 2026-03-10
- 세션: [03_phase2_time_travel_foundation.md](./03_phase2_time_travel_foundation.md)
- 세션: [04_phase2_signal_confirmation_unification.md](./04_phase2_signal_confirmation_unification.md)
- 핵심 요약: `PAPER_TIME_TRAVEL` 세션, `virtual_business_date`, `+1 business day`, fixture loader, paper broker adapter, admin API를 구현했고, 이어서 운영 AI 분석 저장 경로와 fixture signal confirmation 경로를 공통 서비스로 통합했다.
- 이슈/해결: 표준 `unittest` 대신 in-memory DB stub과 직접 로드 검증을 사용해 `synthetic/live decision -> observation -> candidate -> effective target` 공통 경로를 확인했다.
- 다음 목표: Phase 3 멀티데이 run 상태머신과 5일 분할집행 로직으로 이어간다.

## 2026-03-11
- 세션: [05_phase3_run_state_machine_foundation.md](./05_phase3_run_state_machine_foundation.md)
- 핵심 요약: 사용자별 `rebalancing_runs`/`rebalancing_run_snapshots`, 당일 slice 계산, `execute_rebalancing_for_user()` 기반 5일 분할집행 foundation, run 조회 API를 구현했다.
- 이슈/해결: 기존 엔진이 전체 수량 일괄 주문 구조라 상태머신을 붙일 수 없었는데, preview run과 persisted run을 분리해 `max_phase<5`에서는 상태 오염 없이 slice 계획만 확인하도록 정리했다.
- 다음 목표: partial fill 정밀 반영, completion tolerance, MP/Sub-MP 충돌 시 pause/defer/supersede 실제 상태 전이 구현
