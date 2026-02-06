# Hobot Service: 거시경제(FRED) + 경제뉴스 기반 Macro Knowledge Graph 고도화 계획 (Neo4j)

## 1. 개요 (Overview)
본 문서는 `hobot-service`가 현재 수집 중인 **FRED 거시경제 지표(정형)** + **경제 뉴스(비정형)** 를 Neo4j 기반 **Macro Knowledge Graph(MKG)** 로 통합하여,
단순 요약/상관관계를 넘어 다음을 가능하게 하는 개선 방안을 제시합니다.

* **이벤트 → 지표(관측치/파생지표) 연결**: “이 뉴스/이벤트가 어떤 거시 변수에 어떤 방향으로(상승/하락) 영향을 주는가?”
* **거시 내러티브(Story) 추적**: 같은 주제의 뉴스를 묶어 “현재 시장이 믿는 이야기”를 그래프로 축적/검색
* **파급 경로(Ripple Path) 추론**: Event → Theme → Indicator → MarketRisk 등 영향 경로를 질의/설명
* **GraphRAG 기반 LLM 분석 고도화**: 답변을 “그래프 근거 + 원문 증거”에 고정(anchoring)해서 할루시네이션 감소

참고: `work-planning/add-news-graph/2026-02-04_2208/plan.md`에 **News Graph UI/백엔드 프록시 연동 작업**은 완료된 상태이며, 이제 “데이터/분석 그래프”를 채우는 단계로 전환합니다.

## 2. 현황 (Current Status)

### 2.1 이미 갖춰진 것
* **뉴스 수집/저장**: `daily_news_agent.py`, `news_manager.py` 등으로 뉴스 수집 및 요약 저장
* **거시 지표 수집/저장**: FRED 등 시계열 수집 및 저장
* **Neo4j 프록시 & UI**:
    * `/api/neo4j/query`, `/api/neo4j/health` 존재 (database: `architecture` | `news`)
    * Ontology 하위 메뉴에 **News Graph 화면** 존재

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

## 8. UI (News Graph 화면 고도화)
이미 만들어둔 News Graph 화면을 다음 방향으로 확장합니다.

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

## 10. 실행 계획 (Phased Plan)

### Phase A (MVP): 스키마/시딩/기본 링크 (1~2일)
* [ ] `MacroTheme` + FRED 지표(`EconomicIndicator`) seed
* [ ] `IndicatorObservation/DerivedFeature` 적재 파이프라인(최소 피처만)
* [ ] ALFRED(vintage) 스키마/조회 규칙 초안 반영(`as_of_date` 기준 조회)
* [ ] `Document` upsert + 기본 `MENTIONS/ABOUT_THEME` 연결
* [ ] `Entity/EntityAlias` 제약/인덱스 + 최소 alias seed(“Fed/연준/FOMC” 등)

### Phase B: News Extraction 정식화 (2~4일)
* [ ] LLM JSON 스키마 확정(Event/Fact/Claim/Evidence/Links)
* [ ] Evidence 강제(근거 없는 AFFECTS/CAUSES 금지)
* [ ] Country/Category 표준화 + ExternalIndicator 확장(비미국 지표 수용)
* [ ] NEL 파이프라인(추출→후보→연결) 분리 + canonical id 매핑/Wikidata 연동(또는 내부 KB)

### Phase C: 정량 Impact & 자동 통계 엣지 (1주)
* [ ] Event Window Impact 계산 및 `AFFECTS`에 observed_delta 저장
* [ ] `AFFECTS` 동적 가중치(90/180일 슬라이딩 윈도우) 재계산 배치 + 이력화
* [ ] Indicator↔Indicator CORRELATED/LEADS 관계 주기적 생성
* [ ] Story(내러티브) 클러스터링

### Phase D: GraphRAG + UI 완성도 (1주)
* [ ] 질문 → 서브그래프 추출 API(백엔드)
* [ ] UI에서 “근거(Evidence)”까지 보여주는 경로 탐색 UX
* [ ] 일일 MacroState/AnalysisRun 생성 및 리포트 뷰

---
**작성자**: Antigravity (AI Assistant)  
**최종 업데이트**: 2026년 2월 6일
