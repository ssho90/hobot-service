# collected-data-list 최신화 계획

- 대상 문서: `/Users/ssho/project/hobot-service/docs-main-engine/collected-data-list.md`
- 목적: 현재 코드 기준 수집 데이터 목록(코드/명칭/설명) 최신 반영
- 기준 소스:
  - `service.macro_trading.indicator_health`
  - `service.macro_trading.collectors.fred_collector` (US 지표 registry)
- 수행 단계:
  1. 레지스트리 기준 총 항목 수 재산출
  2. 분류별(한국 경제/주식/부동산, 미국 경제/주식, 글로벌) 코드 정렬
  3. 문서 테이블 갱신 및 건수/총계 반영
