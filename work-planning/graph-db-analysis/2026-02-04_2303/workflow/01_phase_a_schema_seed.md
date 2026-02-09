# Phase A: 스키마/시딩/기본 링크 (MVP)

## 📋 Phase 개요
- **예상 기간**: 1~2일
- **목표**: Neo4j에 MKG의 최소 스키마를 적재하고, Seed 데이터 + 샘플 뉴스로 UI 탐색 가능 상태 확보
- **전제 조건**: Macro Graph 연결 가능 (`database="macro"`, env: `NEO4J_MACRO_URI`)

---

## 🔧 작업 상세

### A-0: Macro Graph 연결/헬스체크
**예상 시간**: 0.5시간

#### 작업 내용
- [x] Backend 헬스체크: `GET /api/neo4j/health?database=macro` 성공 확인
- [x] Frontend 라우트: `/ontology/macro` 기본 그래프 로딩 확인
- [x] (선택) 로컬에서 Neo4j Browser로 Macro Graph URI에 직접 접속해 샘플 Cypher 실행

#### 검증
```bash
curl -s "http://localhost:8081/api/neo4j/health?database=macro"
```

---

### A-1: Neo4j 제약조건/인덱스 생성
**예상 시간**: 0.5시간

#### 작업 내용
- [x] UNIQUE 제약조건 생성
  - `MacroTheme(theme_id)`
  - `EconomicIndicator(indicator_code)`
  - `Entity(canonical_id)`
  - `EntityAlias(canonical_id, alias, lang)`
  - `Document(doc_id)`
  - `IndicatorObservation(indicator_code, obs_date)` *(Phase A는 vintage 미사용 전제)*
  - `DerivedFeature(indicator_code, feature_name, obs_date)`
- [x] 성능 인덱스 생성
  - `Document(published_at)`, `Document(country)`, `Document(category)`
  - `IndicatorObservation(obs_date)`
  - `Event(event_time)`
  - `EntityAlias(alias)` *(NEL/검색용)*

#### 산출물
- `cypher/00_constraints.cypher`

#### Cypher 스크립트
```cypher
// Unique Constraints (MVP)
CREATE CONSTRAINT IF NOT EXISTS FOR (t:MacroTheme) REQUIRE t.theme_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (i:EconomicIndicator) REQUIRE i.indicator_code IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.canonical_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (a:EntityAlias) REQUIRE (a.canonical_id, a.alias, a.lang) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE;

// Phase A에서는 vintage를 실제로 저장하지 않으므로 (indicator_code, obs_date) 유니크로 운영
// (Phase C에서 vintage 적재를 시작하면 제약조건을 (indicator_code, obs_date, vintage_date)로 마이그레이션)
CREATE CONSTRAINT IF NOT EXISTS FOR (o:IndicatorObservation) REQUIRE (o.indicator_code, o.obs_date) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (f:DerivedFeature) REQUIRE (f.indicator_code, f.feature_name, f.obs_date) IS UNIQUE;

// Indexes for Performance
CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.published_at);
CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.country);
CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.category);
CREATE INDEX IF NOT EXISTS FOR (o:IndicatorObservation) ON (o.obs_date);
CREATE INDEX IF NOT EXISTS FOR (ev:Event) ON (ev.event_time);
CREATE INDEX IF NOT EXISTS FOR (a:EntityAlias) ON (a.alias);
```

#### 검증
```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
```

---

### A-2: MacroTheme Seed 적재
**예상 시간**: 0.5시간

#### 작업 내용
- [x] 6개 거시 테마 노드 생성
  - `rates`, `inflation`, `growth`, `labor`, `liquidity`, `risk`

#### 산출물
- `cypher/01_seed_themes.cypher`

#### Cypher 스크립트
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

#### 검증
```cypher
MATCH (t:MacroTheme) RETURN t.theme_id, t.name, t.description;
// 예상: 6개 노드
```

---

### A-3: EconomicIndicator Seed 적재 + Theme 연결
**예상 시간**: 1시간

#### 작업 내용
- [x] 22개 지표 노드 생성 (FRED + 파생지표 `NETLIQ`)
- [x] 각 지표를 해당 MacroTheme에 `BELONGS_TO` 관계로 연결

#### 산출물
- `cypher/02_seed_indicators.cypher`

#### Cypher 스크립트
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
  {code: 'WTREGEN', name: 'Treasury General Account', unit: 'Millions USD', freq: 'daily', theme: 'liquidity'},
  {code: 'RRPONTSYD', name: 'Reverse Repo', unit: 'Millions USD', freq: 'daily', theme: 'liquidity'},
  {code: 'NETLIQ', name: 'Net Liquidity (WALCL - TGA - RRP)', unit: 'Millions USD', freq: 'daily', theme: 'liquidity'},
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

#### 검증
```cypher
MATCH (i:EconomicIndicator)-[:BELONGS_TO]->(t:MacroTheme)
RETURN t.theme_id, collect(i.indicator_code) AS indicators;
// 예상: 6개 테마에 지표들 분배
```

---

### A-4: Entity/EntityAlias Seed 적재
**예상 시간**: 0.5시간

#### 작업 내용
- [x] 핵심 기관/인물 Entity 10개 생성
- [x] 한국어/영어 Alias 연결

#### 산출물
- `cypher/03_seed_entities.cypher`

#### Cypher 스크립트
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

// Aliases
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

#### 검증
```cypher
MATCH (e:Entity)-[:HAS_ALIAS]->(a:EntityAlias)
WHERE e.canonical_id = 'ORG_FED'
RETURN e.name, collect(a.alias) AS aliases;
// 예상: ['연준', 'Fed', 'FOMC', '미 연방준비제도']
```

---

### A-5: FRED → IndicatorObservation 동기화 파이프라인
**예상 시간**: 2~3시간

#### 작업 내용
- [x] 데이터 소스 결정
  - 옵션 A: MySQL `fred_data` 테이블에서 Neo4j로 동기화 (권장) ✅
  - 옵션 B: FRED API 직접 호출
- [x] Python 적재 스크립트 작성 (`service/graph/indicator_loader.py`)
- [x] `IndicatorObservation` 노드 생성 및 `HAS_OBSERVATION` 관계 연결 (3,799건)

#### 산출물
- `hobot/service/graph/indicator_loader.py`

#### 파이프라인 구조
```python
# hobot/service/graph/indicator_loader.py
class IndicatorLoader:
    def __init__(self, neo4j_client, mysql_session):
        ...
    
    def sync_observations(self, indicator_codes: list, start_date: str, end_date: str):
        """MySQL fred_data에서 Neo4j로 IndicatorObservation 동기화"""
        for code in indicator_codes:
            observations = self._fetch_from_mysql(code, start_date, end_date)
            self._upsert_to_neo4j(code, observations)
    
    def _upsert_to_neo4j(self, code, observations):
        """MERGE 기반 멱등 적재"""
        query = """
        UNWIND $observations AS obs
        MATCH (i:EconomicIndicator {indicator_code: $code})
        MERGE (o:IndicatorObservation {indicator_code: $code, obs_date: date(obs.date)})
        SET o.value = obs.value, o.updated_at = datetime()
        MERGE (i)-[:HAS_OBSERVATION]->(o)
        """
        ...
```

#### 검증
```cypher
MATCH (i:EconomicIndicator {indicator_code: 'DGS10'})-[:HAS_OBSERVATION]->(o:IndicatorObservation)
RETURN o.obs_date, o.value ORDER BY o.obs_date DESC LIMIT 10;
```

---

### A-6: DerivedFeature 최소 피처 계산/적재
**예상 시간**: 2시간

#### 작업 내용
- [x] 최소 피처 정의
  - `delta_1d`: 전일 대비 변화량
  - `pct_change_1d`: 전일 대비 변화율
- [x] Python 계산 스크립트 작성 (`service/graph/derived_feature_calc.py`)
- [x] `DerivedFeature` 노드 생성 및 `HAS_FEATURE` 관계 연결 (44개 feature 유형)

#### 산출물
- `hobot/service/graph/derived_feature_calc.py`

#### Cypher 예시
```cypher
// 파생 피처 적재
MERGE (f:DerivedFeature {indicator_code: $code, feature_name: 'delta_1d', obs_date: date($date)})
SET f.value = $delta_value, f.updated_at = datetime()
WITH f
MATCH (o:IndicatorObservation {indicator_code: $code, obs_date: date($date)})
MERGE (o)-[:HAS_FEATURE]->(f)
```

---

### A-7: ALFRED 스키마/조회 인터페이스 초안
**예상 시간**: 1시간

#### 작업 내용
- [ ] `IndicatorObservation.vintage_date` 속성 추가 (nullable) _(Phase C로 연기)_
- [ ] `as_of_date` 기준 조회 Cypher 템플릿 작성 _(Phase C로 연기)_

#### 조회 템플릿
```cypher
// as_of_date 기준 최신 빈티지 조회
MATCH (i:EconomicIndicator {indicator_code: $code})-[:HAS_OBSERVATION]->(o:IndicatorObservation)
WHERE o.obs_date >= date($start_date) AND o.obs_date <= date($end_date)
  AND (o.vintage_date IS NULL OR o.vintage_date <= date($as_of_date))
WITH o ORDER BY o.obs_date, o.vintage_date DESC
WITH o.obs_date AS obs_date, collect(o)[0] AS latest_obs
RETURN obs_date, latest_obs.value AS value
```

---

### A-8: News(Document) upsert + 기본 링크 (rule-based)
**예상 시간**: 2~3시간

#### 작업 내용
- [x] MySQL `economic_news`에서 최신 N건 조회 (500건)
- [x] `Document` 노드 upsert (`doc_id = source:id`)
- [x] Rule-based 기본 링크
  - Country/Category → MacroTheme 매핑 (136 links)
  - Alias substring 매칭 → Entity 연결 (86 MENTIONS)

#### 산출물
- `hobot/service/graph/news_loader.py`

#### Python 구조
```python
class NewsLoader:
    THEME_MAPPING = {
        'Interest Rate': 'rates',
        'Inflation Rate': 'inflation',
        'GDP': 'growth',
        'Unemployment Rate': 'labor',
        ...
    }
    
    def upsert_documents(self, news_list):
        """뉴스 Document 노드 생성"""
        ...
    
    def link_to_themes(self, doc_id, category):
        """카테고리 기반 Theme 연결"""
        theme_id = self.THEME_MAPPING.get(category)
        if theme_id:
            # ABOUT_THEME 관계 생성
            ...
    
    def link_to_entities(self, doc_id, text):
        """Alias substring 매칭으로 Entity 연결"""
        for alias, entity_id in self.alias_dict.items():
            if alias in text:
                # MENTIONS 관계 생성
                ...
```

#### 검증
```cypher
MATCH (d:Document)-[:ABOUT_THEME]->(t:MacroTheme)
RETURN t.theme_id, count(d) AS doc_count;

MATCH (d:Document)-[:MENTIONS]->(e:Entity)
RETURN e.name, count(d) AS mention_count ORDER BY mention_count DESC;
```

---

### A-9: Phase A 검증 및 DoD 확인
**예상 시간**: 1시간

#### DoD (Definition of Done) 체크리스트
- [x] `MacroTheme` 6개 생성 확인 ✅
- [x] `EconomicIndicator` 22개 생성 + Theme 연결 확인 (NETLIQ 포함) ✅
- [x] `Entity` 10개 + Alias 31개 연결 확인 ✅
- [x] `IndicatorObservation` 22개 지표, 3,799건 ✅
- [x] `Document` 500건 적재 ✅
- [x] `Document-[:ABOUT_THEME]` 136건 (27%) ✅
- [x] `Document-[:MENTIONS]->Entity` 86건 ✅
- [ ] UI(Macro Graph)에서 탐색 가능 확인

#### 검증 쿼리
```cypher
// 노드 카운트
MATCH (t:MacroTheme) RETURN 'MacroTheme' AS label, count(t) AS count
UNION ALL
MATCH (i:EconomicIndicator) RETURN 'EconomicIndicator' AS label, count(i) AS count
UNION ALL
MATCH (e:Entity) RETURN 'Entity' AS label, count(e) AS count
UNION ALL
MATCH (a:EntityAlias) RETURN 'EntityAlias' AS label, count(a) AS count
UNION ALL
MATCH (d:Document) RETURN 'Document' AS label, count(d) AS count
UNION ALL
MATCH (o:IndicatorObservation) RETURN 'IndicatorObservation' AS label, count(o) AS count;

// 관계 카운트
MATCH ()-[r:BELONGS_TO]->() RETURN 'BELONGS_TO' AS rel, count(r)
UNION ALL
MATCH ()-[r:ABOUT_THEME]->() RETURN 'ABOUT_THEME' AS rel, count(r)
UNION ALL
MATCH ()-[r:MENTIONS]->() RETURN 'MENTIONS' AS rel, count(r)
UNION ALL
MATCH ()-[r:HAS_OBSERVATION]->() RETURN 'HAS_OBSERVATION' AS rel, count(r);
```

---

## 📊 Phase A 산출물 요약

| 구분 | 산출물 |
|------|--------|
| Cypher | `cypher/00_constraints.cypher` ~ `cypher/03_seed_entities.cypher` |
| Python | `service/graph/neo4j_client.py`, `indicator_loader.py`, `derived_feature_calc.py`, `news_loader.py` |
| 문서 | Phase A 완료 보고서, 검증 결과 |
