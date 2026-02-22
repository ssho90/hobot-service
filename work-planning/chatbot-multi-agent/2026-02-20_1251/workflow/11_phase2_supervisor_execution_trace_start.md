# 11_phase2_supervisor_execution_trace_start

## 요청
- "시작해" 지시에 따라 Phase 2(Supervisor 실행기 연결) 구현 착수.

## 반영 파일
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/response_generator.py`
- `/Users/ssho/project/hobot-service/hobot/tests/test_phase_d_response_generator.py`
- `/Users/ssho/project/hobot-service/work-planning/chatbot-multi-agent/2026-02-20_1251/plan.md`

## 반영 내용
1. `supervisor_execution` 실행 트레이스 추가
- `_build_supervisor_execution_trace()` 신설.
- `query_route`의 `sql_need/graph_need/tool_mode/target_agents`를 기반으로
  - 실행 정책(`conditional_parallel`)
  - 브랜치 계획(`sql`/`graph`)
  - dispatch mode(`single`/`parallel`/`skip`)
  를 계산.

2. 응답/저장 메타 연결
- `context_meta.supervisor_execution` 추가.
- `raw_model_output.supervisor_execution` 추가.
- analysis run 저장 metadata에 `supervisor_execution` 추가.
- Top50 scope guard 및 cached response 경로에도 동일 메타 반영.

3. 테스트 추가
- `test_supervisor_execution_trace_parallel_for_us_single_stock`
- `test_supervisor_execution_trace_single_for_macro_summary`

## 검증
- 실행 명령:
  - `cd /Users/ssho/project/hobot-service/hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
- 결과:
  - `Ran 35 tests ... OK`
  - 로컬 환경 특성상 MySQL 미연결 경고 로그는 발생했으나 테스트는 통과.

## 현재 판단
- Phase 2는 "실행 트레이스 연결"까지 완료되어 `진행중`.
- 다음 구현 포인트는 `supervisor_execution`을 실제 agent executor 호출(단일/병렬 분기)로 연결하는 단계.
