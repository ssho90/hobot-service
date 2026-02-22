- 구현 파일
  - hobot/service/macro_trading/collectors/us_corporate_collector.py
  - hobot/service/macro_trading/collectors/kr_corporate_collector.py
  - hobot/service/macro_trading/scheduler.py
  - hobot/service/macro_trading/tests/test_us_corporate_collector.py
  - hobot/service/macro_trading/tests/test_kr_corporate_collector.py
  - hobot/service/macro_trading/tests/test_scheduler_kr_top50_ohlcv.py
  - hobot/service/macro_trading/tests/test_scheduler_us_top50_ohlcv.py

- 핵심 변경점
  1) 연속성 기본값 상수 추가
     - US: DEFAULT_US_TOP50_OHLCV_CONTINUITY_DAYS = 120
     - KR: DEFAULT_KR_TOP50_OHLCV_CONTINUITY_DAYS = 120

  2) 스냅샷 윈도우 유니버스 로더 추가
     - US: load_top50_symbols_in_snapshot_window(...)
     - KR: load_top50_stock_codes_in_snapshot_window(...)
     - 공통: snapshot_date 범위 + rank_position <= top_limit 조건으로 최근 스냅샷 등장 종목 집합 로드

  3) OHLCV 타깃 해상도(Resolver) 확장
     - resolve_top50_*_for_ohlcv에 continuity_days/reference_end_date 파라미터 추가
     - 타깃 = 최신 Top50 + 최근 continuity_days 스냅샷 등장 종목(중복 제거)
     - explicit 입력(symbols/stock_codes)이 있으면 기존처럼 explicit 우선

  4) collect_top50_daily_ohlcv 확장
     - continuity_days 파라미터 추가
     - 결과 요약에 continuity 관련 필드 추가
       - continuity_days / continuity_enabled
       - latest_snapshot_*_count
       - continuity_extra_*_count, continuity_extra_* 목록

  5) 스케줄러 연동
     - run_*_top50_ohlcv_hotpath 및 from_env에 continuity_days 전달
     - 신규 env
       - KR_TOP50_OHLCV_CONTINUITY_DAYS
       - US_TOP50_OHLCV_CONTINUITY_DAYS

  6) 장마감 이후 기본 스케줄 시각 변경
     - KR_TOP50_OHLCV_SCHEDULE_TIME 기본: 16:20
     - US_TOP50_OHLCV_SCHEDULE_TIME 기본: 07:10 (KST 기준)
