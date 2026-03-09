# 02. Phase 1 Signal Foundation

## 목적
- 자동 리밸런싱의 1차 기반인 `Observed Signal -> Pending Candidate -> Effective Target` 흐름을 실제 코드에 넣는다.

## 수행 내용
- `db.py`
  - `strategy_profiles`
  - `user_rebalancing_settings`
  - `rebalancing_signal_observations`
  - `rebalancing_signal_candidates`
  - `effective_rebalancing_targets`
  - `ai_strategy_decisions.strategy_profile_id`
  - 기본 프로필 `DEFAULT_US_MACRO_PROFILE` seed
- 신규 `rebalancing/signal_tracker.py`
  - MP/Sub-MP signature 생성
  - 공식 observation upsert
  - 3관찰일 streak 계산
  - pending candidate 생성/취소
  - confirmed 시 effective target 승격
- `ai_strategist.py`
  - decision 저장 시 `strategy_profile_id` 기록
  - `sub_mp_details_snapshot` 저장
  - 저장 직후 signal tracker 호출
- `target_retriever.py`
  - `get_current_target_data()`
  - `get_effective_target_data()`
  - 기존 getter는 effective target 우선, 없으면 latest fallback
- `kis.py`
  - 보유 종목 자산군 분류용 ETF 매핑을 current/effective target 기준으로 변경

## 검증
- 일반 `unittest`는 현재 로컬 Python 3.9 환경에서 `service.macro_trading.__init__`의 외부 의존 import와 `datetime.UTC` 사용 때문에 실패
- 대신 아래를 검증
  - 수정 파일 전체 `ast.parse` 성공
  - `signal_tracker` signature/streak 핵심 함수 직접 로드 테스트 성공
  - `target_retriever` effective target 우선 / latest fallback 직접 로드 테스트 성공

## 이슈/메모
- 현재 streak는 "공식 observation이 생성된 거래일" 기준이다.
- 실제 거래소 영업일 캘린더를 강제하는 로직은 Phase 2 또는 별도 유틸 단계에서 보강 필요
- `service.macro_trading.__init__`가 너무 많은 모듈을 eager import해서 단위 테스트 격리가 어렵다.

## 다음 단계
- Phase 2에서 `PAPER_TIME_TRAVEL` 세션 상태와 `+1 business day` 실행 경로를 구현한다.
