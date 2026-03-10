# Phase 2. 모의투자 + Time Travel 테스트 인프라

## 목표
- `PAPER_TIME_TRAVEL` 모드를 도입한다.
- `+1 business day`를 누르면 다음 테스트 날짜로 이동하고, 해당 날짜 배치를 즉시 실행할 수 있게 한다.
- 테스트 결과를 세션/일자/사용자 단위로 조회 가능하게 만든다.

## 대상 파일
- `hobot/service/core/time_provider.py`
- `hobot/main.py`
- 신규 `hobot/service/macro_trading/rebalancing/test_session_service.py`
- 신규 `hobot/service/macro_trading/rebalancing/paper_broker_adapter.py`
- 신규 `hobot/service/macro_trading/rebalancing/scenario_fixture_loader.py`

## 구현 포인트
- `PAPER_REALTIME`, `PAPER_TIME_TRAVEL`, `DUMMY_UNIT` 모드 구분
- `virtual_business_date`
- `real_executed_at`
- 테스트 세션 생성/종료
- `+1 business day` API
- 모의투자 계좌 매핑
- 테스트 결과 저장/조회

## 체크리스트

### To-Do
- [x] 테스트 세션 테이블 정의
- [x] 일별 결과 테이블 정의
- [x] assertion 저장 테이블 정의
- [x] fixture 주입 구조 정의
- [ ] 모의투자 테스트 사용자/계좌 운영 방식 정의
  - 전용 계좌
  - baseline 복구 방식

### In Progress
- [x] `TimeProvider` 재사용 방식 검토
- [x] admin API 흐름 설계
  - 세션 시작
  - `+1 business day`
  - 결과 조회
- [x] signal confirmation 실제 배치 연결
  - fixture 기반 synthetic decision -> observation/effective target 경로 연결
- [x] fixture -> signal confirmation 입력 경로 연결
- [ ] 실거래/모의투자 장시간 제약에 대한 holiday 캘린더 보강

### Done
- [x] 테스트 정책 확정
  - 공식 테스트는 모의투자 계좌 사용
  - 달력 대기는 제거
- [x] `TimeProvider`에 `virtual_business_date` / `active_test_session` 상태 추가
- [x] `ScenarioFixtureLoader` 추가
- [x] `PaperTradingBrokerAdapter` 추가
- [x] `TestSessionService` 추가
- [x] `SignalConfirmationService` 추가
- [x] admin API 추가
  - fixture 목록
  - active session 조회
  - session 생성/조회/종료
  - `advance-business-day`
- [x] 샘플 3일 confirm fixture 추가
- [x] signal confirmation assertion 조회 API 추가
- [x] 운영 AI 분석 저장 경로를 signal confirmation 공통 서비스로 정리
  - `save_strategy_decision()`과 fixture 테스트가 동일한 observation/effective target 경로를 사용

## 완료 기준
- 테스트 세션을 생성할 수 있다.
- `+1 business day` 실행 시 virtual date가 전진한다.
- 그 날짜의 signal confirmation + rebalancing execution이 수행된다.
- 사용자별 주문/체결/상태 결과를 화면 또는 API에서 확인할 수 있다.

## 리스크
- 실제 모의투자 주문은 현재 실제 시장 시간 제약을 받는다.
- baseline 상태 복구가 없으면 반복 테스트 재현성이 떨어질 수 있다.
- 현재 signal confirmation은 fixture 기반 synthetic decision 경로로만 연결되어 있다.
- 운영 AI 분석 저장과 테스트 fixture는 이제 동일 signal confirmation 서비스로 동작한다.
