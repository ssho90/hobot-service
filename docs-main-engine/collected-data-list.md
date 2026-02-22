# 현재 수집 데이터 리스트 (용도별)

- 기준 시각: 2026-02-22 11:53
- 기준 소스: `service.macro_trading.indicator_health` 레지스트리
- 총 지표 수: 63
- 분류: 한국 경제 / 한국 주식 / 한국 부동산 / 미국 경제 / 미국 주식 / 공통/글로벌

## 한국 경제

- 건수: 4

| 국가 | 데이터 코드 | 지표명 | description |
| --- | --- | --- | --- |
| KR | KR_BASE_RATE | Korea Base Rate | Bank of Korea policy rate |
| KR | KR_CPI | Korea Consumer Price Index | Korean CPI (headline) |
| KR | KR_UNEMPLOYMENT | Korea Unemployment Rate | Korean unemployment rate |
| KR | KR_USDKRW | USD/KRW Exchange Rate | US dollar to Korean won exchange rate |

## 한국 주식

- 건수: 14

| 국가 | 데이터 코드 | 지표명 | description |
| --- | --- | --- | --- |
| KR | KR_DART_CORP_CODES | KR DART Corp Code Cache | Open DART 기업코드 캐시 최신성 |
| KR | KR_DART_DISCLOSURE_EARNINGS | KR DART Earnings Disclosures | Open DART 실적 공시 이벤트 수집 |
| KR | KR_DART_DPLUS1_SLA | KR DART D+1 Ingestion SLA | 실적 공시 대비 재무 반영 지연(D+1) 준수 여부 |
| KR | KR_DART_EARNINGS_EXPECTATION | KR Earnings Expectations | 실적 기대값(actual/expected 비교용) 적재 상태 |
| KR | KR_DART_FINANCIALS_H1 | KR DART Financials (H1) | Open DART 반기 재무 주요계정 |
| KR | KR_DART_FINANCIALS_Q1 | KR DART Financials (Q1) | Open DART 1분기 재무 주요계정 |
| KR | KR_DART_FINANCIALS_Q3 | KR DART Financials (Q3) | Open DART 3분기 재무 주요계정 |
| KR | KR_DART_FINANCIALS_Y | KR DART Financials (Annual) | Open DART 사업보고서 재무 주요계정 |
| KR | KR_TOP50_CORP_CODE_MAPPING_VALIDATION | KR Top50 CorpCode Mapping Validation | Top50 스냅샷과 DART corp_code 매핑 정합성 검증 상태 |
| KR | KR_TOP50_DAILY_OHLCV | KR Top50 Daily OHLCV | KR Top50 일별 OHLCV 최신 거래일 적재 상태 |
| KR | KR_TOP50_EARNINGS_WATCH_SUCCESS_RATE | KR Top50 Earnings Watch Success Rate | KR Top50 실적 감시 배치 일간 성공률 |
| KR | KR_TOP50_ENTITY_REGISTRY | KR Top50 Entity Registry | KR 기업 canonical registry 최신성 |
| KR | KR_TOP50_TIER_STATE | KR Top50 Tier State | KR Tier-1 상태 저장 최신성 |
| KR | KR_TOP50_UNIVERSE_SNAPSHOT | KR Top50 Universe Snapshot | Top50 고정 유니버스 최신 스냅샷 상태 |

## 한국 부동산

- 건수: 6

| 국가 | 데이터 코드 | 지표명 | description |
| --- | --- | --- | --- |
| KR | KR_HOUSE_PRICE_INDEX | Korea Housing Sale Price Index | REB/KOSIS sale price index |
| KR | KR_HOUSING_SUPPLY_APPROVAL | Korea Housing Supply (Permits/Approvals) | MOLIT/KOSIS housing supply flow |
| KR | KR_JEONSE_PRICE_RATIO | Korea Jeonse-to-Sale Price Ratio | REB/KOSIS jeonse ratio |
| KR | KR_REAL_ESTATE_MONTHLY_SUMMARY | KR Real Estate Monthly Summary | 국내 실거래 월간 집계 최신 적재 상태 |
| KR | KR_REAL_ESTATE_TRANSACTIONS | KR Real Estate Transactions | 국내 실거래 원천 row 최신 적재 상태 |
| KR | KR_UNSOLD_HOUSING | Korea Unsold Housing Inventory | MOLIT/KOSIS unsold housing stock |

## 미국 경제

- 건수: 22

| 국가 | 데이터 코드 | 지표명 | description |
| --- | --- | --- | --- |
| US | BAMLH0A0HYM2 | ICE BofA US High Yield Index Option-Adjusted Spread | ICE BofA US High Yield Index Option-Adjusted Spread |
| US | CPIAUCSL | Consumer Price Index for All Urban Consumers: All Items in U.S. City Average | Consumer Price Index for All Urban Consumers: All Items in U.S. City Average |
| US | DFII10 | 10-Year Treasury Inflation-Indexed Security, Constant Maturity | 10-Year Treasury Inflation-Indexed Security, Constant Maturity |
| US | DGS10 | 10-Year Treasury Constant Maturity Rate | 10-Year Treasury Constant Maturity Rate |
| US | DGS2 | 2-Year Treasury Constant Maturity Rate | 2-Year Treasury Constant Maturity Rate |
| US | FEDFUNDS | Effective Federal Funds Rate | Effective Federal Funds Rate |
| US | GACDFSA066MSFRBPHI | Philly Fed Current Activity | Philly Fed Current Activity |
| US | GAFDFSA066MSFRBPHI | Philly Fed Future Activity (6M) | Philly Fed Future Activity (6M) |
| US | GDPNOW | GDPNow | GDPNow |
| US | NETLIQ | Net Liquidity (Fed Balance Sheet - TGA - RRP) | Net Liquidity (Fed Balance Sheet - TGA - RRP) |
| US | NOCDFSA066MSFRBPHI | Philly Fed New Orders | Philly Fed New Orders |
| US | PAYEMS | All Employees, Total Nonfarm | All Employees, Total Nonfarm |
| US | PCEPI | Personal Consumption Expenditures: Chain-type Price Index | Personal Consumption Expenditures: Chain-type Price Index |
| US | PCEPILFE | Core PCE Price Index | Core PCE Price Index |
| US | RRPONTSYD | Reverse Repurchase Agreements: Treasury Securities Sold by the Federal Reserve in the Temporary Open Market Operations | Reverse Repurchase Agreements: Treasury Securities Sold by the Federal Reserve in the Temporary Open Market Operations |
| US | STLFSI4 | St. Louis Fed Financial Stress Index | St. Louis Fed Financial Stress Index |
| US | T10Y2Y | 10-Year Minus 2-Year Treasury Constant Maturity | 10-Year Minus 2-Year Treasury Constant Maturity |
| US | T10YIE | 10-Year Breakeven Inflation Rate | 10-Year Breakeven Inflation Rate |
| US | UNRATE | Unemployment Rate | Unemployment Rate |
| US | VIXCLS | CBOE Volatility Index: VIX | CBOE Volatility Index: VIX |
| US | WALCL | Assets: Total Assets: Total Assets (Less Eliminations from Consolidation): Wednesday Level | Assets: Total Assets: Total Assets (Less Eliminations from Consolidation): Wednesday Level |
| US | WTREGEN | U.S. Treasury General Account (TGA) | U.S. Treasury General Account (TGA) |

## 미국 주식

- 건수: 9

| 국가 | 데이터 코드 | 지표명 | description |
| --- | --- | --- | --- |
| US | US_SEC_CIK_MAPPING | US SEC CIK Mapping Cache | SEC ticker/cik 매핑 최신성 |
| US | US_TOP50_DAILY_OHLCV | US Top50 Daily OHLCV | US Top50 일별 OHLCV 최신 거래일 적재 상태 |
| US | US_TOP50_EARNINGS_EVENTS_CONFIRMED | US Top50 Earnings Events (Confirmed) | SEC 확정 실적 이벤트(8-K/10-Q/10-K) |
| US | US_TOP50_EARNINGS_EVENTS_EXPECTED | US Top50 Earnings Events (Expected) | yfinance 실적 발표 예정 이벤트 |
| US | US_TOP50_EARNINGS_WATCH_SUCCESS_RATE | US Top50 Earnings Watch Success Rate | US Top50 실적 감시 배치 일간 성공률 |
| US | US_TOP50_ENTITY_REGISTRY | US Top50 Entity Registry | US 기업 canonical registry 최신성 |
| US | US_TOP50_FINANCIALS | US Top50 Financial Statements | yfinance 기반 미국 Top50 재무제표(연간/분기) |
| US | US_TOP50_TIER_STATE | US Top50 Tier State | US Tier-1 상태 저장 최신성 |
| US | US_TOP50_UNIVERSE_SNAPSHOT | US Top50 Universe Snapshot | US Top50 유니버스 최신 스냅샷 상태 |

## 공통/글로벌

- 건수: 8

| 국가 | 데이터 코드 | 지표명 | description |
| --- | --- | --- | --- |
| GLOBAL | ECONOMIC_NEWS_STREAM | Economic News Stream | economic_news 수집 파이프라인 최신 적재 상태 |
| GLOBAL | EQUITY_GRAPH_PROJECTION_SYNC | Equity Graph Projection Sync | 주식 Projection(RDB->Neo4j) 동기화 실행 및 지연 상태 |
| GLOBAL | GRAPH_DOCUMENT_EMBEDDING_COVERAGE | Graph Document Embedding Coverage | Document 노드 임베딩 커버리지(%) |
| GLOBAL | GRAPH_NEWS_EXTRACTION_SYNC | Graph News Extraction Sync | 뉴스 동기화+추출+임베딩 배치 실행 성공률 |
| GLOBAL | GRAPH_RAG_PHASE5_WEEKLY_REPORT | Graph RAG Phase5 Weekly Regression | Phase5 회귀 주간 집계 실행 상태 |
| GLOBAL | GRAPH_RAG_VECTOR_INDEX_READY | Graph RAG Vector Index Readiness | Neo4j vector index(document_text_embedding_idx) 상태 |
| GLOBAL | TIER1_CORPORATE_EVENT_FEED | Tier-1 Corporate Event Feed | corporate_event_feed 최신 적재 상태 |
| KR | TIER1_CORPORATE_EVENT_SYNC | Tier-1 Corporate Event Sync Health | KR/US Tier-1 표준 이벤트 동기화 배치 상태 |
