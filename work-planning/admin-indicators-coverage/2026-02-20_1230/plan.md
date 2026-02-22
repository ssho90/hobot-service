# Admin Indicators Missing Recovery Plan

## 목표
- `/admin/indicators`에서 `미수집`으로 보이는 4개 코드의 근본 원인을 제거한다.
- 대상: `KR_CPI`, `KR_UNEMPLOYMENT`, `KR_DART_DISCLOSURE_EARNINGS`, `GRAPH_DOCUMENT_EMBEDDING_COVERAGE`.

## 범위
- `hobot/service/macro_trading/indicator_health.py`
  - DART 실적 공시 집계 기준 보강
  - Graph timestamp 파싱/정규화 보강
- `hobot/service/macro_trading/tests/test_indicator_health.py`
  - timestamp coercion 회귀 테스트 추가

## 검증
- 단위 테스트: `test_indicator_health.py`
- (터널/네트워크 허용 시) health snapshot 재조회로 missing 코드 축소 확인

## 완료 기준
- 문자열/Neo4j temporal timestamp가 있어도 graph 지표가 `missing`으로 떨어지지 않는다.
- DART periodic report 데이터만 있어도 `KR_DART_DISCLOSURE_EARNINGS`가 집계된다.
