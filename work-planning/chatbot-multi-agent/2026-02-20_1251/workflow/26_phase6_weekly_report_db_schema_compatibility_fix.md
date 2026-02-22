# Phase 6 5차 작업 로그 - Weekly Report DB 스키마 호환 수정 및 실DB 검증

## 1) 배경
- `run_graph_rag_phase5_weekly_report(days=7)` 수동 실행 중 운영 DB에서 즉시 실패.

## 2) 진단
- 최초 에러: `Unknown column 'run_success' in 'field list'`.
- `DESCRIBE macro_collection_run_reports` 결과 확인:
  - 존재 컬럼: `run_count`, `success_run_count`, `failed_run_count`, `success_count`, `failure_count`, `last_success_rate_pct`, `last_status`, `details_json`, `report_date`, `updated_at` 등.
  - 미존재 컬럼: `run_success`, `details`.

🔴 **에러 원인:** `scheduler.py`의 주간 집계 SQL이 운영 테이블 스키마(`macro_collection_run_reports`)와 불일치하여, 존재하지 않는 컬럼(`run_success`, `details`)을 조회하고 있었다.

## 3) 수정 내용
1. `hobot/service/macro_trading/scheduler.py`
   - 주간 집계 조회 SQL을 운영 스키마 기준으로 교체.
     - `run_success` -> `run_count/success_run_count/failed_run_count`
     - `details` -> `details_json`
     - `created_at` 기준 조회 -> `report_date` 기준 조회
   - 집계 계산을 `sum(run_count)` 기반으로 보정.
   - `details_json` 파싱 + 하위 호환(`details`) fallback 유지.

2. 테스트 재검증
   - `service.macro_trading.tests.test_scheduler_graph_phase5_regression` 통과.
   - `service.macro_trading.tests.test_indicator_health` 통과.

## 4) 실DB 검증
1. 수동 실행 결과
   - `run_graph_rag_phase5_weekly_report.__wrapped__(days=7)` 정상 완료.
   - 예시 결과:
     - `status=warning`
     - `status_reason=avg_pass_rate:0.00<85.00`
     - `total_runs=4`

2. `/admin/indicators` 데이터 경로 검증
   - `get_macro_indicator_health_snapshot()`에서 `GRAPH_RAG_PHASE5_WEEKLY_REPORT` row 조회 확인.
   - note에 주간 집계/평균통과율/routing mismatch/평균 structured citation/상태사유 표시 확인.

## 5) 결론
- Phase 6 주간 회귀 집계는 운영 DB 스키마와 호환되도록 수정 완료.
- 스케줄 실행 및 운영 화면(/admin/indicators) 노출 경로 모두 실데이터로 검증 완료.
