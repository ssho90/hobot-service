# 진단 로그

## 2026-02-19 11:13
- 사용자 보고 증상
  - `us_single_stock` 라우트 선택에도 `focus_symbols`가 빈 배열
  - `stock_focus_docs=0`
  - 프론트 콘솔에서 `node not found: event:...` 에러
- 초기 가설
  - 라우터 결과의 `matched_symbols` 위치와 `to_context_request()` 참조 위치 불일치
  - 컨텍스트 응답 조립 시 링크가 노드 집합과 동기화되지 않음

## 2026-02-19 11:17
🔴 **에러 원인:** `query_route` 최상위에는 `matched_symbols/matched_companies`가 없고 `agents[].us_single_stock_agent` 내부에만 존재해 `GraphRagAnswerRequest.to_context_request()`가 종목 포커스를 빈 배열로 전달했습니다. 이로 인해 `phase_d_documents_for_us_single_stock` 경로가 사실상 무력화되어 종목 직접 근거 검색이 0건으로 떨어졌습니다.

🔴 **에러 원인:** `context_api`가 링크를 생성한 뒤 최종 `nodes` 집합과의 존재성 검증 없이 반환해, `nodes`에 없는 `event:*`를 가리키는 dangling link가 남았고 프론트(`react-force-graph`)에서 `node not found` 예외가 발생했습니다.
