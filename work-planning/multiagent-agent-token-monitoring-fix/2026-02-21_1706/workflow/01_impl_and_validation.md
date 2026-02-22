# 구현/검증 로그

## 원인
- `service/graph/rag/response_generator.py`의 `_execute_branch_agents`에서 `log_llm_usage(...)` 호출 시
  `prompt_tokens=0`, `completion_tokens=0`, `total_tokens=0`으로 고정 기록하고 있었다.

## 수정
- `service/graph/rag/response_generator.py`
  - `_estimate_text_tokens` 추가
  - `_estimate_agent_execution_tokens` 추가
  - `_execute_branch_agents`에서
    - 요청/응답 payload JSON 문자열 생성
    - 추정 토큰 계산 후 `log_llm_usage`에 반영
    - metadata에 `token_usage_mode=estimated_from_payload` 및 추정값 기록

- `tests/test_phase_d_response_generator.py`
  - `test_agent_execution_token_estimator_returns_positive_counts` 추가

## 검증 결과
- `PYTHONPATH=. ../.venv/bin/python -m py_compile service/graph/rag/response_generator.py` 통과
- `PYTHONPATH=. ../.venv/bin/python -m unittest discover -s tests -p 'test_phase_d_response_generator.py' -k 'agent_execution_token_estimator_returns_positive_counts'` 통과
