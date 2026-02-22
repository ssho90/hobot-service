# 12_phase2_agent_stub_executor_wiring

## 요청
- "시작해" 이후 Phase 2를 실제 분기 실행 코드까지 확장.

## 반영 파일
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/response_generator.py`
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/agents/__init__.py`
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/agents/macro_agent.py`
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/agents/equity_agent.py`
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/agents/real_estate_agent.py`
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/agents/ontology_agent.py`
- `/Users/ssho/project/hobot-service/hobot/tests/test_phase_d_response_generator.py`
- `/Users/ssho/project/hobot-service/work-planning/chatbot-multi-agent/2026-02-20_1251/plan.md`

## 반영 내용
1. Agent stub 엔트리 생성
- `macro_economy_agent`, `equity_analyst_agent`, `real_estate_agent`, `ontology_master_agent`에 대한 실행 함수 추가.

2. Supervisor 분기 실행기 연결
- `_execute_supervisor_plan()` / `_execute_branch_agents()` 추가.
- `tool_mode=parallel` + `sql_need && graph_need`이면 SQL/Graph 브랜치를 ThreadPoolExecutor로 병렬 실행.
- 그 외는 단일 실행.

3. 실행 결과 메타 표준화
- `supervisor_execution.execution_result`에
  - `status`
  - `dispatch_mode`
  - `branch_results`
  - `invoked_agent_count`
  를 저장.
- scope guard / cache hit 경로는 `status=skipped`로 명시.

4. 테스트 보강
- 병렬/단일 케이스에서 `execution_result` 검증 추가.
- scope guard 케이스에서 `execution_result.reason` 검증 추가.

## 검증
- 실행 명령:
  - `cd /Users/ssho/project/hobot-service/hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
- 결과:
  - `Ran 35 tests ... OK`
  - 로컬 MySQL 미연결 경고 로그는 테스트 환경 이슈로 지속.
