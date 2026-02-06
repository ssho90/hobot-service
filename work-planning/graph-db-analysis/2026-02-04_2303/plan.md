# Hobot Service: 경제 지표 및 뉴스 분석을 위한 Graph DB 도입 및 개선 방안

## 1. 개요 (Overview)
본 문서는 `hobot-service`의 기존 경제 분석 역량을 강화하기 위해 **FRED 거시경제 지표**와 **수집된 뉴스 데이터**를 **Graph Database (Neo4j)** 기반으로 통합 분석하는 개선 방안을 제시합니다.
기존의 단순 시계열 상관관계 분석이나 텍스트 요약을 넘어, 경제 이벤트와 지표 간의 **구조적 인과관계(Causal Inference)**와 **파급 효과(Ripple Effect)**를 분석할 수 있는 시스템을 구축하는 것을 목표로 합니다.

참고 문서: `경제 지표 뉴스 분석 그래프 DB 활용` (Google Docs)

## 2. 현황 분석 (Current Status Analysis)

### 2.1 기존 시스템 구조
*   **News Collection**: `daily_news_agent.py`, `news_manager.py` 등을 통해 뉴스를 수집, 요약하여 텍스트 형태로 저장.
*   **Macro Data**: `macro_trading` 모듈에서 FRED 등의 지표를 시계열 데이터로 수집 및 저장.
*   **한계점**:
    *   뉴스와 경제 지표가 분리되어 있어, "특정 뉴스가 특정 지표에 미치는 영향"을 정량적/구조적으로 파악하기 어려움.
    *   LLM 분석이 텍스트(프롬프트)에 의존하며, 과거 데이터나 복잡한 인과 사슬을 참조하는 데 한계가 있음(Context Window 제한 등).

## 3. 개선 방안 (Improvement Plan)

### 3.1 아키텍처 개선 (Architecture)
기존 RDBMS/File 기반 구조에 **Knowledge Graph Layer (Neo4j)**를 추가합니다.

*   **Data Sources**:
    1.  **Macro Indicators (FRED)**: 정형 데이터. 노드(`EconomicIndicator`)로 매핑.
    2.  **News Articles**: 비정형 텍스트. LLM을 통해 노드(`Event`, `Person`, `Org`)와 엣지(`AFFECTS`, `CAUSES`)로 변환.
*   **Processing Layer (Graph Builder)**:
    *   **Extraction Engine**: LangChain + LLM을 활용하여 뉴스 텍스트에서 엔티티와 관계를 추출.
    *   **Entity Resolution**: 추출된 엔티티(예: "Fed", "연준")를 정규화하고 기존 FRED 지표와 연결.
*   **Analysis Layer**:
    *   **GraphRAG**: LLM 질의 시 그래프 컨텍스트(인접 노드, 경로)를 함께 제공하여 할루시네이션 감소 및 추론 능력 강화.
    *   **Impact Analysis**: 특정 이벤트 발생 시 연결된 지표들의 변동 가능성 시뮬레이션.

### 3.2 데이터 모델링 (Schema Design via FIBO)
금융 산업 표준 온톨로지(FIBO)를 참조하여 스키마를 설계합니다.

#### 주요 노드 (Nodes)
*   `EconomicIndicator` (경제 지표): FRED Series ID, Name, Unit (예: `CPI`, `Oil Price`, `10Y Treasury`)
*   `Event` (이벤트): 뉴스에서 추출된 사건 (예: `Rate Hike`, `War`, `Supply Shock`)
*   `Organization` (기관): `CentralBank`, `Company`, `Government` (예: `Fed`, `BOK`, `Samsung`)
*   `Person` (인물): 주요 정책 결정자 (예: `Powell`)
*   `Topic` (주제): `Inflation`, `Recession` 등
*   `Document` (뉴스 원문): 출처, 날짜, URL

#### 주요 관계 (Relationships)
*   `(:Event)-[:AFFECTS {sentiment, weight}]->(:EconomicIndicator)`: 사건이 지표에 영향을 미침.
*   `(:Organization)-[:ANNOUNCED]->(:Event)`: 기관이 이벤트를 발표함.
*   `(:EconomicIndicator)-[:HAS_CORRELATION {score}]->(:EconomicIndicator)`: 지표 간 통계적 상관관계.
*   `(:Document)-[:MENTIONS]->(:Event|:Person|:Organization)`: 뉴스가 특정 엔티티를 언급.
*   `(:Event)-[:CAUSES]->(:Event)`: 사건 간의 인과관계 (Ripple Effect).

## 4. 상세 워크플로우 (Detailed Workflow)

### Step 1: Neo4j 환경 구성 및 연동 (Infrastructure)
*   **목표**: Hobot Service에서 Neo4j에 접근할 수 있도록 설정.
*   **액션**:
    *   Neo4j 인스턴스 확인 (현재 `52.78.104.1`).
    *   `hobot/service/database/graph_db.py` (신규) 모듈 작성: Neo4j Driver 설정 및 Connection Pool 관리.
    *   Graph DB 초기화 스크립트 작성 (Indicies, Constraints 설정).

### Step 2: 그래프 데이터 파이프라인 구축 (Graph Pipeline)
*   **목표**: 뉴스 수집 시 자동으로 그래프 데이터를 추출하여 적재.
*   **액션**:
    1.  **Indicator Loader**: FRED 지표 목록을 `EconomicIndicator` 노드로 일괄 등록 (Initial Seeding).
    2.  **News Processor**: `daily_news_agent.py`의 수집 로직 후단에 `GraphExtractionService` 호출 추가.
    3.  **LLM Extraction**:
        *   Prompt Engineering: 뉴스 텍스트를 입력받아 JSON 형태의 Graph Data(Nodes, Edges)를 반환하는 프롬프트 작성.
        *   LangChain `LLMGraphTransformer` 활용 고려 또는 커스텀 구현.
    4.  **Ingestion**: 추출된 데이터를 Neo4j에 `MERGE` 구문을 사용하여 중복 없이 적재.

### Step 3: 연결 및 정규화 (Linking & Resolution)
*   **목표**: 텍스트에서 추출된 "유가"와 FRED의 "DCOILWTICO" 지표를 연결.
*   **액션**:
    *   **Entity Resolution**: LLM을 이용해 추출된 엔티티가 기존 `EconomicIndicator` 노드와 일치하는지 판단하여 `SAME_AS` 또는 직접 병합.
    *   **Time-Series Linking**: `EconomicIndicator` 노드에 최신 수치(Value) 속성 업데이트.

### Step 4: 분석 기능 구현 (Analysis Implementation)
*   **목표**: 구축된 그래프를 활용한 인사이트 도출.
*   **액션**:
    *   **Impact Path Query**: "금리 인상" 이벤트 노드에서 2-hop 이내의 `AFFECTS` 관계를 가진 지표 조회.
    *   **Context Retrieval**: `hobot-ui` 챗봇 질의 시, 관련 키워드의 그래프 이웃 노드 정보를 프롬프트 컨텍스트로 주입 (GraphRAG).

### Step 5: 시각화 및 UI 적용 (Visualization)
*   **목표**: 사용자에게 그래프 관계를 직관적으로 보여줌.
*   **액션**:
    *   `hobot-ui-v2`의 "Macro Graph" 페이지에 `react-force-graph` 등을 활용하여 시각화.
    *   지표 클릭 시 관련 뉴스(Event)와 연결선 강조.

## 5. 실행 계획 (Action Plan) - 오늘 할 일

1.  **Work Planning 폴더 생성**: `/work-planning/graph-db-analysis/2026-02-04_2303/` (완료)
2.  **Plan 문서 작성**: 현재 문서 (`plan.md`).
3.  **Graph Extraction 프로토타입**: 뉴스 텍스트 샘플로 LLM을 통해 노드/엣지를 추출하는 스크립트 작성 (`prototype_extract.py`).
4.  **Neo4j 스키마 적용**: `setup_graph_schema.py` 작성 및 실행.

---
**작성자**: Antigravity (AI Assistant)
**작성일**: 2026년 2월 4일
