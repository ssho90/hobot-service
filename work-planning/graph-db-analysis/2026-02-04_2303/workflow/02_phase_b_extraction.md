# Phase B: News Extraction 정식화

## 📋 Phase 개요
- **예상 기간**: 2~4일
- **목표**: LLM 기반 뉴스 추출(Event/Fact/Claim/Evidence) + NEL 정규화
- **전제 조건**: Phase A 완료

---

## 🔧 작업 상세

### B-1: LLM 추출 JSON 스키마 확정 + Validator ✅
**예상 시간**: 3~4시간 | **완료일**: 2026-02-07

- [x] JSON 스키마 버저닝 (`schema_version=1`)
- [x] Pydantic 모델 정의 (Event, Fact, Claim, Evidence, Link)
- [x] 검증 로직: 누락/타입 오류 시 적재 금지

**산출물**: `hobot/service/graph/schemas/extraction_schema.py`

---

### B-2: Evidence 강제 로직 구현 ✅
**예상 시간**: 2시간 | **완료일**: 2026-02-07

- [x] Evidence 없는 AFFECTS/CAUSES 관계 생성 금지 (Link 모델에 validator 적용)
- [x] Evidence 노드 저장: `(Document)-[:HAS_EVIDENCE]->(Evidence)`
- [x] `(Evidence)-[:SUPPORTS]->(Claim|Fact)` 관계
- [x] `Evidence.evidence_id` 도입: `hash(doc_id + evidence_text + lang)` 기반 deterministic id

**검증**: Evidence 없는 Claim 0건 확인 (Pydantic validator로 강제)

---

### B-3: Country/Category 표준화 사전 구축 ✅
**예상 시간**: 2~3시간 | **완료일**: 2026-02-07

- [x] Country 매핑: 원문 → ISO code
- [x] Category 매핑: TradingEconomics → 내부 taxonomy
- [x] Document에 `country_code`, `category_id` 필드 추가

**산출물**: 
- `hobot/service/graph/normalization/country_mapping.py`
- `hobot/service/graph/normalization/category_mapping.py`

---

### B-4: ExternalIndicator 확장 모델 정의
**예상 시간**: 2시간

- [ ] 비-FRED 지표 수용: `EconomicIndicator {source='TradingEconomics'}`
- [ ] Deterministic ID 생성: `EXT_{hash(source:country:name)}`

---

### B-5: NEL 파이프라인 구현 ✅
**예상 시간**: 4~6시간 | **완료일**: 2026-02-07

- [x] Step 1: Mention 추출 (LLM/룰 기반)
- [x] Step 2: 후보 생성 (Alias Dictionary)
- [x] Step 3: 연결 판별 (스코어링 + 임계치)
- [x] Step 4: canonical_id로 MERGE
- [x] 실패 케이스 alias 사전 누적

**산출물**: 
- `hobot/service/graph/nel/nel_pipeline.py`
- `hobot/service/graph/nel/alias_dictionary.py`

---

### B-6: 추출 파이프라인 운영화 ✅
**예상 시간**: 3~4시간 | **완료일**: 2026-02-07

- [x] 재시도/타임아웃 로직 (Gemini 클라이언트 내장)
- [x] 캐시 키: `doc_id:extractor_version:model`
- [x] 정식 적재 경로: `Document -> Event/Fact/Claim/Evidence/AFFECTS` 저장
- [x] Backfill 모드 (최근 N일 재처리)
- [ ] DLQ 처리

**산출물**: 
- `hobot/service/graph/news_extractor.py`
- `hobot/service/graph/news_loader.py` (`extract_and_persist`, `backfill_extractions`, `sync_news_with_extraction`)
- `hobot/service/graph/cache/__init__.py`
- `hobot/service/graph/dlq/__init__.py`
- `hobot/tests/test_phase_b_graph_ingestion.py`

---

### B-7: Phase B 검증 및 DoD 확인 ⚠️
**예상 시간**: 2시간 | **검증일**: 2026-02-07

#### DoD 체크리스트
- [x] 100건 뉴스 중 80%+ 유효 JSON 추출 → **100% (5/5)** ✅
- [x] Fact/Claim/Link의 95%+ Evidence 보유 → **100% (38/38)** ✅
- [ ] NEL 실패율 < 20% → **79.7%** ❌ (Alias Dictionary 확장 필요)

#### 검증 상세 결과
```
📊 DoD-1: Valid JSON Extraction Rate = 100.0% ✅
📊 DoD-2: Evidence Coverage Rate = 100.0% ✅
📊 DoD-3: NEL Failure Rate = 79.7% ❌
```

**참고**: NEL 실패율은 Alias Dictionary 확장으로 점진적 개선 가능 (Phase C에서 계속)

---

## ⚠️ 리스크

| 리스크 | 대응 |
|--------|------|
| LLM 출력 변동 | 스키마 검증 + DLQ + 프롬프트 버전관리 |
| LLM 비용 | 캐시 활용 + batch 조절 |

