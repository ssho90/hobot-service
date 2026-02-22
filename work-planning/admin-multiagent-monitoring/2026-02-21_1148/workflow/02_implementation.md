# 02 구현 로그

## 백엔드
- `llm_usage_logs` 스키마 확장
  - `flow_type`, `flow_run_id`, `agent_name`, `trace_order`, `metadata_json` 컬럼/인덱스 추가
- `service/llm_monitoring.py`
  - ContextVar 기반 run 컨텍스트(`set/reset/get_llm_flow_context`) 추가
  - `log_llm_usage` 및 `track_llm_call`에 멀티에이전트 추적 파라미터 확장
- GraphRAG 계측 강화
  - 요청별 `flow_run_id(chatbot-*)` 생성
  - Authorization 토큰에서 `user_id` 추출
  - router intent LLM 호출(`graph_rag_router_intent`) 로그 추가
  - final answer LLM 호출에 `flow_type/chatbot`, `flow_run_id`, `agent_name` 기록
- AI Strategist 계측 강화
  - `run_ai_analysis(triggered_by_user_id=None)` 확장
  - 실행 단위 `flow_run_id(dashboard-*)`, `flow_type=dashboard_ai_analysis` 컨텍스트 설정
  - 병렬 호출 일부에 flow 컨텍스트 명시 전달
- Admin API 추가
  - `GET /api/admin/multi-agent-monitoring/options`
  - `GET /api/admin/multi-agent-monitoring/flows`
  - `GET /api/admin/multi-agent-monitoring/calls`

## 프론트엔드
- 신규 화면: `AdminMultiAgentMonitoring.tsx`
  - run 목록 + 선택 run 호출 상세 테이블
  - 필터: flow_type/user/start/end
- 라우트 추가: `/admin/multi-agent`
- 헤더 Admin 메뉴 추가: `Multi-Agent 모니터링`

