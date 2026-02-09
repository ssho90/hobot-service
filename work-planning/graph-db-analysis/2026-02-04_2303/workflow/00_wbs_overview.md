# Macro Knowledge Graph (MKG) 프로젝트 WBS (Work Breakdown Structure)

## 📋 프로젝트 개요
- **프로젝트명**: FRED 거시경제 + 경제뉴스 기반 Macro Knowledge Graph 고도화
- **목표**: Neo4j 기반 MKG 구축으로 이벤트-지표 연결, 파급 경로 추론, GraphRAG 분석 고도화
- **예상 기간**: 약 3~4주

---

## 🔤 용어/연동 규칙 (중요)
- 본 WBS에서 말하는 **`macro` database**는 “Neo4j 내부 멀티-DB 이름”이 아니라, **Macro Graph 연결(profile)** 을 의미합니다.
  - API에서 `database="macro"`로 지정하면 Macro Graph로 질의/적재합니다. (legacy: `database="news"`도 허용)
- **UI 화면명/라우팅**
  - Ontology > **Macro Graph**: `/ontology/macro`
  - legacy: `/ontology/news`는 `/ontology/macro`로 redirect
- **환경변수**
  - `NEO4J_MACRO_URI` 사용

---

## 🗂 Phase 구성 및 일정

| Phase | 명칭 | 예상 기간 | 주요 목표 |
|-------|------|----------|----------|
| **A** | MVP: 스키마/시딩/기본 링크 | 1~2일 | Neo4j에 MKG 최소 스키마 적재 + Seed 데이터 + 기본 탐색 가능 |
| **B** | News Extraction 정식화 | 2~4일 | LLM 기반 뉴스 추출(Event/Fact/Claim/Evidence) + NEL 파이프라인 |
| **C** | 정량 Impact & 통계 엣지 | 1주 | Event Window Impact, 동적 가중치, Indicator 상관관계, Story 클러스터링 |
| **D** | GraphRAG + UI 완성 | 1주 | 질문→서브그래프 API, Evidence 경로 탐색 UX, MacroState/AnalysisRun |
| **E** | Strategy Integration | 1주 | MP/Sub-MP 선택(리밸런싱 비율 산출) ↔ Macro Graph 근거 연결 + 결정/근거 그래프 저장 |

---

## 📁 WBS 파일 구조

```
workflow/
├── 00_wbs_overview.md          # 현재 파일 (전체 WBS 개요)
├── 01_phase_a_schema_seed.md   # Phase A: 스키마/시딩/기본 링크
├── 02_phase_b_extraction.md    # Phase B: News Extraction 정식화
├── 03_phase_c_impact_stats.md  # Phase C: 정량 Impact & 통계 엣지
└── 04_phase_d_graphrag_ui.md   # Phase D: GraphRAG + UI 완성
└── 05_phase_e_strategy_integration.md  # Phase E: Strategy Integration (MP/Sub-MP ↔ Macro Graph)
```

---

## ✅ 전체 체크리스트 요약

### Phase A (MVP)
- [ ] A-0: Macro Graph 연결/헬스체크
- [ ] A-1: Neo4j 제약조건/인덱스 생성
- [ ] A-2: MacroTheme Seed 적재
- [ ] A-3: EconomicIndicator Seed 적재 + Theme 연결
- [ ] A-4: Entity/EntityAlias Seed 적재
- [ ] A-5: FRED → IndicatorObservation 동기화 파이프라인
- [ ] A-6: DerivedFeature 최소 피처 계산/적재
- [ ] A-7: ALFRED 스키마/조회 인터페이스 초안
- [ ] A-8: News(Document) upsert + 기본 링크(rule-based)
- [ ] A-9: Phase A 검증 및 DoD 확인

### Phase B (News Extraction)
- [ ] B-1: LLM 추출 JSON 스키마 확정 + Validator
- [ ] B-2: Evidence 강제 로직 구현
- [ ] B-3: Country/Category 표준화 사전 구축
- [ ] B-4: ExternalIndicator 확장 모델 정의
- [ ] B-5: NEL 파이프라인 구현 (추출→후보→연결)
- [x] B-6: 추출 파이프라인 운영화 (재시도/캐시/Backfill)
- [ ] B-7: Phase B 검증 및 DoD 확인

### Phase C (정량 Impact & 통계)
- [x] C-1: Event Window Impact 계산 모듈
- [x] C-2: AFFECTS 동적 가중치 재계산 배치
- [x] C-3: Indicator↔Indicator 통계 엣지 생성
- [x] C-4: Story(내러티브) 클러스터링
- [x] C-5: 데이터 품질/모니터링 지표 추가
- [x] C-6: Phase C 검증 및 DoD 확인
- 최신 실측(2026-02-08 재실행): `AFFECTS observed_delta=3966/3966(100%)`, `CORRELATED_WITH=31`, `LEADS=24`, `Story=25` (`source_documents=314`, `story_min_docs=3`)

### Phase D (GraphRAG + UI)
- [x] D-1: 질문→서브그래프 추출 API 개발 (`POST /api/graph/rag/context`)
- [x] D-2: GraphRAG 응답 생성 모듈 (`POST /api/graph/rag/answer`)
- [x] D-3: UI Evidence/경로 탐색 UX 구현 (`OntologyPage` Macro Graph UX + Path Explorer)
- [x] D-4: MacroState/AnalysisRun 적재 로직 (`state/macro_state_generator.py` + answer API 연동)
- [x] D-5: 운영/품질 모니터링 구축 (`GraphRagApiCall` 로그 + `/api/graph/rag/metrics` + UI Top-K/페이지네이션)
- [x] D-6: Phase D 검증 및 DoD 확인
- 최신 실측(2026-02-08 재검증): 질문 성공 `10/10`, Evidence 포함 `10/10`, 문서링크 포함 `10/10`, `Document→Evidence→Claim=2,950`, `MacroState(2026-02-08)=1`, `AnalysisRun(당일=2/누적=20)`, 재현성 `84.62%`

### Phase E (Strategy Integration)
- [ ] E-1: StrategyDecision 그래프 스키마 확정
- [ ] E-2: Macro Graph 컨텍스트 빌더(전략 프롬프트 주입용)
- [ ] E-3: `ai_strategist.py` MP/Sub-MP 프롬프트에 그래프 근거 블록 통합(옵션 + 폴백)
- [ ] E-4: 전략결정(MySQL `ai_strategy_decisions`) → Macro Graph 미러링 저장
- [ ] E-5: StrategyDecision 조회 API/템플릿 질의
- [ ] E-6: UI에서 최신 전략/근거(Evidence) 탐색 UX
- [ ] E-7: Phase E 검증 및 DoD 확인

---

## 🔗 의존성 관계

```
Phase A ────┬───> Phase B ───> Phase C ───> Phase D ───> Phase E
            │
            └───> (UI 기본 탐색 가능)
```

- **Phase A 완료 필수**: Phase B 이전에 Schema/Seed가 반드시 완료되어야 함
- **Phase B → C 순차**: Evidence 및 NEL이 확립되어야 정량 Impact 계산이 유의미함
- **Phase C → D 순차**: 통계 엣지/Story가 있어야 GraphRAG 품질이 높아짐

---

## 📌 핵심 의사결정 포인트

1. **Neo4j DB 경계**: `macro` database 사용 (결정됨)
2. **ID 정책**: Deterministic ID (`source:id`, hash 기반)
3. **ALFRED 도입 수준**: Phase A에서 스키마만, 실제 적재는 Phase C
4. **LLM 비용 관리**: Phase B부터 캐시/재시도/DLQ 필수
5. **Strategy Integration 범위**: MP/Sub-MP 선택(리밸런싱 비율 산출)과 “그래프 근거/저장”을 Phase E로 분리
