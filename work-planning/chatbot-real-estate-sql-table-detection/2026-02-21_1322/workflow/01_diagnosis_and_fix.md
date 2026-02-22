# 01 Diagnosis and Fix

## 진단
- `llm_usage_logs`의 `graph_rag_agent_execution` 로그에서 real_estate SQL 브랜치가 지속적으로
  `sql_template_table_not_found`로 실패함을 확인.
- 동일 DB에서 `kr_real_estate_monthly_summary`, `kr_real_estate_transactions` 테이블과 데이터는 존재.
- 원인: `live_executor.py`에서 information_schema 조회 결과를 `row.get("table_name")`,
  `row.get("column_name")`로 읽는데, 실제 DictCursor 키가 `TABLE_NAME`, `COLUMN_NAME`으로 반환되어
  탐지 실패.

## 수정
- `service/graph/rag/agents/live_executor.py`
  - `_row_get_ci`(case-insensitive row getter) 추가
  - `_fetch_existing_tables`, `_fetch_table_columns`를 대소문자 무관 읽기로 변경

## 검증
- 신규 테스트 추가: `tests/test_phase_d_live_executor.py`
  - uppercase 키 반환 시 테이블/컬럼 탐지 성공 검증
- 실행:
  - `PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_live_executor.py` -> OK
  - `PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_real_estate_agent.py` -> OK
- DB 스모크:
  - `_execute_sql_template(agent_name="real_estate_agent")` 결과 `status=ok`, `row_count=5` 확인
