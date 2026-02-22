# 03_validation

## 실행 명령
- `PYTHONPATH=. /Users/ssho/project/hobot-service/.venv/bin/python -m unittest service.macro_trading.tests.test_us_corporate_collector service.macro_trading.tests.test_kr_corporate_collector service.macro_trading.tests.test_scheduler_us_top50_ohlcv service.macro_trading.tests.test_scheduler_kr_top50_ohlcv service.macro_trading.tests.test_scheduler_us_top50_financials service.macro_trading.tests.test_scheduler_us_top50_earnings`

## 결과
- Ran 44 tests
- OK
- 참고: 샌드박스 환경에서 MySQL 접속 경고가 출력되었으나, 테스트 자체는 모킹 기반으로 통과
