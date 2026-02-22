# 08_supervisor_routing_flags_skeleton

## 요청
- Supervisor 라우팅에 `sql_need`, `graph_need` 스켈레톤을 코드로 반영하고 테스트까지 확인.

## 반영 파일
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/response_generator.py`
- `/Users/ssho/project/hobot-service/hobot/tests/test_phase_d_response_generator.py`

## 반영 내용 요약
1. 라우팅 전략 계산 헬퍼 추가
- `_derive_conditional_parallel_strategy()` 신설.
- 입력: `question`, `selected_type`, `selected_question_id`.
- 출력: `sql_need`, `graph_need`, `tool_mode(single|parallel)`, `target_agents[]`.

2. 타깃 에이전트 판정 로직 추가
- `_resolve_target_agents()`에서 질의 의도(주식/부동산/거시/온톨로지) 기준으로 에이전트 목록을 생성.
- 현재 스켈레톤 에이전트 키:
  - `macro_economy_agent`
  - `equity_analyst_agent`
  - `real_estate_agent`
  - `ontology_master_agent`

3. `query_route` 반환 스키마 확장
- `_route_query_type_multi_agent()` 반환값에 아래 필드 추가:
  - `sql_need`
  - `graph_need`
  - `tool_mode`
  - `target_agents`
- 기존 필드(`selected_type`, `agents`, `aggregated_scores`, `matched_symbols` 등)는 유지.

4. 테스트 보강
- `test_query_route_sets_parallel_flags_for_us_single_stock`
- `test_query_route_sets_single_flags_for_macro_summary`
- `test_query_route_sets_parallel_flags_for_indicator_lookup`

## 검증
- 실행 명령:
  - `cd /Users/ssho/project/hobot-service/hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
- 결과:
  - `Ran 33 tests ... OK`
  - 테스트는 통과했으며, 로컬 MySQL 미연결 경고 로그는 기존 테스트 환경 특성으로 지속 출력됨.
