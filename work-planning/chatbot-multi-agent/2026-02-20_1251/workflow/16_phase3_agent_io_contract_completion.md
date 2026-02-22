# Phase 3 완료 기록 - Agent I/O 계약 및 Citation 이중화

- 일시: 2026-02-20
- 범위: `citations[]`(문서) / `structured_citations[]`(정형) 분리 계약을 코드 경로 전체에 적용

## 변경 파일
- `hobot/service/graph/rag/response_generator.py`

## 구현 내용
1. 응답 스키마에 `structured_citations` 필드 정식 반영.
2. `supervisor_execution.execution_result.branch_results.sql.agent_runs[*].tool_probe`에서 SQL 실행 근거를 추출해 `structured_citations` 자동 생성.
3. `analysis_run` 저장 메타(`run_metadata`) 및 캐시 복원 경로에 `structured_citations` 포함.
4. `context_meta`에 `structured_citation_count` 집계값 반영.

## 테스트
- `cd hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
  - 결과: `Ran 42 tests ... OK (skipped=2)`
- `cd hobot && GRAPH_RAG_REQUIRE_DB_TESTS=1 PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
  - 결과: `Ran 42 tests ... OK`

## 비고
- DB/Neo4j 연결 경고 로그는 테스트 더블/환경 차이로 발생했으나, 검증 assertions는 모두 통과.
