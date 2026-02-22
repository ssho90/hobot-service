# Phase 6 4차 작업 로그 - Weekly Report Health 연동 및 Slack 스킵

## 1) 작업 배경
- 사용자 지시: `slack 알림은 스킵`
- Phase 6 주간 회귀 집계(`GRAPH_RAG_PHASE5_WEEKLY_REPORT`)를 `/admin/indicators`에서 직접 확인 가능하도록 확장 필요.

## 2) 반영 내용
1. `hobot/service/macro_trading/scheduler.py`
   - `run_graph_rag_phase5_weekly_report`에서 Slack 알림 분기 제거.
   - 주간 집계는 run report 저장/상태 판정(`healthy|warning`)만 수행하도록 단순화.

2. `hobot/service/macro_trading/indicator_health.py`
   - `GRAPH_RAG_PHASE5_WEEKLY_REPORT`를 Graph registry에 추가.
   - `RUN_HEALTH_JOB_CODES`에 포함하여 실행상태 기반 health 판정 적용.
   - `macro_collection_run_reports` 조회 query_map에 해당 job_code 추가.
   - indicators note에 주간 핵심 지표 표시 추가:
     - 주간 집계 횟수
     - 경고/실패 횟수
     - 평균 통과율
     - routing mismatch 건수
     - 평균 structured citation 수
     - 상태 사유

3. `hobot/service/macro_trading/tests/test_indicator_health.py`
   - registry 포함 검증에 `GRAPH_RAG_PHASE5_WEEKLY_REPORT` 추가.
   - 주간 리포트 note 포맷 검증 테스트 신규 추가.

4. `work-planning/chatbot-multi-agent/2026-02-20_1251/plan.md`
   - Phase 6 상태/완료 항목(19번) 업데이트.

## 3) 기대 효과
- Slack 없이도 `/admin/indicators`에서 주간 회귀 품질 지표를 바로 확인 가능.
- run report 기반 운영 추적 경로가 단일화되어 장애/품질 이슈 추적성이 개선됨.
