# Phase 6 6차 작업 로그 - 주간 실패 원인/케이스 자동요약

## 1) 작업 목적
- Phase 6 주간 리포트가 "경고 여부"만 보여주는 수준을 넘어, 운영자가 즉시 원인을 파악할 수 있도록 실패 요약을 자동 포함한다.

## 2) 구현 내용
1. `hobot/service/macro_trading/scheduler.py`
   - `run_graph_rag_phase5_weekly_report` 집계 보강:
     - `top_failure_categories` (상위 실패 카테고리)
     - `top_failed_cases` (상위 실패 케이스)
   - 통과율 계산 보정:
     - `last_success_rate_pct`가 0/누락된 경우에도 `success_count/failure_count` 기반으로 pass rate 복원.

2. `hobot/service/macro_trading/indicator_health.py`
   - `GRAPH_RAG_PHASE5_WEEKLY_REPORT` note에 다음 자동 표기:
     - `Top실패 {category}:{count}`
     - `Top케이스 {case_id}:{count}`

3. 테스트
   - `hobot/service/macro_trading/tests/test_scheduler_graph_phase5_regression.py`
     - 주간 집계 결과에 top summary 포함 검증 추가.
     - 보정 pass rate(94.44%) 검증 추가.
   - `hobot/service/macro_trading/tests/test_indicator_health.py`
     - weekly note의 `Top실패/Top케이스` 노출 검증 추가.

## 3) 실DB 검증
- `run_graph_rag_phase5_weekly_report(days=7)` 수동 실행 성공.
- 결과 예시:
  - `avg_pass_rate_pct = 25.00`
  - `top_failure_categories = freshness_stale:2`
  - `top_failed_cases = Q1_US_SINGLE_STOCK_DROP_CAUSE_001, Q5_RATES_RISK_PATHWAY_001`
- `get_macro_indicator_health_snapshot()` 확인:
  - `GRAPH_RAG_PHASE5_WEEKLY_REPORT.note`에 Top실패/Top케이스 포함.

## 4) 운영 시사점
- 현재 주간 경고 핵심 원인은 `freshness_stale`이며, 품질 회복은 회귀 케이스의 최신성 보강(근거 문서 recency 관리)부터 우선 대응하는 것이 타당하다.
