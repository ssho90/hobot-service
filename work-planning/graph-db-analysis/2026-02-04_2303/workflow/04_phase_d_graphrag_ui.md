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
- [ ] 입력: `question`, `time_range(7/30/90d)`, `country?`, `as_of_date?`
- [ ] 처리 흐름:
  1. 키워드/엔티티/지표 후보 매칭
  2. 후보에서 최근 Event/Document/Story 확장
  3. Evidence 포함 컨텍스트 패키징
- [ ] 출력: 서브그래프(nodes/links) + 근거텍스트 + 추천쿼리

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
- [ ] LLM 프롬프트에 그래프 노드/관계/근거 주입
- [ ] 응답 포맷:
  - 핵심 결론 (불확실성/대안 포함)
  - 근거: `Document.url + Evidence.text + 노드id`
  - 영향 경로: Event → Theme → Indicator
- [ ] 할루시네이션 방지: Evidence에 없는 사실 금지

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
- [ ] 필터: 기간/국가/카테고리/테마/신뢰도
- [ ] 노드 패널:
  - Document 클릭: 원문링크, 요약, Evidence/Fact/Claim 목록
  - Indicator 클릭: 최신값/변화, 미니차트 링크
- [ ] 경로 탐색: 관련 경로 하이라이트 + Evidence 표시
- [ ] 질문 템플릿: 자주 쓰는 질의 5~10개 버튼화

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
- [ ] `MacroState(date)`: 당일 주요 시그널/테마 요약
  - `(MacroState)-[:HAS_SIGNAL]->(DerivedFeature)`
  - `(MacroState)-[:DOMINANT_THEME]->(MacroTheme)`
- [ ] `AnalysisRun`: 질문/응답/모델/소요시간/근거노드 저장
- [ ] `as_of_date` 기록 필수

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
- [ ] GraphRAG 품질: 근거 링크 포함률, 질문 재현성, 응답 일관성
- [ ] UI 성능: 큰 서브그래프 Top-K/페이지네이션
- [ ] API 응답시간/에러율

---

### D-6: Phase D 검증 및 DoD 확인
**예상 시간**: 0.5일

#### DoD 체크리스트
- [ ] 질문 10개를 "그래프 근거 + 문서 링크"로 답변 가능
- [ ] UI에서 Document→Evidence→Claim 경로 탐색 가능
- [ ] MacroState 일일 생성 확인
- [ ] AnalysisRun 저장 및 재현 가능
- [ ] (범위 확인) MP/Sub-MP 선택 및 리밸런싱 비율 산출/저장은 Phase E에서 수행

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
