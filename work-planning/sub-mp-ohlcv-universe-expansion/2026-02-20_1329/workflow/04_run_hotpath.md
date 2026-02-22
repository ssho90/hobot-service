# 04_run_hotpath

## 실행
- 권한 상승 실행으로 KR/US OHLCV 핫패스 수행
- lookback: 14일

## 결과 요약
- KR
  - target_stock_count: 56 (Top50 + Sub-MP extra 6)
  - sub_mp_extra_stock_codes: 261240, 453850, 357870, 133690, 360750, 458730
  - fetched_rows: 392
  - upserted_rows: 692
  - failed_stock_count: 0
- US
  - target_symbol_count: 50
  - sub_mp_extra_symbol_count: 0
  - fetched_rows: 400
  - upserted_rows: 800
  - failed_symbol_count: 0

## 참고
- `upserted_rows`는 MySQL `ON DUPLICATE KEY UPDATE`에서 update row가 2로 카운트될 수 있어 `fetched_rows`보다 클 수 있음.
- 현재 활성 Sub-MP 구성은 KR ETF 코드 위주이며, US로 분류되는 유효 심볼은 없음.

## DB 검증 (KR Sub-MP 6종목)
- `kr_top50_daily_ohlcv`에서 6개 종목 모두 최신 거래일 `2026-02-20` 확인
- 종목별 적재 row_count: 각 7건
