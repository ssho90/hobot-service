# 21_phase5_snapshot_earnings_sync_and_lag_metrics

## 요청
- Phase 5 다음 단계 진행:
  - 월간 Universe/실적 감시 잡 완료 직후에도 equity projection 동기화 트리거 확장
  - projection lag metric + warning 정책 반영

## 반영 파일
- `/Users/ssho/project/hobot-service/hobot/service/macro_trading/scheduler.py`
- `/Users/ssho/project/hobot-service/hobot/service/macro_trading/indicator_health.py`
- `/Users/ssho/project/hobot-service/hobot/service/macro_trading/tests/test_scheduler_kr_top50_snapshot.py`
- `/Users/ssho/project/hobot-service/hobot/service/macro_trading/tests/test_scheduler_us_top50_snapshot.py`
- `/Users/ssho/project/hobot-service/hobot/service/macro_trading/tests/test_scheduler_kr_top50_earnings.py`
- `/Users/ssho/project/hobot-service/hobot/service/macro_trading/tests/test_scheduler_us_top50_earnings.py`
- `/Users/ssho/project/hobot-service/hobot/service/macro_trading/tests/test_scheduler_equity_projection_sync.py` (신규)
- `/Users/ssho/project/hobot-service/hobot/service/macro_trading/tests/test_indicator_health.py`
- `/Users/ssho/project/hobot-service/work-planning/chatbot-multi-agent/2026-02-20_1251/plan.md`

## 반영 내용
1. 월간 Universe 스냅샷 직후 Graph 동기화 확장
   - `run_kr_top50_monthly_snapshot_job`, `run_us_top50_monthly_snapshot_job`에 `sync_equity_projection_to_graph` 연동.
   - env 플래그 추가:
     - `KR_TOP50_SNAPSHOT_GRAPH_SYNC_ENABLED`
     - `US_TOP50_SNAPSHOT_GRAPH_SYNC_ENABLED`
     - `*_GRAPH_SYNC_INCLUDE_DAILY_BARS`
     - `*_GRAPH_SYNC_INCLUDE_EARNINGS`
     - `*_GRAPH_SYNC_ENSURE_SCHEMA`
2. 실적 감시 핫패스 직후 Graph 동기화 확장
   - `run_kr_top50_earnings_hotpath`, `run_us_top50_earnings_hotpath`에 `sync_equity_projection_to_graph` 연동.
   - env 플래그 추가:
     - `KR_TOP50_EARNINGS_GRAPH_SYNC_ENABLED`
     - `US_TOP50_EARNINGS_GRAPH_SYNC_ENABLED`
     - `*_GRAPH_SYNC_INCLUDE_UNIVERSE`
     - `*_GRAPH_SYNC_INCLUDE_DAILY_BARS`
     - `*_GRAPH_SYNC_ENSURE_SCHEMA`
3. projection lag metric + warning 정책 반영
   - `sync_equity_projection_to_graph`에서:
     - `max_trade_date`, `max_event_date`, `latest_graph_date`, `lag_hours` 계산
     - 임계치(`EQUITY_GRAPH_PROJECTION_WARN_LAG_HOURS`, `EQUITY_GRAPH_PROJECTION_FAIL_LAG_HOURS`) 기반 상태 판정
     - `macro_collection_run_reports`에 `EQUITY_GRAPH_PROJECTION_SYNC` 코드로 실행/상태 기록
4. admin indicators 연동
   - `indicator_health.py`에 `EQUITY_GRAPH_PROJECTION_SYNC` registry/query/note 포맷 추가
   - run health note에 lag/최신 그래프일/max_trade/max_event 표시

## 테스트
- `cd /Users/ssho/project/hobot-service/hobot && PYTHONPATH=. ../.venv/bin/python -m unittest service.macro_trading.tests.test_scheduler_kr_top50_snapshot service.macro_trading.tests.test_scheduler_us_top50_snapshot service.macro_trading.tests.test_scheduler_kr_top50_earnings service.macro_trading.tests.test_scheduler_us_top50_earnings service.macro_trading.tests.test_scheduler_equity_projection_sync service.macro_trading.tests.test_indicator_health` 통과
- `cd /Users/ssho/project/hobot-service/hobot && PYTHONPATH=. ../.venv/bin/python -m unittest service.macro_trading.tests.test_scheduler_kr_top50_ohlcv service.macro_trading.tests.test_scheduler_us_top50_ohlcv` 통과

## 결과
- Phase 5 잔여 과제(월간/실적 경로 동기화 확장 + lag 경고 자동화) 반영 완료.
- `/admin/indicators`에서 `EQUITY_GRAPH_PROJECTION_SYNC` 상태/지연 정보 확인 가능.
