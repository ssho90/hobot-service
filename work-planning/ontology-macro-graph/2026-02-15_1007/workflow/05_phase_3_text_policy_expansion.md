# Phase 3 상세 계획: US/KR 텍스트/정책 데이터 확장

## 1. 목표
- US/KR 정책기관 문서와 기업 이벤트 문서를 표준 스키마로 수집/정규화한다.
- 문서-이벤트-기업 연결을 강제해 Q1/Q2(기업 급락 원인/기업 비교) 질문 대응력을 확보한다.
- 다국어 검색 인덱스를 운영 가능한 수준으로 완성한다.
- 온디맨드 수집(Tier-2)은 추후 구현 항목으로 보류한다.

## 2. 기간
- 권장 기간: 2026-04-06 ~ 2026-04-24 (3주)

## 3. 작업 스트림
### 3.1 정책/공식 문서 파이프라인
- [x] Fed/BOK 및 주요 정책기관 문서 수집기 구현
- [x] 국토부/한국부동산원/주택금융 문서 파이프라인 구현
- [x] `published_at`, `release_date`, `effective_date`, `observed_at` 필드 저장 강제

### 3.2 기업 이벤트 파이프라인 (Tier-1)
- [x] US Tier-1: yfinance 뉴스/실적 이벤트 + SEC IR성 공시 연계
- [x] KR Tier-1: Open DART 공시 + IR 이벤트(기업설명회/투자설명회) 분류
- [x] 표준 이벤트 스키마(`symbol`, `event_type`, `source_url`, `effective_date`) 적용

예상 대상 코드
- `hobot/service/graph/news_loader.py`
- `hobot/service/graph/news_extractor.py`
- `hobot/service/macro_trading/collectors/news_collector.py`

### 3.3 온디맨드 수집 (Tier-2, 보류)
- [보류] 기업명 추출 -> 비동기 큐 등록 -> 30~90일 백필 구현
- [보류] 질의 후 7일 추적 수집 로직 구현
- [보류] 캐시 TTL 및 누락 구간 증분 수집 규칙 적용

예상 대상 코드
- `hobot/service/graph/scheduler/weekly_batch.py`
- `hobot/service/graph/dlq/__init__.py`

### 3.4 중복/노이즈/장애 복구
- [x] 중복 키(`source_url + normalized_title + published_at`) 적용
- [x] 본문 유사도 중복 제거(0.95+) 정책 적용
- [x] 소스별 재시도(1/5/15분), DLQ, 경보 규칙 구현

### 3.5 다국어 적재/검색 + 엔터티 정규화
- [x] US 원문 필드(`title_en`, `body_en`)와 한국어 요약 필드(`summary_ko`, `keywords_ko`) 동시 저장
- [ ] Hybrid 검색(Keyword + Vector) 적용
- [ ] CompanyAlias/RegionAlias 기반 엔터티 통합 강화

예상 대상 코드
- `hobot/service/graph/rag/context_api.py`
- `hobot/service/graph/nel/nel_pipeline.py`

## 4. 완료 기준 (DoD)
- 정책/기업 문서가 표준 시간 모델 및 이벤트 스키마로 저장된다.
- Tier-1 상시 수집이 스케줄러에서 정상 동작한다.
- 다국어 검색에서 한국어 질의 기준 영어 원문 근거 회수가 가능하다.

## 5. 리스크/대응
- 리스크: 사이트별 포맷 변경으로 파서 깨짐
- 대응: 소스별 파서 버전 관리 및 스키마 드리프트 테스트 추가
- 리스크: 과도한 수집량으로 비용/지연 증가
- 대응: 4.8 매트릭스 기반 cap/rate guard를 코드 상수로 고정

## 6. Phase 4 인계 항목
- 문서/이벤트/기업 연결 그래프 샘플 데이터셋
- 온디맨드 수집 상태 메타는 보류 항목으로 유지
- 다국어 검색 품질 리포트(Top-10 Recall 기준선)

진행 현황 업데이트 (2026-02-18, 1차)
- [x] Fed/BOK 정책기관 RSS 수집기 추가
  - 신규 수집기: `hobot/service/macro_trading/collectors/policy_document_collector.py`
  - 기본 소스:
    - Fed: `FED_POLICY_RSS_URL` (기본 `https://www.federalreserve.gov/feeds/press_monetary.xml`)
    - BOK: `BOK_POLICY_RSS_URL` (기본값 제공, 필요시 env override)
  - 저장 스키마(강제 시간 필드):
    - `published_at`, `release_date`, `effective_date`, `observed_at`, `source_type`
  - DB 마이그레이션:
    - `hobot/service/database/db.py`에 `economic_news` 신규 컬럼 추가 로직 반영
  - 스케줄러 연동:
    - 실행 함수: `collect_policy_documents()`
    - 스케줄 함수: `setup_policy_document_scheduler()`
    - `start_all_schedulers()`/`start_news_scheduler_thread()`에 등록
    - 환경변수:
      - `POLICY_DOC_COLLECTION_ENABLED` (기본 1)
      - `POLICY_DOC_COLLECTION_INTERVAL_MINUTES` (기본 120)
      - `POLICY_DOC_LOOKBACK_HOURS` (기본 72)
- [x] Graph 적재 연계 필드 확장
  - `hobot/service/graph/news_loader.py`에서 `release_date/effective_date/observed_at/source_type` 조회/업서트 반영
- [x] 테스트 추가
  - `hobot/service/macro_trading/tests/test_policy_document_collector.py`
  - `hobot/service/macro_trading/tests/test_scheduler_policy_document_collection.py`

진행 현황 업데이트 (2026-02-18, 2차)
- [x] KR 주택정책 3개 기관(국토부/한국부동산원/주택금융공사) 파이프라인 확장
  - 소스 추가:
    - `molit_housing_policy` (`MOLIT_HOUSING_POLICY_RSS_URL`)
    - `kreb_housing_policy` (`KREB_HOUSING_POLICY_RSS_URL`)
    - `khf_housing_policy` (`KHF_HOUSING_POLICY_RSS_URL`)
  - URL 미설정 시 안전 스킵(수집 실패로 간주하지 않음)
  - 전용 실행 경로:
    - `collect_kr_housing_policy_documents()`
  - 전용 스케줄:
    - `setup_kr_housing_policy_document_scheduler()`
    - env:
      - `KR_HOUSING_POLICY_DOC_COLLECTION_ENABLED` (기본 1)
      - `KR_HOUSING_POLICY_DOC_COLLECTION_INTERVAL_MINUTES` (기본 180)
      - `KR_HOUSING_POLICY_DOC_LOOKBACK_HOURS` (기본 168)
  - 테스트 확장:
    - `test_scheduler_policy_document_collection.py`에 KR 주택정책 소스 필터/스케줄 등록 케이스 추가

진행 현황 업데이트 (2026-02-18, 3차)
- [x] Tier-1 기업 이벤트 표준 스키마 동기화 경로 구현
  - 신규 수집기: `hobot/service/macro_trading/collectors/corporate_event_collector.py`
  - 신규 표준 테이블: `corporate_event_feed`
    - 필수 필드 저장: `symbol`, `event_type`, `source_url`, `effective_date`
    - 공통 식별/메타: `country_code`, `event_status`, `source`, `source_ref`, `payload_json`
  - 동기화 소스(현재):
    - KR: `kr_corporate_disclosures` (Top50 스냅샷 조인)
    - US: `us_corporate_earnings_events` (Top50 스냅샷 조인)
  - 신규 실행 경로:
    - `sync_tier1_corporate_events(...)`
    - `sync_tier1_corporate_events_from_env()`
  - 신규 스케줄:
    - `setup_tier1_corporate_event_sync_scheduler()`
    - env:
      - `TIER1_EVENT_SYNC_ENABLED` (기본 1)
      - `TIER1_EVENT_SYNC_INTERVAL_MINUTES` (기본 60)
      - `TIER1_EVENT_SYNC_LOOKBACK_DAYS` (기본 30)
      - `TIER1_EVENT_SYNC_INCLUDE_US_EXPECTED` (기본 1)
  - 테스트:
    - `hobot/service/macro_trading/tests/test_corporate_event_collector.py`
    - `hobot/service/macro_trading/tests/test_scheduler_tier1_corporate_event_sync.py`
  - 실DB 스모크(2026-02-18):
    - `sync_tier1_corporate_events_from_env()`
    - 결과: `kr_event_count=0`, `us_event_count=96`, `normalized_rows=96`, `db_affected=96`, `status=ok`

메모(3.2 잔여 범위)
- KR 외부 IR 보도자료(언론/기업 IR 페이지 원문) 소스 연동은 다음 단계에서 추가 구현 예정.

진행 현황 업데이트 (2026-02-18, 4차)
- [x] US `yfinance` 뉴스 수집 안정화
  - `hobot/service/macro_trading/collectors/corporate_event_collector.py`
  - 구/신 yfinance 뉴스 포맷 동시 파싱
    - legacy: `title/link/providerPublishTime`
    - nested: `content.title/content.canonicalUrl/content.pubDate`
  - epoch seconds/milliseconds 자동 보정
  - 상대 URL(`/news/...`) -> 절대 URL(`https://finance.yahoo.com/...`) 정규화
  - `source_ref` 우선순위(`id/uuid`) + 해시 fallback 적용
- [x] KR/US 이벤트 카테고리 표준화(질의/필터 기반 마련)
  - 카테고리: `news`, `earnings`, `periodic_report`, `ir_event`, `corporate_disclosure`
  - 도메인: `news`, `ir`, `disclosure`
  - 저장 위치: `payload_json` 내 `event_category`, `event_domain`
  - 동기화 결과에 `event_category_counts` 집계 추가
- [x] 테스트 보강
  - `hobot/service/macro_trading/tests/test_corporate_event_collector.py`
    - KR IR 이벤트 자동 분류 검증
    - US 표준 이벤트 카테고리/도메인 검증
    - yfinance nested 뉴스 포맷 파싱 검증
  - 실행 결과:
    - `test_corporate_event_collector`: `Ran 5 tests ... OK`
    - `test_scheduler_tier1_corporate_event_sync`: `Ran 3 tests ... OK`

추가 메모
- KR 외부 IR 보도자료(언론/IR 페이지 직접 크롤링) 소스는 아직 미연동이며, 현재는 Open DART 공시 기반 IR 이벤트까지 운영 범위로 본다.

진행 현황 업데이트 (2026-02-18, 5차)
- [x] KR 외부 IR 보도자료 feed 연동 1차 구현 (RSS/Atom)
  - `hobot/service/macro_trading/collectors/corporate_event_collector.py`
  - 신규 경로: `fetch_kr_ir_news_rows(...)`
    - 입력: KR Top50 최신 스냅샷(시장/상위 N) + RSS/Atom feed URL 목록
    - 동작: 제목/요약 텍스트에서 기업명 매칭 후 `ir_news` 이벤트 생성
    - 출력: `corporate_event_feed` 표준 스키마 적재(`symbol`, `event_type`, `source_url`, `effective_date`)
  - 지원 포맷:
    - RSS(`item/title/link/description/pubDate/guid`)
    - Atom(`entry/title/link/summary/published/updated/id`)
  - 운영 제어:
    - `TIER1_EVENT_SYNC_INCLUDE_KR_IR_NEWS` (기본 1)
    - `TIER1_EVENT_SYNC_KR_IR_FEED_URLS` (CSV)
    - fallback: `KR_TIER1_IR_FEED_URLS` (CSV)
- [x] Tier-1 동기화 summary 확장
  - `kr_ir_news_event_count`, `kr_ir_feed_url_count` 추가
  - 카테고리 집계(`event_category_counts`)에 KR IR 뉴스 포함
- [x] 테스트 보강
  - `test_corporate_event_collector.py`
    - KR IR feed -> Top50 symbol 매핑 테스트 추가
  - `test_scheduler_tier1_corporate_event_sync.py`
    - env 기반 KR IR feed URL 파싱/전달 테스트 추가
  - 실행 결과:
    - `test_corporate_event_collector`: `Ran 6 tests ... OK`
    - `test_scheduler_tier1_corporate_event_sync`: `Ran 3 tests ... OK`
    - 관련 회귀 묶음: `Ran 17 tests ... OK`

진행 현황 업데이트 (2026-02-18, 6차)
- [x] KR IR feed 운영값(.env) 반영 후 실동기화 실행 확인
  - 설정:
    - `TIER1_EVENT_SYNC_INCLUDE_KR_IR_NEWS=1`
    - `KR_TIER1_IR_FEED_URLS=<2개 RSS URL>`
  - 실행:
    - `sync_tier1_corporate_events_from_env()`
  - 결과:
    - `kr_ir_feed_url_count=2`
    - `kr_ir_news_event_count=10`
    - `normalized_rows=606`
    - `event_category_counts.ir_event=10`
    - `status=ok`

진행 현황 업데이트 (2026-02-18, 7차)
- [x] Tier-1 뉴스성 이벤트 유사도 중복 제거(0.95+) 적용
  - 대상:
    - US `yfinance_news`
    - KR `ir_news`
  - 구현:
    - `corporate_event_collector.dedupe_similar_news_rows(...)`
    - 동일 그룹(`country_code+symbol+event_date+event_type`) 내
      - URL 동일 중복 제거
      - 제목 동일 중복 제거
      - `title+summary` 유사도(SequenceMatcher) 0.95 이상 중복 제거
  - 동기화 요약 확장:
    - `us_news_deduped_count`
    - `kr_ir_news_deduped_count`
- [x] 테스트 보강 및 회귀 확인
  - `test_corporate_event_collector`: `Ran 7 tests ... OK`
  - `test_scheduler_tier1_corporate_event_sync`: `Ran 3 tests ... OK`
  - 관련 회귀 묶음: `Ran 18 tests ... OK`

진행 현황 업데이트 (2026-02-18, 8차)
- [x] 유사도 중복 제거 로직 반영 후 실동기화 재검증
  - 실행: `sync_tier1_corporate_events_from_env()`
  - 결과:
    - `kr_ir_news_event_count=10`
    - `kr_ir_news_deduped_count=0`
    - `us_news_event_count=500`
    - `us_news_deduped_count=0`
    - `normalized_rows=606`
    - `status=ok`

진행 현황 업데이트 (2026-02-18, 9차)
- [x] 뉴스성 이벤트 중복 키를 결정론적 키로 고정
  - 규칙: `source_url + normalized_title + published_at` 기반 SHA1
  - 적용 대상:
    - US `yfinance_news`
    - KR `ir_news`
  - 구현:
    - `corporate_event_collector._build_news_source_ref(...)`
  - 효과:
    - 소스별 `id/guid` 변동과 무관하게 동일 기사 재수집 시 동일 `source_ref`로 upsert 정합성 강화
- [x] 적용 후 실동기화 재검증
  - 실행: `sync_tier1_corporate_events_from_env()`
  - 결과:
    - `kr_ir_news_event_count=10`
    - `us_news_event_count=500`
    - `normalized_rows=606`
    - `db_affected=702`
    - `status=ok`

진행 현황 업데이트 (2026-02-18, 10차)
- [x] 소스별 재시도(1/5/15분) + DLQ 적재 경로 구현
  - 구현 위치:
    - `corporate_event_collector._run_with_source_retry(...)`
    - `corporate_event_collector.record_dlq(...)`
    - 신규 DLQ 테이블: `corporate_event_ingest_dlq`
  - 재시도 정책:
    - 기본 `1,5,15` 분 (env: `TIER1_EVENT_SOURCE_RETRY_DELAYS_MINUTES`)
    - 실패 소스:
      - KR IR feed fetch/parse
      - US yfinance news fetch
  - 동기화 summary 확장:
    - `retry_failure_count`
    - `dlq_recorded_count`
- [x] 테스트 보강
  - `test_corporate_event_collector.py`
    - 최종 실패 시 DLQ 기록 경로 테스트 추가
  - 실행 결과:
    - `test_corporate_event_collector`: `Ran 8 tests ... OK`
    - 관련 회귀 묶음: `Ran 19 tests ... OK`
- [x] 실동기화 재검증
  - 실행: `sync_tier1_corporate_events_from_env()`
  - 결과:
    - `retry_failure_count=0`
    - `dlq_recorded_count=0`
    - `status=ok`

진행 현황 업데이트 (2026-02-18, 11차)
- [x] Tier-1 이벤트 동기화 경보 규칙(healthy/warn/degraded) 구현
  - 구현 위치:
    - `hobot/service/macro_trading/scheduler.py`
    - `sync_tier1_corporate_events_from_env()`
  - 경보 임계치(env):
    - `TIER1_EVENT_SYNC_WARN_RETRY_FAILURE_COUNT` (기본 1)
    - `TIER1_EVENT_SYNC_WARN_DLQ_RECORDED_COUNT` (기본 1)
    - `TIER1_EVENT_SYNC_DEGRADED_RETRY_FAILURE_COUNT` (기본 3)
    - `TIER1_EVENT_SYNC_DEGRADED_DLQ_RECORDED_COUNT` (기본 3)
  - 동작:
    - 수집 결과의 `retry_failure_count`/`dlq_recorded_count`를 기준으로 `health_status` 계산
    - 결과 payload에 `health_status`, `health_thresholds` 추가
    - `macro_collection_run_reports`에 `job_code='TIER1_CORPORATE_EVENT_SYNC'`로 실행 리포트 저장
    - `warn/degraded` 시 스케줄러 로그 경보 출력
- [x] 테스트 보강
  - `hobot/service/macro_trading/tests/test_scheduler_tier1_corporate_event_sync.py`
    - healthy/warn/degraded 판정 및 run report 기록 파라미터 검증 케이스 추가

진행 현황 업데이트 (2026-02-18, 12차)
- [x] `/admin/indicators`에 `TIER1_CORPORATE_EVENT_SYNC` 지표 노출
  - 구현 위치:
    - `hobot/service/macro_trading/indicator_health.py`
    - `KR_CORPORATE_REGISTRY` 추가
    - `macro_collection_run_reports` 조회 query_map 추가(`job_code='TIER1_CORPORATE_EVENT_SYNC'`)
  - 상태/노트:
    - 기존 성공률 지표와 동일한 포맷(일간 실행, 성공/실패, 요청 성공)
    - Tier-1 전용 확장 노트(`표준이벤트`, `재시도실패/DLQ`, `헬스상태`) 추가
  - 테스트:
    - `hobot/service/macro_trading/tests/test_indicator_health.py`
    - 신규 케이스: `test_snapshot_formats_tier1_event_sync_note`
- [x] Phase 3.5 다국어 필드 1차 저장 경로 반영
  - 구현 위치:
    - `hobot/service/macro_trading/collectors/corporate_event_collector.py`
  - 반영 범위:
    - KR DART 이벤트 payload: `summary_ko`, `keywords_ko`
    - US SEC/실적 이벤트 payload: `title_en`, `body_en`
    - US yfinance 뉴스 payload: `title_en`, `body_en`
    - KR IR feed 뉴스 payload: `summary_ko`, `keywords_ko`
  - 필드 정책:
    - 텍스트 내 한글 포함 여부 기반으로 `en/ko` 필드 자동 분기
    - `keywords_ko`는 한글 토큰(2글자 이상) 추출
  - 테스트:
    - `hobot/service/macro_trading/tests/test_corporate_event_collector.py` 필드 검증 추가
  - 실DB 확인:
    - `sync_tier1_corporate_events_from_env()` 1회 실행 후 샘플 조회
    - `event_type='yfinance_news'`: `title_en/body_en` 저장 확인
    - `event_type='ir_news'`: `summary_ko/keywords_ko` 저장 확인

진행 현황 업데이트 (2026-02-18, 13차)
- [x] 그래프 뉴스 마이그레이션 스케줄에 증분 임베딩 동기화 연동
  - 구현 위치:
    - `hobot/service/graph/embedding_loader.py` (신규)
    - `hobot/service/macro_trading/scheduler.py` (`run_graph_news_extraction_sync` 후단 호출)
  - 동작:
    - `Document` 증분 후보 조회(미임베딩/실패 재시도/업데이트 반영/모델·차원 변경)
    - `gemini-embedding-001` 기반 벡터 생성
    - `Document.text_embedding` + 메타(`embedding_model`, `embedding_dimension`, `embedding_status`, `embedding_updated_at`, `embedding_text_hash`) 저장
    - Neo4j Vector Index 자동 보장: `document_text_embedding_idx`
  - 스케줄 연동 정책:
    - 같은 트리거에서 실행하되, 임베딩 실패가 뉴스 동기화를 중단시키지 않도록 분리 처리
  - 환경변수:
    - `GEMINI_EMBEDDING_API_KEY` (우선 사용)
    - `GRAPH_NEWS_EMBEDDING_ENABLED` (기본 1)
    - `GRAPH_NEWS_EMBEDDING_MODEL` (기본 `gemini-embedding-001`)
    - `GRAPH_NEWS_EMBEDDING_DIMENSION` (기본 768)
    - `GRAPH_NEWS_EMBEDDING_LIMIT` (기본 800)
    - `GRAPH_NEWS_EMBEDDING_BATCH_SIZE` (기본 16)
    - `GRAPH_NEWS_EMBEDDING_MAX_TEXT_CHARS` (기본 6000)
    - `GRAPH_NEWS_EMBEDDING_RETRY_FAILED_AFTER_MINUTES` (기본 180)
- [x] 테스트 추가
  - `hobot/service/macro_trading/tests/test_document_embedding_loader.py`
  - `hobot/service/macro_trading/tests/test_scheduler_graph_news_embedding.py`
  - 실동작 스모크:
    - `sync_document_embeddings(limit=1)` 실행
    - 결과: `status=success`, `embedded_docs=1`, `failed_docs=0`

진행 현황 업데이트 (2026-02-18, 14차)
- [x] Graph RAG 검색을 BM25 + Vector 실제 Hybrid로 확장
  - 구현 위치:
    - `hobot/service/graph/rag/context_api.py`
  - 변경 내용:
    - 질문 임베딩 생성(`gemini-embedding-001`) 후 Neo4j Vector Index(`document_text_embedding_idx`) 검색 추가
    - BM25 full-text / vector / contains-fallback / base-doc 후보를 점수 결합해 단일 문서 랭킹으로 병합
    - 응답 `meta.retrieval`에 검색 모드/가중치/각 소스 문서수/임베딩 사용 여부 노출
  - 환경변수:
    - `GRAPH_RAG_VECTOR_SEARCH_ENABLED` (기본 1)
    - `GRAPH_RAG_VECTOR_INDEX_NAME` (기본 `document_text_embedding_idx`)
    - `GRAPH_RAG_QUERY_EMBEDDING_MODEL` (기본 `gemini-embedding-001`)
    - `GRAPH_RAG_QUERY_EMBEDDING_DIMENSION` (기본 768)
    - `GRAPH_RAG_VECTOR_QUERY_MULTIPLIER` (기본 3)
    - `GRAPH_RAG_BM25_WEIGHT` (기본 0.55)
    - `GRAPH_RAG_VECTOR_WEIGHT` (기본 0.45)
    - `GRAPH_RAG_FALLBACK_WEIGHT` (기본 0.15)
- [x] 테스트 추가
  - `hobot/service/macro_trading/tests/test_graph_rag_hybrid_search.py`
    - API key 미설정 시 query embedding skip 검증
    - 벡터 점수 우선 랭킹 병합 검증

진행 현황 업데이트 (2026-02-18, 15차)
- [x] `/admin/indicators`에 Graph 임베딩/벡터 인덱스 헬스 지표 추가
  - 구현 위치:
    - `hobot/service/macro_trading/indicator_health.py`
    - `hobot-ui-v2/src/components/admin/AdminIndicatorManagement.tsx`
  - 추가 지표:
    - `GRAPH_DOCUMENT_EMBEDDING_COVERAGE`: Document 임베딩 커버리지(%), 실패 건수 노트 표시
    - `GRAPH_RAG_VECTOR_INDEX_READY`: 벡터 인덱스 online 상태(flag), 인덱스명/구축률 노트 표시
  - 소스 그룹:
    - 관리자 화면 필터에 `그래프 (Neo4j)` 그룹 추가
- [x] 테스트 보강
  - `hobot/service/macro_trading/tests/test_indicator_health.py`
    - Graph 지표 코드 노출 검증
    - Graph 노트 포맷 검증(`test_snapshot_formats_graph_notes`)

진행 현황 업데이트 (2026-02-18, 16차)
- [x] `/admin/indicators` 상단에 Graph 운영 KPI 카드 추가
  - 구현 위치:
    - `hobot-ui-v2/src/components/admin/AdminIndicatorManagement.tsx`
  - 추가 카드:
    - 그래프 임베딩 커버리지(`GRAPH_DOCUMENT_EMBEDDING_COVERAGE`)
    - 벡터 인덱스 상태(`GRAPH_RAG_VECTOR_INDEX_READY`)
- [x] 그래프 뉴스/임베딩 스케줄 실행 이력 저장
  - 구현 위치:
    - `hobot/service/macro_trading/scheduler.py`
  - 저장 정책:
    - `job_code='GRAPH_NEWS_EXTRACTION_SYNC'`로 `macro_collection_run_reports` 적재
    - 성공/실패 카운트에 추출 실패건 + 임베딩 실패건 반영
    - `details_json`에 sync/extraction/embedding 세부 메트릭 저장
    - 예외 발생 시 실패 리포트 기록 후 재시도/상위 예외 전파
- [x] 테스트 보강
  - `hobot/service/macro_trading/tests/test_scheduler_graph_news_embedding.py`
    - 실행 리포트 기록 검증(성공/임베딩 비활성/예외 경로)

진행 현황 업데이트 (2026-02-18, 17차)
- [x] `/admin/indicators` 테이블에 `GRAPH_NEWS_EXTRACTION_SYNC` 지표 노출
  - 구현 위치:
    - `hobot/service/macro_trading/indicator_health.py`
  - 반영 내용:
    - `GRAPH_REGISTRY`에 `GRAPH_NEWS_EXTRACTION_SYNC` 등록
    - `macro_collection_run_reports`(`job_code='GRAPH_NEWS_EXTRACTION_SYNC'`) 조회 추가
    - note에 동기화/추출/임베딩 세부 결과 표시
- [x] 관리자 필터에서 Graph 소스 그룹 분류 보강
  - 구현 위치:
    - `hobot-ui-v2/src/components/admin/AdminIndicatorManagement.tsx`
  - 반영 내용:
    - 코드 prefix(`GRAPH_*`) 기준으로 `그래프 (Neo4j)` 그룹 매핑
- [x] 스케줄러 프로세스 재시작(코드 반영 적용)
  - 포트 8991 리스너 재기동 확인
  - Uvicorn startup 로그에서 `Macro Graph 뉴스 추출 스케줄` 포함 전체 스케줄 재등록 확인

진행 현황 업데이트 (2026-02-18, 18차)
- [x] Graph 운영 KPI/섹션 분리 UI 반영 완료
  - 구현 위치:
    - `hobot-ui-v2/src/components/admin/AdminIndicatorManagement.tsx`
  - 반영 내용:
    - 상단 Graph KPI 카드에 `GRAPH_NEWS_EXTRACTION_SYNC` 추가
    - Graph 지표를 본문에서 별도 테이블 섹션(`Graph 지표`)으로 분리
- [x] `GRAPH_NEWS_EXTRACTION_SYNC` 판정 강화
  - 구현 위치:
    - `hobot/service/macro_trading/indicator_health.py`
  - 반영 내용:
    - 런타임 상태 `healthy/warning/failed` 계산(`run_health_status`, `run_health_reason`)
    - failure count/rate 기반 임계치 적용:
      - `GRAPH_NEWS_SYNC_WARN_FAILURE_COUNT`(기본 10)
      - `GRAPH_NEWS_SYNC_FAIL_FAILURE_COUNT`(기본 50)
      - `GRAPH_NEWS_SYNC_WARN_FAILURE_RATE_PCT`(기본 5.0)
      - `GRAPH_NEWS_SYNC_FAIL_FAILURE_RATE_PCT`(기본 20.0)
    - 비정상 상태는 admin health를 `stale`로 승격 표시
- [x] 검증
  - 백엔드 테스트: `test_indicator_health`, `test_scheduler_graph_news_embedding`, `test_document_embedding_loader`, `test_graph_rag_hybrid_search` 통과
  - 프론트 빌드(`npm run build`) 통과

진행 현황 업데이트 (2026-02-18, 19차)
- [x] `/admin/indicators` 미국 기업 지표 필터 누락 수정
  - 증상:
    - US 기업 지표(SEC/YFINANCE/INTERNAL)가 화면에서 `기타`로 분류되어 노출성이 낮음
  - 원인:
    - 프론트 분류 로직이 `US + FRED`만 `US_MACRO`로 분기하고, US corporate 소스 분기가 없음
  - 조치:
    - `hobot-ui-v2/src/components/admin/AdminIndicatorManagement.tsx`
    - 소스 그룹 `US_CORPORATE` 추가
    - `US + {SEC,YFINANCE,INTERNAL}` 및 `US_*` code prefix를 `US_CORPORATE`로 매핑
  - 검증:
    - 프론트 빌드(`npm run build`) 통과
