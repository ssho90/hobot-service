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
- [ ] 입력: `Event.event_time` + 연결 후보 `EconomicIndicator`
- [ ] 계산: 이벤트 전/후 `window_days`(3/7/14)에서 DerivedFeature 변화 추출
- [ ] 저장: `AFFECTS {observed_delta, window_days, baseline_method, as_of}`

#### Cypher 예시
```cypher
MATCH (ev:Event)-[r:AFFECTS]->(i:EconomicIndicator)
SET r.observed_delta = $delta,
    r.window_days = $window,
    r.baseline_method = 'mean_prev_7d',
    r.as_of = date()
```

**산출물**: `hobot/service/graph/impact/event_impact_calc.py`

---

### C-2: AFFECTS 동적 가중치 재계산 배치
**예상 시간**: 1일

#### 작업 내용
- [ ] 재계산 기준: 최근 90/180일 슬라이딩 윈도우
- [ ] 이력화: `as_of`, `window_days`, `method` 저장
- [ ] 배치 스케줄: 주 1회 (일요일)
- [ ] 스케줄러 연결: 주간 배치 진입점 작성 + 실행 로그/실패 알림(최소 로그)

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

**산출물**: `hobot/service/graph/impact/affects_recalc_batch.py`
**(권장) 스케줄러 산출물**: `hobot/service/graph/scheduler/weekly_batch.py`

---

### C-3: Indicator↔Indicator 통계 엣지 생성
**예상 시간**: 1일

#### 작업 내용
- [ ] `CORRELATED_WITH {corr, window_days, as_of}`
- [ ] `LEADS {lag_days, score, window_days, as_of}`
- [ ] Top-K 제한 (과다 생성 방지)

#### Cypher 예시
```cypher
MATCH (i1:EconomicIndicator), (i2:EconomicIndicator)
WHERE i1.indicator_code < i2.indicator_code
  AND abs($corr) > 0.6
MERGE (i1)-[r:CORRELATED_WITH]->(i2)
SET r.corr = $corr, r.window_days = 180, r.as_of = date()
```

**산출물**: `hobot/service/graph/stats/correlation_generator.py`

---

### C-4: Story(내러티브) 클러스터링
**예상 시간**: 1~2일

#### 작업 내용
- [ ] 입력: 최근 N일 Document/Event/Theme
- [ ] 방법 선택:
  - A) Rule-based: 테마+키워드 군집 (빠름)
  - B) 임베딩 기반: HDBSCAN (품질↑)
- [ ] 저장:
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

**산출물**: `hobot/service/graph/story/story_clusterer.py`

---

### C-5: 데이터 품질/모니터링 지표 추가
**예상 시간**: 0.5일

#### 모니터링 지표
- [ ] 정량 엣지 생성률 (`observed_delta` 채워진 비율)
- [ ] 관계 가중치 분포
- [ ] 이상치(스파이크) 감지
- [ ] 배치 실행 로그/성공률/소요시간

---

### C-6: Phase C 검증 및 DoD 확인
**예상 시간**: 0.5일

#### DoD 체크리스트
- [ ] `AFFECTS` 중 `observed_delta` 채워진 비율 60%+
- [ ] `CORRELATED_WITH` 엣지 최소 30개+
- [ ] Story 최소 10개, 각 Story에 문서 3건+

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
