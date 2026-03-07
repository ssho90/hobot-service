# Admin Indicators Coverage Expansion Plan

## 목표
- `/admin/indicators` 화면에 현재 수집 중인 주요 데이터군(OHLCV/뉴스/이벤트/부동산)이 누락 없이 표시되도록 `indicator_health` 스냅샷을 확장한다.

## 작업 범위
- `hobot/service/macro_trading/indicator_health.py`
  - 레지스트리 코드 추가
  - DB 집계 쿼리(query_map) 추가
  - 표시용 note 보강

## 검증
- 파이썬 구문 체크(py_compile)
- 코드 검색으로 신규 코드/테이블 매핑 확인

## 완료 기준
- `/admin/indicators` API 스냅샷에 신규 코드가 포함되고, 데이터가 존재할 경우 최신 시점/건수/메모가 채워진다.
