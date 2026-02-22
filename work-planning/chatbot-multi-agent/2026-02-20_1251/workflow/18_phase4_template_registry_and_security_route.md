# Phase 4 2차 착수 기록 - 템플릿 레지스트리 분리 + security_id 라우팅 확장

- 일시: 2026-02-20
- 목표:
  1. 도메인별 SQL/Cypher 템플릿 정의를 실행기 코드에서 분리
  2. 라우팅 결과에 `matched_security_ids`를 추가해 식별자 표준 경로를 강화

## 변경 파일
- `hobot/service/graph/rag/templates/__init__.py` (신규)
- `hobot/service/graph/rag/templates/macro_query_templates.py` (신규)
- `hobot/service/graph/rag/templates/equity_query_templates.py` (신규)
- `hobot/service/graph/rag/templates/real_estate_query_templates.py` (신규)
- `hobot/service/graph/rag/templates/ontology_query_templates.py` (신규)
- `hobot/service/graph/rag/agents/live_executor.py`
- `hobot/service/graph/rag/response_generator.py`
- `hobot/tests/test_phase_d_response_generator.py`

## 구현 내용
1. 템플릿 레지스트리 분리
   - 기존 `live_executor.py` 내 하드코딩된 `SQL_TEMPLATE_SPECS`/`GRAPH_TEMPLATE_SPECS`를 도메인별 파일로 분리.
   - 실행기는 `service.graph.rag.templates`에서 레지스트리만 import 하도록 변경.

2. 라우팅 보강 (`matched_security_ids`)
   - `query_route`에 `matched_security_ids` 필드 추가.
   - US 단일종목 강제 라우팅 시 `US:{ticker}`를 함께 기록.
   - `GraphRagAnswerRequest.to_context_request()`에서 `matched_symbols`가 비어 있으면 `matched_security_ids`를 심볼(native_code)로 복원해 `focus_symbols`로 전달.

3. 식별자 파생 로직 정합
   - `_derive_matched_security_ids()` 추가:
     - `matched_symbols` + `selected_type` + `requested_country_code` 기반으로 `security_id` 생성.
     - equity 문맥일 때만 생성하도록 제한.

## 테스트
- `cd hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase4_security_id.py`
  - 결과: `Ran 5 tests ... OK`
- `cd hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
  - 결과: `Ran 43 tests ... OK (skipped=2)`
- `cd hobot && GRAPH_RAG_REQUIRE_DB_TESTS=1 PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
  - 결과: `Ran 43 tests ... OK`

## 비고
- 테스트 로그의 MySQL/Neo4j 경고는 테스트 더블 및 sandbox 제약에 따른 노이즈이며, assertions는 모두 통과.
