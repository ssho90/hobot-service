# 01_init

- 요청: Top50 일봉 OHLCV 수집 범위를 Sub-MP 세부 종목까지 확장
- 확인 결과:
  - KR/US OHLCV는 `collect_top50_daily_ohlcv` 경로만 사용
  - 재무/실적 수집에는 `grace_universe`가 있으나 OHLCV에는 부재
  - Sub-MP 구성 종목은 `sub_portfolio_models` + `sub_portfolio_compositions`에서 관리됨
- 구현 결정:
  - Scheduler에서 Sub-MP ticker 조회/국가별 정규화 후 collector에 `extra_*`로 전달
  - Collector는 Top50 타깃 + extra 타깃 병합
