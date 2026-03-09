# 03. Phase 2 Time Travel Foundation

## 목적
- `PAPER_TIME_TRAVEL` 테스트 세션의 최소 동작 단위를 구현한다.
- 가상 거래일, `+1 business day`, 세션/일별 결과 저장, admin API를 연결한다.

## 수행 내용
- `db.py`
  - `rebalancing_test_sessions`
  - `rebalancing_test_session_users`
  - `rebalancing_test_day_results`
  - `rebalancing_test_assertions`
- `time_provider.py`
  - `virtual_business_date`
  - `active_rebalancing_test_session`
  - 거래일 기준 `add_business_days()`
- 신규 `scenario_fixture_loader.py`
  - fixture 목록 조회
  - fixture 로드
  - 거래일별 fixture resolve
- 신규 `paper_broker_adapter.py`
  - paper account 강제
  - baseline snapshot 조회
  - 미국 정규장 시간 여부 판단
- 신규 `test_session_service.py`
  - 세션 생성
  - baseline capture
  - active session 조회
  - `advance_business_day`
  - day result 저장
  - assertion 저장
  - session 종료
- `main.py`
  - `/api/test/rebalancing-sessions/fixtures`
  - `/api/test/rebalancing-sessions/active`
  - `/api/test/rebalancing-sessions`
  - `/api/test/rebalancing-sessions/{session_id}`
  - `/api/test/rebalancing-sessions/{session_id}/day-results`
  - `/api/test/rebalancing-sessions/{session_id}/advance-business-day`
  - `/api/test/rebalancing-sessions/{session_id}/close`
  - 기존 `/api/test/status`, `/api/test/time-travel/next-day` 보강

## 검증
- 수정 파일 AST parse 성공
- `TimeProvider` 직접 로드 테스트
  - `set_virtual_business_date()`
  - `add_business_days()`가 주말을 skip하는지 확인
  - active session state 저장/초기화 확인
- `ScenarioFixtureLoader.resolve_fixture_for_business_date()` 직접 검증
- `PaperTradingBrokerAdapter.is_us_market_open()` 직접 검증
- `TestSessionService`는 stub dependency로 import 가능 여부 확인

## 남은 범위
- signal confirmation 실제 배치 연결
- fixture를 AI signal input으로 주입하는 경로
- 미국 휴장일 캘린더 보강
- baseline 복구 정책
- assertion report 생성 자동화

## 이슈/메모
- 현재 `advance_business_day`는 signal confirmation을 아직 실행하지 않고 `SKIPPED_NOT_IMPLEMENTED`로 기록한다.
- `run_rebalancing_execution=true`일 때만 모의투자 실행을 시도하며, 시장 시간이 아니면 `PENDING_MARKET_WINDOW`로 저장한다.
- 표준 `unittest`는 여전히 패키지 eager import 문제로 불안정해서, 직접 로드 검증을 사용했다.

## 다음 단계
- Phase 3 이전에 최소한 signal confirmation job을 서비스 계층에서 호출 가능하게 연결해야 한다.
