# 작업 로그

## 1. 코드 검증
- `response_generator.py`에서 아래 경로 확인:
  - `router_intent_classifier` 호출 (`graph_rag_router_intent`)
  - `conditional_parallel` 전략 계산(`sql_need`, `graph_need`, `tool_mode`, `target_agents`)
  - 브랜치 실행 및 fallback
  - `graph_rag_agent_execution` 호출
  - `graph_rag_answer` 최종 합성
  - `query_rewrite`, `query_normalization`, `citation_postprocess` 유틸리티 호출
  - `web fallback(google_news_rss)` 조건부 수행

## 2. 문서 개편
- 기존 `working-logic-multi-agent.md` 전면 교체.
- 구성:
  - 개략 흐름(High-Level) 다이어그램
  - 세부 흐름(라우팅/조건부 병렬/브랜치 내부/최종 합성) 다이어그램
  - 에이전트/모델/데이터소스/로그 매핑표
  - 모니터링 호출 체인
  - 스트리밍 API 동작 요약

## 3. 결과
- 현재 구현 코드와 문서 정합성 확보.
