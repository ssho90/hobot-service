# 02 구현

## 수정 파일
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/response_generator.py`

## 구현 내용
1. 하위 에이전트 실행 로그 계측 추가
- `_execute_branch_agents(...)`에 아래 인자 추가
  - `flow_type`, `flow_run_id`, `user_id`
- 각 `execute_agent_stub(...)` 실행 직후 `log_llm_usage(...)` 호출
  - `service_name="graph_rag_agent_execution"`
  - `provider="Internal"`
  - `model_name=agent_model_policy[agent_name]` 또는 `internal-agent-executor`
  - 토큰 0
  - `request_prompt`: branch/agent/selected_type/question/sql_need/graph_need 요약 JSON
  - `response_prompt`: run_result JSON
  - `metadata_json`: tool/status/reason/row_count/metric_value/companion_branch 등

2. 병렬 브랜치 컨텍스트 누락 방지
- `_execute_supervisor_plan(...)`에 `flow_type`, `flow_run_id`, `user_id` 인자 추가
- SQL/Graph 병렬 실행(`ThreadPoolExecutor`) 포함 모든 `_execute_branch_agents(...)` 호출에 위 인자 전달
- `generate_graph_rag_answer(...)`의 `_execute_supervisor_plan(...)` 호출 2곳에서
  - `flow_type="chatbot"`
  - `flow_run_id=effective_flow_run_id`
  - `user_id=effective_user_id`
  전달하도록 변경

## 기대 효과
- 기존에 보이던 `router_intent_classifier`, `supervisor_agent` 외에
  `equity_analyst_agent`(sql/graph), `macro_economy_agent`, `real_estate_agent`, `ontology_master_agent` 실행도
  동일 run에서 호출 상세에 표시됨.
