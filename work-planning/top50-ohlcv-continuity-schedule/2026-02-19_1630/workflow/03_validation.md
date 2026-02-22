- 실행 명령
  - PYTHONPATH=. ../.venv/bin/python -m unittest \
    service.macro_trading.tests.test_us_corporate_collector \
    service.macro_trading.tests.test_kr_corporate_collector \
    service.macro_trading.tests.test_scheduler_kr_top50_ohlcv \
    service.macro_trading.tests.test_scheduler_us_top50_ohlcv

- 결과
  - Ran 35 tests
  - OK

- 검증 포인트
  - collector: 연속성 유니버스 병합 로직 테스트 추가/통과
  - scheduler: continuity_days env 파싱 및 collector 전달 테스트 통과
  - scheduler setup: 기본 시각 KR 16:20, US 07:10 검증 통과
