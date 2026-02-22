# 후속 수정 로그 (MSFT 케이스)

## 2026-02-19 11:25
- 재현 증상
  - `route_type=us_single_stock`, `focus_symbols=["MSFT"]`인데 `retrieval.stock_focus_docs=0`
  - 답변이 다시 섹터 일반론으로 흘러 종목 직접 근거가 약함

🔴 **에러 원인:** 티커 기반 포커스 검색어가 `msft` 중심으로만 생성되어, 문서의 실제 표기(`Microsoft`)를 충분히 매칭하지 못했습니다. 또한 국가 미지정 단일종목 질의에서 US 스코프가 강제되지 않아 잡음 문서가 과다 유입되었습니다.

## 수정
- `hobot/service/graph/rag/response_generator.py`
  - `US_SINGLE_STOCK_SYMBOL_COMPANY_HINTS` 추가
  - `_build_us_single_stock_forced_route()`에서 `matched_companies`가 비어도 심볼 기반 회사명 힌트를 채우도록 보강

- `hobot/service/graph/rag/context_api.py`
  - `US_SINGLE_STOCK_SYMBOL_COMPANY_HINTS` 추가
  - 심볼 기반 회사명 확장 메서드 `_expand_focus_companies_from_symbols()` 추가
  - `build_context()`에서 `focus_symbols`로부터 `focus_companies` 자동 확장
  - `us_single_stock` + 국가 미지정인 경우 기본 국가를 `US`로 보정

## 테스트
- 추가/강화 테스트
  - `hobot/tests/test_phase_d_context_api.py::test_us_single_stock_symbol_expands_company_terms_and_defaults_us_scope`
  - `hobot/tests/test_phase_d_response_generator.py` us_single_stock 라우트에서 `matched_companies` 포함 검증 보강

- 실행
  - `PYTHONPATH=hobot .venv/bin/python -m unittest hobot/tests/test_phase_d_response_generator.py hobot/tests/test_phase_d_context_api.py`
  - 결과: `Ran 37 tests`, `OK`

- 정적 확인
  - `PYTHONPATH=hobot .venv/bin/python -m py_compile hobot/service/graph/rag/response_generator.py hobot/service/graph/rag/context_api.py`
  - 결과: 성공
