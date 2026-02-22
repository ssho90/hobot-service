# 02_implementation

## 반영 내용
- US 수집기(`us_corporate_collector.py`)
  - `us_top50_daily_ohlcv` 테이블 생성 로직 추가
  - Top50 대상 심볼 해석 메서드 추가
  - yfinance 일봉 OHLCV 수집 메서드 추가
  - OHLCV UPSERT 메서드 추가
  - `collect_top50_daily_ohlcv` 엔드투엔드 수집 메서드 추가

- KR 수집기(`kr_corporate_collector.py`)
  - `kr_top50_daily_ohlcv` 테이블 생성 로직 추가
  - Top50 대상 종목코드 해석 메서드 추가(스냅샷 우선, 필요 시 Naver fallback)
  - 시장별 yfinance suffix(`.KS`, `.KQ`) 해석 로직 추가
  - yfinance 일봉 OHLCV 수집 메서드 추가
  - OHLCV UPSERT 메서드 추가
  - `collect_top50_daily_ohlcv` 엔드투엔드 수집 메서드 추가

- 스케줄러(`scheduler.py`)
  - KR/US OHLCV 핫패스 함수 추가
    - `run_kr_top50_ohlcv_hotpath`
    - `run_us_top50_ohlcv_hotpath`
  - env 래퍼 추가
    - `run_kr_top50_ohlcv_hotpath_from_env`
    - `run_us_top50_ohlcv_hotpath_from_env`
  - 스케줄 등록 함수 추가
    - `setup_kr_top50_ohlcv_scheduler`
    - `setup_us_top50_ohlcv_scheduler`
  - `start_all_schedulers()`에 OHLCV 스케줄 설정 단계 연결
