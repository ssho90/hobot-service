# Phase 6 3차: 주간 회귀 요약 리포트 자동화

## 1. 작업 목적
- Phase 6 잔여 항목 중 "주간 자동 리포트 산출"을 구현한다.
- 일별 회귀 실행 로그를 주간 운영 관점으로 집계해 품질 추세를 모니터링한다.

## 2. 반영 내용
1. 주간 집계 실행 함수
   - 파일: `hobot/service/macro_trading/scheduler.py`
   - 함수: `run_graph_rag_phase5_weekly_report(days=7)`
   - 집계 항목:
     - 실행 건수/성공 건수/경고 건수
     - 평균/최저/최고 pass rate
     - `routing_mismatch_count`
     - `tool_mode_counts`, `target_agent_counts`, `freshness_status_counts`
     - 평균 `structured_citation_count` 추세
   - 상태 판정:
     - `GRAPH_RAG_PHASE5_WEEKLY_*` 임계치 환경변수 기준으로 `healthy|warning` 결정
   - 저장:
     - `GRAPH_RAG_PHASE5_WEEKLY_REPORT` job_code로 `macro_collection_run_reports`에 기록

2. 주간 스케줄 연결
   - 함수: `setup_graph_rag_phase5_weekly_report_scheduler()`
   - 기본 스케줄:
     - 매주 월요일 08:20 (`GRAPH_RAG_PHASE5_WEEKLY_REPORT_SCHEDULE_DAY/TIME`)
   - 등록 경로:
     - `start_news_scheduler_thread`
     - `start_all_schedulers`

3. 주간 알림 옵션
   - `GRAPH_RAG_PHASE5_WEEKLY_ALERT_ENABLED` (기본 off)
   - `GRAPH_RAG_PHASE5_WEEKLY_ALERT_ONLY_ON_WARNING`
   - `GRAPH_RAG_PHASE5_WEEKLY_ALERT_CHANNEL`

## 3. 테스트
1. `PYTHONPATH=. ../.venv/bin/python -m unittest service.macro_trading.tests.test_scheduler_graph_phase5_regression`
   - 주간 집계 정상 상태 케이스
   - `routing_mismatch` 경고 상태 케이스
   - 주간 스케줄 등록 케이스

테스트 통과.

## 4. 다음 작업
1. 주간 Slack 알림 포맷에서 top failure 케이스 샘플(질문/case_id) 포함 강화.
2. 운영 대시보드에 `GRAPH_RAG_PHASE5_WEEKLY_REPORT` 카드 연결.
