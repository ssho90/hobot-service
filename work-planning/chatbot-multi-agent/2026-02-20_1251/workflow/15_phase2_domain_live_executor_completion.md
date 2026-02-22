# Phase 2 5차 구현: 도메인 Live SQL/Cypher 템플릿 실행기 연결

## 작업 목적
- Phase 2의 마지막 미완료 항목인 "도메인별 실제 SQL/Cypher 템플릿 실행기"를 연결해, probe/stub 수준을 넘어 실제 쿼리 실행 경로를 확보한다.

## 구현 내용
1. Live executor 신규 추가
- 파일: `hobot/service/graph/rag/agents/live_executor.py`
- 추가:
  - `execute_live_tool(...)`
  - agent별 SQL 템플릿 스펙(`SQL_TEMPLATE_SPECS`)
  - agent별 Graph 템플릿 스펙(`GRAPH_TEMPLATE_SPECS`)
- 동작:
  - SQL: 테이블 존재/컬럼 메타 자동 탐지 후 템플릿 쿼리 실행
  - Graph: context counts 우선 활용, 필요 시 Cypher 실행
  - 장애 시 `degraded` 상태 반환 + fast-fail window로 과도한 재시도 억제

2. 도메인 agent를 live executor 우선으로 전환
- 파일:
  - `hobot/service/graph/rag/agents/macro_agent.py`
  - `hobot/service/graph/rag/agents/equity_agent.py`
  - `hobot/service/graph/rag/agents/real_estate_agent.py`
  - `hobot/service/graph/rag/agents/ontology_agent.py`
- 변경:
  - 기존 `run_sql_probe/run_graph_probe` direct 호출 제거
  - `execute_live_tool` 기반 `tool_probe` 생성
  - `needs_companion_branch`/`companion_branch` 계약 유지

3. Phase 문서 상태 반영
- 파일: `work-planning/chatbot-multi-agent/2026-02-20_1251/plan.md`
- 반영:
  - Phase 2 상태를 `완료`로 갱신
  - Done 항목에 "Phase 2 5차" 추가
  - Phase 2 섹션 진행 현황 업데이트

## 테스트 실행
1. 기본 회귀
- 명령: `cd hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
- 결과: `Ran 40 tests ... OK (skipped=2)` (sandbox 환경)

2. DB 강제 모드 회귀
- 명령: `cd hobot && GRAPH_RAG_REQUIRE_DB_TESTS=1 PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
- 결과: `Ran 40 tests ... OK` (터널 DB 환경)

## 비고
- 현재 `structured_citations` 강제 분리는 Phase 3 범위다.
- Phase 2는 "실행 경로 연결" 기준으로 종료하고, 다음 우선순위는 Phase 3이다.
