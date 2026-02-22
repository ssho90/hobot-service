# 구현 로그

## 작업 시작
- Phase5 회귀 스케줄러에 외부 알림 연동 지점을 추가한다.
- 기존 잡 실행 성공/실패 저장(`_record_collection_run_report`)은 그대로 유지한다.

## 구현 내용
- `hobot/service/macro_trading/scheduler.py`
  - `_send_phase5_regression_alert(...)` 추가
  - env 기반 알림 제어 추가
    - `GRAPH_RAG_PHASE5_ALERT_ENABLED` (default `0`)
    - `GRAPH_RAG_PHASE5_ALERT_ONLY_ON_WARNING` (default `1`)
    - `GRAPH_RAG_PHASE5_ALERT_CHANNEL` (default `#auto-trading-error`)
    - `GRAPH_RAG_PHASE5_ALERT_CASE_LIMIT` (default `3`)
    - `GRAPH_RAG_PHASE5_ALERT_ERROR_MESSAGE_LIMIT` (default `2`)
  - `run_graph_rag_phase5_regression`의 성공/예외 경로에서 알림 호출 연결
  - Slack import/전송 실패는 경고 로그만 남기고 실행 흐름은 유지하도록 안전 처리

- `hobot/service/macro_trading/tests/test_scheduler_graph_phase5_regression.py`
  - 성공/예외 테스트에서 `_send_phase5_regression_alert` 호출 검증 추가

## 검증
- `PYTHONPATH=. ../.venv/bin/python -m unittest discover -s service/macro_trading/tests -p 'test_scheduler_graph_phase5_regression.py'`
  - `Ran 3 tests ... OK`
- `PYTHONPATH=. ../.venv/bin/python -m unittest discover -s tests -p 'test_phase5_regression_batch_runner.py'`
  - `Ran 3 tests ... OK`
