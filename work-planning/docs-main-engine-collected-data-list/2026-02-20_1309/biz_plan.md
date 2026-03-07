# Collected Data List Documentation Plan

## 목표
- `docs-main-engine/collected-data-list.md`에 현재 수집 중인 데이터를 테이블로 정리한다.

## 요구 컬럼
- 국가
- 데이터 코드
- 지표명
- description

## 데이터 소스
- `hobot/service/macro_trading/indicator_health.py`의 레지스트리
  - `KR_INDICATOR_REGISTRY`
  - `KR_CORPORATE_REGISTRY`
  - `US_CORPORATE_REGISTRY`
  - `GRAPH_REGISTRY`
  - `PIPELINE_REGISTRY`
  - `_build_us_registry()` (FRED 지표)

## 완료 기준
- Markdown 표가 문서에 반영되고, 총 코드 수가 현재 레지스트리 기준과 일치한다.
