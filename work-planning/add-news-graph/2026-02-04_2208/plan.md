# Ontology 메뉴 하위 화면 구성 및 Macro Graph 연결 계획

## 1. 개요
* **목표**: Ontology 메뉴를 "Architecture Graph"와 "Macro Graph"로 분리하고, Macro Graph는 별도 Neo4j 도메인에 연결. (legacy 명칭: News Graph)
* **기간**: 2026-02-04
* **담당**: Antigravity

## 2. 작업 내용

### 2.1 Backend (Python)
* [x] `hobot/main.py` 수정
    * `Neo4jQueryRequest` 모델에 `database` 필드 추가 (기본값: "architecture")
    * `get_neo4j_driver` 함수가 `database` 인자에 따라 다른 드라이버("architecture" 또는 "macro")를 반환하도록 수정 (legacy: "news")
    * `_neo4j_macro_driver` 싱글톤 추가
    * APi 엔드포인트 `/api/neo4j/query`, `/api/neo4j/health` 수정

### 2.2 Frontend (React)
* [x] `hobot-ui-v2/src/services/neo4jService.ts` 수정
    * `runCypherQuery`, `checkNeo4jHealth` 함수에 `database` 파라미터 추가
* [x] `hobot-ui-v2/src/components/OntologyPage.tsx` 수정
    * `mode` prop 추가 ('architecture' | 'macro')
    * `mode`에 따라 쿼리 실행 시 `database` 파라미터 전달
    * UI 타이틀 및 예제 질문을 모드에 맞게 변경
* [x] `hobot-ui-v2/src/components/Header.tsx` 수정
    * Ontology 메뉴를 Dropdown으로 변경
    * 하위 메뉴: "Architecture Graph", "Macro Graph" 추가
* [x] `hobot-ui-v2/src/App.tsx` 수정
    * 라우트 추가: `/ontology/architecture`, `/ontology/macro` (legacy: `/ontology/news`는 redirect)
    * `/ontology` 접속 시 리다이렉트 처리

### 2.3 Deployment
* [x] `.github/workflows/deploy.yml` 수정
    * `NEO4J_MACRO_URI` Secret 환경변수 추가
* [x] `.github/deploy/deploy.sh` 수정
    * `NEO4J_MACRO_URI` export 및 `.env` 파일 생성 로직 추가

## 3. 검증 계획
* 배포 후 각 페이지 접속 테스트
* Architecture Graph가 기존 데이터(Localhost/Existing)를 잘 불러오는지 확인
* Macro Graph가 새로운 데이터(Macro Neo4j)를 잘 불러오는지 확인

## 4. 기술적 주의사항 및 고도화 제언 (Data/Analysis Layer)
본 문서는 “Macro Graph UI/연결(legacy: News Graph)”까지를 범위로 작성되었으나, **그래프의 분석 가치**는 결국 “데이터 적재/정규화/가중치 관리” 품질에 의해 결정됩니다.
아래 항목은 Macro Graph 도메인에 실제 분석 데이터를 채우는 단계에서 반드시 고려해야 할 기술적 주의사항과 고도화 방향입니다.

### 4.1 엔티티 정규화(Entity Normalization) / NEL 강화
뉴스 텍스트는 표현이 매우 다양하므로, 엔티티 정규화가 무너지면 그래프 연결성 자체가 파편화됩니다.

* **문제 예시**: "연준" / "연방준비제도" / "Fed" / "FOMC"가 서로 다른 노드로 생성되면, 질의/경로 분석이 왜곡됨
* **권장 방향**
    * **Canonical Entity 노드 중심 설계**: `Entity{canonical_id, type, name}` + `EntityAlias{alias, lang, source}` 또는 `aliases[]` 속성 관리
    * **Named Entity Linking(NEL) 파이프라인 분리**:
        1) NER(추출) → 2) Candidate 생성(사전/벡터/룰) → 3) Disambiguation(LLM/규칙) → 4) Canonical로 `MERGE`
    * **표준 ID 매핑**:
        * 기관/인물/지명: Wikipedia/Wikidata ID(또는 내부 KB ID)
        * 거시 지표: FRED series id(가능 시)
    * **운영 포인트**
        * “신규 엔티티 생성”은 보수적으로(충분한 근거가 없으면 기존 후보에 연결/보류)
        * 정규화 실패 케이스를 수집해 **alias 사전/룰**을 지속적으로 확장
* **검증 기준(예)**: 동일 의미 엔티티(예: Fed)가 1개의 canonical node로 수렴하고, alias/언어별 표현은 alias로만 관리

### 4.2 FRED 수정 이력(Revision History) 반영: ALFRED(빈티지) 기반
거시 지표는 과거 값이 계속 수정되므로, 모델 검증/학습에서는 “현재의 과거 데이터”가 아니라 “당시 발표(가용) 데이터”를 사용해야 룩어헤드 편향을 차단할 수 있습니다.

* **권장 방향**
    * FRED 단일 시계열 저장에 더해, **ALFRED 빈티지 데이터**를 함께 적재
    * 그래프 모델에 `IndicatorObservation`의 빈티지 개념을 도입:
        * 예: `IndicatorObservation{indicator_code, obs_date, value, vintage_date}`
        * 또는 `Observation` 노드와 `Vintage` 노드를 분리해 `(Observation)-[:AS_OF]->(Vintage)` 형태로 관리
    * GraphRAG/분석 시에는 항상 `as_of_date`(분석 기준일)를 입력으로 받아,
      해당 시점에 이용 가능했던 최신 빈티지를 선택하도록 **조회 규칙을 표준화**
* **검증 기준(예)**: “2023-01-15 기준의 GDP”를 조회하면, 2023-01-15 이전에 발표된 vintage만 반환

### 4.3 인과관계 비정상성(Non-stationarity) 대응: 동적 가중치/슬라이딩 윈도우
경제 관계는 시기별로 약해지거나 반전될 수 있습니다. 따라서 그래프의 `AFFECTS`(영향) 관계는 고정 지식이 아니라, **시간에 따라 업데이트되는 통계적 가중치**로 운영하는 것이 안전합니다.

* **권장 방향**
    * `AFFECTS` 관계에 `as_of`, `window_days`, `method`, `weight`, `confidence` 등 속성을 추가하고, 주기적으로 재계산
    * **슬라이딩 윈도우**(예: 최근 90/180일) 기반으로 관계 강도를 업데이트하는 배치 작업을 파이프라인에 포함
    * 업데이트 전/후를 추적할 수 있도록 “관계 스냅샷”을 저장:
        * 예: `(AFFECTS_SNAPSHOT{as_of, window_days, weight, stats...})` 노드로 이력화하거나, 관계 속성에 `history[]`를 별도 보관
* **검증 기준(예)**: 동일 Event/Theme→Indicator 관계가 기간(window)에 따라 다른 weight를 갖고, UI에서 “as_of 기준”으로 필터링 가능

---
**추가 반영일**: 2026-02-06
