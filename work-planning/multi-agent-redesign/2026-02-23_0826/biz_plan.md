# [Plan] 멀티 에이전트 시스템 로직 전면 재설계 (역할 분리 및 고도화)

## 1. 개요 및 배경 (현재 문제점 진단)

* **도메인 에이전트의 역할 한계**: 각 도메인 에이전트(`equity`, `real_estate`, `ontology`, `macro`)가 전문적인 "분석" (인사이트 추출, 지표 가중치 산출, 트렌드 모델링 등) 역할을 수행하지 못하고, 단순히 시스템 도구(Neo4j, SQL)를 호출하여 원시 데이터(raw data)를 조회해 던지는 수준에 머물러 있음 (근거 빈약).
* **슈퍼에이전트(Supervisor Agent) 데이터 과부하 (Context Overflow)**: 도메인 에이전트가 로 데이터 수준으로 무지성으로 올려보낸 정보들이 슈퍼에이전트 프롬프트에 그대로 쌓이고 있음. 이로 인해 슈퍼에이전트가 단편적 사실을 직접 거르고 통합해야 하는 이중 과부하 및 할루시네이션(환각) 리스크를 떠안고 있음 (Jack of all trades 현상 유발).
* **목표**: `멀티 에이전트 분석 설계.md` 문서에 기술된 권장 아키텍처(Graph Pattern, 구조화된 출력 기반 Handoff)를 기준으로, 도메인 에이전트와 슈퍼에이전트 간의 역할을 엄격하게 분리(Decoupling)하는 작업을 Phase별로 수립.

---

## 2. 작업 Phase (슈퍼에이전트 vs 도메인 에이전트 분리)

### 📌 [Phase 1] 도메인 에이전트 (Domain Agent) 중심 파이프라인 자율화 및 고도화
**(목표: 도메인 에이전트는 원시 데이터를 스스로 "해석/분석"하여 결론과 명확한 수치/근거를 내놓아야 함)**

1. **도메인 특화 자율 분석 파이프라인 구축 (Domain-Specific Refinement)**:
    * `equity_analyst_agent (주식 분석 에이전트)`:
        * **정형 데이터(기술적/거시 지표) 정제**: OHLCV 기반 60여 개 기술적 지표 및 변동성 계산, FRED 거시경제 지표(스케일링, 빈티지 백테스팅)를 활용한 경제 국면(Regime) 진단 및 지표 가중치 동적 부여.
        * **비정형 데이터(펀더멘털/센티먼트) 정형화**: 비구조화된 재무제표 KPI 추출 및 구조화, 실적 발표(Earnings Call) 및 뉴스를 자연어처리(NLP)로 분석하여 경영진의 톤/내부 리스크를 센티먼트 점수(Sentiment Score)로 수치화.
    * `real_estate_agent (부동산 분석 에이전트)`:
        * **실거래 및 수급 지표 정량화**: 단순 시계열 가격 변동 뿐만 아니라 거래량 추이 파악, 전세가율, 재고율(미분양 물량), 수요/공급 지수 및 임대수익률(Cap Rate와 유사) 산출.
        * **정책 데이터의 재무적 치환 및 공간 융합**: 비정형 텍스트인 정부 규제문건(LTV 완화 등)의 NLP 파싱을 통한 실제 세후 수익률/현금흐름 변수로 치환. 그리고 주담대 금리 민감도 산출과 개발 호재(공간 데이터)를 결합한 가치 모델링.
    * `ontology_master_agent (온톨로지 마스터 에이전트)`:
        * **FIBO 기반 지식 그래프 구축**: 파편화된 기업명 및 비정형 뉴스 이벤트(M&A, 화재, 파업 등)를 FIBO(금융 비즈니스 온톨로지) 스키마를 뼈대로 한 일관된 엔티티 및 연결성(Edge)으로 구조화.
        * **숨겨진 파급 효과(Ripple Effect) 탐지**: 그래프 데이터베이스(Neo4j)와 중심성 알고리즘 등을 가동하여 개별 이벤트가 공급망/파트너사 체인을 거쳐 전체 시장에 미치는 파급 점수(Impact Score) 계산.
2. **원시 데이터 차단 및 분석 요약 강화**:
    * 도메인 에이전트의 LLM 프롬프트(`graph_rag_agent_execution` 내)를 수정하여, 내부에서 조회한 DB/Graph 원시 결과를 외부(슈퍼)에 그대로 유출하지 못하게 강제.
    * 대신 이 데이터를 바탕으로 "왜 이런 결과가 나왔는지(Why)"에 대한 구체적 논리와 "결론(So What)"을 생산해야 함.

### 📌 [Phase 2] 통신 인터페이스 규격화 (Structured Output 도입)
**(목표: 도메인과 융합 계층 사이에 엄격한 JSON 기반 Handoff 프로토콜 도입)**

1. **표준 응답 JSON 스키마(Pydantic/Zod 등 구조체) 정의**:
    도메인 에이전트가 슈퍼에이전트로 정보를 보낼 때는 무조건 아래 포맷(또는 이와 유사한 형태)으로만 반환하게 제한.
    * `domain_source`: "MACRO", "EQUITY", "REAL_ESTATE" 등 식별자.
    * `confidence_score`: 분석 결과 확신도 (0.0 ~ 1.0)
    * `primary_trend`: 단일 방향성 요약 (예: BEAR, BULL, NEUTRAL)
    * `key_drivers`: 결론을 짓는 결정적 수치 및 변수 3~5가지 목록 (명확한 근거)
    * `quantitative_metrics`: 주요 도메인 산출 지표 및 점수
    * `analytical_summary`: 사람이 볼 수 있는 통찰 기반 요약 텍스트
2. **파이프라인 레이어 (live_executor) 변경**:
    * 도메인 에이전트 실행 완료 지점에 파서를 도입하여 구조화된 출력이 아니면 재귀적으로 수정 혹은 페일오버.
    * 슈퍼에이전트를 위한 컨텍스트 메이커(`build_graph_rag_context()`)에서 도메인의 원본 툴(Tool) 결과를 다 뺀 후 위 JSON 요소들만 남겨서 간결하게 연결.

### 📌 [Phase 3] 슈퍼에이전트 (Super Agent) 합성/오케스트레이션 고도화
**(목표: 정보 취합기가 아니라 비판적 다차원 의사결정자로 역할 전환)**

1. **다중 도메인 데이터 복합 추론 (Cognitive Synthesis)**:
    * 슈퍼에이전트 프롬프트 템플릿의 대대적 변경: 들어오는 데이터 구조가 이전의 무질서한 텍스트에서 각 도메인별 JSON(Summary, drivers, score) 블록들로 간결해짐을 안내.
    * 여러 도메인(거시환경 vs 개별자산, 단기이슈 vs 장기트렌드 등) 간의 결과를 조합하여 하나의 확고한 답변(Insight)으로 Synthesis 하도록 지침 구체화.
2. **논리 충돌 해결 (Safe Debate Protocol)**:
    * `macro` 에이전트는 "금리 인하 유동성에 따른 긍정적"을 외치고, `real_estate` 에이전트는 "대출 한도 축소에 따른 부정적" 시그널을 구조화된 출력으로 보냈을 경우,
    * 슈퍼에이전트 단일 패스로 답변하기 전에, 비평가(Critic)로서 충돌(Conflict)이 발생함을 인식하고 해당 모순지점을 명백히 지적하거나 조율(가중치 조절 등)하게 만들어 "양면을 종합한 결론 추론(Reflective Reasoning)"을 내도록 한다.

### 📌 [Phase 4] 운영 안정화 및 예외 처리 (Error Fallback)
**(목표: LLM Parsing 에러 및 스키마 불일치로 인한 시스템 파면 방지)**

1. **스키마 불일치 및 파싱 에러 재시도 (Retry Strategy)**:
    * 도메인 에이전트의 LLM 응답이 지정된 JSON(DomainInsight)을 준수하지 않거나 파싱이 불가능한 경우, 최대 1회(또는 환경변수 설정값) 재시도(Retry)를 수행합니다.
2. **최후의 보루 (Safe Fallback)**:
    * 재시도마저 실패하거나 타임아웃이 발생할 경우, 예외를 던져 파이프라인 전체를 죽이지 않고 **Rule-based Empty JSON**을 반환합니다. 
    * `{"domain_source": "{AGENT_NAME}", "confidence_score": 0.0, "primary_trend": "NEUTRAL", "key_drivers": ["에이전트 응답 지연/오류"], "analytical_summary": "현재 데이터를 분석할 수 없습니다."}`
3. **롤백 (Rollback) 차단기**:
    * 배포 후 `fallback` 발생률이 일정 비율(예: 전체 질의의 5%)을 초과하면 환경 변수(`USE_STRUCTURED_HANDOFF=false`)를 통해 기존의 Raw Data 덤프 방식으로 런타임에 즉시 롤백 가능하도록 플래그를 심습니다.

### 📌 [Phase 5] 정량적 KPI 측정 (검증 계획)
**(목표: 감이 아닌 수치로 아키텍처 개편 성능 증명)**

1. **비용 및 지연시간 (Cost / Latency)**:
    * **토큰 소비량 감소**: 슈퍼에이전트로 유입되는 Context Prompt Token 수가 기존 대비 **최소 40% 이상 감소**함을 측정 (Raw Data를 버리기 때문).
    * **지연시간(Latency)**: 다중 에이전트 Parallel 호출의 P95 지연시간을 기존 구조 대비 **동일하거나 최대 +2초 이내**로 방어.
2. **응답 품질 (Quality & Accuracy)**:
    * **근거 밀도(Evidence Density)**: 최종 반환되는 답변의 모든 key_points가 명확한 데이터(SQL / Graph)에 Mapping 되는 비율 **90% 이상** 달성 (Hallucination 억제).
    * **의견 충돌 조율 성공률**: 2개 이상의 도메인에서 상반된 추세(BEAR vs BULL)를 반환했을 때, 슈퍼에이전트가 이를 그대로 뱉지 않고 "상충되는 요인이 있다"고 인지하는 비율 테스트.
3. **회귀 테스트 (Regression Test) 조건**:
    * 기존 운영망에서 자주 묻는 "송파구 아파트 가격 추이 및 거시 전망 결합 질문", "미국 실업률 쇼크 파급효과 질문" 등 Standard Query 10종을 정의하여 A/B 테스트 진행 및 Pass 여부 확인.

---

## 3. 요약 (AS-IS vs TO-BE)

| 구분 | AS-IS (현재) | TO-BE (재설계 후) |
| --- | --- | --- |
| **도메인 에이전트의 역할** | 도구(툴) 실행기. DB/그래프 데이터 긁어오기 후 즉시 상위 토스. | 자체 분석가. 데이터를 분석/해석하고 결론/확신도 및 파급효과 도출. |
| **에이전트간 데이터 전달 형식** | 정형화되지 않은 Markdown 및 긴 원시 데이터 스트링의 조합 | 철저하게 다이어트 및 정제된 JSON 스키마 (Structured Outputs) |
| **슈퍼에이전트의 역할** | 방대한 데이터를 읽고 요약하려다 지시 따르기에 버거움 (정보 과부하) | 취합된 구조화 데이터를 통해 도메인 간 비판적 리뷰 수행 및 최종 인사이트 종합 의사결정 수행 |
| **장애 대응 (안정성)** | LLM 포맷 깨지면 파이프라인 붕괴 위험 | 자체 파서 + 빈 JSON Fallback + 런타임 롤백 플래그 구축 |

## 4. 진행 순서 (Workflow)

1. `workflow/01_domain_agent_refactoring.md` - Phase 1 도메인 자율화 변경 및 프롬프트 재작성 (✅ 완료)
2. `workflow/02_structured_output_interface.md` - Phase 2 API 규격화 (DomainInsight JSON Schema 완성) 및 파서 수정 (✅ 완료 - Phase 1에 병합)
3. `workflow/03_super_agent_orchestration.md` - Phase 3 프롬프트 및 로직 고도화 구현 (✅ 완료)
4. `workflow/04_fallback_and_validation.md` - Phase 4 (안정화: Retry/Fallback/롤백 플래그) (✅ 완료)
5. `workflow/05_domain_insight_bridge_fix.md` - Phase 2 보완: DomainInsight 스키마 브릿지 수정 (✅ 완료)
6. Phase 5 (정량 검증): 골든셋 회귀 테스트 및 KPI 측정 (🔲 미착수)
