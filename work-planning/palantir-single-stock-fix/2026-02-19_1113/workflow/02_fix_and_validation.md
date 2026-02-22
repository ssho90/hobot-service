# 수정 및 검증 로그

## 2026-02-19 11:18
### 코드 수정
- `hobot/service/graph/rag/response_generator.py`
  - `GraphRagAnswerRequest`에 라우트 포커스 추출 fallback 추가
    - 최상위 `matched_symbols/matched_companies`가 없을 때 `agents` 내 `us_single_stock_agent`에서 복구
  - `to_context_request()`가 fallback 결과를 `focus_symbols/focus_companies`로 전달하도록 변경
  - `_route_query_type_multi_agent()` 반환값에 `matched_symbols`, `matched_companies`를 top-level로 포함

- `hobot/service/graph/rag/context_api.py`
  - `nodes` 확정 후 `links`를 정합성 필터링
    - `source`와 `target`가 모두 `nodes`에 존재하는 링크만 유지
  - 제거된 dangling link 개수를 warning 로그로 남기도록 추가

### 테스트 추가
- `hobot/tests/test_phase_d_response_generator.py`
  - `test_answer_request_to_context_request_uses_agent_focus_fallback` 추가
  - us_single_stock 라우팅 테스트에 `route.matched_symbols` top-level 검증 추가

- `hobot/tests/test_phase_d_context_api.py`
  - `test_build_graph_context_filters_dangling_links` 추가
  - 누락 이벤트를 참조하는 링크가 최종 결과에서 제거되는지 검증

### 검증 실행
- 명령:
  - `PYTHONPATH=hobot .venv/bin/python -m unittest hobot/tests/test_phase_d_response_generator.py hobot/tests/test_phase_d_context_api.py`
- 결과:
  - `Ran 36 tests`
  - `OK`
- 참고:
  - 샌드박스 환경에서 MySQL/임베딩 네트워크 경고 로그는 출력되지만 테스트 결과에는 영향 없음
- 추가 정적 검증:
  - `PYTHONPATH=hobot .venv/bin/python -m py_compile hobot/service/graph/rag/response_generator.py hobot/service/graph/rag/context_api.py`
  - 결과: 성공
