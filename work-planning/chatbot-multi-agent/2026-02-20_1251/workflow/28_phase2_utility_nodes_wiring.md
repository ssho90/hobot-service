# 28) Phase 2 Utility Nodes Wiring

## 작업 배경
- 기존 GraphRAG 파이프라인은 `router_intent -> (domain agent branches) -> supervisor_answer` 구조였고,
  계획서의 `query_rewrite_utility`, `query_normalization_utility`, `citation_postprocess_utility`가 실제 호출되지 않았음.

## 🔴 에러 원인
- 유틸리티 모델 정책(`query_rewrite_utility`, `query_normalization_utility`, `citation_postprocess_utility`)은 선언되어 있었지만,
  `generate_graph_rag_answer()` 실행 경로에 유틸리티 노드를 호출하는 코드가 없어서 모니터링/토큰 집계/실행 결과가 누락됨.

## 구현 내용
1. `response_generator.py`에 유틸리티 노드 함수 3개 추가
- `_invoke_query_rewrite_utility()`
- `_invoke_query_normalization_utility()`
- `_invoke_citation_postprocess_utility()`

2. 유틸리티 적용 결과를 요청 실행에 반영
- rewrite 결과로 `effective_request.question` 갱신
- normalization 결과로 `effective_request.country_code/region_code/property_type/time_range` 갱신
- citation postprocess 결과로 citation 순서 재정렬

3. 모니터링/추적 로그 추가
- `graph_rag_query_rewrite`
- `graph_rag_query_normalization`
- `graph_rag_citation_postprocess`
- `context_meta`/`raw_model_output`에 `utility_execution`, `effective_request`, `utility_llm_enabled` 기록

4. 안전장치
- API 키 미존재/호출 실패 시 `degraded|skipped`로 처리하고 원본 흐름 유지
- supervisor LLM 주입 테스트 환경에서는 기본적으로 utility LLM 호출 비활성화

## 테스트
- 파일: `hobot/tests/test_phase_d_response_generator.py`
- 추가 테스트:
  - `test_generate_answer_applies_effective_request_from_utility_nodes`
  - `test_generate_answer_applies_citation_postprocess_order`
- 실행:
  - `cd hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
  - 결과: `Ran 53 tests ... OK (skipped=2)`

## 다음 작업
- Supervisor 단일 웹 fallback 노드(근거 부족/지연 시) 연결
- utility 노드별 feature flag를 admin에서 runtime 제어 가능하도록 확장
