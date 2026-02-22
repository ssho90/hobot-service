# 구현 로그

- 초기 생성: US 단일종목 템플릿 강제(가격/변동률/실적/밸류/리스크) 작업 시작.
- 코드 반영:
  - `hobot/service/graph/rag/response_generator.py`
    - `US_SINGLE_STOCK_TEMPLATE_SPECS` 추가
    - `us_single_stock` 라우트 전용 후처리 `_enforce_us_single_stock_template_output` 추가
    - 라우팅 프롬프트 가이던스에 4개 섹션 라벨 출력 규칙 추가
    - 응답 메타 필드에 `us_single_stock_template_enforced`, `us_single_stock_missing_sections` 추가
- 테스트 반영:
  - `hobot/tests/test_phase_d_response_generator.py`
    - `팔란티어 주가 어때?` 케이스에서
      - 프롬프트 내 템플릿 문구 포함 검증
      - 응답 `key_points` 4개 섹션 라벨 강제 검증
      - 메타 플래그 검증
- 검증:
  - `tests/test_phase_d_response_generator.py`: `Ran 20 tests ... OK`
  - `tests/test_phase_d_context_api.py`: `Ran 12 tests ... OK`
  - `py_compile`: 성공

## 추가 고도화 (2차)
- `가격/변동률` 섹션 정확도 보강:
  - 종목 템플릿 요약 함수에 점수화 로직 추가
  - 포커스 심볼/회사명(`matched_symbols`, `matched_companies`) 매칭 점수 반영
  - `가격/변동률`은 숫자 신호(`%` 또는 `$`)가 있는 문장만 후보로 허용
- 스모크 테스트 확장:
  - `PLTR`, `NVDA`, `AAPL` 루프 기반 스모크 테스트 추가
  - 숫자 신호 우선 선택 회귀 테스트(`7.2%` 문장 선택) 추가
- 검증:
  - `tests/test_phase_d_response_generator.py`: `Ran 22 tests ... OK`
  - `tests/test_phase_d_context_api.py`: `Ran 12 tests ... OK`
  - `py_compile`: 성공
