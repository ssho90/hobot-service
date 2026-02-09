# Phase E 작업 로그: Strategy Integration (2026-02-08)

## 📅 작업 일시
- **시작**: 2026-02-08 11:00
- **완료**: 2026-02-08 12:16
- **소요 시간**: 약 1시간 16분

---

## 🎯 목표
AI 전략가(ai_strategist)의 의사결정 과정을 Macro Knowledge Graph(MKG)와 통합하여, 
전략 결정에 대한 **근거 기반 추적(Evidence-based Strategy History)**을 구현

---

## ✅ 완료 작업

### E-1: StrategyDecision 그래프 스키마 확정
- **산출물**: `cypher/10_strategy_constraints.cypher`
- Neo4j 제약조건/인덱스 생성 완료
  - `StrategyDecision.decision_id` UNIQUE 제약조건
  - `decision_date`, `mp_id` 인덱스

### E-2: Macro Graph 컨텍스트 빌더
- **산출물**: `hobot/service/graph/strategy/graph_context_provider.py`
- `build_strategy_graph_context()` 함수 구현
  - 최근 이벤트/스토리/Evidence 조회
  - LLM 프롬프트용 컴팩트 컨텍스트 블록 생성
  - 그래프 장애 시 빈 문자열 반환 (폴백)
- **테스트 결과**: 1,116자 컨텍스트 생성 성공

### E-3: ai_strategist 프롬프트에 그래프 근거 통합
- **수정 파일**: `hobot/service/macro_trading/ai_strategist.py`
- `create_mp_analysis_prompt()`, `create_sub_mp_analysis_prompt()`에 `graph_context` 파라미터 추가
- `analyze_and_decide()`에서 그래프 컨텍스트 자동 생성 및 주입
- 그래프 장애 시 기존 전략 로직으로 폴백

### E-4: 전략결정 MySQL → Macro Graph 미러링
- **산출물**: `hobot/service/graph/strategy/decision_mirror.py`
- `StrategyDecisionMirror` 클래스 구현
  - `mirror_latest_decision()`: 최신 결정 미러링
  - `mirror_decisions_backfill(days)`: 백필 모드
- Deterministic `decision_id` 생성 (upsert 가능)
- **백필 결과**: 49개 결정 → 45개 노드 (중복 제거)
- MacroState 연결 시도 (현재 MacroState 노드 미존재로 연결 안됨)

### E-5: Strategy Decision 조회 API
- **산출물**: `hobot/service/graph/strategy/strategy_api.py`
- **API 엔드포인트**:
  - `GET /api/strategy/decisions` - 전략 결정 목록 조회
  - `GET /api/strategy/decisions/{id}` - 전략 결정 상세 (관련 이벤트/Evidence 포함)
  - `POST /api/strategy/mirror` - MySQL→Graph 백필
  - `POST /api/strategy/mirror/latest` - 최신 결정 미러링
  - `POST /api/strategy/context` - 그래프 컨텍스트 생성
  - `GET /api/strategy/stats` - 통계 조회
- `main.py`에 라우터 등록 완료

---

## 📁 생성/수정 파일 목록

### 신규 생성
| 파일 | 설명 |
|------|------|
| `cypher/10_strategy_constraints.cypher` | StrategyDecision 스키마 정의 |
| `service/graph/strategy/__init__.py` | Strategy 모듈 초기화 |
| `service/graph/strategy/graph_context_provider.py` | 그래프 컨텍스트 빌더 |
| `service/graph/strategy/decision_mirror.py` | MySQL→Graph 미러링 |
| `service/graph/strategy/strategy_api.py` | REST API 엔드포인트 |

### 수정
| 파일 | 변경 내용 |
|------|----------|
| `ai_strategist.py` | 그래프 컨텍스트 주입 로직 추가 |
| `main.py` | Strategy API 라우터 등록 |

---

## 📊 Neo4j 데이터 현황

```
StrategyDecision 노드: 45개
- 최근 결정: 2026-02-08 (MP-4)
- MP 분포: MP-4가 대부분
```

---

## ⏳ 대기 작업

### E-6: UI 연동 (백엔드 로직 변경) ✅
- **상태**: 완료 (2026-02-08)
- **작업 내용**:
  - 사용자 요청: "기존 UI 유지, 백엔드만 Graph DB 기반으로 변경"
  - `decision_mirror.py`: `recommended_stocks` 정보 미러링 추가 (Backfill 완료)
  - `service/macro_trading/overview_service.py`: Graph DB 우선 조회 로직 구현
  - `main.py`: `/api/macro-trading/overview` 핸들러가 `overview_service`를 호출하도록 수정
- **결과**: `AIMacroReport` 등 기존 UI가 Graph DB 데이터를 기반으로 렌더링됨
  - 검증 테스트 성공: `get_overview_data()` 호출 시 Graph DB 데이터에 Sub-MP 상세 정보(ETF Details)가 정상적으로 확장되어 반환됨.


### E-7: 최종 검증
- Evidence/Document 연결 품질 확인
- "왜 MP-4인가?" 질의 테스트

---

## 🔍 향후 개선 사항

1. **MacroState 연결**: MacroState 노드가 생성되면 자동 연결 활성화
2. **Evidence 직접 연결**: 전략 결정 시 사용된 Evidence를 명시적으로 연결
3. **GraphRAG 통합**: "왜 MP-4를 선택했나?" 질문에 대한 자연어 답변 생성
4. **캐싱**: 그래프 컨텍스트 캐싱으로 LLM 호출 비용 절감

---

## 🐛 알려진 이슈

1. **MacroState 연결 실패**: 현재 MacroState 노드가 없어서 연결 안됨
2. **GitHub Actions 린트 경고**: `NEO4J_MACRO_URI` 시크릿 접근 경고 (기존 이슈)
