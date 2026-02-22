# Phase 6 1차: 회귀/운영 관측 필드 확장

## 1. 작업 목적
- Phase 6 요구사항 중 "회귀 리포트 필드 확장"을 우선 구현한다.
- 필수 관측값: `tool_mode`, `target_agents`, `structured_citation_count`, `freshness_status`.

## 2. 반영 내용
1. `hobot/service/graph/monitoring/phase5_regression.py`
   - `evaluate_golden_case_response` 결과에 아래 필드 추가:
     - `tool_mode`
     - `target_agents`
     - `structured_citation_count`
     - `freshness_status` (기존 유지)
   - 집계 리포트에 관측 요약 필드 추가:
     - `tool_mode_counts`
     - `target_agent_counts`
     - `freshness_status_counts`
     - `structured_citation_stats` (`total/average/max/cases_with_structured_citations`)

2. `hobot/service/macro_trading/scheduler.py`
   - `run_graph_rag_phase5_regression`의 run report(`GRAPH_RAG_PHASE5_REGRESSION`) details에 위 관측 요약 필드 저장.
   - `_build_phase5_failure_debug_entries`에 케이스별 디버깅 필드 추가:
     - `structured_citation_count`
     - `tool_mode`
     - `target_agents`

3. `work-planning/chatbot-multi-agent/2026-02-20_1251/plan.md`
   - Phase 6 상태 설명 업데이트.
   - Done 항목에 "Phase 6 1차 착수 완료" 추가.

## 3. 테스트
1. `PYTHONPATH=. ../.venv/bin/python tests/test_phase5_golden_regression.py`
2. `PYTHONPATH=. ../.venv/bin/python tests/test_phase5_regression_batch_runner.py`
3. `PYTHONPATH=. ../.venv/bin/python -m unittest service.macro_trading.tests.test_scheduler_graph_phase5_regression`

모든 테스트 통과.

## 4. 다음 작업(Phase 6 잔여)
1. Multi-Agent 전용 golden set을 `single`/`parallel` 케이스로 분리 확장.
2. 운영 알림에 관측 요약(특히 `structured_citation_stats`)의 임계치 경고 규칙 추가.
3. 주간 자동 리포트 산출 스케줄(배치 + 저장 + 알림) 연결.
