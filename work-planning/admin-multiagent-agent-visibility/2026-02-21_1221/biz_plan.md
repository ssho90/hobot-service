# Admin Multi-Agent Agent Visibility 개선 계획

## 목표
- Multi-Agent 모니터링에서 실제 호출된 하위 에이전트(SQL/Graph 실행 포함)가 모두 보이도록 로그 계층을 확장한다.

## 문제 정의
- 현재 화면은 `llm_usage_logs` 기반이라 LLM invoke만 노출됨.
- `equity_analyst_agent`, `macro_economy_agent` 등은 Phase2에서 SQL/Neo4j 템플릿 실행이 중심이며, LLM 호출이 없으면 모니터링에서 누락됨.

## 구현 전략
1. Supervisor branch 실행 시점에서 agent run 단위 실행 로그를 `llm_usage_logs`에 추가 기록한다.
   - service_name: `graph_rag_agent_execution`
   - agent_name: 실제 agent
   - model_name: agent_model_policy 기반(없으면 `internal-agent-executor`)
   - provider: `Internal`
   - 토큰: 0
   - metadata_json: branch/tool/status/reason/row_count 등
   - request_prompt/response_prompt: agent 입력 요약, 실행 결과 요약(JSON)
2. 기존 LLM 호출 로그(router/supervisor)는 유지하여 한 run에서 함께 보이게 한다.
3. monitor API/프론트는 기존 컬럼 구조 그대로 재사용(이미 agent_name/service_name/metadata_json 포함).

## 검증
- 단위: Python syntax check
- 동작: 샘플 질의 실행 후 `/api/admin/multi-agent-monitoring/calls?flow_run_id=...`에서
  - router + supervisor + sql/graph agent execution 로그가 모두 반환되는지 확인

## 산출물
- 코드 수정 파일
  - `hobot/service/graph/rag/response_generator.py`
- workflow 로그 문서
