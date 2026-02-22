# Phase 6 2차: 골든셋 single/parallel 분리 검증

## 1. 작업 목적
- Phase 6의 잔여 항목 중 "single/parallel 케이스 분리"를 회귀 평가에 직접 반영한다.
- 라우팅 전략 회귀를 `expected_tool_mode` 기준으로 자동 검증한다.

## 2. 반영 내용
1. 골든셋 스키마 확장
   - 파일: `hobot/service/graph/monitoring/golden_sets/phase5_q1_q6_v1.json`
   - 각 케이스에 `expected_tool_mode`를 추가:
     - `Q1`, `Q2`: `single`
     - `Q3`, `Q4`, `Q5`, `Q6`: `parallel`

2. 회귀 평가 로직 확장
   - 파일: `hobot/service/graph/monitoring/phase5_regression.py`
   - `GoldenQuestionCase`에 `expected_tool_mode` 필드 추가.
   - `evaluate_golden_case_response`에서 실제 `tool_mode`와 기대값이 다르면 `routing_mismatch` 실패로 판정.
   - 결과 payload에 `expected_tool_mode`를 포함해 디버깅 가능하게 정규화.

3. 운영 디버그 payload 확장
   - 파일: `hobot/service/macro_trading/scheduler.py`
   - `failed_case_debug_entries`에 `expected_tool_mode`를 저장해 알림/운영 로그에서 라우팅 불일치 원인을 직접 확인 가능하게 반영.

## 3. 테스트
1. `PYTHONPATH=. ../.venv/bin/python tests/test_phase5_golden_regression.py`
2. `PYTHONPATH=. ../.venv/bin/python tests/test_phase5_regression_batch_runner.py`
3. `PYTHONPATH=. ../.venv/bin/python -m unittest service.macro_trading.tests.test_scheduler_graph_phase5_regression`

모든 테스트 통과.

## 4. 다음 작업
1. 주간 자동 회귀 리포트 배치(요약 + 상세 실패 원인 + 라우팅 통계) 스케줄 연결.
2. `routing_mismatch`/`structured_citation_stats` 기반 알림 임계치 규칙 추가.
