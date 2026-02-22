# 29) Web Fallback 무료 검색 전환 (Tavily 제거)

## 요청 사항
- Tavily 사용량 제한/과금 이슈로 미사용.
- API 키 없이 동작하는 무료 검색 fallback 필요.

## 🔴 에러 원인
- 초기 구현이 Tavily 의존(`TAVILY_API_KEY`, `langchain_tavily`)이라 운영 환경에서 비용/쿼터 제약이 발생할 수 있었음.

## 변경 내용
1. GraphRAG fallback 검색 엔진 교체
- `TavilySearch` 제거
- `Google News RSS` 무료 검색으로 전환
  - 쿼리: `https://news.google.com/rss/search?q=...`
  - 국가별 로케일 자동 반영 (`KR` -> `ko/KR`, 그 외 `en-US/US`)

2. 파서/정규화 추가
- RSS XML 파싱 (`xml.etree.ElementTree`)
- RFC822 pubDate -> ISO8601 변환
- description HTML 태그 제거

3. 기존 fallback 파이프라인 유지
- `citation_shortage`, `freshness_missing/stale` 조건에서만 fallback 시도
- 검색 결과를 `GraphRagCitation(support_labels=["WebFallback"])`로 변환
- 최종 응답 메타에 `web_fallback` 추적값 유지

## 테스트
- `cd hobot && PYTHONPATH=. ../.venv/bin/python -m py_compile service/graph/rag/response_generator.py tests/test_phase_d_response_generator.py`
- `cd hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
- 결과: `Ran 54 tests ... OK (skipped=2)`

## 참고
- GraphRAG 코드에서는 Tavily 의존이 제거됨.
- fallback 제어 환경변수:
  - `GRAPH_RAG_WEB_FALLBACK_ENABLED` (기본: on)
  - `GRAPH_RAG_WEB_FALLBACK_MAX_RESULTS` (기본: 3)
  - `GRAPH_RAG_WEB_FALLBACK_TIMEOUT_SEC` (기본: 7)
  - `GRAPH_RAG_WEB_FALLBACK_ON_WARNING` (기본: off)
