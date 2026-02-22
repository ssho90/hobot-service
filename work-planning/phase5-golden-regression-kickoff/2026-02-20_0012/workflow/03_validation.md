- 실행 테스트
  1) `PYTHONPATH=. ../.venv/bin/python -m unittest discover -s tests -p 'test_phase5_golden_regression.py'`
  2) `PYTHONPATH=. ../.venv/bin/python -m unittest discover -s tests -p 'test_phase_d_monitoring.py'`
  3) `PYTHONPATH=. ../.venv/bin/python -m unittest discover -s tests -p 'test_phase5_regression_batch_runner.py'`
  4) `PYTHONPATH=. ../.venv/bin/python -m unittest discover -s service/macro_trading/tests -p 'test_scheduler_graph_phase5_regression.py'`
  5) `PYTHONPATH=. ../.venv/bin/python -m unittest discover -s service/macro_trading/tests -p 'test_scheduler_graph_news_embedding.py'`

- 결과
  - `test_phase5_golden_regression.py`: 4 tests, OK
  - `test_phase_d_monitoring.py`: 3 tests, OK
  - `test_phase5_regression_batch_runner.py`: 3 tests, OK
  - `test_scheduler_graph_phase5_regression.py`: 3 tests, OK
  - `test_scheduler_graph_news_embedding.py`: 3 tests, OK

- 해석
  - Phase 5 착수용 골든셋/회귀 실행기의 기본 동작은 정상
  - Graph scheduler 배치 러너 + macro scheduler 연동이 테스트 기준 정상
  - 회귀 리포트 저장 시 실패 케이스 디버깅 상세(`failed_case_debug_entries`) 적재 동작 검증 완료
  - 기존 Phase D 모니터링/Graph 뉴스 추출 스케줄 테스트와 충돌 없음
