# 03_validation

## 실행
- `PYTHONPATH=hobot .venv/bin/python -m unittest -q hobot.service.macro_trading.tests.test_scheduler_kr_top50_ohlcv hobot.service.macro_trading.tests.test_scheduler_us_top50_ohlcv hobot.service.macro_trading.tests.test_kr_corporate_collector hobot.service.macro_trading.tests.test_us_corporate_collector`

## 결과
- `Ran 41 tests in 0.013s`
- `OK`

## 비고
- `.venv`에 `pytest`가 없어 `unittest`로 대체 검증함.
