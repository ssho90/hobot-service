# 19_phase4_cypher_direction_contract_completion

## 요청
- Phase 4(식별자/쿼리 템플릿 표준화) 남은 항목인 Ontology Cypher 방향성 강제 계약을 코드에 반영.

## 반영 파일
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/templates/cypher_schema_prompt.py` (신규)
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/agents/ontology_agent.py`
- `/Users/ssho/project/hobot-service/hobot/tests/test_phase4_ontology_cypher_prompt.py` (신규)

## 반영 내용
1. 방향 포함 스키마 문자열(`SCHEMA_DIRECTION_LINES`)과 few-shot(`CYPHER_DIRECTION_FEW_SHOTS`)을 고정 주입하는 프롬프트 계약 구현.
2. `prompt_version=ontology.cypher.schema_prompt.v1`를 계약 메타에 포함.
3. `validate_cypher_direction(query)` 추가:
   - `HAS_DAILY_BAR`, `HAS_EARNINGS_EVENT`, `ABOUT_THEME` 역방향 패턴 탐지.
4. Ontology agent graph branch 결과에 검증 결과(`cypher_direction_validation`)와 프롬프트 버전(`schema_prompt_version`) 기록.

## 테스트
- `PYTHONPATH=. ../.venv/bin/python tests/test_phase4_ontology_cypher_prompt.py` 통과.
- `PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py` 통과.
- `GRAPH_RAG_REQUIRE_DB_TESTS=1 PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py` 통과.

## 결과
- Phase 4의 “Cypher 방향성 스키마 문자열 + few-shot 고정 주입” 항목 완료.
- 방향 오류로 인한 empty query 리스크를 실행 전/후 메타에서 추적 가능.

