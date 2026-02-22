# Workflow Log - Grouped Table Update

## 실행 계획
1. indicator_health 레지스트리에서 (country, code, name, description) 추출
2. 용도별 분류 규칙 적용
3. 분류별 Markdown 테이블 생성
4. 문서 반영 및 누락 검증

## 실행 결과
- `docs-main-engine/collected-data-list.md`를 용도별 섹션으로 재구성.
- 카테고리별 건수:
  - 한국 경제: 4
  - 한국 주식: 14
  - 한국 부동산: 6
  - 미국 경제: 22
  - 미국 주식: 9
  - 공통/글로벌: 6
- 총합: 61 (레지스트리 기준 전체 코드와 일치)

## 분류 규칙
- 한국 경제: `KR_BASE_RATE`, `KR_CPI`, `KR_UNEMPLOYMENT`, `KR_USDKRW`
- 한국 부동산: `KR_HOUSE_PRICE_INDEX`, `KR_JEONSE_PRICE_RATIO`, `KR_UNSOLD_HOUSING`, `KR_HOUSING_SUPPLY_APPROVAL`, `KR_REAL_ESTATE_TRANSACTIONS`, `KR_REAL_ESTATE_MONTHLY_SUMMARY`
- 미국 주식: `US_TOP50_*`, `US_SEC_CIK_MAPPING`
- 공통/글로벌: `GLOBAL` 지표 + `TIER1_CORPORATE_EVENT_SYNC`
- 나머지 KR/US는 각각 한국 주식/미국 경제로 분류
