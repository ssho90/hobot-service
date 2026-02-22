# 20_phase5_equity_projection_loader_and_hotpath_sync

## 요청
- 다음 Phase 진행: Phase 5(Neo4j 주식 Projection) 착수.
- KR/US OHLCV 수집 완료 직후 Graph projection 동기화가 자동으로 실행되도록 연결.

## 반영 파일
- `/Users/ssho/project/hobot-service/hobot/service/graph/equity_loader.py` (신규)
- `/Users/ssho/project/hobot-service/hobot/service/graph/__init__.py`
- `/Users/ssho/project/hobot-service/hobot/service/macro_trading/scheduler.py`
- `/Users/ssho/project/hobot-service/hobot/tests/test_phase5_equity_projection.py` (신규)
- `/Users/ssho/project/hobot-service/hobot/service/macro_trading/tests/test_scheduler_kr_top50_ohlcv.py`
- `/Users/ssho/project/hobot-service/hobot/service/macro_trading/tests/test_scheduler_us_top50_ohlcv.py`

## 반영 내용
1. `EquityProjectionLoader` 구현
   - RDB 원천 읽기:
     - `kr_top50_universe_snapshot`, `us_top50_universe_snapshot`
     - `kr_top50_daily_ohlcv`, `us_top50_daily_ohlcv`
     - `kr_corporate_disclosures`, `us_corporate_earnings_events`
   - Neo4j 투영:
     - `Company`
     - `EquityUniverseSnapshot`
     - `EquityDailyBar`
     - `EarningsEvent`
   - 관계 방향 고정:
     - `Company-[:IN_UNIVERSE]->EquityUniverseSnapshot`
     - `Company-[:HAS_DAILY_BAR]->EquityDailyBar`
     - `Company-[:HAS_EARNINGS_EVENT]->EarningsEvent`
2. 스키마 제약/인덱스 자동 보장
   - `Company.security_id`, `EquityUniverseSnapshot.snapshot_key`, `EquityDailyBar.bar_key`, `EarningsEvent.event_key` 유니크 제약.
3. 스케줄러 이벤트 기반 연동
   - `sync_equity_projection_to_graph(...)` helper 추가.
   - `run_kr_top50_ohlcv_hotpath` / `run_us_top50_ohlcv_hotpath` 완료 후 projection 동기화 자동 호출.
   - 환경변수 제어 추가:
     - `KR_TOP50_OHLCV_GRAPH_SYNC_ENABLED`
     - `US_TOP50_OHLCV_GRAPH_SYNC_ENABLED`
     - `*_GRAPH_SYNC_INCLUDE_UNIVERSE`
     - `*_GRAPH_SYNC_INCLUDE_EARNINGS`
     - `*_GRAPH_SYNC_ENSURE_SCHEMA`

## 테스트
- `PYTHONPATH=. ../.venv/bin/python tests/test_phase5_equity_projection.py` 통과.
- `PYTHONPATH=. ../.venv/bin/python service/macro_trading/tests/test_scheduler_kr_top50_ohlcv.py` 통과.
- `PYTHONPATH=. ../.venv/bin/python service/macro_trading/tests/test_scheduler_us_top50_ohlcv.py` 통과.
- `PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py` 통과.
- `GRAPH_RAG_REQUIRE_DB_TESTS=1 PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py` 통과.

## 결과
- Phase 5의 첫 구현 단위(주식 projection loader + OHLCV 완료 이벤트 기반 동기화) 완료.
- 남은 작업: 월간 universe/실적 감시 잡 완료 시점까지 projection 트리거 확장, RDB->Neo4j lag metric + 경고 정책 연결.

