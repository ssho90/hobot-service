# 02_implementation

## 변경 파일
- `hobot/service/macro_trading/scheduler.py`
- `hobot/service/macro_trading/collectors/kr_corporate_collector.py`
- `hobot/service/macro_trading/collectors/us_corporate_collector.py`
- `hobot/service/macro_trading/tests/test_scheduler_kr_top50_ohlcv.py`
- `hobot/service/macro_trading/tests/test_scheduler_us_top50_ohlcv.py`
- `hobot/service/macro_trading/tests/test_kr_corporate_collector.py`
- `hobot/service/macro_trading/tests/test_us_corporate_collector.py`

## 핵심 구현
1. Scheduler
- 활성 Sub-MP 구성 ticker 조회 helper 추가
  - `_load_active_sub_mp_tickers()`
  - `_resolve_country_sub_mp_symbols(country_code=KR|US)`
- KR/US OHLCV hotpath에 Sub-MP 병합 옵션 추가
  - `include_sub_mp_universe` (기본 true)
  - `sub_mp_max_*_count` (기본 150)
- collector 호출 시 `extra_stock_codes`/`extra_symbols` 전달
- 실행 결과에 `sub_mp_universe_enabled`, `sub_mp_extra_*` 메타 포함

2. Collector
- KR: `resolve_top50_stock_codes_for_ohlcv`/`collect_top50_daily_ohlcv`에 `extra_stock_codes` 추가
- US: `resolve_top50_symbols_for_ohlcv`/`collect_top50_daily_ohlcv`에 `extra_symbols` 추가
- Top50 기본 해상 결과 뒤에 extra 유니버스 병합(dedup)
- summary에 `extra_*_count`, `extra_*` 포함

3. Env 확장
- KR
  - `KR_TOP50_OHLCV_INCLUDE_SUB_MP_UNIVERSE` (기본 1)
  - `KR_TOP50_OHLCV_SUB_MP_MAX_STOCK_COUNT` (기본 150)
- US
  - `US_TOP50_OHLCV_INCLUDE_SUB_MP_UNIVERSE` (기본 1)
  - `US_TOP50_OHLCV_SUB_MP_MAX_SYMBOL_COUNT` (기본 150)
