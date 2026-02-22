- 구현 완료 파일
  - `hobot/service/graph/monitoring/phase5_regression.py`
  - `hobot/service/graph/monitoring/golden_sets/phase5_q1_q6_v1.json`
  - `hobot/service/graph/monitoring/__init__.py`
  - `hobot/tests/test_phase5_golden_regression.py`
  - `hobot/service/graph/scheduler/phase5_regression_batch.py`
  - `hobot/service/graph/scheduler/__init__.py`
  - `hobot/service/graph/__init__.py`
  - `hobot/service/macro_trading/scheduler.py`
  - `hobot/tests/test_phase5_regression_batch_runner.py`
  - `hobot/service/macro_trading/tests/test_scheduler_graph_phase5_regression.py`

- 구현 내용
  1) 골든셋 회귀 실행기 추가 (`phase5_regression.py`)
     - 골든 케이스 로드/파싱
     - 케이스별 검증(필수키/근거수/신선도/국가스코프/가드레일 문구)
     - 실패 유형 분류 집계
       - `schema_mismatch`
       - `citation_missing`
       - `freshness_stale`
       - `scope_violation`
       - `guardrail_violation`
       - `evaluator_error`

  2) Q1~Q6 초기 골든셋 파일 추가
     - 경로: `hobot/service/graph/monitoring/golden_sets/phase5_q1_q6_v1.json`
     - 케이스 수: 6개 (Q1~Q6 각 1개)

  3) 모니터링 패키지 export 확장
     - `hobot/service/graph/monitoring/__init__.py`에 Phase5 회귀 함수/상수 export

  4) 단위테스트 추가
     - 기본 골든셋 파일 로딩 검증
     - 실패 유형 분류 검증
     - evaluator 예외 집계 검증
     - 파일 기반 실행 경로 검증

  5) 자동 실행 파이프라인(운영 스케줄) 추가
     - `run_phase5_golden_regression_jobs` 추가
       - 골든셋 로딩 + 선택 케이스 필터 + GraphRAG 답변 생성 호출 + 회귀 평가
     - `run_graph_rag_phase5_regression` 추가
       - 환경변수 기반 실행 옵션
       - 결과를 `macro_collection_run_reports`에 적재
       - 실패 시 에러 리포트 저장
     - `setup_graph_rag_phase5_regression_scheduler` 추가
       - 기본 스케줄: 매일 `08:10` (KST)
       - `start_news_scheduler_thread`, `start_all_schedulers` 연결

  6) 실패 케이스 디버깅 리포트 저장 보강
     - `run_graph_rag_phase5_regression`에서 실패 케이스 상세를 `details_json`에 저장
       - `failed_case_debug_total`
       - `failed_case_debug_returned`
       - `failed_case_debug_entries`
         - `case_id`, `question_id`, `citation_count`
         - `failure_categories`, `failure_messages`, `failure_count`
     - 저장 payload 제한을 위해 env 기반 상한 추가
       - `GRAPH_RAG_PHASE5_FAILURE_DEBUG_CASE_LIMIT` (default: `10`)
       - `GRAPH_RAG_PHASE5_FAILURE_DEBUG_MESSAGE_LIMIT` (default: `3`)
