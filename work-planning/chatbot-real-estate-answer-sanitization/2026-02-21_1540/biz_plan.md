# 작업 계획

## 목표
1. 부동산 답변에서 법정동코드(예: 48250)를 사용자 친화 지역명으로 치환한다.
2. 내부 식별자(EVT_, EV_, EVID_, CLM_) 노출을 제거한다.
3. 1년 이상 누적 데이터 기반 시계열 추세를 답변에 강제 반영한다.

## 구현 범위
- `service/graph/rag/agents/live_executor.py`
  - 부동산 월간 집계 테이블 기준 시계열(최대 18개월) 추세 요약 추가
- `service/graph/rag/response_generator.py`
  - StructuredDataContext 지역명 치환
  - 사용자 노출 텍스트 내부 ID 제거/정제
  - 부동산 시계열 추세 반영 강제 후처리
- 테스트 보강
  - `tests/test_phase_d_live_executor.py`
  - `tests/test_phase_d_response_generator.py`

## 검증 계획
- 단위 테스트 실행 (수정된 테스트 중심)
- 문법 검증(py_compile)
