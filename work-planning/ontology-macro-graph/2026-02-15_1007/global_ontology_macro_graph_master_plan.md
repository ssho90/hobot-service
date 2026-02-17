# 미국·한국 Ontology > Macro Graph 구축 마스터 플랜 (US-KR Focus)

본 문서는 다음 목표를 위한 단일 기준 문서(Single Source of Truth)입니다.

1. 미국 주식 투자 목적의 경제 분석 Agent를 안정적으로 운영한다.
2. Ontology/Macro Graph QA 범위를 미국(US)과 한국(KR)에 집중하고, 한국 부동산 데이터를 1급 도메인으로 포함해 구축한다.

작성일: 2026-02-14  
소유자: Macro Trading / Graph 팀

---

## 1. 목표와 원칙

### 1.1 핵심 목표
- **Goal A (운영 목표)**: 트레이딩 의사결정은 `US equities first` 원칙으로 유지한다.
- **Goal B (확장 목표)**: QA 시스템은 미국/한국 매크로 + 한국 부동산 질의응답을 지원한다.
- **Goal C (도메인 목표)**: 한국 부동산(가격/거래/공급/금융/정책)을 경제 온톨로지의 핵심 축으로 반영한다.
- **Goal D (품질 목표)**: 답변마다 근거 노드(문서/이벤트/지표)와 시간 범위를 명시한다.

### 1.2 설계 원칙
- **분리 원칙**: `투자 의사결정(US 중심)`과 `지식 QA(US/KR)`를 논리적으로 분리한다.
- **스코프 원칙**: 1차 배포 범위는 `country_code IN (US, KR)`로 고정한다.
- **정규화 원칙**: 국가 식별자는 ISO 3166-1 alpha-2(`country_code`)로 표준화한다.
- **도메인 원칙**: 한국 부동산은 매크로 보조 정보가 아니라 독립 온톨로지 도메인으로 모델링한다.
- **근거 원칙**: 지표 수치/뉴스 근거 없이는 확정적 결론을 만들지 않는다.
- **운영 원칙**: 데이터 커버리지와 신선도(Freshness)를 모니터링하고 SLA를 둔다.

---

## 2. 현재 상태 진단 (문제 정의)

### 2.1 데이터 커버리지 갭
- 현재 정량 핵심은 FRED 중심이며 실질적으로 미국 시계열에 편중되어 있다.
- 한국 매크로 분석에 필요한 공식 통계/정책 데이터(예: ECOS, KOSIS 계열) 연동이 부족하다.
- 한국 부동산 핵심 데이터(실거래, 전세/월세, 공급·인허가, 미분양, 대출·금리)의 구조적 수집이 부족하다.
- 미국-한국 비교에 필요한 공통 지표 프레임(동일 정의/동일 주기/동일 단위)이 부족하다.

### 2.2 그래프/질의 구조 갭
- 일부 경로는 `country`, 일부는 `country_code`를 사용해 필터 일관성이 떨어질 수 있다.
- Event/Story/Evidence 전부에서 국가 필터가 일관되게 적용되는지 점검 체계가 부족하다.
- 미국-한국 비교 질의(예: "미국 vs 한국 물가/금리 모멘텀")용 응답 템플릿이 부족하다.
- 한국 부동산 지역 단위(시도/시군구) 질의를 처리할 공간 차원 스키마가 부족하다.

### 2.3 운영/평가 갭
- US/KR 데이터 신선도와 누락률을 추적하는 대시보드가 없다.
- US/KR QA 정확도 측정용 골든셋과 회귀 테스트가 부족하다.
- 한국 부동산 지표 리비전/지연 공시를 반영한 품질 규칙이 부족하다.

---

## 3. Target Architecture (To-Be)

### 3.1 이원화된 제품 경로
- **Track 1: US Trading Intelligence**
  - 목적: 미국 주식 배분 의사결정 최적화
  - 입력: US 중심 정량 + US 시장 영향 이벤트
- **Track 2: US-KR Macro + KR Real Estate QA**
  - 목적: 미국/한국 단일국가 및 비교 질의 + 한국 부동산 질의응답
  - 입력: US/KR 정량 + US/KR 뉴스/공식 문서 + 한국 부동산 시계열/거래 데이터 + 그래프 근거

### 3.2 데이터 레이어
- **Bronze**: 원천 Raw 적재 (원문, 수집시간, 라이선스 메타데이터)
- **Silver**: 정규화 (country_code, 단위, 빈도, timezone, release/effective date)
- **Gold**: 분석 친화 모델 (지표 팩터, surprise, diffusion index, regime features, housing cycle features)
- **Graph**: Ontology 엔터티 및 관계 저장 (Neo4j)

### 3.3 시간 모델 표준
- `published_at`: 문서 공개 시점
- `release_date`: 공식 통계 발표 시점
- `effective_date`: 수치가 의미하는 기준 시점
- `observed_at`: 시스템 수집 시점

### 3.4 진입점 경계 규칙 (중요)
- **트레이딩 엔진 진입점**: `US equities first`를 적용하며, 리밸런싱 비율 산출 로직은 US 중심 입력으로 제한한다.
- **온톨로지 챗봇 진입점**: `US/KR + KR 부동산` 질의응답을 지원하며, 국가/도메인 범위를 질문 스코프에 따라 확장한다.
- 두 경로는 목적과 출력이 다르므로 분리 운영한다.
- 트레이딩 엔진 출력: 실제 의사결정(배분/리스크 관리)
- 챗봇 출력: 근거 기반 설명/비교/시나리오
- 트레이딩 엔진의 US 제한 정책은 챗봇 질의 스코프를 제한하지 않는다.
- 반대로 챗봇의 KR/부동산 분석 결과는 트레이딩 엔진 입력으로 자동 반영하지 않는다(명시적 온보딩 전까지 차단).

---

## 4. 데이터 확장 전략 (핵심)

### 4.1 우선 보강 영역
- **정량 매크로(US/KR)**: 성장/물가/고용/금리/신용/유동성
- **정책/공식문서**: 연준(Fed) 및 한국은행(BOK) 성명/회의자료, 통계청/재무부/기재부 자료
- **시장데이터**: 국채금리곡선, FX(USD/KRW), 주가지수, 스프레드, 원자재
- **이벤트 캘린더**: 주요 지표 발표 일정 + 실제/컨센서스/서프라이즈
- **한국 부동산 데이터**: 매매/전세/월세 가격, 실거래 건수, 거래량, 미분양, 인허가/착공/준공, 주택금융 지표

### 4.2 데이터 소스 후보군
- **미국 정량 유지**: FRED + 필요 시 BLS/BEA/US Treasury/Fed 공개 데이터 보강
- **한국 정량 보강**: 한국은행 ECOS + KOSIS + 공공기관 공개 통계 API
- **공식 정책 데이터**: FOMC/Fed 발표 + 금통위/BOK 발표
- **뉴스/텍스트**: 기존 경제뉴스 + 미국/한국 정책기관 원문 + 라이선스 가능한 뉴스 피드
- **국제기구 리포트**: IMF/OECD/BIS는 보조 근거 소스로 사용
- **한국 부동산 공공 데이터**: 국토교통부 실거래/정책 자료, 한국부동산원(R-ONE), KOSIS 주택통계, 주택금융 관련 공개 통계

### 4.3 소스 온보딩 기준 (필수)
- 라이선스/재배포 가능 여부 명확
- `country_code`(US/KR), 지표 코드 매핑 가능
- 한국 부동산의 경우 `region_code`(시도/시군구), `property_type`, `transaction_type` 매핑 가능
- 최소 3년 이상 히스토리 확보 가능
- 갱신 주기와 결측 처리 규칙 명시 가능
- 장애/지연 시 재수집 경로 존재

### 4.3.1 KR 부동산 지역 코드 Canonical 규칙
- Canonical ID는 **법정동 코드(10자리)**를 기준으로 사용한다.
- 행정동/기관별 자체 코드(행안부, 부동산원, KB 등)는 별도 매핑 테이블로 관리한다.
- 매핑 관계는 `(RegionAlias)-[:MAPPED_TO]->(RealEstateRegion)` 또는 동등한 매핑 테이블로 표현한다.
- 질의 확장 규칙:
  - 사용자가 행정동 명칭으로 질문하면, 대응하는 법정동 코드 집합으로 확장 조회한다.
  - 예시: `판교동(행정동)` 질의 -> `판교동/백현동/삼평동(법정동)` 데이터 병합 조회

### 4.4 한국 데이터 도메인 스택 (P0~P4)
- **P0 거시/대외 환경**: 경기선행지수, PMI, USD/KRW, 미국 2Y/10Y 금리, 반도체 가격(DRAM/NAND), 무역/수출입
- **P1 금융 유동성/통화정책**: 기준금리, 본원통화, M1/M2, 국고채 금리곡선, 회사채 스프레드, 가계대출/주담대
- **P2 주식 시장 마이크로**: 투자자별 순매수(외국인/기관/개인), 공매도, 신용융자 잔고, 거래대금/회전율
- **P3 기업 펀더멘털**: US(yfinance for US Financials) + KR(Open DART) 기반 재무제표(매출/영업이익/순이익/ROA 등), 분기/반기/연간 공시, 컨센서스 추정치
- **P4 부동산**: 실거래가(매매/전세/월세), 가격지수, 인허가/착공/준공, 미분양, 매수심리/전세가율

### 4.5 우선 온보딩 소스 (공식성 기준)
| 도메인 | 1순위(공식/공공) | 2순위(보완) | 주기 |
| :--- | :--- | :--- | :--- |
| P0 | ECOS, KOSIS, FRED(미국 금리), 관세/무역 공공 통계 | TradingEconomics, 반도체 민간 데이터 | 일/주/월 |
| P1 | ECOS(통화/금리), 금융위·공공포털 금리/대출 통계 | 증권사/KIS 보완 API | 일/월 |
| P2 | KRX 데이터(투자자수급/공매도), 금융위 주식·지수 API | 증권사 API 보완 | 일 |
| P3 | US: yfinance for US Financials, KR: Open DART (재무/공시) | 컨센서스 상용 데이터 | 분기/반기/연간 |
| P4 | 국토부 실거래가 API, REB(R-ONE), KOSIS 주택 통계 | KB 등 보조 지표 | 일/월 |

- 원칙: 공공·공식 소스를 canonical로 사용하고, 민간 소스는 결측 보완/교차검증에만 사용한다.
- 원칙: P2/P3/P4는 종목코드·기업코드·행정코드 표준 매핑 테이블을 먼저 확정하고 수집기를 붙인다.
- 원칙(US P3): `yfinance for US Financials`는 미국 기업의 공시 기반 재무제표를 구조화해 제공하는 공식/공공 파생 소스로 간주한다.
- 원칙(US P3 단일화): 미국 재무제표 수집은 별도 공식 공시 원문 재조회 없이 `yfinance for US Financials` 경로로 일원화한다.

### 4.6 다주기 시계열 통합 규격
- 기준 시계열은 `daily`이며 `monthly/quarterly` 지표는 `merge_asof(backward)`로 결합한다.
- `published_at`과 `effective_date`를 분리 저장해 데이터 누수(Data Leakage)를 방지한다.
- 리샘플 표준:
  - 금리/지수: `last`
  - 거래량/거래건수: `sum`
  - 확산지수·심리지수: `mean`
- 리비전 데이터는 `revision_flag=true`로 별도 버전 저장하고, QA 답변에는 `as_of_date`를 함께 표기한다.

### 4.7 US/KR 기업 뉴스 수집 운영 정책 (Q1/Q2 대응)
- 목적: 다음 질문에 근거 기반으로 답하기 위한 기업 마이크로 이벤트 커버리지 확보
  - "팔란티어 주가가 지금 많이 떨어지는데 왜 그런거야?"
  - "스노우 플레이크와 팔란티어 중에 어떤 게 더 전망이 좋아?"
- 운영 범위:
  - **Tier-1 상시 수집 (US)**: 미국 시가총액 상위 50개 종목
  - **Tier-1 상시 수집 (KR)**: 코스피 시가총액 상위 50개 종목
  - **Tier-2 온디맨드 수집 (US/KR 공통)**: 사용자 질의에 등장한 기업 (Tier-1 외 포함)
  - **Tier-3 승격 규칙**: 질의 빈도/포트폴리오 편입/변동성 급등 기준 충족 시 상시 수집으로 승격
- Tier-1 운영 규칙:
  - 월 1회 시총 기준 리밸런싱 (US Top 50 / 코스피 Top 50)
  - 이벤트 중심 수집: 실적/가이던스, 공시/재무 이벤트(US는 yfinance 기반, KR은 DART 공시), 대형 계약, 애널리스트 목표가/추정치 변경, 규제/소송/경영진 이슈
  - 중복 제거: `source_url + title_hash + published_at` 기준
- Tier-2 운영 규칙:
  - 질의 발생 즉시 최근 30~90일 백필
  - 질의 후 7일간 단기 추적 수집
  - 동일 기업 재질의 시 TTL 내 캐시 재사용 후 누락 구간만 증분 수집
- 소스 우선순위:
  - 1순위: US(yfinance for US Financials + yfinance 티커 뉴스/실적 이벤트), KR(Open DART 공시) + 기업 IR 보도자료/실적자료
  - 2순위: 라이선스 가능한 기업 뉴스 피드(Reuters/Bloomberg/WSJ 등)
  - 3순위: 기업 특화 보조 소스(예: 정부 계약 비중이 큰 기업의 계약 공시 데이터)
  - 구현 기준(US 재무제표 분석): `yfinance for US Financials` 라이브러리를 사용한다.
  - 구현 기준(US): 공식 공시 원문 직접 수집은 v1 범위에서 제외하고 yfinance 경로로 통일한다.
  - 구현 기준(KR 공시): 한국 주가 공시는 Open DART Open API를 사용한다.
  - API 스펙 문서: `hobot/docs/macro-trading/api_description/api_description_dart.md`
  - 인증키: `.env`의 `DART_API_KEY`를 사용한다.
- 출력/연결 규칙:
  - 문서 단위로 `symbol`, `event_type`, `published_at`, `effective_date`, `source`, `source_url`를 표준화 저장
  - Graph에서는 `Document -> Event -> Company(Symbol)` 연결을 강제해 Q1(급락 원인)과 Q2(기업 비교) 질의에 바로 사용
- 비용/품질 가드레일:
  - 전 종목 전수 수집은 하지 않고 US Top 50 + 코스피 Top 50 + 온디맨드 원칙 유지
  - 수집 실패/지연은 티어별 SLA로 모니터링하고 재시도 큐로 복구

### 4.8 뉴스 수집 운영 매트릭스 (사이트/빈도/수집량 고정)
- 원칙: 운영 중 임의 변경 금지, 변경 시 ADR/문서 업데이트를 선행한다.
- 기준 타임존: 한국 시간(KST), 해외 소스 원문 시각은 UTC 원본도 함께 저장한다.

| 트랙 | 사이트/소스 | 목적 | 수집 빈도 | 1회 수집량 | 일 최대 수집량 | 백필 범위 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Macro-Global | TradingEconomics Stream | 글로벌 매크로 헤드라인 | 1시간마다 | 최신 100건 | 2,400건 | 최근 7일 |
| US-Financials/Events | yfinance (US Financials + ticker news/earnings) | 미국 기업 재무/실적/이벤트 | 30분마다 | 기업당 최신 10건 | 기업당 120건 | 최근 30일 |
| KR-Disclosure | Open DART API | 한국 기업 공시 이벤트 | 10분마다 (KST 07:00~20:00), 30분마다 (그 외) | 최신 200건 | 10,000건 | 최근 30일 |
| US-IR | 기업 IR 보도자료/실적자료 (US Tier-1) | 실적/가이던스/계약/경영 이벤트 | 30분마다 | 기업당 최신 5건 | 기업당 40건 | 최근 90일 |
| KR-IR | 기업 IR 보도자료/실적자료 (KR Tier-1) | 실적/가이던스/계약/경영 이벤트 | 30분마다 | 기업당 최신 5건 | 기업당 40건 | 최근 90일 |
| Licensed-News | 라이선스 기업 뉴스 피드(도입 시) | 공시 외 해설/속보 보강 | 15분마다 | 최신 150건 | 12,000건 | 최근 14일 |
| On-Demand | 질의 기업 즉시 수집 (US/KR Tier-2) | 사용자 질문 대응 | 질의 발생 시 즉시 큐 등록(비동기) | 기업당 최대 300건 | 기업당 300건(요청당) | 최근 30~90일 + 이후 7일 추적 |

- 운영 모드 정합성:
  - v1(현재 운영): 거시 뉴스는 시간 단위 배치, 온디맨드는 비동기 큐 등록 후 증분 반영
  - v2(확장 운영): 4.8 표 기준의 소스별 세분 주기를 전면 적용

- 저장/중복 정책:
  - 중복 키: `source_url + normalized_title + published_at`
  - 동일 본문 유사도 0.95 이상은 중복으로 처리
  - 원문 보존기간: 180일, 구조화 이벤트/지표 연결 데이터: 2년
- 실패/재시도 정책:
  - 소스별 3회 재시도(1분/5분/15분), 실패 시 DLQ 적재
  - 동일 소스 30분 연속 실패 시 경보 발생
- 품질 하한선:
  - 일일 수집 성공률 98% 미만이면 운영 이슈로 분류
  - `published_at` 누락 문서는 QA 근거로 사용하지 않고 보류 큐로 이동

### 4.9 다국어 텍스트 적재/검색 규격 (US 원문 대응)
- US 원문 문서 적재 시 다음 필드를 필수로 저장한다.
  - `title_en`, `body_en`(원문)
  - `summary_ko`, `keywords_ko`(한국어 요약/키워드)
  - `language`, `translated_at`, `translation_model`
- 검색 전략은 `Hybrid(Keyword + Vector)`를 기본으로 한다.
  - 한국어 질의는 `summary_ko/keywords_ko` 키워드 검색과 다국어 벡터 검색을 동시 적용
  - 영어 질의는 원문 필드 우선 검색 후 필요 시 한국어 필드 보조
- 엔터티 정규화(Entity Resolution):
  - 회사명 영문/한글 Alias를 단일 Company 노드로 통합한다.
  - 예시: `Apple`, `애플` -> `Company(symbol=AAPL, country_code=US)`

---

## 5. 온톨로지 스키마 확장안

### 5.1 신규/강화 엔터티
- `Country` (1차 운영 범위: US, KR)
- `Company` (종목코드, 거래소, 국가, 섹터, 시총 티어)
- `RegionAlias` (행정동/기관코드/별칭 -> 법정동 Canonical 매핑)
- `CompanyAlias` (영문명/한글명/약칭 -> Company 매핑)
- `IndicatorSeries` (지표 정의)
- `IndicatorObservation` (실측값 시계열)
- `PolicyAction` (금리 인상/인하, 유동성 조치, 재정정책)
- `MacroEvent` (경제 이벤트)
- `Document` / `Evidence` / `Claim`
- `MarketInstrument` (지수/금리/환율/원자재)
- `RealEstateRegion` (시도/시군구 코드, 행정구역 메타)
- `PropertyType` (아파트/연립/단독/오피스텔 등)
- `HousingTransaction` (거래일, 가격, 면적, 거래유형)
- `HousingIndicatorSeries` (가격지수, 전세가율, 미분양, 공급지표 등)
- `HousingPolicy` (대출규제, 세제, 공급정책)

### 5.2 핵심 관계
- `(IndicatorSeries)-[:FOR_COUNTRY]->(Country)`
- `(IndicatorObservation)-[:OF_SERIES]->(IndicatorSeries)`
- `(MacroEvent)-[:IN_COUNTRY]->(Country)`
- `(Company)-[:IN_COUNTRY]->(Country)`
- `(RegionAlias)-[:MAPPED_TO]->(RealEstateRegion)`
- `(CompanyAlias)-[:ALIAS_OF]->(Company)`
- `(PolicyAction)-[:BY_INSTITUTION]->(Institution)`
- `(Document)-[:ABOUT_COUNTRY]->(Country)`
- `(Document)-[:ABOUT_COMPANY]->(Company)`
- `(MacroEvent)-[:AFFECTS_COMPANY]->(Company)`
- `(Evidence)-[:SUPPORTS]->(Claim)`
- `(Claim)-[:ABOUT]->(MacroEvent|IndicatorSeries|PolicyAction)`
- `(RealEstateRegion)-[:IN_COUNTRY]->(Country)`
- `(HousingTransaction)-[:IN_REGION]->(RealEstateRegion)`
- `(HousingTransaction)-[:OF_PROPERTY_TYPE]->(PropertyType)`
- `(HousingIndicatorSeries)-[:FOR_REGION]->(RealEstateRegion)`
- `(HousingPolicy)-[:TARGETS_REGION]->(RealEstateRegion)`
- `(Claim)-[:ABOUT]->(HousingTransaction|HousingIndicatorSeries|HousingPolicy)`

### 5.3 표준 필드
- `country_code` (ISO-2)
- `symbol`, `exchange`, `corp_code`
- `dart_code` (KR 전용), `isin` (선택적)
- `region_type` (`legal_dong`/`admin_dong`/`custom`)
- `legal_dong_code_10`, `admin_dong_code_10`, `canonical_region_code`
- `alias`, `alias_lang`
- `source`, `source_url`, `license`
- `frequency` (daily/weekly/monthly/quarterly)
- `unit`, `seasonal_adjustment`, `revision_flag`
- `scope_version` (예: `USKR_v1`)
- `region_code` (시도/시군구 표준 코드)
- `property_type`, `transaction_type` (매매/전세/월세)
- `building_area_m2`, `contract_date`, `completion_year`

### 5.4 기업 식별자(Company PK) 규칙
- Company Primary Key는 실운영 조회 효율 기준으로 `(country_code, symbol)`을 사용한다.
  - US: `symbol` = 티커(예: AAPL)
  - KR: `symbol` = 6자리 종목코드(예: 005930)
- `corp_code`/`dart_code`는 KR 공시 연계를 위한 속성으로 관리한다.
- `ISIN`은 선택적 보조 식별자로 저장하며, 미존재를 허용한다.
- 회사명 다국어 표기는 `CompanyAlias`로 분리해 동의어/별칭 탐색에 사용한다.

---

## 6. Graph QA 시스템 설계

### 6.1 질의 타입
- 단일 국가 질의(US): "최근 미국 고용 둔화 신호는?"
- 단일 국가 질의(KR): "한국 물가 하방 압력은?"
- 국가 비교 질의: "미국 vs 한국 금리 경로 차이와 주식시장 영향?"
- 전이 경로 질의: "미국 장기금리 급등이 한국 증시에 미치는 경로?"
- 한국 부동산 질의: "서울 아파트 전세가율 추세와 매매가격 관계는?"
- 한국 부동산 정책 질의: "최근 대출 규제가 거래량에 준 영향은?"

### 6.1.1 우선 예상 질문 세트 (사용자 요청 기반, 필수 지원)
- "팔란티어 주가가 지금 많이 떨어지는데 왜 그런거야?"
- "스노우 플레이크와 팔란티어 중에 어떤 게 더 전망이 좋아?"
- "현재 한국 부동산 시장 요약해줘."
- "한국 주식 중 유망한 섹터 추천해줘."
- "한국 원달러 환율이 왜 이렇게 급등하는 걸까?"
- "언제쯤 부동산을 매수/매도해야할까?"

### 6.2 검색/추론 파이프라인
1. 질문 파싱: 국가(US/KR), 시간, 테마, 지역(시도/시군구), 부동산 유형 추출
2. 후보 회수: Graph + Full-text + 시계열 조건 검색
3. 근거 정렬: 최신성/신뢰도/질문 적합도 기반 rerank
4. 답변 생성: 템플릿 기반 + 근거 ID 인용
5. 검증: 근거 없는 문장 필터링 및 불확실성 태깅

### 6.3 출력 규격(필수)
- 답변 요약
- 핵심 근거 3~10개 (지표/문서/이벤트)
- 시간 범위 명시
- 스코프 명시 (`US`, `KR`, `US-KR`)
- 지역 명시 (`전국`, `시도`, `시군구`) 및 부동산 유형 명시
- 확신도(High/Medium/Low)
- 추천/타이밍 질문의 경우 단정적 지시 대신 조건형 시나리오(예: 금리·거래량·가격지표 임계값 기반)로 제시

### 6.3.1 데이터 부재/온디맨드 대응 시나리오 (필수)
- 기본 정책은 C안(절충안)으로 고정한다.
  - 1차 응답: 현재 보유 근거로 가능한 범위의 설명을 먼저 제공
  - 2차 안내: "최신 데이터 수집을 예약/진행 중" 상태를 명시
  - 3차 갱신: 수집 완료 후 근거 기반 답변으로 자동 보강(또는 재질의 시 우선 반환)
- 금지 정책:
  - 단순 "데이터 없음"으로 종료하지 않는다.
  - 근거 없이 LLM 사전지식만으로 확정적 결론을 내리지 않는다.
- 응답 메타 필드:
  - `data_freshness`: `fresh|stale|collecting`
  - `collection_eta_minutes`
  - `used_evidence_count`

### 6.4 필수 질문 답변 JSON 스키마 (회귀 테스트 표준)
- 적용 범위: 6.1.1의 필수 예상 질문 6개
- 목적: 답변 형식/근거/가드레일을 강제해 품질 회귀를 자동 검증

```json
{
  "question_id": "Q1|Q2|Q3|Q4|Q5|Q6",
  "question_text": "string",
  "answer_type": "explain_drop|compare_outlook|market_summary|sector_recommendation|fx_driver|timing_scenario",
  "scope": {
    "country_code": "US|KR|US-KR",
    "region_code": "string|null",
    "property_type": "string|null",
    "time_range": "e.g. 30d",
    "as_of_date": "YYYY-MM-DD"
  },
  "summary": "string",
  "drivers": [
    {
      "label": "string",
      "direction": "up|down|mixed",
      "impact_horizon": "short|medium|long",
      "confidence": 0.0
    }
  ],
  "evidences": [
    {
      "id": "event/doc/indicator/evidence id",
      "type": "indicator|event|document|housing",
      "source": "string",
      "date": "YYYY-MM-DD",
      "snippet": "string"
    }
  ],
  "scenarios": [
    {
      "name": "base|bull|bear",
      "conditions": ["string"],
      "implication": "string"
    }
  ],
  "recommendation_guardrail": {
    "is_direct_buy_sell_instruction": false,
    "risk_notice": "string",
    "decision_checklist": ["string"]
  },
  "confidence": {
    "level": "High|Medium|Low",
    "score": 0.0
  },
  "limitations": ["string"]
}
```

- `Q1` 팔란티어 급락 원인: `answer_type=explain_drop`, `scope.country_code=US`
- `Q2` 스노우플레이크 vs 팔란티어: `answer_type=compare_outlook`, `scope.country_code=US`
- `Q3` 한국 부동산 시장 요약: `answer_type=market_summary`, `scope.country_code=KR`
- `Q4` 한국 유망 섹터: `answer_type=sector_recommendation`, `scope.country_code=KR`
- `Q5` 원달러 급등 원인: `answer_type=fx_driver`, `scope.country_code=US-KR`
- `Q6` 부동산 매수/매도 시점: `answer_type=timing_scenario`, `scope.country_code=KR`

---

## 7. 단계별 실행 로드맵

### Phase 0 (완료/즉시) - US Focus 안정화
- 경제 분석 입력을 미국 중심으로 고정
- 그래프 컨텍스트 국가 필터를 US 우선으로 적용

### Phase 1 (2주) - 데이터/스키마 기반 공사
- `country_code` 표준화 마이그레이션 설계 및 백필 실행
- Country 노드 운영 범위를 US/KR로 고정
- 누락/오분류 국가 데이터 품질 리포트 생성

### Phase 2 (3주) - US/KR 정량 데이터 확장
- 한국 핵심 지표 수집기 추가 (성장/물가/고용/금리/유동성)
- 미국 지표는 FRED 기반 유지 + 필요한 공백 지표 보강
- 한국 부동산 핵심 시계열 수집기 추가 (가격/거래/공급/미분양/금융)
- 지표 단위/주기 정규화 및 결측 처리 룰 확정

### Phase 2.5 (2주) - 한국 주식/기업 데이터 확장 (P2/P3)
- KRX/금융위 기반 투자자수급·공매도·지수·종목 데이터 수집기 추가
- Open DART 기반 기업 펀더멘털 수집기 추가 (기업코드 캐시 포함)
- 컨센서스/추정치 데이터는 라이선스 검토 후 보조 소스로 단계적 온보딩
- 종목코드(`symbol`)·기업코드(`corp_code`)·섹터 분류 정합성 검증

### Phase 3 (3주) - US/KR 텍스트/정책 데이터 확장
- Fed/BOK 및 미국/한국 정책기관 문서 파이프라인 추가
- 국토교통부/한국부동산원/주택금융 관련 문서 파이프라인 추가
- US 시총 상위 50개 + 코스피 시총 상위 50개 기업 대상 공시/IR/핵심 기업뉴스 파이프라인 추가
- 사용자 질의 기업(US/KR) 온디맨드 백필(30~90일) + 7일 추적 수집 트리거 추가
- 문서-이벤트-지표 연결 관계 강화
- 중복/노이즈 제거 규칙 적용

### Phase 4 (2~3주) - QA 엔진 고도화
- 질의 스키마 확장: `country in {US, KR, US-KR}`, `compare_mode`
- 미국-한국 비교/전이 경로 답변 템플릿 구현
- 한국 부동산 지역/유형 필터 답변 템플릿 구현
- 근거 인용 강제 및 불확실성 표기

### Phase 5 (2주) - 평가/운영 전환
- US/KR QA 골든셋 구축 및 자동 회귀 테스트
- US/KR Freshness/커버리지 대시보드 운영
- 한국 부동산 골든셋(가격/거래/정책) 구축 및 회귀 테스트 추가
- 운영 가이드/장애 대응 플레이북 확정

---

## 8. KPI / 수용 기준

### 8.1 데이터 KPI
- US/KR 핵심 지표 커버리지 95%+
- US/KR 일/주/월 신선도 SLA 충족률 95%+
- 국가 매핑 정확도 99%+
- 한국 부동산 핵심 지표 커버리지 90%+
- 한국 부동산 지역 매핑 정확도 98%+
- P0~P4 도메인별 최소 지표 충족률 90%+
- P2(주식 마이크로) 일간 수집 성공률 98%+
- P3(DART) 분기 공시 반영 지연 D+1 이내 95%+
- P4(실거래/미분양/공급) 월간 지표 반영 지연 D+2 이내 95%+
- 뉴스 수집 신선도 SLA: Macro 1시간, 공시/기업이벤트 30분, 질의 온디맨드 큐 등록 5분·증분 반영 30분 이내 95%+
- 다국어 검색 재현율(한국어 질의 -> 영어 원문 근거 회수) Top-10 Recall 90%+

### 8.2 QA KPI
- 골든셋 기준 정답률(또는 전문가 적합도) 80%+
- 근거 인용 누락률 2% 이하
- 미국-한국 비교 질의 응답 시간 P95 < 8초
- 한국 부동산 질의 정답률(전문가 적합도) 80%+

### 8.3 운영 KPI
- 파이프라인 일일 성공률 99%+
- 장애 탐지/알림까지 5분 이내
- 재처리 완료까지 2시간 이내

---

## 9. 리스크 및 대응

- **라이선스/비용 리스크**: 소스별 계약/비용 검토 후 우선순위 적용
- **스키마 드리프트**: 원천 변경 감지 테스트 + 파서 버전 관리
- **국가 분류 오류**: US/KR 고정 스코프 검증 및 수동 검수 큐 운영
- **용어 불일치(한영 혼합)**: KR 지표/정책 용어 사전 운영
- **부동산 지역/유형 정합성 리스크**: 행정구역 코드 표준화 및 거래유형 정규화 룰 운영
- **LLM 환각**: 근거 없는 문장 차단 규칙/검증기 적용

---

## 10. 즉시 실행 백로그 (이번 스프린트)

- [ ] US/KR 데이터 소스 인벤토리 작성 (현재/후보/라이선스/비용/주기)
- [ ] US/KR 표준 코드 및 용어 사전 확정
- [ ] `country` vs `country_code` 사용처 전수 조사 문서화
- [ ] US/KR 핵심 지표 최소 세트 정의 (국가별 25~35개)
- [ ] 한국 부동산 핵심 지표 세트 정의 (가격/거래/공급/미분양/금융)
- [ ] 한국 부동산 지역 코드 매핑 테이블 설계 (전국/시도/시군구)
- [ ] KR 지역 코드 Canonical 규칙 확정(법정동 10자리 기준) 및 행정동/기관코드 매핑 테이블 구축
- [ ] 부동산 거래 스키마 설계 (`property_type`, `transaction_type`, `area`, `price`)
- [ ] P0 온보딩: ECOS/KOSIS/FRED/환율/반도체 가격 수집기 및 코드 매핑
- [ ] P1 온보딩: 본원통화/M1/M2/금리/대출 지표 수집기와 파생지표(통화승수 등) 정의
- [ ] P2 온보딩: KRX 투자자수급·공매도·신용융자 일간 수집 파이프라인 구축
- [ ] P3 온보딩: US는 `yfinance for US Financials`, KR은 Open DART 재무제표 수집기(사업/반기/분기 보고서 코드 포함) 구축 (`hobot/docs/macro-trading/api_description/api_description_dart.md` 기준, `.env` `DART_API_KEY` 사용)
- [ ] P4 온보딩: 국토부 실거래 + REB + 공급/미분양 월간 파이프라인 구축
- [ ] US Top 50 + 코스피 Top 50 종목 리스트 자동 갱신 배치(월 1회) 및 티어 테이블 설계
- [ ] Tier-1 기업 이벤트 수집기 구축(US: yfinance + IR 보도자료, KR: Open DART + IR 보도자료 + 라이선스 뉴스)
- [ ] 질의 기반 Tier-2 온디맨드 수집 트리거 구축(기업명 추출 -> 비동기 큐 등록 -> 30~90일 백필 -> 7일 추적, US/KR 공통)
- [ ] 기업 이벤트 표준 스키마 확정(`symbol`, `event_type`, `published_at`, `effective_date`, `source_url`)
- [ ] US 원문 적재 시 `summary_ko`/`keywords_ko` 필수화 및 Hybrid 검색 파이프라인 반영
- [ ] CompanyAlias/RegionAlias 기반 Entity Resolution 파이프라인 구축(영문/한글 동의어 통합)
- [ ] 4.8 뉴스 수집 운영 매트릭스의 빈도/수집량/백필 범위를 스케줄러 상수로 코드 고정
- [ ] 소스별 일 최대 수집량 초과 방지(rate/cap guard) 및 DLQ/재시도 정책 구현
- [ ] `Company` 엔터티/관계(`ABOUT_COMPANY`, `AFFECTS_COMPANY`) 마이그레이션 및 인덱스 설계
- [ ] 온디맨드 질의 응답 정책 추가(C안 고정: 선응답 + 수집 진행 안내 + 완료 후 보강)
- [ ] 다주기 통합: `merge_asof` 기반 daily anchor 조인 모듈 및 누수 방지 테스트 추가
- [ ] 리비전 관리: `effective_date/published_at/revision_flag` 저장 및 백필 전략 수립
- [ ] Graph RAG US/KR 질의 API 스펙 초안 작성
- [ ] 골든 질의 160개(US 단일/KR 단일/US-KR 비교/KR 부동산) 초안 수집
- [ ] 필수 예상 질문 6개를 골든셋에 고정하고 회귀 테스트 케이스로 등록
- [ ] 6.4 JSON 스키마 기반 응답 검증기(필수 필드/타입/가드레일) 추가

---

## 11. 의사결정 로그 (ADR)

### ADR-001
- 결정: 트레이딩 의사결정 엔진은 `US equities first` 유지
- 이유: 사용자 목적이 미국 주식 투자이며 성과/리스크 일관성 확보가 우선

### ADR-002
- 결정: QA 엔진 1차 스코프는 US/KR로 제한
- 이유: 데이터 품질과 운영 복잡도를 통제하면서 정확도를 높이기 위함

### ADR-003
- 결정: 국가 식별자는 `country_code`를 canonical로 사용
- 이유: 질의 필터와 데이터 정합성 일관성 확보

### ADR-004
- 결정: 스코프 외 국가 질의는 명시적으로 "현재 지원 범위 아님"으로 처리
- 이유: 잘못된 답변(환각/추정) 방지

### ADR-005
- 결정: 한국 부동산을 온톨로지 1급 도메인으로 채택
- 이유: 한국 경제/금융 사이클 해석에서 부동산의 구조적 영향이 크기 때문

### ADR-006
- 결정: 추천/매수·매도 시점 질문은 확정 지시형이 아닌 조건형 시나리오 답변으로 제공
- 이유: 고위험 금융 의사결정에서 근거 기반 설명 가능성과 운영 안전성을 함께 확보하기 위함

### ADR-007
- 결정: 트레이딩 엔진(US 중심)과 온톨로지 챗봇(US/KR + KR 부동산)은 진입점과 적용 범위를 분리 운영한다.
- 이유: 동일 플랫폼 내 목적이 다른 경로의 정책 충돌을 방지하고, 운영 책임 경계를 명확히 하기 위함

### ADR-008
- 결정: US 기업 재무제표 분석의 기본 소스로 `yfinance for US Financials`를 채택하고, 이를 공시 기반 공식/공공 파생 소스로 취급한다.
- 이유: 대량 수집/정규화 효율을 확보하고, US 재무 데이터 수집 경로를 단일화해 운영 복잡도를 줄이기 위함

### ADR-009
- 결정: 질의 기반 온디맨드 수집은 동기 블로킹이 아닌 비동기 큐 방식으로 운영한다.
- 이유: 현재 배치/스케줄러 구조와 충돌 없이 안정적으로 챗봇 응답 시간을 유지하기 위함

### ADR-010
- 결정: KR 부동산 지역 Canonical ID는 법정동 코드(10자리)로 통일하고, 행정동/기관코드는 매핑 관계로 처리한다.
- 이유: 코드 변동성이 낮은 기준을 중심으로 데이터 정합성과 질의 확장 일관성을 확보하기 위함

### ADR-011
- 결정: 다국어 검색은 US 원문 + 한국어 요약/키워드 병행 저장 후 Hybrid 검색으로 운영한다.
- 이유: 한국어 질의에서 영어 원문 근거 회수율(Recall) 저하를 방지하기 위함

### ADR-012
- 결정: Company PK는 `(country_code, symbol)`로 고정하고, KR `dart_code/corp_code`는 속성으로 관리한다.
- 이유: 트레이딩/질의 조회 성능을 유지하면서 공시 연계를 안정적으로 처리하기 위함

### ADR-013
- 결정: 온디맨드 데이터 부재 시 C안(선응답 + 수집 진행 안내 + 후속 보강) UX를 기본 정책으로 사용한다.
- 이유: 사용자 경험을 해치지 않으면서 근거 기반 답변 원칙을 유지하기 위함

---

## 12. 변경 관리

- 본 문서를 **US/KR Ontology/Macro Graph 개선의 기준 문서**로 사용한다.
- 스프린트 종료 시 다음 항목을 반드시 갱신한다.
  - 완료/미완료 백로그
  - KPI 달성 현황
  - 리스크 상태
  - ADR 추가/수정

---

## 13. US/KR 최소 지표 세트 v1 (보고서 반영)

### 13.1 P0/P1 (거시·유동성)
- 경기선행지수 순환변동치 (월, ECOS/KOSIS)
- 제조업 PMI (월, S&P Global/공식 배포)
- USD/KRW 환율 (일, ECOS/시장 데이터)
- 미국 2Y/10Y 국채금리 (일, FRED)
- 본원통화/협의통화(M1)/광의통화(M2) (월, ECOS)
- 한국 기준금리/국고채 3Y·10Y (일/월, ECOS)

### 13.2 P2/P3 (주식·기업)
- KOSPI/KOSDAQ 지수, 업종지수 (일, 금융위/거래소)
- 투자자별 순매수 (일, KRX)
- 공매도 거래대금·잔고 (일, KRX)
- 신용융자 잔고 (일, 공공/증권사)
- DART 재무(매출/영업이익/순이익/자산/부채/ROA) (분기, Open DART)
- US Financials(매출/영업이익/순이익/자산/부채/ROA) (분기/연간, yfinance for US Financials)
- US 개별종목 가격/거래량(OHLCV) 및 변동성 지표 (일, yfinance)
- US 실적 발표일/실적 서프라이즈(EPS actual vs estimate) (분기, yfinance)
- US 밸류에이션(PE/PS/EV/EBITDA) 및 추정치 변화(가능 범위) (일/주, yfinance)

### 13.3 P4 (부동산)
- 아파트/연립/오피스텔 실거래가 (일/월, 국토부)
- 전세/월세 실거래 지표 (월, 국토부)
- 주택가격지수·전세가율·매수심리지수 (월, REB/KB 보완)
- 인허가/착공/준공 (월, 국토부)
- 미분양 주택 수 (월, 국토부/KOSIS)

### 13.4 분석 연결 규칙
- P0/P1 변화가 P2 밸류에이션 및 수급에 미치는 경로를 기본 템플릿으로 제공한다.
- P2 수익/변동성이 P4 심리·거래량으로 전이되는 시차를 1/3/6개월 윈도우로 추적한다.
- P3 실적(확정)과 컨센서스(예상)를 분리 저장하고, 답변에는 데이터 성격을 명시한다.
