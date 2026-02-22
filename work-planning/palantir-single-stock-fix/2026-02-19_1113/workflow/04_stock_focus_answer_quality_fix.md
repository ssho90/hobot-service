# 04. 팔란티어 종목답변 품질 보정 (2026-02-19)

## Diagnose
- 증상: `route_type=us_single_stock`, `focus_symbols=['PLTR']`, `stock_focus_docs>0`인데도 최종 답변이 섹터 일반론 중심.
- 확인 결과:
  - 컨텍스트 문서에는 종목 직접 근거가 포함되어도, 프롬프트에 들어가는 evidence 상단이 특정 문서(`te:6463`) 중심으로 편중.
  - `us_single_stock` 템플릿 섹션(`가격/변동률`, `실적`, `밸류`)이 종목 비직접 근거도 채택 가능하여, 엉뚱한 동종/타종목 문장 채택.
  - LLM이 일반 evidence만 인용하면 citations도 그대로 굳어 종목 직접 증거가 누락됨.

## 🔴 에러 원인
- 종목 포커스 retrieval 이후 단계(프롬프트 evidence 선택 + citation 후처리 + 템플릿 섹션 선택)에 `종목 직접성 우선 규칙`이 약해, 결과적으로 최종 답변에서 종목 직접 근거가 희석됨.

## Fix
- 파일: `hobot/service/graph/rag/response_generator.py`
- 변경사항:
  1. `us_single_stock` 프롬프트 evidence 재정렬
     - 종목명/티커 direct match + Fact + 숫자신호(%, price) 점수 기반 정렬.
     - 문서당 evidence 편중 완화(per-doc cap).
  2. citations 보강
     - `us_single_stock`에서 LLM 인용이 일반근거 위주여도, 컨텍스트에서 종목 직접 evidence를 최대 3개까지 주입/대체.
  3. 템플릿 엄격화
     - `가격/변동률`, `실적`, `밸류` 섹션은 종목 direct match가 없으면 fallback(근거 불충분) 처리.

## Tests
- 업데이트 파일: `hobot/tests/test_phase_d_response_generator.py`
- 추가 테스트:
  - `test_us_single_stock_strict_sections_fallback_without_focus_evidence`
  - `test_us_single_stock_citations_include_focus_evidence_even_when_llm_misses`
- 실행:
  - `PYTHONPATH=hobot .venv/bin/python -m unittest hobot/tests/test_phase_d_response_generator.py hobot/tests/test_phase_d_context_api.py`
  - 결과: `Ran 39 tests ... OK`
  - 환경 경고: sandbox 내 MySQL 연결 실패 로그는 테스트와 무관(기존과 동일).

