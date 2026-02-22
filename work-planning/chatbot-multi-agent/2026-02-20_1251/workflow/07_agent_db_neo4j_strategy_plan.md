# 07_agent_db_neo4j_strategy_plan

## 요청
- 에이전트마다 어떤 RDB와 Neo4j를 볼지 포함한 작업 세부 계획 수립.

## 반영 파일
- `/Users/ssho/project/hobot-service/work-planning/chatbot-multi-agent/2026-02-20_1251/plan.md`

## 반영 내용 요약
1. `12. 작업 세부 계획: 에이전트별 RDB/Neo4j 조회 전략` 섹션 신설
- Agent별 `RDB 1순위 조회 대상`, `Neo4j 1순위 조회 대상`, `기본 실행 모드`, `structured_citations 대상` 표 추가.

2. 에이전트별 실행 전략 추가
- Supervisor / Macro / Equity / RealEstate / Ontology 각각에 대해
  - 어떤 질의에서 SQL 우선인지
  - 어떤 질의에서 Graph 우선인지
  - 언제 조건부 병렬인지
  - fallback 기준이 무엇인지
  를 명시.

3. 구현 태스크와 완료 기준 추가
- 라우팅 정책 코드화, I/O 계약 분리, security_id 정규화, 템플릿화, 회귀 지표 확장까지 실행 순서를 정의.

## 작성 근거(코드 확인)
- RDB 테이블: `kr_top50_daily_ohlcv`, `us_top50_daily_ohlcv`, `kr_corporate_financials`, `us_corporate_financials`, `kr_corporate_disclosures`, `us_corporate_earnings_events`, `corporate_event_feed`, `kr_real_estate_transactions`, `kr_real_estate_monthly_summary`, `fred_data`, `economic_news` 등
- Neo4j 라벨/관계: `Document`, `Event`, `Fact`, `Claim`, `Evidence`, `MacroTheme`, `EconomicIndicator`, `IndicatorObservation`, `RealEstateMonthlySummary`, `ABOUT_THEME`, `AFFECTS`, `SUPPORTS`, `HAS_OBSERVATION` 등
