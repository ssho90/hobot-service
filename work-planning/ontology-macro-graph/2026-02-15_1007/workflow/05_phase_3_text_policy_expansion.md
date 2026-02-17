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
- [ ] Fed/BOK 및 주요 정책기관 문서 수집기 구현
- [ ] 국토부/한국부동산원/주택금융 문서 파이프라인 구현
- [ ] `published_at`, `release_date`, `effective_date`, `observed_at` 필드 저장 강제

### 3.2 기업 이벤트 파이프라인 (Tier-1)
- [ ] US Tier-1: yfinance 뉴스/실적 이벤트 + IR 자료 수집
- [ ] KR Tier-1: Open DART 공시 + IR 보도자료 수집
- [ ] 표준 이벤트 스키마(`symbol`, `event_type`, `source_url`, `effective_date`) 적용

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
- [ ] 중복 키(`source_url + normalized_title + published_at`) 적용
- [ ] 본문 유사도 중복 제거(0.95+) 정책 적용
- [ ] 소스별 재시도(1/5/15분), DLQ, 경보 규칙 구현

### 3.5 다국어 적재/검색 + 엔터티 정규화
- [ ] US 원문 필드(`title_en`, `body_en`)와 한국어 요약 필드(`summary_ko`, `keywords_ko`) 동시 저장
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
