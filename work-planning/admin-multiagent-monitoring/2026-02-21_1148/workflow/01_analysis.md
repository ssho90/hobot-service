# 01 분석 로그

- 기존 `llm_usage_logs` 기반 LLM 모니터링이 존재한다.
- 멀티에이전트 전용 필드(`flow_type`, `flow_run_id`, `agent_name`)가 없어 run 단위 추적이 어렵다.
- GraphRAG `/graph/rag/answer`는 현재 `user_id="system"`으로 저장되어 사용자 식별이 되지 않는다.
- AI Strategist는 서비스명 단위 로깅은 존재하나 run_id/user 연계가 약하다.
