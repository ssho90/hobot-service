# 01 분석

- 현재 누락 원인:
  - Admin Multi-Agent 모니터링은 `llm_usage_logs`만 조회.
  - 하위 에이전트는 `execute_agent_stub -> execute_live_tool(SQL/Neo4j)` 경로로 실행되며 LLM invoke가 없어 `track_llm_call`이 발생하지 않음.
- 결과:
  - 화면에는 `router_intent_classifier`, `supervisor_agent` 등 LLM 호출만 표출됨.
