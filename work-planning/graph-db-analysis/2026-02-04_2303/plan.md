# Hobot Service: 거시경제(FRED) + 경제뉴스 기반 Macro Knowledge Graph 고도화 계획 (Neo4j)

## 1. 개요 (Overview)
본 문서는 `hobot-service`가 현재 수집 중인 **FRED 거시경제 지표(정형)** + **경제 뉴스(비정형)** 를 Neo4j 기반 **Macro Knowledge Graph(MKG)** 로 통합하여,
단순 요약/상관관계를 넘어 다음을 가능하게 하는 개선 방안을 제시합니다.

* **이벤트 → 지표(관측치/파생지표) 연결**: “이 뉴스/이벤트가 어떤 거시 변수에 어떤 방향으로(상승/하락) 영향을 주는가?”
* **거시 내러티브(Story) 추적**: 같은 주제의 뉴스를 묶어 “현재 시장이 믿는 이야기”를 그래프로 축적/검색
* **파급 경로(Ripple Path) 추론**: Event → Theme → Indicator → MarketRisk 등 영향 경로를 질의/설명
* **GraphRAG 기반 LLM 분석 고도화**: 답변을 “그래프 근거 + 원문 증거”에 고정(anchoring)해서 할루시네이션 감소

참고: `work-planning/add-news-graph/2026-02-04_2208/plan.md`에 **Macro Graph(UI)/백엔드 프록시 연동 작업**은 완료된 상태이며, 이제 “데이터/분석 그래프”를 채우는 단계로 전환합니다.

## 2. 현황 (Current Status)

### 2.1 이미 갖춰진 것
* **뉴스 수집/저장**: `daily_news_agent.py`, `news_manager.py` 등으로 뉴스 수집 및 요약 저장
* **거시 지표 수집/저장**: FRED 등 시계열 수집 및 저장
* **Neo4j 프록시 & UI**:
    * `/api/neo4j/query`, `/api/neo4j/health` 존재 (database: `architecture` | `macro`, legacy: `news`)
    * Ontology 하위 메뉴에 **Macro Graph 화면** 존재
    * **본 계획(MKG)은 Neo4j `macro` database에 적재/조회**하여 기존 UI/프록시를 그대로 재사용 (legacy 명칭: `news`)

### 2.2 현재 수집 중인 데이터 (Inventory)

#### (A) FRED 지표 (현재 보유)
아래 지표들은 “거시 상태(state)”를 설명하는 핵심 축이며, 그래프에서는 `EconomicIndicator` + `IndicatorObservation` + `DerivedFeature`로 분해해 사용합니다.

* **금리/커브**: `DGS10`, `DGS2`, `FEDFUNDS`, `T10Y2Y`, `DFII10`
* **물가/기대인플레**: `CPIAUCSL`, `PCEPI`, `PCEPILFE`, `T10YIE`
* **성장/고용**: `GDP`, `UNRATE`, `PAYEMS`, `GACDFSA066MSFRBPHI`, `NOCDFSA066MSFRBPHI`, `GAFDFSA066MSFRBPHI`
* **유동성(연준/재무부)**: `WALCL`, `WTREGEN`, `RRPONTSYD`, `NETLIQ`
* **리스크/금융여건**: `BAMLH0A0HYM2`, `VIXCLS`, `STLFSI4`

#### (B) 경제 뉴스 (예: TradingEconomics Stream)
현재 뉴스 레코드는 대략 다음 필드 구조를 갖습니다.

* `id`, `title`, `link`, `source`
* `country`, `category`, `description`
* `published_at`, `collected_at`
* `*_ko` 번역 필드

→ MKG에서 핵심은 “뉴스 원문(Document)에서 **(1) 사건(Event)** 과 **(2) 정량 팩트(수치/기간/전월 대비)**, **(3) 원인/드라이버(Claim)** 를 추출해 그래프 구조로 저장하는 것입니다.

### 2.3 현재 한계
* 뉴스와 지표가 분리되어 “뉴스-지표 영향”을 구조적으로 질의하기 어려움
* LLM 분석이 프롬프트 텍스트 중심이라 과거 근거/인과 사슬을 누적/재사용하기 어려움
* “수치 팩트”와 “해석(원인 주장)”이 섞여 있어 신뢰도/근거 관리가 어려움

## 3. 목표 (What to Build)

### 3.1 사용자 질문을 그래프로 답하기
예시 질문을 “그래프 질의 + 근거 문서”로 답할 수 있어야 합니다.

* “최근 7일간 인플레이션 리스크를 높인 이벤트/뉴스는 무엇이며 어떤 지표와 연결되는가?”
* “유동성 악화(NETLIQ 하락)와 관련된 뉴스/이벤트의 상위 원인은 무엇인가?”
* “남아공 외환보유액 뉴스가 의미하는 거시 테마(대외건전성/통화/리스크)는 무엇인가?”
* “금리 인상 → 신용 스프레드 확대 → 금융 스트레스 상승” 같은 경로가 최근에도 관측되는가?

### 3.2 성공 지표 (간단 KPI)
* **링킹 커버리지**: News → Theme 연결 비율, News → Indicator 연결 비율
* **근거 보존**: 모든 `AFFECTS/CAUSES` 관계가 최소 1개의 `Evidence`(문장/스팬)와 연결
* **질의 응답 품질**: GraphRAG 답변에서 “근거 노드/문서”를 함께 리턴

## 4. 그래프 설계 (Schema / Ontology)

### 4.1 설계 원칙
* **MVP는 가볍게**: FIBO는 “개념 정렬 가이드”로만 사용하고, Neo4j에는 MKG에 필요한 최소 스키마부터 도입
* **시간이 1급 시민**: 대부분의 노드/관계는 `event_time`, `period_start/end`, `published_at` 등 시간 속성을 가짐
* **팩트와 주장 분리**: “수치 팩트(Fact)”와 “원인/영향 주장(Claim)”을 분리해 신뢰도를 관리
* **증거(원문 스팬) 저장**: LLM이 만든 구조는 항상 “근거 문장”을 연결(검증/디버깅 가능)
* **엔티티 정규화가 0순위**: "연준/Fed/FOMC" 같은 표기가 분리되면 그래프 가치가 급락하므로, NEL(Named Entity Linking) + canonical id 매핑을 초기부터 포함
* **빈티지(Revision) 우선**: 거시 지표는 계속 수정되므로 ALFRED(vintage) 기반으로 “as_of_date 기준 가용 데이터”를 조회하는 설계를 전제로(룩어헤드 편향 차단)
* **관계는 동적 가중치로 운영**: `AFFECTS`는 고정 지식이 아니라 최근 90/180일 슬라이딩 윈도우로 재계산/이력화(비정상성 대응)

### 4.2 MVP 노드/관계 (권장)

#### 노드 (Nodes)
* `Document` : 뉴스 원문(또는 요약) 1건
    * key: `doc_id` (예: `source:id`)
    * props: `title`, `url`, `source`, `published_at`, `country`, `category`, `lang`
* `Event` : 뉴스에서 추출된 사건(정책/지표발표/충격/변화)
    * key: `event_id` (doc_id 기반 deterministic hash 권장)
    * props: `type`, `summary`, `event_time`, `country`
* `MacroTheme` : 거시 주제(Inflation/Growth/Liquidity/Risk 등)
    * key: `theme_id` (slug)
* `Entity` : 표준화된 명명 엔티티(기관/인물/지명 등) — 필요 시 `Organization`, `Person` 등 추가 라벨 부여
    * key: `canonical_id` (예: Wikidata QID / Wikipedia page id / 내부 KB id)
    * props: `name`, `entity_type`, `country?`, `source_kb?`
* `EntityAlias` : 엔티티 별칭(표현/언어별 표기)
    * key: `(canonical_id, alias, lang)`
    * props: `alias`, `lang`, `source?`
* `EconomicIndicator` : FRED 시리즈(또는 외부 지표)
    * key: `indicator_code` (FRED series id)
    * props: `name`, `unit`, `frequency`, `source="FRED"`, `country="US"`
* `IndicatorObservation` : 특정 일자의 관측치(시계열 포인트) — ALFRED 사용 시 빈티지까지 포함
    * key: `(indicator_code, obs_date, vintage_date?)`
    * props: `value`, `obs_date`, `vintage_date?`(=as-of), `release_date?`
* `DerivedFeature` : 파생 피처(전월대비/YoY/Z-score/변곡 등)
    * key: `(indicator_code, feature_name, obs_date)`
* `Fact` : 뉴스에서 추출된 정량 사실(값/기간/이전값/변화)
    * props: `metric`, `value`, `prev_value`, `unit`, `period`
* `Claim` : “~때문에 증가했다” 같은 인과/영향 주장
    * props: `polarity`(+, -, mixed), `confidence`
* `Evidence` : Claim/Fact를 뒷받침하는 문장/스팬
    * props: `text`, `offset_start?`, `offset_end?`, `lang`

#### 관계 (Relationships)
* `(Document)-[:MENTIONS]->(Event|Fact|Entity|EconomicIndicator|MacroTheme)`
* `(Document)-[:HAS_EVIDENCE]->(Evidence)`
* `(Evidence)-[:SUPPORTS]->(Fact|Claim)`
* `(Entity)-[:HAS_ALIAS]->(EntityAlias)`
* `(Event)-[:ABOUT_THEME]->(MacroTheme)`
* `(EconomicIndicator)-[:BELONGS_TO]->(MacroTheme)`
* `(Event)-[:AFFECTS {polarity, weight, confidence, horizon_days}]->(EconomicIndicator|MacroTheme)`
* `(Claim)-[:ABOUT]->(Event|EconomicIndicator|MacroTheme)`
* `(Event)-[:CAUSES {confidence}]->(Event)`
* `(EconomicIndicator)-[:HAS_OBSERVATION]->(IndicatorObservation)`
* `(IndicatorObservation)-[:HAS_FEATURE]->(DerivedFeature)`

### 4.3 FRED 지표 → MacroTheme 매핑 (초기 Seed)
초기에는 rule-based로 테마를 고정(정확도 높고 유지보수 쉬움)하고, 이후에 LLM 분류/확장으로 넘어갑니다.

* `Rates`(금리): DGS10, DGS2, FEDFUNDS, T10Y2Y, DFII10
* `Inflation`(물가): CPIAUCSL, PCEPI, PCEPILFE, T10YIE
* `Growth`(성장): GDP, GACDFSA066MSFRBPHI, NOCDFSA066MSFRBPHI, GAFDFSA066MSFRBPHI
* `Labor`(고용): UNRATE, PAYEMS
* `Liquidity`(유동성): WALCL, WTREGEN, RRPONTSYD, NETLIQ
* `Risk`(리스크): BAMLH0A0HYM2, VIXCLS, STLFSI4

### 4.4 제약/인덱스 (Constraints/Indexes)
* `EconomicIndicator(indicator_code)` UNIQUE
* `Document(doc_id)` UNIQUE
* `MacroTheme(theme_id)` UNIQUE
* `Entity(canonical_id)` UNIQUE
* `EntityAlias(canonical_id, alias, lang)` UNIQUE
* `IndicatorObservation(indicator_code, obs_date, vintage_date)` UNIQUE (ALFRED 적용 시)
* 자주 조회하는 `published_at`, `country`, `category`, `event_time` 인덱스

## 5. 데이터 파이프라인 (Ingestion / Linking)

### 5.1 FRED → Graph 적재
* **Seed(1회)**: 현재 보유한 FRED 지표 목록을 `EconomicIndicator`로 등록 + `MacroTheme` 연결
* **Daily/Periodic Update**:
    * 최신 관측치(Observation) upsert
    * 파생 피처 계산(최소: `Δ`, `Δ%`, `zscore(rolling)`, `yoy/mom` 등) 후 `DerivedFeature`로 저장
* **Revision/Vintage (필수 권장)**:
    * FRED 값은 수정되므로 **ALFRED(vintage) 데이터**를 함께 적재해 `(obs_date, vintage_date)` 단위로 기록
    * 모델 검증/학습/LLM 분석에서는 `as_of_date`를 입력으로 받아 **해당 시점에 이용 가능했던 최신 빈티지**만 조회(룩어헤드 편향 차단)

### 5.2 News → Graph 적재 (핵심)
뉴스 1건을 다음 3가지 레이어로 구조화합니다.

1) **Document 레이어**: 원문 메타데이터 저장(중복 방지: `doc_id=source:id`)
2) **Extraction 레이어**: Event / Fact / Claim / Evidence 생성
3) **Linking 레이어**: Event ↔ Theme ↔ Indicator 연결 + AFFECTS/CAUSES 관계 생성

#### LLM 추출 출력(JSON) 최소 스펙 (권장)
* `events[]`: {`type`, `summary`, `event_time`, `country`, `themes[]`}
* `facts[]`: {`metric`, `value`, `unit`, `period`, `prev_value?`, `direction?`, `evidence_text`}
* `claims[]`: {`subject`, `predicate`, `object`, `polarity`, `confidence`, `evidence_text`}
* `links[]`: {`from`, `to`, `rel`, `polarity`, `weight`, `confidence`, `horizon_days`, `evidence_text`}

#### Entity Resolution (정규화)
* **Country/Category 정규화**: `South Africa` → `ZA`, `Foreign Exchange Reserves` → 표준 카테고리
* **Named Entity Linking(NEL) 강화(필수)**:
    * alias/표현(“연준”, “Fed”, “FOMC”)을 **canonical entity**로 수렴시키는 프로세스를 분리(추출 → 후보 생성 → 판별/연결 → MERGE)
    * canonical id는 가능한 한 외부 KB(Wikipedia/Wikidata) 또는 내부 KB로 고정해 재사용/검증 가능하게 유지
* **Indicator linking**:
    * US 거시(금리/물가/고용/유동성 등)는 FRED로 직접 연결
    * 비미국/외부 지표(예: 남아공 외환보유액)는 `ExternalIndicator`(또는 `EconomicIndicator` with `source="TradingEconomics"`)로 확장

### 5.3 이벤트-지표 “영향”을 정량화하는 방법(추천)
초기에는 LLM이 만든 `AFFECTS`를 그대로 쓰지 말고, **정량 근거**를 함께 부착합니다.

* **(정량) Event Window Impact**:
    * Event_time 기준 전/후 N일 구간에서 해당 지표/파생피처 변화량을 계산
    * 결과를 `AFFECTS` 관계 속성으로 저장: `observed_delta`, `window_days`, `baseline_method`
* **(정성) News Claim Impact**:
    * Claim은 `confidence` + `evidence`를 강제 저장
    * Claim은 “가설”로 취급하고, 나중에 데이터로 검증되면 `validated=true` 업데이트
* **(운영) Non-stationarity 대응**:
    * `AFFECTS.weight/confidence`는 고정값이 아니라 **최근 90/180일 슬라이딩 윈도우**로 주기 재계산
    * 관계 속성에 `as_of`, `window_days`, `method`를 남기고, 필요 시 스냅샷/이력 노드로 변화 추적

## 6. 그래프 기반 거시 분석(고도화 아이디어)

### 6.1 “거시 상태 그래프” (State Graph)
하루(또는 주간) 단위로 `MacroState(date)` 노드를 만들고,
그날의 주요 `DerivedFeature`를 연결하여 “현재 거시 상태”를 일관된 구조로 저장합니다.

* `(MacroState)-[:HAS_SIGNAL]->(DerivedFeature)`
* `(MacroState)-[:DOMINANT_THEME]->(MacroTheme)`
* `(MacroState)-[:EXPLAINED_BY]->(Event|Story)`

→ LLM은 매번 원문 전체를 보지 않고, `MacroState` 인접 서브그래프만으로도 요약/전망이 가능해집니다.

### 6.2 내러티브/스토리 클러스터링 (Story Graph)
뉴스를 테마/원인/대상 지표 기준으로 군집화하여 `Story` 노드를 생성합니다.

* `(Story)-[:CONTAINS]->(Document)`
* `(Story)-[:ABOUT_THEME]->(MacroTheme)`
* `(Story)-[:AFFECTS]->(EconomicIndicator)`

→ “이번 주 인플레 내러티브” 같은 뷰를 제공할 수 있습니다.

### 6.3 통계 엣지 자동 생성 (Indicator ↔ Indicator)
시계열로부터 다음 관계를 주기적으로 계산해 그래프에 반영합니다.

* `CORRELATED_WITH {corr, window_days}`
* `LEADS {lag_days, score}` (교차상관/간단 리드-래그)
* (선택) `GRANGER_CAUSES {lag, pvalue}` 등은 추후

※ 인과(inference)를 단정하지 말고 “통계적 관계”로 명확히 라벨링합니다.

## 7. GraphRAG / LLM 활용 (Retrieval + Reasoning)

### 7.1 그래프 기반 컨텍스트 구성
질문(Q)이 들어오면, 다음 순서로 서브그래프를 수집합니다.

1) 키워드 → `MacroTheme/EconomicIndicator/Country` 후보 매칭
2) 최근 기간 필터(예: 7/30/90일)로 `Event/Document/Story` 확장
3) `Evidence` 포함해서 “근거 텍스트”를 함께 전달

### 7.2 “분석도 그래프에 저장” (추천)
일일 리포트/LLM 분석 결과를 `AnalysisRun` 노드로 저장하면, 다음을 할 수 있습니다.

* 과거 예측/가설이 맞았는지 회고 가능
* 동일 질문에 대한 답변 일관성 확보(이미 만든 해석을 재사용)
* “근거 그래프”가 자연스럽게 누적

## 8. UI (Macro Graph 화면 고도화)
이미 만들어둔 Macro Graph 화면을 다음 방향으로 확장합니다.

* **필터**: 기간, 국가, 카테고리, 테마, 신뢰도(confidence)
* **노드 패널**: Document 클릭 → Evidence/Fact/Claim 표시, 관련 Indicator 미니 차트 링크
* **경로 탐색**: Event → Theme → Indicator 경로 하이라이트(“왜 이 결론인가?”)
* **질문 템플릿**: “최근 인플레 관련 이벤트 Top N”, “유동성 악화 경로”, “리스크 상승 원인”

## 9. 기술적 구현 시의 주의 사항 및 고도화 제언
제안된 MKG를 실제 운영 수준으로 만들기 위해, 아래 3가지는 “나중에 개선”이 아니라 **초기부터 설계에 포함**하는 것을 권장합니다.

### 9.1 엔티티 정규화(Entity Normalization) 철저 관리
뉴스 텍스트는 표현이 지저분해 동일 대상을 다양한 문자열로 언급합니다. 이는 그래프 연결성을 급격히 파편화시키므로 NEL을 별도 파이프라인으로 관리합니다.

* **핵심 원칙**: 추출된 문자열은 노드로 바로 만들지 말고, 가능한 한 **canonical entity(표준 ID)** 로 매핑 후 `MERGE`
* **권장 매핑**: 거시/기관/인물은 Wikipedia/Wikidata(또는 내부 KB), 지표는 FRED series id 우선
* **운영 팁**: 신규 엔티티 생성은 보수적으로(불확실하면 후보/보류), 실패 케이스를 alias 사전으로 누적

### 9.2 FRED 수정 이력(Revision History) 반영: ALFRED 빈티지 기반
거시 지표는 과거 값이 수정됩니다. 모델/전략을 검증할 때 “현재의 과거 데이터”를 쓰면 룩어헤드가 발생합니다.

* **원칙**: 모든 지표 조회는 `as_of_date`를 입력으로 받아, 해당 시점에 가용했던 **최신 빈티지(vintage_date ≤ as_of_date)** 를 사용
* **저장 방식**: `IndicatorObservation(indicator_code, obs_date, vintage_date)` 형태로 빈티지를 누적(또는 Observation/Vintage 분리 모델)
* **GraphRAG 반영**: LLM 분석/리포트 생성 시에도 `as_of_date`를 전달해 동일한 빈티지 규칙을 강제

### 9.3 인과관계 비정상성(Non-stationarity) 대응: 동적 가중치
경제 관계는 시대/국면에 따라 약화/반전될 수 있습니다. 따라서 `AFFECTS`는 고정 지식이 아니라 최신 데이터를 반영해 지속 갱신해야 합니다.

* **슬라이딩 윈도우**: 최근 90/180일 기준으로 관계 강도/방향을 재계산(정량 검증 파이프라인 포함)
* **이력화**: `as_of`, `window_days`, `method`를 저장하고, 필요 시 관계 스냅샷을 별도 노드로 남겨 변화 추적

## 10. 초기 데이터 설계 방안 (Initial Data Seeding Plan)

이 섹션은 Neo4j 그래프 DB에 **최초 적재할 Seed 데이터**와 **주기적 업데이트 전략**을 정의합니다.

### 10.1 Seed 데이터 정의

#### (A) MacroTheme (거시 테마) - 6개

| theme_id | name | description |
|----------|------|-------------|
| `rates` | Rates (금리) | 기준금리, 국채금리, 금리 커브 관련 |
| `inflation` | Inflation (물가) | CPI, PCE, 기대인플레이션 관련 |
| `growth` | Growth (성장) | GDP, 경기선행지수, 제조업 지표 |
| `labor` | Labor (고용) | 실업률, 비농업고용, 임금 관련 |
| `liquidity` | Liquidity (유동성) | 연준 대차대조표, TGA, 역레포 |
| `risk` | Risk (리스크) | 하이일드 스프레드, VIX, 금융스트레스 |

#### (B) EconomicIndicator (FRED 지표) - 17개

| indicator_code | name | unit | frequency | theme_id |
|----------------|------|------|-----------|----------|
| `DGS10` | 10-Year Treasury Constant Maturity Rate | % | daily | rates |
| `DGS2` | 2-Year Treasury Constant Maturity Rate | % | daily | rates |
| `FEDFUNDS` | Effective Federal Funds Rate | % | daily | rates |
| `T10Y2Y` | 10-Year Treasury Minus 2-Year Spread | % | daily | rates |
| `DFII10` | 10-Year TIPS (Real Interest Rate) | % | daily | rates |
| `CPIAUCSL` | Consumer Price Index (CPI) | Index | monthly | inflation |
| `PCEPI` | Personal Consumption Expenditures Price Index | Index | monthly | inflation |
| `PCEPILFE` | Core PCE (ex Food & Energy) | Index | monthly | inflation |
| `T10YIE` | 10-Year Breakeven Inflation Rate | % | daily | inflation |
| `GDP` | Gross Domestic Product | Billions USD | quarterly | growth |
| `GACDFSA066MSFRBPHI` | Philadelphia Fed Leading Index | Index | monthly | growth |
| `NOCDFSA066MSFRBPHI` | Philadelphia Fed Coincident Index | Index | monthly | growth |
| `GAFDFSA066MSFRBPHI` | Philadelphia Fed Lagging Index | Index | monthly | growth |
| `UNRATE` | Unemployment Rate | % | monthly | labor |
| `PAYEMS` | All Employees: Total Nonfarm Payrolls | Thousands | monthly | labor |
| `WALCL` | Fed Total Assets | Millions USD | weekly | liquidity |
| `WTREGEN` | Treasury General Account (TGA) | Millions USD | weekly | liquidity |
| `RRPONTSYD` | Overnight Reverse Repurchase Agreements | Billions USD | daily | liquidity |
| `BAMLH0A0HYM2` | ICE BofA High Yield Spread | % | daily | risk |
| `VIXCLS` | CBOE Volatility Index (VIX) | Index | daily | risk |
| `STLFSI4` | St. Louis Fed Financial Stress Index | Index | weekly | risk |

#### (C) Entity / EntityAlias (핵심 기관/인물) - 초기 10개

| canonical_id | name | entity_type | aliases (ko/en) |
|--------------|------|-------------|-----------------|
| `ORG_FED` | Federal Reserve | organization | 연준, Fed, FOMC, 미 연방준비제도, Federal Reserve System |
| `ORG_ECB` | European Central Bank | organization | ECB, 유럽중앙은행 |
| `ORG_BOJ` | Bank of Japan | organization | BOJ, 일본은행, 日銀 |
| `ORG_BOK` | Bank of Korea | organization | 한국은행, BOK |
| `ORG_PBOC` | People's Bank of China | organization | PBOC, 인민은행, 중국인민은행 |
| `ORG_TREASURY` | U.S. Department of Treasury | organization | 미 재무부, Treasury, 재무부 |
| `PERSON_POWELL` | Jerome Powell | person | 파월, Powell, 제롬 파월 |
| `PERSON_YELLEN` | Janet Yellen | person | 옐런, Yellen, 재닛 옐런 |
| `GEO_US` | United States | country | 미국, US, USA, America |
| `GEO_KR` | South Korea | country | 한국, Korea, KR |

### 10.2 초기 적재 Cypher 스크립트

**실행 대상 DB**: Neo4j `macro` database (legacy 명칭: `news`)  
(예) Neo4j Browser에서 `:use macro` 후 실행, 또는 `cypher-shell -d macro -f <file>.cypher`

#### Step 1: 제약조건 및 인덱스 생성

```cypher
// Unique Constraints
CREATE CONSTRAINT IF NOT EXISTS FOR (t:MacroTheme) REQUIRE t.theme_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (i:EconomicIndicator) REQUIRE i.indicator_code IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.canonical_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE;

// Indexes for Performance
CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.published_at);
CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.country);
CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.category);
CREATE INDEX IF NOT EXISTS FOR (o:IndicatorObservation) ON (o.obs_date);
CREATE INDEX IF NOT EXISTS FOR (ev:Event) ON (ev.event_time);
```

#### Step 2: MacroTheme Seed

```cypher
UNWIND [
  {theme_id: 'rates', name: 'Rates (금리)', description: '기준금리, 국채금리, 금리 커브 관련'},
  {theme_id: 'inflation', name: 'Inflation (물가)', description: 'CPI, PCE, 기대인플레이션 관련'},
  {theme_id: 'growth', name: 'Growth (성장)', description: 'GDP, 경기선행지수, 제조업 지표'},
  {theme_id: 'labor', name: 'Labor (고용)', description: '실업률, 비농업고용, 임금 관련'},
  {theme_id: 'liquidity', name: 'Liquidity (유동성)', description: '연준 대차대조표, TGA, 역레포'},
  {theme_id: 'risk', name: 'Risk (리스크)', description: '하이일드 스프레드, VIX, 금융스트레스'}
] AS row
MERGE (t:MacroTheme {theme_id: row.theme_id})
SET t.name = row.name, t.description = row.description, t.created_at = datetime();
```

#### Step 3: EconomicIndicator Seed + Theme 연결

```cypher
UNWIND [
  {code: 'DGS10', name: '10-Year Treasury Rate', unit: '%', freq: 'daily', theme: 'rates'},
  {code: 'DGS2', name: '2-Year Treasury Rate', unit: '%', freq: 'daily', theme: 'rates'},
  {code: 'FEDFUNDS', name: 'Fed Funds Rate', unit: '%', freq: 'daily', theme: 'rates'},
  {code: 'T10Y2Y', name: '10Y-2Y Spread', unit: '%', freq: 'daily', theme: 'rates'},
  {code: 'DFII10', name: '10-Year TIPS', unit: '%', freq: 'daily', theme: 'rates'},
  {code: 'CPIAUCSL', name: 'CPI', unit: 'Index', freq: 'monthly', theme: 'inflation'},
  {code: 'PCEPI', name: 'PCE Price Index', unit: 'Index', freq: 'monthly', theme: 'inflation'},
  {code: 'PCEPILFE', name: 'Core PCE', unit: 'Index', freq: 'monthly', theme: 'inflation'},
  {code: 'T10YIE', name: 'Breakeven Inflation', unit: '%', freq: 'daily', theme: 'inflation'},
  {code: 'GDP', name: 'Gross Domestic Product', unit: 'Billions USD', freq: 'quarterly', theme: 'growth'},
  {code: 'GACDFSA066MSFRBPHI', name: 'Philly Fed Leading', unit: 'Index', freq: 'monthly', theme: 'growth'},
  {code: 'NOCDFSA066MSFRBPHI', name: 'Philly Fed Coincident', unit: 'Index', freq: 'monthly', theme: 'growth'},
  {code: 'GAFDFSA066MSFRBPHI', name: 'Philly Fed Lagging', unit: 'Index', freq: 'monthly', theme: 'growth'},
  {code: 'UNRATE', name: 'Unemployment Rate', unit: '%', freq: 'monthly', theme: 'labor'},
  {code: 'PAYEMS', name: 'Nonfarm Payrolls', unit: 'Thousands', freq: 'monthly', theme: 'labor'},
  {code: 'WALCL', name: 'Fed Total Assets', unit: 'Millions USD', freq: 'weekly', theme: 'liquidity'},
  {code: 'WTREGEN', name: 'Treasury General Account', unit: 'Millions USD', freq: 'weekly', theme: 'liquidity'},
  {code: 'RRPONTSYD', name: 'Reverse Repo', unit: 'Billions USD', freq: 'daily', theme: 'liquidity'},
  {code: 'BAMLH0A0HYM2', name: 'High Yield Spread', unit: '%', freq: 'daily', theme: 'risk'},
  {code: 'VIXCLS', name: 'VIX', unit: 'Index', freq: 'daily', theme: 'risk'},
  {code: 'STLFSI4', name: 'Financial Stress Index', unit: 'Index', freq: 'weekly', theme: 'risk'}
] AS row
MERGE (i:EconomicIndicator {indicator_code: row.code})
SET i.name = row.name, i.unit = row.unit, i.frequency = row.freq, 
    i.source = 'FRED', i.country = 'US', i.created_at = datetime()
WITH i, row
MATCH (t:MacroTheme {theme_id: row.theme})
MERGE (i)-[:BELONGS_TO]->(t);
```

#### Step 4: Entity + Alias Seed

```cypher
// Core Entities
UNWIND [
  {id: 'ORG_FED', name: 'Federal Reserve', type: 'organization'},
  {id: 'ORG_ECB', name: 'European Central Bank', type: 'organization'},
  {id: 'ORG_BOJ', name: 'Bank of Japan', type: 'organization'},
  {id: 'ORG_BOK', name: 'Bank of Korea', type: 'organization'},
  {id: 'ORG_PBOC', name: "People's Bank of China", type: 'organization'},
  {id: 'ORG_TREASURY', name: 'U.S. Department of Treasury', type: 'organization'},
  {id: 'PERSON_POWELL', name: 'Jerome Powell', type: 'person'},
  {id: 'PERSON_YELLEN', name: 'Janet Yellen', type: 'person'},
  {id: 'GEO_US', name: 'United States', type: 'country'},
  {id: 'GEO_KR', name: 'South Korea', type: 'country'}
] AS row
MERGE (e:Entity {canonical_id: row.id})
SET e.name = row.name, e.entity_type = row.type, e.created_at = datetime();

// Aliases (sample)
UNWIND [
  {entity_id: 'ORG_FED', alias: '연준', lang: 'ko'},
  {entity_id: 'ORG_FED', alias: 'Fed', lang: 'en'},
  {entity_id: 'ORG_FED', alias: 'FOMC', lang: 'en'},
  {entity_id: 'ORG_FED', alias: '미 연방준비제도', lang: 'ko'},
  {entity_id: 'PERSON_POWELL', alias: '파월', lang: 'ko'},
  {entity_id: 'PERSON_POWELL', alias: 'Powell', lang: 'en'},
  {entity_id: 'GEO_US', alias: '미국', lang: 'ko'},
  {entity_id: 'GEO_US', alias: 'US', lang: 'en'},
  {entity_id: 'GEO_US', alias: 'USA', lang: 'en'},
  {entity_id: 'GEO_KR', alias: '한국', lang: 'ko'},
  {entity_id: 'GEO_KR', alias: 'Korea', lang: 'en'}
] AS row
MATCH (e:Entity {canonical_id: row.entity_id})
MERGE (a:EntityAlias {canonical_id: row.entity_id, alias: row.alias, lang: row.lang})
MERGE (e)-[:HAS_ALIAS]->(a);
```

### 10.3 주기적 업데이트 전략

| 데이터 종류 | 업데이트 주기 | 트리거 방식 | 설명 |
|------------|--------------|-------------|------|
| **IndicatorObservation** | Daily (평일) | Cron Job (09:00 KST) | FRED API에서 최신 관측치 수집 후 `MERGE` |
| **DerivedFeature** | Daily (평일) | Observation 적재 직후 | Δ, Δ%, Z-score, MoM/YoY 계산 |
| **Document (뉴스)** | 4시간마다 | Cron Job | 뉴스 수집 → LLM 추출 → Graph 적재 |
| **Event/Fact/Claim** | 뉴스 적재 시 | 동기 처리 | LLM이 추출한 구조를 Graph에 저장 |
| **AFFECTS 가중치** | Weekly (일요일) | Batch Job | 90/180일 슬라이딩 윈도우로 재계산 |
| **CORRELATED/LEADS 엣지** | Weekly (일요일) | Batch Job | 지표 간 상관관계 재계산 |

### 10.4 Python 적재 파이프라인 구조 (권장)

```
hobot/
└── service/
    └── graph/
        ├── __init__.py
        ├── neo4j_client.py          # Neo4j 연결/쿼리 래퍼
        ├── seed_data.py             # 초기 Seed 적재 스크립트
        ├── indicator_loader.py      # FRED → IndicatorObservation 적재
        ├── derived_feature_calc.py  # 파생 피처 계산
        ├── news_extractor.py        # 뉴스 → Event/Fact/Claim 추출 (LLM)
        ├── news_loader.py           # 추출 결과 → Graph 적재
        └── scheduler.py             # APScheduler 기반 주기 실행
```

### 10.5 검증 쿼리 (Seed 적재 후 확인용)

```cypher
// 노드 카운트 확인
MATCH (t:MacroTheme) RETURN 'MacroTheme' AS label, count(t) AS count
UNION ALL
MATCH (i:EconomicIndicator) RETURN 'EconomicIndicator' AS label, count(i) AS count
UNION ALL
MATCH (e:Entity) RETURN 'Entity' AS label, count(e) AS count
UNION ALL
MATCH (a:EntityAlias) RETURN 'EntityAlias' AS label, count(a) AS count;

// 관계 확인
MATCH (i:EconomicIndicator)-[:BELONGS_TO]->(t:MacroTheme)
RETURN t.theme_id, collect(i.indicator_code) AS indicators;

// Alias 확인
MATCH (e:Entity)-[:HAS_ALIAS]->(a:EntityAlias)
WHERE e.canonical_id = 'ORG_FED'
RETURN e.name, collect(a.alias) AS aliases;
```

---

## 11. 실행 계획 (Phased Plan)

### 11.0 Phase 검토 요약 (리스크/의사결정 포인트)
Phase A~D 구성이 타당하며 “그래프 뼈대 → 추출 품질 → 정량/통계 엣지 → GraphRAG/UI” 순서가 올바릅니다.
다만 아래 항목은 **초기에 명확히 결정/합의**되어야 이후 Phase의 재작업을 줄일 수 있습니다.

1) **Neo4j DB 경계(결정됨)**  
   - **결정: 기존 `macro` database에 MKG를 적재**하여 UI/프록시를 그대로 재사용 (legacy 명칭: `news`)  
   - 운영 규칙(권장)
     - MKG 적재/조회는 기본적으로 `database="macro"`를 사용
     - 추후 다른 그래프가 `macro` DB에 추가될 가능성이 있으면, 모든 MKG 노드에 `domain='mkg'` 속성을 넣고(선택),
       UI/질의 템플릿에서 `WHERE n.domain='mkg'` 형태로 필터할 수 있게 준비

2) **ID 정책 & 멱등성(idempotency)**  
   - `Document.doc_id`, `Event.event_id` 등은 **deterministic id**(예: `source:id`, `hash(doc_id+span)`)로 통일  
   - 모든 적재는 `MERGE` 기반 upsert + `created_at/updated_at` 관리

3) **Evidence 강제와 “팩트/주장 분리”의 적용 범위**  
   - Phase B에서 Evidence 강제를 넣는 것은 좋지만, Phase A에서 최소한의 **Evidence 노드/관계 틀**은 잡아두는 편이 안전

4) **ALFRED(vintage) 도입 수준**  
   - Phase A에서 “스키마/조회 규칙만” 먼저 반영하고, 실제 빈티지 적재는 Phase C로 미루는 편이 일정에 유리  
   - 단, GraphRAG/리포트 생성에서는 `as_of_date`를 **처음부터 인터페이스에 포함**(룩어헤드 방지)

5) **LLM 비용/지연(운영)**  
   - 뉴스 1건당 추출 호출이 누적되므로 Phase B부터는 **캐시/재시도/부분 실패 처리**가 필수  
   - “Backfill(과거 N일 재처리)”을 고려해 배치/스케줄러 설계를 초기에 포함

아래 Phase 상세 계획은 위 포인트를 반영한 **개발 체크리스트 + 산출물/검증 기준(DoD)** 중심으로 작성합니다.

### Phase A (MVP): 스키마/시딩/기본 링크 (1~2일)
* [ ] `MacroTheme` + FRED 지표(`EconomicIndicator`) seed
* [ ] `IndicatorObservation/DerivedFeature` 적재 파이프라인(최소 피처만)
* [ ] ALFRED(vintage) 스키마/조회 규칙 초안 반영(`as_of_date` 기준 조회)
* [ ] `Document` upsert + 기본 `MENTIONS/ABOUT_THEME` 연결
* [ ] `Entity/EntityAlias` 제약/인덱스 + 최소 alias seed(“Fed/연준/FOMC” 등)

#### 목표
* Neo4j에 **MKG의 최소 스키마를 실제로 “올리고”**, Seed + 일부 샘플 데이터가 들어가 **UI에서 탐색 가능한 상태**를 만든다.
* 뉴스/지표가 완전히 분리된 상태를 깨고, 최소한 `Document ↔ MacroTheme ↔ EconomicIndicator`가 연결되도록 한다.

#### 작업 범위 (In / Out)
* In: 제약/인덱스, Seed, 기본 upsert 파이프라인, 최소 링크(rule-based), 최소 파생피처(Δ/Δ%), `as_of_date` 인터페이스
* Out(Phase B/C로 이관): 고품질 LLM 추출/NER, 동적 가중치/통계 엣지, Story/GraphRAG/UI 고도화

#### 상세 작업
1) **Neo4j 스키마/제약/인덱스 확정**
   - `MacroTheme/EconomicIndicator/Document/Entity/EntityAlias` UNIQUE 제약 적용
   - `IndicatorObservation`/`DerivedFeature` 키 설계
     - (권장) `IndicatorObservation`의 키는 `(indicator_code, obs_date[, vintage_date])`
     - Phase A에서는 `vintage_date`를 nullable로 두고, 제약은 “빈티지 미사용” 버전으로 먼저 적용(또는 두 모델 중 하나 선택)
   - 자주 조회될 `published_at`, `country`, `category`, `obs_date` 인덱스 적용

2) **Seed 적재 스크립트/절차 구성**
   - `## 10.2`의 Cypher를 실제 운영 절차로 정리(어디서/어떻게 실행하는지)
   - 산출물 예:
     - `cypher/00_constraints.cypher`
     - `cypher/01_seed_themes.cypher`
     - `cypher/02_seed_indicators.cypher`
     - `cypher/03_seed_entities.cypher`
   - 실행 방식(예시):
     - 로컬 개발: Neo4j Browser/CLI로 실행
     - 운영: 배포 파이프라인에서 idempotent하게 실행(실패 시 재실행 안전)

3) **FRED → IndicatorObservation 적재(최소)**
   - 데이터 소스 결정을 먼저 함
     - (옵션 A, 빠름) 기존 MySQL의 `fred_data`를 읽어 Neo4j로 **동기화**  
     - (옵션 B) FRED API를 직접 호출해 Neo4j로 적재
   - 적재 규칙
     - `EconomicIndicator`가 없으면 적재 금지(Seed가 선행되어야 함)
     - `obs_date`는 ISO date로 정규화
     - 결측/휴장일 처리 정책(예: daily series는 주말 결측 허용, 필요 시 보간은 파생피처에서만 사용)

4) **DerivedFeature(최소 피처) 계산/적재**
   - Phase A 최소 피처 정의(권장)
     - `delta_1d`: `value - value(t-1)`
     - `pct_change_1d`: `(value/value(t-1)-1)`
     - `mom`/`yoy`는 월/분기 지표에 한해 Phase A에 포함해도 됨(선택)
   - 피처 키
     - `(indicator_code, feature_name, obs_date)`
   - 저장
     - `(:IndicatorObservation)-[:HAS_FEATURE]->(:DerivedFeature)` 또는 `DerivedFeature`를 관측치에 직접 속성으로 둘지 결정(권장: 노드 분리)

5) **ALFRED(vintage) “스키마/조회 인터페이스”만 우선 반영**
   - 스키마 초안
     - `IndicatorObservation.vintage_date`(없으면 최신/비-vintage)  
     - (향후) 빈티지별 관측치를 다 저장할지, “vintage node”를 분리할지
   - 조회 규칙(필수)
     - 모든 “지표 조회 함수/API”는 `as_of_date` 입력을 받고,
       `vintage_date <= as_of_date` 중 최신을 선택(룩어헤드 방지)
   - Phase A 산출물
     - Cypher 템플릿 2~3개(예: 최신값, 특정 기간, as_of_date 적용 버전)

6) **News(Document) upsert + 기본 Theme/Entity 링크(rule-based)**
   - 소스: MySQL `economic_news` (또는 기존 뉴스 저장소)에서 최신 N건 적재
   - `Document.doc_id` 규칙(예: `TradingEconomics:{id}` 또는 `source:{id}`)
   - 기본 링크(Phase A는 LLM 없이 rule-based)
     - `Document.country/category` → `MacroTheme` 매핑 룰(키워드/사전 기반)
     - Alias 사전 기반 `MENTIONS`(문서 텍스트에서 alias substring 매칭 → `Entity` 연결)
   - “근거”는 Phase B에서 강화하되, Phase A에서도 `Evidence` 틀을 미리 넣어두면 이후 변경 비용이 낮음

7) **운영 관점 최소 요구**
   - 적재 재실행 시 중복이 생기지 않는지(멱등성) 확인
   - 실패/부분 실패 시 재시도 전략(최소한 로그/에러 리포트)

#### 산출물 (Deliverables)
* Neo4j: 제약/인덱스/Seed Cypher 세트 + 실행 가이드(문서화)
* Backend: (권장 구조 기준) `service/graph/*` 골격 + 적재 스크립트(Seed, FRED sync, News sync)
* 검증: Seed 검증 Cypher + 샘플 질의(“최근 7일 뉴스 → 테마 → 지표” 경로)

#### 검증/DoD (Definition of Done)
* Neo4j에서 아래가 확인된다.
  - `MacroTheme` 6개, `EconomicIndicator` 20개 내외(현재 목록 기준) 생성
  - 최신 `IndicatorObservation`이 최소 5개 지표에서 존재
  - `Document`가 최소 50건 적재되고, 그중 50% 이상이 `ABOUT_THEME`로 연결
  - `Entity` 10개 + alias 연결 존재, `Document-[:MENTIONS]->Entity`가 최소 20건 생성
* UI(Macro Graph)에서 “Document 클릭 → 연결된 Theme/Indicator/Entity”가 보인다.

#### 리스크/대응
* (리스크) `macro` DB에 타 그래프가 섞이면 노이즈/성능 이슈 가능 → `domain='mkg'` 필터(선택) + 템플릿 쿼리 도입
* (리스크) DerivedFeature 설계가 바뀌면 이후 통계/Impact 로직이 연쇄 변경 → Phase A에서 최소 키/모델을 확정

### Phase B: News Extraction 정식화 (2~4일)
* [ ] LLM JSON 스키마 확정(Event/Fact/Claim/Evidence/Links)
* [ ] Evidence 강제(근거 없는 AFFECTS/CAUSES 금지)
* [ ] Country/Category 표준화 + ExternalIndicator 확장(비미국 지표 수용)
* [ ] NEL 파이프라인(추출→후보→연결) 분리 + canonical id 매핑/Wikidata 연동(또는 내부 KB)

#### 목표
* 뉴스 1건이 **일관된 JSON 구조(Event/Fact/Claim/Evidence/Links)** 로 추출되고, 그래프에 “근거(Evidence) 포함” 형태로 저장된다.
* 엔티티/국가/카테고리/지표가 표준화되어 **그래프 파편화(fragmentation)** 를 최소화한다.

#### 작업 범위 (In / Out)
* In: LLM 추출 스키마/검증, Evidence 강제, 표준화(국가/카테고리), ExternalIndicator, NEL 파이프라인 기본형
* Out(Phase C/D로 이관): 영향 가중치 정량 검증, 통계 엣지 자동 생성, GraphRAG/UI 고도화

#### 상세 작업
1) **LLM 추출 JSON 스키마 확정 + 밸리데이션**
   - 스키마 버저닝(예: `schema_version=1`)과 함께 저장
   - Pydantic(또는 JSON Schema)로 **엄격 검증**: 누락/타입 오류 시 적재 금지(또는 DLQ로 이동)
   - 최소 요구
     - `events[].event_time`(가능하면), `facts[].value/unit/period`, `claims[].polarity/confidence`
     - 모든 `facts/claims/links`는 `evidence_text`를 반드시 포함

2) **Evidence 강제 로직**
   - 금지 규칙
     - `AFFECTS/CAUSES` 생성 시 `Evidence`가 없으면 관계 생성 금지
   - Evidence 저장 방식
     - `Evidence.text` + (가능하면) `offset_start/end` + `lang`
     - `Evidence`는 `Document`에 귀속(`(Document)-[:HAS_EVIDENCE]->(Evidence)`)
     - `Evidence`가 `Fact/Claim/Link`를 지원(`SUPPORTS`)

3) **표준화(Normalization)**
   - Country 표준화
     - 원문(`country`) → ISO code(예: `ZA`) + 한국어명(`country_ko`) 유지
   - Category 표준화
     - TradingEconomics 카테고리 → 내부 표준 taxonomy(최소 20~40개)
   - 결과적으로 `Document.country_code`, `Document.category_id` 같은 canonical field를 추가(권장)

4) **ExternalIndicator 확장**
   - 비미국/비-FRED 지표를 수용하기 위한 모델 확정
     - (안 A) `EconomicIndicator {source='TradingEconomics'}`로 통합
     - (안 B) `ExternalIndicator` 라벨을 추가해 분리
   - 최소 규칙
     - `code`가 없으면 `name+country+source` 기반 deterministic id 생성
     - 가능한 경우 FRED로 매핑되는 건 `EconomicIndicator(indicator_code=FRED)`로 우선 연결

5) **NEL 파이프라인 분리(추출 → 후보 → 연결)**
   - 단계 분리 이유: “추출된 문자열”을 그대로 노드로 만들면 alias 폭발 → 그래프 가치 급락
   - 구현(권장)
     - (1) LLM/룰 기반으로 mention(표현 문자열) 후보 추출
     - (2) 후보 생성: alias dictionary + (선택) Wikidata search
     - (3) 연결 판별: 스코어링(문맥/국가/카테고리) + 임계치
     - (4) 확정: `Entity(canonical_id)`로 `MERGE`, `EntityAlias` 누적
   - 운영
     - 실패 케이스를 alias 사전에 누적(“human-in-the-loop” 개선 루프)

6) **추출 파이프라인 운영화**
   - 재시도/타임아웃/레이트리밋 고려
   - 캐시 키(예: `doc_id + extractor_version + model`)로 재처리 비용 절감
   - Backfill 모드(최근 N일) 지원

#### 산출물 (Deliverables)
* `news_extractor`(LLM) + `news_loader`(Graph 적재) + JSON schema validator
* Normalization 사전(국가/카테고리) + ExternalIndicator 정책 문서
* NEL 기본 파이프라인 + alias seed/누적 메커니즘

#### 검증/DoD
* 최근 100건 뉴스 기준
  - 80% 이상이 “유효 JSON”으로 추출(검증 통과)
  - `Fact/Claim/Link`의 95% 이상이 Evidence를 보유(없으면 생성 금지이므로 구조상 100% 목표)
  - `EntityAlias`가 신규로 누적되며, alias 폭발(중복/노이즈)이 통제되는지 확인
* 샘플 질의
  - “최근 7일 inflation 테마의 Event Top 10 + Evidence”가 Cypher로 조회됨

#### 리스크/대응
* (리스크) LLM 출력 변동으로 파이프라인이 자주 깨짐 → 스키마 엄격 검증 + DLQ + 빠른 롤백(프롬프트 버전)
* (리스크) Wikidata 연동은 네트워크/응답 품질 이슈 → 내부 KB를 1차로 두고, 외부 KB는 선택적으로

### Phase C: 정량 Impact & 자동 통계 엣지 (1주)
* [ ] Event Window Impact 계산 및 `AFFECTS`에 observed_delta 저장
* [ ] `AFFECTS` 동적 가중치(90/180일 슬라이딩 윈도우) 재계산 배치 + 이력화
* [ ] Indicator↔Indicator CORRELATED/LEADS 관계 주기적 생성
* [ ] Story(내러티브) 클러스터링

#### 목표
* “뉴스/이벤트가 지표에 영향을 준다”를 **정량 근거(관측 변화)** 로 보강하고,
  관계를 최신 국면에 맞게 **동적으로 갱신**한다.
* 지표 간 통계 엣지(`CORRELATED/LEADS`)와 Story 클러스터를 생성하여 탐색/질의 가치를 높인다.

#### 상세 작업
1) **Event Window Impact 계산**
   - 입력: `Event.event_time`, 연결 후보 `EconomicIndicator`
   - 계산
     - 이벤트 기준 전/후 `window_days`(예: 3/7/14)에서 `DerivedFeature` 변화 추출
     - baseline(예: 이벤트 전 N일 평균) 대비 observed_delta 산출
   - 저장
     - `(Event)-[:AFFECTS {observed_delta, window_days, baseline_method, as_of}]->(EconomicIndicator)`
     - 기존 LLM `AFFECTS`와 충돌 시 병합 정책 결정(LLM은 “가설”, observed는 “관측”)

2) **AFFECTS 동적 가중치 재계산(슬라이딩 윈도우)**
   - 재계산 기준
     - 최근 90/180일 윈도우에서 “Event theme ↔ indicator feature”의 상관/회귀 기반 스코어
     - 또는 “claim polarity의 누적 신뢰도 + observed_delta 합성” 같은 휴리스틱
   - 이력화
     - 관계 속성에 `as_of`를 남기거나, 별도 `AffectsSnapshot` 노드로 스냅샷 저장
   - 배치 스케줄
     - 주 1회(일요일) 실행 + 실패 시 재시도/중복 방지 키

3) **Indicator↔Indicator 통계 엣지 생성**
   - `CORRELATED_WITH {corr, window_days, as_of}`  
   - `LEADS {lag_days, score, window_days, as_of}`  
   - (선택) Granger 등은 Phase D 이후로 미룸
   - 주의: 인과 단정 금지(라벨/설명에 “통계적 관계” 명시)

4) **Story(내러티브) 클러스터링**
   - 입력: `Document/Event/Theme/Indicator`의 최근 N일 데이터
   - 방법(권장)
     - (안 A) 테마+키워드 기반 rule clustering(빠름)
     - (안 B) 임베딩 기반(문서 요약 임베딩) + HDBSCAN/KMeans(품질↑)
   - 저장
     - `Story {story_id, created_at, window_days, method}`
     - `(Story)-[:CONTAINS]->(Document)`, `(Story)-[:ABOUT_THEME]->(MacroTheme)`, `(Story)-[:AFFECTS]->(EconomicIndicator)`

5) **데이터 품질/모니터링**
   - “정량 엣지 생성률”, “관계 가중치 분포”, “이상치(스파이크) 감지” 지표 추가
   - 재계산 배치의 실행 로그/성공률/소요시간 추적

#### 산출물 (Deliverables)
* Impact 계산 모듈 + 배치 스케줄러
* 통계 엣지 생성 모듈 + 저장 정책 문서
* Story 생성/업데이트 로직 + 검증 쿼리

#### 검증/DoD
* 최근 30일 데이터 기준
  - `AFFECTS` 관계 중 `observed_delta`가 채워진 비율 60% 이상(링킹 커버리지에 따라 조정)
  - `CORRELATED_WITH` 엣지가 최소 수십 개 생성(지표 수에 따라 상한/하한 설정)
  - Story가 최소 10개 이상 생성되고, 각 Story에 문서 3건 이상 연결

#### 리스크/대응
* (리스크) 이벤트 시간(event_time)이 불명확하면 window impact가 흔들림 → Phase B에서 event_time 추출 품질/대체 규칙(발행일 사용) 정의
* (리스크) 통계 엣지 과다 생성으로 UI/질의가 느려짐 → 임계치/Top-K 제한 + 주기 조절

### Phase D: GraphRAG + UI 완성도 (1주)
* [ ] 질문 → 서브그래프 추출 API(백엔드)
* [ ] UI에서 “근거(Evidence)”까지 보여주는 경로 탐색 UX
* [ ] 일일 MacroState/AnalysisRun 생성 및 리포트 뷰

#### 목표
* 사용자가 질문하면 “서브그래프 + Evidence”를 근거로 **재현 가능한 답변**을 제공한다.
* UI에서 **왜(Why)** 를 보여주는 경로 탐색 UX를 완성하고, 일일 상태/분석 결과를 그래프에 누적한다.

#### 상세 작업
1) **질문 → 서브그래프 추출 API**
   - 입력
     - `question`, `time_range(7/30/90d)`, `country?`, `as_of_date?`
   - 처리 흐름(권장)
     - (1) 키워드/엔티티/지표 후보 매칭(룰 + 임베딩 선택)
     - (2) 후보 노드에서 최근 기간의 `Event/Document/Story` 확장
     - (3) Evidence 포함해 컨텍스트 패키징(문장/URL/노드 id)
   - 출력
     - 서브그래프(nodes/links) + 근거 텍스트(evidence) + 추천 쿼리(선택)
   - 구현 메모
     - 기존 `/neo4j/query` 프록시를 재사용하되, “GraphRAG용 안전 쿼리 템플릿”을 별도 엔드포인트로 제공(권장)

2) **GraphRAG 응답 생성**
   - LLM 프롬프트에 “그래프 노드/관계/근거 텍스트”를 주입
   - 응답 포맷(권장)
     - 핵심 결론(불확실성/대안 포함)
     - 근거: `Document.url` + `Evidence.text` + 관련 노드 id
     - 영향 경로: Event → Theme → Indicator
   - 할루시네이션 방지
     - Evidence에 없는 사실을 말하면 안 되도록 제약(“근거 없는 문장 금지” 규칙)

3) **UI: Evidence까지 보여주는 경로 탐색 UX**
   - 필터: 기간/국가/카테고리/테마/신뢰도
   - 노드 패널
     - Document 클릭 시: 원문 링크, 요약, Evidence/Fact/Claim 목록
     - Indicator 클릭 시: 최신값/변화(간단 미니차트 링크)
   - 경로 탐색
     - “왜 인플레 리스크↑?” 질문 시, 관련 경로 하이라이트 + Evidence 표시
   - 질문 템플릿
     - 자주 쓰는 질의 5~10개 버튼화(최근 인플레 이벤트, 유동성 악화, 리스크 상승 등)

4) **MacroState/AnalysisRun 적재**
   - `MacroState(date)` 생성: 당일 주요 시그널(`DerivedFeature`)과 테마 요약 연결
   - `AnalysisRun` 생성: 질문/프롬프트/응답/사용 모델/소요시간/근거 노드 링크 저장
   - 회고/재현성을 위한 “as_of_date” 기록(필수)
   - 참고: `ai_strategist.py` 기반 MP/Sub-MP 선택 및 리밸런싱 비율 산출/저장은 **Phase E**로 분리

5) **운영/품질**
   - GraphRAG 품질 측정: “근거 링크 포함률”, “질문 재현성”, “응답 일관성”
   - UI 성능: 큰 서브그래프를 Top-K/페이지네이션으로 제한

#### 산출물 (Deliverables)
* Backend: GraphRAG 서브그래프 추출 API + 응답 생성 모듈
* UI: Evidence/경로 탐색/템플릿 질의/미니차트 연결
* Graph: `MacroState`, `AnalysisRun` 적재 + 조회 뷰/쿼리

#### 검증/DoD
* 질문 10개(예: 섹션 3.1)를 “그래프 근거 + 문서 링크”로 답할 수 있다.
  - 각 답변은 최소 2개 이상의 `Document.url` 및 `Evidence.text`를 포함
  - “근거 없는 주장”이 UI/로그에서 탐지되면 실패(품질 게이트)
* UI에서
  - (1) 기간/테마 필터로 그래프가 축소/확장되고
  - (2) 경로 하이라이트가 동작하며
  - (3) Evidence가 패널에서 즉시 확인된다.

#### 리스크/대응
* (리스크) GraphRAG 컨텍스트가 커져 토큰/비용 증가 → 서브그래프 Top-K, Evidence 요약/압축, 캐시 적용
* (리스크) UI가 “무거운 그래프”를 렌더링하기 어려움 → 서버에서 요약 그래프/계층 뷰 제공

### Phase E: Strategy Integration (1주)
`hobot/service/macro_trading/ai_strategist.py`의 MP/Sub-MP 선택 결과(=리밸런싱 목표 비중 산출)를 **Macro Graph(MKG)와 양방향으로 연결**합니다.

#### 목표
* MP/Sub-MP 선택(리밸런싱 비율 산출)의 **근거를 Macro Graph의 Evidence/경로로 앵커링**하여 “왜 이 배분인가?”를 재현 가능하게 한다.
* AI 전략 의사결정 결과(선택/비중/근거/사용 근거 노드)를 그래프에 저장해, GraphRAG/UI에서 **전략 히스토리 회고/추적**이 가능하게 한다.

#### 상세 작업
1) **Strategy Decision 그래프 모델(스키마) 확정**
   - 최소 노드(권장)
     - `StrategyDecision {decision_id, decision_date, mp_id, target_allocation, sub_mp, created_at}`
     - (선택) `StrategyRun {run_id, model, duration_ms, as_of_date, created_at}` (MP 호출/ Sub-MP 호출 분리 저장)
   - 최소 관계(권장)
     - `(StrategyDecision)-[:BASED_ON]->(MacroState)`
     - `(StrategyDecision)-[:USED_EVIDENCE]->(Evidence)`
     - `(StrategyDecision)-[:USED_NODE]->(Event|Story|MacroTheme|EconomicIndicator|Document)`
     - (선택) `(StrategyDecision)-[:DERIVED_FROM]->(IndicatorObservation|DerivedFeature)` (정량 근거 연결)
   - ID 정책
     - `decision_id = date + mp_id + hash(sub_mp)` 같은 deterministic 규칙(재실행/백필 안전)

2) **Macro Graph → ai_strategist 컨텍스트 주입(옵션)**
   - 목표: `create_mp_analysis_prompt()`, `create_sub_mp_analysis_prompt()`에 “그래프 근거 요약 블록”을 선택적으로 추가
   - 컨텍스트 구성(권장)
     - 최근 7/30일 `MacroTheme`별 상위 `Event/Story` + 연결 `EconomicIndicator` + `Evidence.text` + `Document.url`
     - “관측 기반 영향(Event Window Impact)”이 있으면 `observed_delta/window_days`를 같이 포함
   - 운영 규칙
     - 그래프가 비어있거나 장애면 **기존 로직(FRED+뉴스 요약)** 으로 폴백(전략 시스템 가용성 우선)
     - `as_of_date`를 기준으로 조회(룩어헤드 방지)

3) **ai_strategist → Macro Graph 저장(미러링)**
   - MySQL의 `ai_strategy_decisions.target_allocation`을 source-of-truth로 유지하면서,
     Macro Graph에 `StrategyDecision`(또는 `AnalysisRun`)으로 미러링 저장
   - 저장 내용(권장)
     - MP/Sub-MP 선택 결과 + 최종 목표 비중(`target_allocation`) + Sub-MP 상세(ETF weights) + reasoning 요약
     - 사용한 근거(`Evidence`, `Document`) 및 연결 경로(가능한 범위에서)
   - 백필/재실행
     - 최근 N일 전략결정을 재적재(backfill)할 수 있게 “upsert + deterministic id”로 운영

4) **리밸런싱 파이프라인과의 연결 확인(DoD 관점)**
   - 현행 리밸런싱은 `ai_strategy_decisions`를 기준으로 목표 비중을 조회해 실행됨
   - Phase E에서는 “결정→실행”의 설명 가능성을 위해, 다음을 그래프에 남길 수 있게 준비(선택)
     - `(RebalancingRun)-[:TARGETED]->(StrategyDecision)`
     - 실행 전/후 drift/거래 결과 요약(최소 메타)

5) **UI/질의 템플릿 확장(Strategy View)**
   - Macro Graph 화면에서 “최신 StrategyDecision 카드” 또는 템플릿 질의 추가(예)
     - “오늘 선택된 MP/Sub-MP와 근거(Evidence)”
     - “최근 30일 MP 전환 히스토리 + 전환 근거”
     - “MP-4가 선택된 날들의 공통 경로(Event→Theme→Indicator)”

#### 검증/DoD
* “오늘(또는 특정일) MP/Sub-MP가 왜 선택됐는가?”를 **Evidence 링크 포함** 형태로 조회/설명 가능
* `StrategyDecision`이 `MacroState` 및 최소 2개 이상의 `Evidence/Document`와 연결됨(데이터 가용 시)
* 전략결정 저장/미러링은 재실행 시 중복 없이(upsert) 동작

---
**작성자**: Antigravity (AI Assistant)  
**최종 업데이트**: 2026년 2월 7일
