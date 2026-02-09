# Phase C: 정량 Impact & 통계 엣지

## 📋 Phase 개요
- **예상 기간**: 1주
- **목표**: Event Window Impact 정량화, 동적 가중치, Indicator 상관관계, Story 클러스터링
- **전제 조건**: Phase B 완료 (Evidence/NEL 확립)

---

## 🔧 작업 상세

### C-1: Event Window Impact 계산 모듈
**예상 시간**: 1일

#### 작업 내용
- [x] 입력: `Event.event_time` + 연결 후보 `EconomicIndicator`
- [x] 계산: 이벤트 전/후 `window_days`(3/7/14)에서 DerivedFeature 변화 추출
- [x] 저장: `AFFECTS {observed_delta, window_days, baseline_method, as_of}`

#### Cypher 예시
```cypher
MATCH (ev:Event)-[r:AFFECTS]->(i:EconomicIndicator)
SET r.observed_delta = $delta,
    r.window_days = $window,
    r.baseline_method = 'mean_prev_7d',
    r.as_of = date()
```

**산출물**: `hobot/service/graph/impact/event_impact_calc.py` ✅

---

### C-2: AFFECTS 동적 가중치 재계산 배치
**예상 시간**: 1일

#### 작업 내용
- [x] 재계산 기준: 최근 90/180일 슬라이딩 윈도우
- [x] 이력화: `as_of`, `window_days`, `method` 저장
- [x] 배치 스케줄: 주 1회 (일요일) 실행 진입점 구현
- [x] 스케줄러 연결: 주간 배치 진입점 작성 + 실행 로그(기본)

#### 관계 속성 구조
```
(Event)-[:AFFECTS {
  polarity: "positive",
  weight: 0.72,
  observed_delta: 0.15,
  window_days: 7,
  as_of: date("2026-02-07"),
  method: "rolling_90d"
}]->(EconomicIndicator)
```

**산출물**: `hobot/service/graph/impact/affects_recalc_batch.py` ✅
**(권장) 스케줄러 산출물**: `hobot/service/graph/scheduler/weekly_batch.py` ✅

---

### C-3: Indicator↔Indicator 통계 엣지 생성
**예상 시간**: 1일

#### 작업 내용
- [x] `CORRELATED_WITH {corr, window_days, as_of}`
- [x] `LEADS {lag_days, score, window_days, as_of}`
- [x] Top-K 제한 (과다 생성 방지)

#### Cypher 예시
```cypher
MATCH (i1:EconomicIndicator), (i2:EconomicIndicator)
WHERE i1.indicator_code < i2.indicator_code
  AND abs($corr) > 0.6
MERGE (i1)-[r:CORRELATED_WITH]->(i2)
SET r.corr = $corr, r.window_days = 180, r.as_of = date()
```

**산출물**: `hobot/service/graph/stats/correlation_generator.py` ✅

---

### C-4: Story(내러티브) 클러스터링
**예상 시간**: 1~2일

#### 작업 내용
- [x] 입력: 최근 N일 Document/Event/Theme
- [x] 방법 선택:
  - A) Rule-based: 테마+키워드 군집 (빠름)
  - B) 임베딩 기반: HDBSCAN (품질↑)
- [x] 저장:
  - `Story {story_id, created_at, window_days, method}`
  - `(Story)-[:CONTAINS]->(Document)`
  - `(Story)-[:ABOUT_THEME]->(MacroTheme)`

#### Cypher 예시
```cypher
CREATE (s:Story {
  story_id: $story_id,
  title: $title,
  window_days: 7,
  method: 'keyword_cluster',
  created_at: datetime()
})
WITH s
UNWIND $doc_ids AS did
MATCH (d:Document {doc_id: did})
CREATE (s)-[:CONTAINS]->(d)
```

**산출물**: `hobot/service/graph/story/story_clusterer.py` ✅

---

### C-5: 데이터 품질/모니터링 지표 추가
**예상 시간**: 0.5일

#### 모니터링 지표
- [x] 정량 엣지 생성률 (`observed_delta` 채워진 비율)
- [x] 관계 가중치 분포
- [x] 이상치(스파이크) 감지
- [x] 배치 실행 로그/성공률/소요시간

**산출물**: `hobot/service/graph/impact/quality_metrics.py` ✅

---

### C-6: Phase C 검증 및 DoD 확인
**예상 시간**: 0.5일

#### DoD 체크리스트
- [x] `AFFECTS` 중 `observed_delta` 채워진 비율 60%+
- [x] `CORRELATED_WITH` 엣지 최소 30개+
- [x] Story 최소 10개, 각 Story에 문서 3건+
- [x] 컴포넌트 단위 테스트 추가 (`hobot/tests/test_phase_c_components.py`)
- [x] 실환경 1회 실행 및 실측치 수집 (`run_phase_c_weekly_jobs`, 2026-02-08)

#### 2026-02-08 실측 결과 (Neo4j macro profile)
- 실행 배치: `run_phase_c_weekly_jobs()` 실행 완료 (`as_of=2026-02-08`)
- 선행 작업:
  - `sync_news_with_extraction(limit=3000, days=30)` 실행 후 누락 문서 대상 추출 백필 완료
  - 타겟 백필 결과: `90/90 success`, 최신 400건 `success=400`, `missing=0`
- 최종 실측:
  - `AFFECTS observed_delta` 커버리지: `3966 / 3966 = 100.0%` (목표 60%+, **충족**)
  - `CORRELATED_WITH` 엣지 수: `31` (목표 30+, **충족**)
  - `LEADS` 엣지 수: `24`
  - Story 수: `25` (목표 10+, **충족**)
  - Story별 문서 수 최소값: `3` (`stories_lt_3=0`, 목표 조건 **충족**)
  - Story 클러스터 입력 문서 수: `314` (`window_days=14`, `bucket_days=3`, 배치 생성 `19`)
  - 최신 Document 시각: `2026-02-07T14:23:39Z`

#### 해석
- `AFFECTS` 커버리지는 100%로 유지되며, 30일 범위 추출 백필 후에도 주간 배치에서 안정적으로 갱신됨.
- 상관 엣지(31) 및 Story 조건(25개, 각 3건+)을 모두 충족하여 Phase D 진행 전 데이터 품질 게이트를 통과.

#### 검증 쿼리
```cypher
// AFFECTS observed_delta 채워진 비율
MATCH ()-[r:AFFECTS]->()
WITH count(r) AS total, 
     count(CASE WHEN r.observed_delta IS NOT NULL THEN 1 END) AS filled
RETURN total, filled, toFloat(filled)/total * 100 AS pct;

// Story 현황
MATCH (s:Story)-[:CONTAINS]->(d:Document)
RETURN s.story_id, s.title, count(d) AS doc_count
ORDER BY doc_count DESC;
```

---

## 📊 Phase C 산출물 요약

| 구분 | 산출물 |
|------|--------|
| Impact | `impact/event_impact_calc.py`, `affects_recalc_batch.py` |
| Stats | `stats/correlation_generator.py` |
| Story | `story/story_clusterer.py` |
| Scheduler | `scheduler/weekly_batch.py` *(권장 경로: `hobot/service/graph/scheduler/weekly_batch.py`)* |

---

## ⚠️ 리스크

| 리스크 | 대응 |
|--------|------|
| event_time 불명확 | Phase B에서 추출 품질 확보 / 발행일 대체 |
| 통계 엣지 과다 생성 | 임계치/Top-K 제한 + 주기 조절 |
