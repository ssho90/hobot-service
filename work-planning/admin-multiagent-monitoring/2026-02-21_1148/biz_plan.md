# Admin Multi-Agent Monitoring 구현 계획

## 목표
- Admin 화면에서 멀티에이전트 호출 흐름을 모니터링한다.
- 호출별 토큰 사용량, 사용자, 모델, 에이전트/서비스 단위를 확인 가능하게 한다.
- 대상 플로우:
  - Dashboard AI 거시경제 분석 (`dashboard_ai_analysis`)
  - Chatbot GraphRAG (`chatbot`)

## 구현 범위
1. LLM 로그 스키마 확장
   - `llm_usage_logs`에 멀티에이전트 추적 컬럼 추가
2. 로깅 컨텍스트 확장
   - `flow_type`, `flow_run_id`, `agent_name`, `trace_order`, `metadata_json` 지원
   - 요청 단위 컨텍스트(ContextVar) 지원
3. 멀티에이전트 경로 계측
   - GraphRAG: router/answer 호출 로깅 및 사용자 식별
   - AI Strategist: run 단위 컨텍스트 전파(수동 실행 시 admin 사용자 포함)
4. Admin API 추가
   - `/api/admin/multi-agent-monitoring/options`
   - `/api/admin/multi-agent-monitoring/flows`
   - `/api/admin/multi-agent-monitoring/calls`
5. Admin UI 추가
   - `/admin/multi-agent` 화면 추가
   - 플로우 목록 + 선택 플로우의 호출 상세 테이블 제공
6. 테스트
   - API/로깅 단위 테스트 추가 또는 기존 테스트 보강

## 완료 기준
- 두 플로우의 run 목록이 admin 화면에서 보인다.
- run 선택 시 호출별 토큰/사용자/서비스/모델/시간이 보인다.
- GraphRAG 호출의 `user_id`가 `system` 고정이 아니라 실제 인증 사용자 기준으로 기록된다.
