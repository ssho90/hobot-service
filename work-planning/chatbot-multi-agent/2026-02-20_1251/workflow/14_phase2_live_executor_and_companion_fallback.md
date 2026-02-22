# Phase 2 4차 구현: Live Tool Probe + Companion Fallback

## 작업 목적
- Phase 2 미완료 항목이던 "실제 SQL/Graph executor 연결"을 stub 단계에서 한 단계 진전시켜, 각 agent 실행 시 도구 상태를 실제 probe 결과로 반환하도록 개선.
- `tool_mode=single`에서 주 브랜치 실패/불충분 신호가 있으면 보조 브랜치를 1회 자동 호출하는 companion fallback 로직 구현.

## 구현 내용
1. Agent 공통 도구 probe 모듈 추가
- 파일: `hobot/service/graph/rag/agents/tool_probe.py`
- 추가 함수:
  - `run_sql_probe(agent_name)`
  - `run_graph_probe(agent_name, context_meta)`
  - `detect_companion_branch(branch, probe)`
- 동작:
  - SQL: agent별 대표 테이블의 존재/row_count/latest_date probe
  - Graph: context `counts` 기반 상태 확인 + (옵션) live ping
  - probe 상태가 `ok`가 아니면 companion branch 추천(`sql -> graph`, `graph -> sql`)

2. Agent 실행 결과 확장 (Macro/Equity/RealEstate/Ontology)
- 파일:
  - `hobot/service/graph/rag/agents/macro_agent.py`
  - `hobot/service/graph/rag/agents/equity_agent.py`
  - `hobot/service/graph/rag/agents/real_estate_agent.py`
  - `hobot/service/graph/rag/agents/ontology_agent.py`
- 변경:
  - branch별 `tool_probe` 결과 포함
  - `needs_companion_branch`, `companion_branch` 필드 포함
  - 상태를 `executed/degraded`로 구분

3. Supervisor single 모드 companion fallback 구현
- 파일: `hobot/service/graph/rag/response_generator.py`
- 변경:
  - `_execute_supervisor_plan`에서 single 모드 시 주 브랜치 결과를 검사
  - `needs_companion_branch=true`면 비활성 보조 브랜치를 1회 실행
  - `execution_result`에 `fallback_used`, `fallback_reason` 추가

4. 테스트 추가
- 파일: `hobot/tests/test_phase_d_response_generator.py`
- 추가 테스트:
  - `test_supervisor_single_mode_runs_companion_fallback_once`
- 검증:
  - single 모드에서 graph -> sql companion fallback 1회 수행
  - `fallback_used/fallback_reason` 반영 확인

## 테스트 실행
- 명령:
  - `cd hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
- 결과:
  - `Ran 38 tests ... OK`
  - 참고: 현재 로컬 환경은 MySQL 미연결로 probe/모니터링 경고 로그가 출력되지만 테스트는 통과.

## 잔여 작업 (Phase 2)
- 현재는 "도구 연결 + 상태/fallback 오케스트레이션" 수준.
- 다음 단계로 agent별 도메인 SQL/Cypher 템플릿(실제 질의) 연결 필요:
  - Macro: 지표 최신값/변화율 템플릿
  - Equity: OHLCV/실적 템플릿
  - RealEstate: 실거래/요약 템플릿
  - Ontology: path/query 템플릿
