# Domain Golden Set Coverage Extension (2026-02-20)

## 1) 목적
- Phase 6 미비점 중 핵심 잔여 항목인 "agent별 single/parallel 회귀 커버리지 부족"을 해소한다.
- 단순 `tool_mode` 검증에서 더 나아가, 케이스별 기대 agent가 실제 라우팅 결과에 포함되는지까지 회귀로 검증한다.

## 2) 변경 사항
1. 회귀 케이스 스키마 확장
   - 파일: `hobot/service/graph/monitoring/phase5_regression.py`
   - 추가 필드:
     - `GoldenQuestionCase.expected_target_agents: List[str]`
   - 평가 로직:
     - 실제 `target_agents`가 `expected_target_agents`를 포함하지 않으면 `routing_mismatch` 실패로 집계.
     - 결과 payload에 `expected_target_agents`, `missing_target_agents` 추가.

2. 기본 골든셋 확장
   - 파일: `hobot/service/graph/monitoring/golden_sets/phase5_q1_q6_v1.json`
   - 기존 6개 케이스에 `expected_target_agents`를 명시.
   - 신규 8개 케이스 추가:
     - `AGENT_MACRO_SINGLE_001`, `AGENT_MACRO_PARALLEL_001`
     - `AGENT_EQUITY_SINGLE_001`, `AGENT_EQUITY_PARALLEL_001`
     - `AGENT_REAL_ESTATE_SINGLE_001`, `AGENT_REAL_ESTATE_PARALLEL_001`
     - `AGENT_ONTOLOGY_SINGLE_001`, `AGENT_ONTOLOGY_PARALLEL_001`
   - 결과: 기본 골든셋에서 각 도메인 agent의 single/parallel 커버리지 정의 완료.

3. 테스트 보강
   - 파일: `hobot/tests/test_phase5_golden_regression.py`
   - 추가 검증:
     - 기본 골든셋이 domain agent 4종의 `single`/`parallel` 커버리지를 모두 포함하는지 검증.
     - `expected_target_agents` 불일치가 `routing_mismatch`로 실패 처리되는지 검증.

## 3) 실행 검증 결과
- 통과:
  - `hobot/tests/test_phase5_golden_regression.py`
  - `hobot/tests/test_phase5_regression_batch_runner.py`
  - `hobot/service/macro_trading/tests/test_scheduler_graph_phase5_regression.py`
  - `hobot/tests/test_phase_d_response_generator.py` (`GRAPH_RAG_REQUIRE_DB_TESTS=1`)

## 4) 남은 작업
1. 확장된 골든셋을 운영 환경에서 실제 배치 회귀로 실행해 pass/fail 분포를 수집.
2. 주간 KPI 리포트에 latency 계열 지표(p95 단일/복합) 자동 집계를 추가해 6장 KPI와 일치시킨다.
