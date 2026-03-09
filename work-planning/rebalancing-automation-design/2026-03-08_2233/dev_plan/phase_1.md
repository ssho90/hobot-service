# Phase 1. 신호 안정화 계층 도입

## 목표
- 최신 `ai_strategy_decisions`를 즉시 매매에 사용하지 않고, `Observed Signal -> Pending Candidate -> Effective Target` 구조로 분리한다.
- MP/Sub-MP 변경을 3거래일 기준으로 확정하는 기반을 만든다.

## 대상 파일
- `hobot/service/database/db.py`
- `hobot/service/macro_trading/rebalancing/target_retriever.py`
- `hobot/service/macro_trading/ai_strategist.py`
- 신규 `hobot/service/macro_trading/rebalancing/signal_tracker.py`

## 구현 포인트
- `strategy_profiles`
- `user_rebalancing_settings`
- `rebalancing_signal_observations`
- `rebalancing_signal_candidates`
- `effective_rebalancing_targets`
- MP/Sub-MP signature 계산 함수
- 거래일 기준 3일 확정 로직

## 체크리스트

### To-Do
- [x] `strategy_profile_id` 축을 어떻게 둘지 결정
  - `ai_strategy_decisions.strategy_profile_id` 컬럼 추가
  - 기본 프로필 `DEFAULT_US_MACRO_PROFILE` fallback 사용
- [x] MP signature 정규화 규칙 정의
- [x] Sub-MP signature 정규화 규칙 정의
- [x] 거래일 캘린더 기준 연속일 계산 규칙 정의
  - Phase 1에서는 "거래일별 공식 observation 1건"을 기준으로 streak 계산
- [x] 동일 거래일 다중 AI 분석 저장 시 공식 관찰값 선택 규칙 정의
  - `(strategy_profile_id, business_date)` upsert로 당일 마지막 성공 결과를 공식값으로 사용

### In Progress
- [ ] 실제 거래소 거래일 캘린더 연동
- [ ] Local scope(Sub-MP 단독 변경) candidate 분리

### Done
- [x] `biz_plan.md`와 원본 설계 문서 기준 범위 확정
- [x] 신규 상태 테이블 스키마 작성
- [x] `get_effective_target()` 설계 및 코드 반영
- [x] `Observed Signal -> Pending Candidate -> Effective Target` DB 흐름 구현
- [x] `target_retriever`를 effective target 우선 조회로 변경
- [x] 현재 활성 ETF 매핑을 effective target 기준으로 정렬

## 완료 기준
- 3거래일 연속 동일 신호일 때만 `Effective Target`이 생성된다.
- 기존 최신값 조회와 별개로 "현재 확정 목표" 조회 경로가 생긴다.
- 멀티유저/전략 프로필 구조를 깨지 않는 스키마가 준비된다.

## 리스크
- `ai_strategy_decisions`가 현재 전역 구조라서 전략 프로필 축 추가 시 호환성 이슈가 생길 수 있다.
- 거래일 정의를 명확히 하지 않으면 3일 확정 로직이 흔들릴 수 있다.
