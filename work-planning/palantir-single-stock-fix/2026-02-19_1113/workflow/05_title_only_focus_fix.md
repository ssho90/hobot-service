# 05. MSFT 제목-오탐 포커스 보정

## 배경
- `us_single_stock` 인용 보강에서 `doc_title`에 종목명이 포함된 경우가 `focus`로 과대평가되어,
  본문(text)에 종목 직접 언급이 없는 citation이 유지되는 문제가 재현됨.

## 원인
- `response_generator.py`의 포커스 스코어가 본문 + 제목을 함께 사용.
- `target_focus_count` 계산도 동일 스코어를 사용해 `title-only` citation을 종목 직접 근거로 오인.

## 조치
- `focus_count`/교체 판단을 `citation.text` 기준으로 변경.
- candidate evidence 선택도 `evidence.text` 기준 포커스 매치 우선으로 변경.
- title-only 매치가 본문 직접 근거를 가리는 케이스 회귀 테스트 추가.

## 검증
- 단위 테스트: `hobot/tests/test_phase_d_response_generator.py` 통과.
- 실데이터 재현:
  - MSFT: focus citation 3건 본문 직접 매치 확인.
  - PLTR: focus citation 3건 유지 확인.
