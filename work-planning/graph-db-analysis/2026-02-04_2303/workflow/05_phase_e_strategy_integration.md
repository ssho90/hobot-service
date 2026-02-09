# Phase E: Strategy Integration (MP/Sub-MP ↔ Macro Graph)

## 📋 Phase 개요
- **예상 기간**: 1주
- **목표**: `ai_strategist.py`의 MP/Sub-MP 선택(리밸런싱 목표 비중 산출)을 Macro Graph(MKG)와 연결해 “근거 기반 전략 히스토리”를 만든다.
- **전제 조건**:
  - Phase D 완료(`MacroState/AnalysisRun`, Evidence 경로 탐색 기본 UX)
  - `ai_strategy_decisions`(MySQL) 저장이 정상 동작 중

---

## ✅ Phase E 착수 전 체크 (2026-02-08 실측)
- [x] Phase C DoD 충족 확인
  - `AFFECTS observed_delta`: `3966/3966 (100.0%)`
  - `CORRELATED_WITH`: `31`, `LEADS`: `24`
  - `Story`: `25`개, `story_min_docs=3`
- [x] Phase D DoD 충족 확인
  - 질문 성공 `10/10`, Evidence 포함 `10/10`, 문서 링크 포함 `10/10`
  - `Document→Evidence→Claim`: `2,950`
  - `MacroState(2026-02-08)`: `1`
  - `AnalysisRun(2026-02-08)`: `2` (`누적=20`)
  - 운영지표(최근 1일): `total_calls=35`, `success=32`, `error=3`, `api_error_rate=8.57%`, `reproducibility=84.62%`

### 착수 판단
- **결론**: Phase E 착수 가능
- **권장 시작 순서**: `E-1(스키마)` → `E-2(컨텍스트 빌더)` → `E-3(ai_strategist 통합)` → `E-4(미러링 저장)` → `E-5/E-6(API/UI)` → `E-7(검증)`

---

## 🔧 작업 상세

### E-1: StrategyDecision 그래프 스키마 확정 ✅
**예상 시간**: 0.5일 → **완료 (2026-02-08)**

#### 작업 내용
- [x] 최소 노드/속성 정의(권장)
  - `StrategyDecision {decision_id, decision_date, mp_id, target_allocation, sub_mp, created_at}`
  - (선택) `StrategyRun {run_id, run_type('mp'|'sub_mp'), model, duration_ms, as_of_date, created_at}`
- [x] 최소 관계 정의(권장)
  - `(StrategyDecision)-[:BASED_ON]->(MacroState)`
  - `(StrategyDecision)-[:USED_EVIDENCE]->(Evidence)`
  - `(StrategyDecision)-[:USED_NODE]->(Event|Story|MacroTheme|EconomicIndicator|Document)`
  - (선택) `(StrategyDecision)-[:DERIVED_FROM]->(IndicatorObservation|DerivedFeature)`
- [x] ID/멱등성 규칙
  - `decision_id`는 deterministic(예: `date + mp_id + hash(sub_mp_json)`), upsert 가능해야 함

#### 산출물
- `cypher/10_strategy_constraints.cypher` ✅
- 스키마/관계 요약 문서(현재 파일) ✅

---

### E-2: Macro Graph 컨텍스트 빌더(전략 프롬프트 주입용) ✅
**예상 시간**: 1일 → **완료 (2026-02-08)**

#### 작업 내용
- [x] 입력: `as_of_date`, `time_range(7/30d)`, (선택) `country`, `theme_ids`
- [x] 출력: LLM 프롬프트에 붙일 **compact context block**
  - 최근 주요 `Event/Story` 요약
  - 관련 `EconomicIndicator`(최신 변화/파생피처) 요약
  - 핵심 `Evidence.text` + `Document.url` (2~5개 수준)
- [x] 방어 로직
  - 그래프가 비어있거나 Neo4j 장애면 빈 문자열 반환(=기존 전략 로직 폴백)

#### 산출물(권장)
- `hobot/service/graph/strategy/graph_context_provider.py` ✅

---

### E-3: ai_strategist MP/Sub-MP 프롬프트에 그래프 근거 블록 통합 ✅
**예상 시간**: 0.5~1일 → **완료 (2026-02-08)**

#### 작업 내용
- [x] `create_mp_analysis_prompt()` / `create_sub_mp_analysis_prompt()`에 `graph_context: Optional[str]` 파라미터 추가(권장)
- [x] `analyze_and_decide()`에서 컨텍스트 빌더 호출 후 프롬프트에 삽입
- [x] 폴백: 그래프 컨텍스트가 없으면 기존 프롬프트 그대로
- [x] (권장) LLM 모니터링 로그에 "컨텍스트 길이/사용 여부"를 남김

#### 검증
- [x] 동일 입력에서 `graph_context` 유무에 따라 프롬프트에 블록이 포함/미포함되는지 확인
- [ ] 컨텍스트가 길어져도 토큰 한도 내에서 안정 동작(Top-K 제한)

---

### E-4: 전략결정(MySQL) → Macro Graph 미러링 저장 ✅
**예상 시간**: 1일 → **완료 (2026-02-08)**

#### 작업 내용
- [x] Source-of-truth는 MySQL `ai_strategy_decisions.target_allocation` 유지
- [x] Macro Graph에 `StrategyDecision` upsert
  - `mp_id`, `target_allocation`, `sub_mp`, `reasoning(요약)` 포함
  - `(StrategyDecision)-[:BASED_ON]->(MacroState)` 연결 시도
- [x] Backfill 모드(최근 N일) 지원 → 49개 결정 미러링 완료

#### 산출물
- `hobot/service/graph/strategy/decision_mirror.py` ✅

---

### E-5: StrategyDecision 조회 API/템플릿 질의 ✅
**예상 시간**: 0.5일 → **완료 (2026-02-08)**

#### 작업 내용
- [x] 조회 API 구현
  - `GET /api/strategy/decisions` - 전략 결정 목록 조회
  - `GET /api/strategy/decisions/{id}` - 전략 결정 상세 (관련 이벤트/Evidence 포함)
  - `POST /api/strategy/mirror` - MySQL→Graph 백필
  - `POST /api/strategy/mirror/latest` - 최신 결정 미러링
  - `POST /api/strategy/context` - 그래프 컨텍스트 생성
  - `GET /api/strategy/stats` - 통계 조회
- [x] "nodes/links + evidences" 형태 응답 구현

#### 산출물
- `hobot/service/graph/strategy/strategy_api.py` ✅
- `main.py`에 라우터 등록 ✅

---

### E-6: UI 연동 (백엔드 로직 변경) ✅
**예상 시간**: 1일 → **완료 (2026-02-08)**

#### 작업 내용
- [x] 사용자 요청에 따라 기존 UI 유지하되 백엔드만 Graph DB 기반으로 변경
- [x] `decision_mirror.py`: `recommended_stocks` 정보 미러링 추가
- [x] `service/macro_trading/overview_service.py` 생성 (Graph DB 우선 조회)
- [x] `main.py`: `/api/macro-trading/overview` 핸들러 교체


---

### E-7: Phase E 검증 및 DoD 확인
**예상 시간**: 0.5일

#### DoD 체크리스트
- [x] 특정일(오늘) `StrategyDecision` 1건이 Macro Graph에 존재 (45개 확인)
- [ ] `StrategyDecision`이 최소 2개 이상의 `Evidence/Document`와 연결(데이터 가용 시)
- [ ] "왜 MP-4인가?" 질문에 대해 Evidence 링크 포함 답변을 생성/표시 가능
- [x] 재실행(backfill 포함) 시 중복 없이 upsert 동작 (deterministic decision_id)

---

## ⚠️ 리스크

| 리스크 | 대응 |
|--------|------
| 그래프가 비어있어 컨텍스트 품질 낮음 | 컨텍스트는 옵션, FRED+뉴스 요약 기반 기존 전략 폴백 유지 |
| LLM 비용/지연 증가 | 컨텍스트 Top-K 제한 + Evidence 압축 + 캐시 |
| 근거 연결(링킹) 품질 문제 | Evidence 강제(Phase B) + NEL 개선 + "연결 실패 시 미연결로 저장" 정책 |
