# 04. Phase 2 Signal Confirmation Unification

## 목적
- 운영 AI 분석 저장과 `PAPER_TIME_TRAVEL` fixture 저장이 동일한 signal confirmation 경로를 사용하도록 정리한다.
- signal observation/candidate/effective target 판정 로직의 중복 진입점을 제거한다.

## 수행 내용
- `signal_confirmation_service.py`
  - `register_strategy_decision_signal()` 공통 함수 추가
  - 기존 fixture path가 공통 함수로 delegation 하도록 변경
- `ai_strategist.py`
  - `save_strategy_decision()`이 더 이상 `track_signal_observation()`을 직접 호출하지 않도록 변경
  - 저장 완료 로그에 `candidate_status`, `consecutive_days`, `promoted`를 추가
- `test_rebalancing_signal_confirmation_service.py`
  - 공통 registration helper 단위 테스트 추가

## 검증
- 수정 파일 AST parse 성공
- `signal_confirmation_service.register_strategy_decision_signal()` 직접 로드 검증
  - payload 정규화
  - 기본 `strategy_profile_id` 보정
  - `track_signal_observation()` delegation 확인
- `ai_strategist.py`는 함수 본문 AST parse로 import/호출 구조가 유지되는지 확인

## 남은 범위
- 운영 scheduler에서 signal confirmation job 이름/관측 로그를 별도 명시할지 결정
- holiday calendar 보강
- baseline 복구 정책 확정

## 이슈/메모
- 운영 스케줄러는 별도 signal confirmation 잡을 추가하지 않아도 된다.
- `run_ai_analysis()`가 `save_strategy_decision()`을 통해 저장될 때 자동으로 공통 signal confirmation 서비스가 실행된다.
