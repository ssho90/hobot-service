# Phase D: GraphRAG + UI 완성

## 📋 Phase 개요
- **예상 기간**: 1주
- **목표**: 질문→서브그래프API, Evidence경로탐색UX, MacroState/AnalysisRun 적재
- **전제 조건**: Phase C 완료 (통계엣지/Story 확보)

---

## 🔧 작업 상세

### D-1: 질문→서브그래프 추출 API 개발
**예상 시간**: 1.5일

#### 작업 내용
- [x] 입력: `question`, `time_range(7/30/90d)`, `country?`, `as_of_date?`
- [x] 처리 흐름:
  1. 키워드/엔티티/지표 후보 매칭
  2. 후보에서 최근 Event/Document/Story 확장
  3. Evidence 포함 컨텍스트 패키징
- [x] 출력: 서브그래프(nodes/links) + 근거텍스트 + 추천쿼리

#### 구현 메모 (2026-02-07)
- 신규 파일: `hobot/service/graph/rag/context_api.py`
- 라우터 연결: `hobot/main.py`에서 `graph_rag_router`를 `api_router`에 include
- 테스트 추가: `hobot/tests/test_phase_d_context_api.py`
- 응답 확장: `meta`(기간/매칭테마/카운트) 포함

#### Hybrid Search 개선 (2026-02-08)
- **Full-text Index 도입**: `document_fulltext` 인덱스 생성 (`cjk` analyzer 적용, 한글/영어 혼용 지원)
- **기존 CONTAINS 스캔 → BM25 랭킹 기반 검색으로 교체**
  - 속도: 데이터 증가에도 안정적인 인덱스 기반 검색
  - 정확도: BM25 점수로 관련도 높은 문서 우선 순위 부여
  - 유연성: 구문/다중 토큰 검색 (예: "Kevin Warsh Fed chair") 강화
- **Hybrid Pipeline**: Full-text로 후보 회수 → 그래프 관계로 필터링
- **Fallback 지원**: Full-text Index 미존재 시 기존 CONTAINS 방식으로 자동 폴백
- 검색 대상 속성: `title`, `text`, `title_ko`, `description_ko`

#### API 엔드포인트
```
POST /api/graph/rag/context
{
  "question": "최근 인플레이션 리스크를 높인 이벤트는?",
  "time_range": "7d",
  "as_of_date": "2026-02-07"
}

Response:
{
  "nodes": [...],
  "links": [...],
  "evidences": [
    {"text": "...", "doc_url": "...", "doc_id": "..."}
  ],
  "suggested_queries": [...]
}
```

**산출물(권장)**: `hobot/service/graph/rag/context_api.py` (FastAPI router로 만들고 `hobot/main.py`에서 include)

---

### D-2: GraphRAG 응답 생성 모듈
**예상 시간**: 1일

#### 작업 내용
- [x] LLM 프롬프트에 그래프 노드/관계/근거 주입
- [x] 응답 포맷:
  - 핵심 결론 (불확실성/대안 포함)
  - 근거: `Document.url + Evidence.text + 노드id`
  - 영향 경로: Event → Theme → Indicator
- [x] 할루시네이션 방지: Evidence에 없는 사실 금지

#### 구현 메모 (2026-02-07)
- 신규 파일: `hobot/service/graph/rag/response_generator.py`
- 신규 API: `POST /api/graph/rag/answer`
- 모델 제한: `gemini-3-flash-preview`, `gemini-3.1-pro-preview`만 허용 (그 외 입력 시 `gemini-3.1-pro-preview` 폴백)
- 출력 구성: `answer(conclusion/uncertainty/key_points/impact_pathways)` + `citations(evidence/doc)` + `suggested_queries`
- 테스트 추가: `hobot/tests/test_phase_d_response_generator.py`

#### 프롬프트 구조
```
[Context]
- Related Events: {events}
- Key Indicators: {indicators}
- Evidences: {evidences}

[Question]
{user_question}

[Rules]
1. 모든 주장은 Evidence에서 인용해야 함
2. 불확실한 경우 "근거 불충분" 명시
3. 영향 경로(Event→Theme→Indicator) 설명 포함
```

**산출물**: `hobot/service/graph/rag/response_generator.py`

---

### D-3: UI Evidence/경로 탐색 UX 구현
**예상 시간**: 1.5일

#### 작업 내용
- [x] 필터: 기간/국가/카테고리/테마/신뢰도
- [x] 노드 패널:
  - Document 클릭: 원문링크, 요약, Evidence/Fact/Claim 목록
  - Indicator 클릭: 최신값/변화, 미니차트 링크
- [x] 경로 탐색: 관련 경로 하이라이트 + Evidence 표시
- [x] 질문 템플릿: 자주 쓰는 질의 5~10개 버튼화

#### 구현 메모 (2026-02-07)
- 메인 구현: `hobot-ui-v2/src/components/OntologyPage.tsx`
  - Macro Graph 전용 필터 바(기간/국가/카테고리/테마/신뢰도/기준일)
  - Path Explorer(경로 버튼 선택 시 그래프 하이라이트)
  - Document 노드 패널(Evidence/Claim 표시 + 원문 링크)
  - Indicator 노드 패널(최근 Observation 요약 + 미니차트 + FRED 링크)
  - 질문 템플릿 8개 버튼 + 추천 질의 칩 UI
- API 연동 서비스 추가: `hobot-ui-v2/src/services/graphRagService.ts`
  - `POST /api/graph/rag/context`
  - `POST /api/graph/rag/answer`

#### 템플릿 예시
- "최근 인플레 관련 이벤트 Top 10"
- "유동성 악화 경로"
- "리스크 상승 원인"
- "금리 인상 영향 체인"

**산출물(권장)**: `hobot-ui-v2/src/components/OntologyPage.tsx` (Macro Graph 모드 UX 고도화)
**(선택) 리팩터링 산출물**: `hobot-ui-v2/src/components/ontology/macro/*` (패널/필터/경로탐색 컴포넌트 분리)

---

### D-4: MacroState/AnalysisRun 적재 로직
**예상 시간**: 1일

#### 작업 내용
- [x] `MacroState(date)`: 당일 주요 시그널/테마 요약
  - `(MacroState)-[:HAS_SIGNAL]->(DerivedFeature)`
  - `(MacroState)-[:DOMINANT_THEME]->(MacroTheme)`
- [x] `AnalysisRun`: 질문/응답/모델/소요시간/근거노드 저장
- [x] `as_of_date` 기록 필수

#### 구현 메모 (2026-02-07)
- 신규 파일: `hobot/service/graph/state/macro_state_generator.py`
  - `MacroStateGenerator`: 최근 뉴스 테마/파생시그널 집계 후 `MacroState` + `DOMINANT_THEME` + `HAS_SIGNAL` 저장
  - `AnalysisRunWriter`: `AnalysisRun` + `USED_EVIDENCE` + `USED_NODE` 저장
- GraphRAG 연동: `hobot/service/graph/rag/response_generator.py`
  - `POST /api/graph/rag/answer` 호출 시 D-4 저장 로직 자동 수행
  - 요청 파라미터로 `persist_macro_state`, `persist_analysis_run` 토글 가능
- 테스트 추가: `hobot/tests/test_phase_d_state_persistence.py`

#### Cypher 예시
```cypher
// MacroState 생성
MERGE (ms:MacroState {date: date($today)})
SET ms.summary = $summary, ms.updated_at = datetime()
WITH ms
MATCH (t:MacroTheme {theme_id: $dominant_theme})
MERGE (ms)-[:DOMINANT_THEME]->(t);

// AnalysisRun 저장
CREATE (ar:AnalysisRun {
  run_id: $run_id,
  question: $question,
  response: $response,
  model: $model,
  duration_ms: $duration,
  as_of_date: date($as_of),
  created_at: datetime()
})
WITH ar
UNWIND $evidence_ids AS eid
MATCH (e:Evidence {evidence_id: eid})
CREATE (ar)-[:USED_EVIDENCE]->(e);
```

**산출물**: `hobot/service/graph/state/macro_state_generator.py`

---

### D-5: 운영/품질 모니터링 구축
**예상 시간**: 0.5일

#### 모니터링 지표
- [x] GraphRAG 품질: 근거 링크 포함률, 질문 재현성, 응답 일관성
- [x] UI 성능: 큰 서브그래프 Top-K/페이지네이션
- [x] API 응답시간/에러율

#### 구현 메모 (2026-02-07)
- 백엔드 모니터링 모듈 추가: `hobot/service/graph/monitoring/graphrag_metrics.py`
  - `GraphRagApiCallLogger`: `/api/graph/rag/answer` 호출 성공/실패 로그(`GraphRagApiCall`) 저장
  - `GraphRagMonitoringMetrics`: 품질/재현성/일관성/성능 집계
  - 신규 API: `GET /api/graph/rag/metrics?days=7`
- 응답 API 연동: `hobot/service/graph/rag/response_generator.py`
  - 성공/에러 시 호출 로그 자동 기록
- UI 성능 보강: `hobot-ui-v2/src/components/OntologyPage.tsx`
  - Top-K 제어(30/50/80/100)
  - Evidence Explorer 페이지네이션(이전/다음)
  - 필터 연동된 근거 건수 표시
- 테스트 추가: `hobot/tests/test_phase_d_monitoring.py`

---

### D-6: Phase D 검증 및 DoD 확인
**예상 시간**: 0.5일

#### DoD 체크리스트
- [x] 질문 10개를 "그래프 근거 + 문서 링크"로 답변 가능 (실측: 근거 10/10, 문서 링크 10/10)
- [x] UI에서 Document→Evidence→Claim 경로 탐색 가능 (실측 경로 수: 2,950)
- [x] MacroState 일일 생성 확인 (실측: 2026-02-08 기준 1건)
- [x] AnalysisRun 저장 및 재현 가능 (실측: 전체 20건, 2026-02-08 당일 2건, 재현성 84.62%)
- [x] (범위 확인) MP/Sub-MP 선택 및 리밸런싱 비율 산출/저장은 Phase E에서 수행

#### 검증 실행 결과 (2026-02-08, 최신 기준)
- 실행 커맨드:
  - `run_phase_c_weekly_jobs` 실행 후 최신 그래프 상태 반영
  - `GraphRagAnswerRequest(question='최근 7일 인플레이션 리스크를 높인 핵심 이벤트와 근거를 요약해줘', time_range='7d', model='gemini-3-flash-preview')` 스모크 1회
- 모델: `gemini-3-flash-preview`
- 회귀 기준 유지:
  - 질문 10개 성공률 `10/10 (100%)`
  - Evidence 포함률 `10/10 (100%)`
  - Document 링크 포함률 `10/10 (100%)` (`coalesce(d.url, d.link)` 반영)
- 2026-02-08 스모크 결과:
  - 응답 성공 + 근거 포함 (`citation_count=2`)
  - 컨텍스트 구성 (`nodes=92`, `links=517`, `events=25`, `documents=35`, `stories=12`, `evidences=40`)
  - 상태 저장 성공 (`analysis_run_id=ar_38fd990e5ec04781`, `persistence_keys=['analysis_run','macro_state']`)
  - MacroState 생성 확인 (`date=2026-02-08`, `count=1`)
  - AnalysisRun 저장 확인 (`as_of_date=2026-02-08`, `count=2`, 누적 `20`)
- 운영 지표(최근 1일):
  - `total_calls=35`, `success=32`, `error=3`
  - `evidence_link_rate=100.0%`, `api_error_rate=8.57%`
  - `reproducibility=84.62%`, `consistency=84.62%`

#### 반영된 보완사항
1. Citation 문서 링크 조회를 `url/link` 병행 조회로 수정
2. 동일 질문/조건의 최근 성공 `AnalysisRun` 재사용(`reuse_cached_run`) 경로 추가

#### 샘플 질문 (검증용)
1. "최근 7일간 인플레이션 리스크를 높인 이벤트/뉴스는?"
2. "유동성 악화(NETLIQ 하락)와 관련된 상위 원인은?"
3. "금리 인상 → 신용 스프레드 확대 경로가 최근 관측되는가?"
4. "현재 시장의 주요 거시 내러티브(Story)는?"

---

## 📊 Phase D 산출물 요약

| 구분 | 산출물 |
|------|--------|
| Backend | `rag/context_api.py`, `rag/response_generator.py` |
| State | `state/macro_state_generator.py` |
| UI | `hobot-ui-v2/src/components/OntologyPage.tsx` |

---

## ⚠️ 리스크

| 리스크 | 대응 |
|--------|------|
| 큰 서브그래프로 UI 느려짐 | Top-K 제한 + 페이지네이션 |
| 할루시네이션 발생 | Evidence 강제 + 프롬프트 제약 |
