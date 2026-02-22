# Workflow Log - Missing Indicators Recovery

## 수행 내용
1. 기존 코드 상태 점검
- KR macro 기본 파라미터(`KR_CPI`, `KR_UNEMPLOYMENT`)는 이미 올바른 값으로 반영되어 있음을 확인.
- `KR_DART_DISCLOSURE_EARNINGS`는 `is_earnings_event=1`만 집계하여 periodic report 데이터가 누락되는 문제 확인.
- Graph health는 timestamp가 문자열/Neo4j temporal일 때 `_coerce_reference_timestamp`가 `None`을 반환할 수 있는 문제 확인.

2. 코드 수정
- `indicator_health.py`
  - `KR_DART_DISCLOSURE_EARNINGS` 쿼리 조건을 `event_type='periodic_report'` 및 보고서명 패턴까지 확장.
  - `_coerce_reference_timestamp`에 문자열 ISO(나노초 포함) 및 `to_native()/to_pydatetime()` temporal 파싱 로직 추가.
  - timezone-aware datetime을 UTC naive로 정규화해 lag 계산 충돌 방지.

3. 테스트 보강
- `test_indicator_health.py`
  - ISO 나노초 문자열 파싱 테스트 추가.
  - Neo4j temporal 유사 객체(`to_native`) 파싱 테스트 추가.

## 비고
- 현재 샌드박스 네트워크 제한으로 로컬 DB/Neo4j 실접속 검증은 권한 상승 실행이 필요.

## 검증 결과
- 단위 테스트
  - 실행: `PYTHONPATH=. ../.venv/bin/python -m unittest service.macro_trading.tests.test_indicator_health -v`
  - 결과: 11 tests, 모두 통과.

- 실데이터 수집(권한 상승 실행)
  - 실행: `collect_kr_macro_data(indicator_codes=['KR_CPI','KR_UNEMPLOYMENT'], days=3650)`
  - 결과: `KR_CPI` 120건, `KR_UNEMPLOYMENT` 120건 적재 성공.

- health snapshot 재확인(권한 상승 실행)
  - 요약: `healthy 57 / stale 4 / missing 0`
  - `missing` 코드: 없음.
