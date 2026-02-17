# Phase 2 상세 계획: US/KR 정량 데이터 확장

## 1. 목표
- US/KR 거시/유동성(P0/P1)과 KR 부동산(P4) 핵심 시계열을 수집 가능한 상태로 만든다.
- 다주기 시계열 통합(`daily` anchor + `merge_asof`)과 리비전 관리 규격을 적용한다.
- KPI 추적 가능한 품질/신선도 모니터링 기초를 구축한다.

## 2. 기간
- 권장 기간: 2026-03-02 ~ 2026-03-20 (3주)

## 3. 작업 스트림
### 3.1 P0/P1 수집기 온보딩 (US/KR)
- [x] ECOS/KOSIS/FRED 기반 성장·물가·고용·금리·통화 지표 수집기 구현
- [x] USD/KRW, 미 국채 2Y/10Y 등 공통 비교 지표 라인업 확정
- [x] 주기/단위 정규화 규칙 적용 (`daily/weekly/monthly/quarterly`)

예상 대상 코드
- `hobot/service/macro_trading/collectors/fred_collector.py`
- `hobot/service/graph/indicator_loader.py`
- `hobot/service/macro_trading/config/macro_trading_config.json`

### 3.2 P4 한국 부동산 수집기 온보딩
- [x] 국토부 실거래(매매/전세/월세) 수집 파이프라인 구현
- [x] 지역 적재 정책 확정: 서울/경기 전수 + 지방 주요 도시 선별 적재
- [x] REB/KOSIS 기반 가격지수·전세가율·미분양·공급 지표 수집기 추가
- [x] `region_code`, `property_type`, `transaction_type` 스키마 일관화

예상 산출물
- 부동산 표준 스키마 명세서
- 수집기별 결측/지연 처리 규칙 문서
  - `work-planning/ontology-macro-graph/2026-02-15_1007/workflow/phase2_real_estate_schema_spec.md`

### 3.3 다주기 통합/누수 방지
- [x] `merge_asof(backward)` 기반 daily anchor 결합 모듈 추가
- [x] `published_at`/`effective_date` 분리 저장 로직 적용
- [x] 누수(Data Leakage) 방지 단위 테스트 추가

예상 대상 코드
- `hobot/service/graph/derived_feature_calc.py`
- `hobot/service/graph/state/macro_state_generator.py`

### 3.4 리비전/품질 규칙
- [x] 리비전 데이터 버전 저장(`revision_flag=true`) 구현
- [x] `as_of_date` 기준 조회 로직 추가
- [x] 신선도/누락률 모니터링 지표 수집

예상 대상 코드
- `hobot/service/graph/impact/quality_metrics.py`
- `hobot/service/graph/monitoring/graphrag_metrics.py`

### 3.5 테스트/운영 검증
- [ ] 수집기별 샘플 백필(최근 3년) 수행
- [x] 단위/주기 정규화 회귀 테스트 구축
- [x] 월간 지표 지연 반영 검증 시나리오 추가

예상 대상 테스트
- `hobot/service/macro_trading/tests/test_fred.py`
- `hobot/tests/test_phase_c_components.py`

## 4. 완료 기준 (DoD)
- P0/P1/P4 핵심 지표가 US/KR 스코프로 안정 수집된다.
- 일/주/월 신선도 SLA를 모니터링할 수 있는 기본 대시보드 데이터가 생성된다.
- 다주기 통합 및 리비전 저장 규칙이 코드와 테스트로 고정된다.

## 5. 리스크/대응
- 리스크: 부동산 소스 지연 공시/리비전 빈발
- 대응: 리비전 버전 관리와 `as_of_date` 노출을 기본 동작으로 강제
- 리스크: 지표별 단위 불일치
- 대응: 표준 단위 테이블과 ingest 단계 변환 함수 운영

## 6. Phase 2.5 인계 항목
- P0/P1/P4 표준 데이터 계약서
- 지표 코드 매핑 테이블 v2
- 시계열 통합 모듈/테스트 결과

## 7. 진행 로그 (2026-02-15)
- 완료: `IndicatorObservation` ingest 메타데이터/리비전 버전 저장 강화
  - `hobot/service/graph/indicator_loader.py`
- 완료: `merge_asof(backward)` daily anchor 유틸 및 파생피처 시점 필터 적용
  - `hobot/service/graph/derived_feature_calc.py`
- 완료: MacroState 시그널 조회 누수 방지(`effective/published/as_of`) 조건 적용
  - `hobot/service/graph/state/macro_state_generator.py`
- 완료: 지표 신선도/누락률 품질 지표 추가
  - `hobot/service/graph/impact/quality_metrics.py`
  - `hobot/service/graph/scheduler/weekly_batch.py`
- 완료: Phase2 관련 단위 테스트 추가/보강
  - `hobot/tests/test_phase2_multifrequency_alignment.py`
  - `hobot/tests/test_phase_c_quality_metrics.py`
  - `hobot/tests/test_phase_d_state_persistence.py`
- 완료: KR 매크로 수집기(ECOS/KOSIS/FRED) 및 US/KR 비교 지표 수집 진입점 추가
  - `hobot/service/macro_trading/collectors/kr_macro_collector.py`
  - `hobot/service/macro_trading/scheduler.py`
- 완료: KR 부동산 canonical 스키마 수집기 및 MOLIT XML 파서 추가
  - `hobot/service/macro_trading/collectors/kr_real_estate_collector.py`
  - `hobot/service/macro_trading/tests/test_kr_collectors.py`
- 완료: KR 부동산 보조지표(REB/KOSIS) collector 확장
  - 신규 지표 코드:
    - `KR_HOUSE_PRICE_INDEX`
    - `KR_JEONSE_PRICE_RATIO`
    - `KR_UNSOLD_HOUSING`
    - `KR_HOUSING_SUPPLY_APPROVAL`
  - 운영 함수:
    - `collect_kr_real_estate_supplemental_data(days=3650)`
    - (내부적으로 `collect_kr_macro_data(indicator_codes=...)` 사용)
  - KOSIS 파라미터 운영:
    - `KR_HOUSE_PRICE_INDEX`, `KR_JEONSE_PRICE_RATIO`, `KR_UNSOLD_HOUSING`, `KR_HOUSING_SUPPLY_APPROVAL` 기본 파라미터는 코드에 내장
    - 운영에서는 `KOSIS_<INDICATOR_CODE>_PARAMS_JSON` 및 `KOSIS_KR_*` 환경변수로 override 가능
    - 통계 목록 탐색은 `https://kosis.kr/openapi/statisticsList.do?method=getList` 사용
      - 예: `vwCd=MT_ZTITLE`, `parentListId=I1` (주택통계 카테고리)
    - 미분양(`KR_UNSOLD_HOUSING`)은 월별 시도 행에서 `C2_NM='계'`만 필터 후 월 단위 합(sum)으로 전국값 산출
    - 미분양 테이블(`DT_MLTM_2082`)은 운영 기준 최소 시작월 `202410` 보정 및 최신 공표 지연 시 `endPrdDe` 자동 후퇴(fallback) 적용
    - 수집 로그의 `apiKey/serviceKey`는 `***REDACTED***`로 마스킹
  - 코드:
    - `hobot/service/macro_trading/collectors/kr_macro_collector.py`
    - `hobot/service/macro_trading/scheduler.py`
    - `hobot/service/macro_trading/tests/test_kr_collectors.py`
- 완료: KR 부동산 지역 범위 정책/월별 적재 루프 추가
  - 기본 정책: `서울 전 지역 + 경기 전 지역 + 지방 주요 도시`
  - 환경변수:
    - `MOLIT_REGION_SCOPE` (`seoul_gyeonggi_all_major_cities`, `seoul_gyeonggi_all`, `major_cities_only`)
    - `MOLIT_TARGET_LAWD_CODES` (CSV 지정 시 우선 적용)
  - 코드:
    - `hobot/service/macro_trading/collectors/kr_real_estate_collector.py`
    - `hobot/service/macro_trading/scheduler.py`
- 완료: KR 부동산 적재 진행률 관측 기능 추가
  - `total_pairs/completed_pairs/remaining_pairs/progress_pct` 요약 포함
  - `progress_file` JSON 스냅샷 저장 및 `progress_log_interval` 주기 로그 지원
  - 코드:
    - `hobot/service/macro_trading/collectors/kr_real_estate_collector.py`
    - `hobot/service/macro_trading/scheduler.py`
- 완료: KR 부동산 월×지역 집계 테이블 구축 (`RDB 상세 + Graph 집계` 전략)
  - 집계 테이블: `kr_real_estate_monthly_summary`
  - 집계 축: `stat_ym(YYYYMM) × lawd_cd(5자리) × property_type × transaction_type`
  - 기본 서빙 뷰: `apartment + sale`
  - 코드:
    - `hobot/service/macro_trading/collectors/kr_real_estate_collector.py`
    - `hobot/service/macro_trading/scheduler.py`
- 완료: KR 부동산 집계 -> Neo4j Graph 동기화 로더 추가
  - Graph 노드/관계:
    - `(:RealEstateRegion {country_code, lawd_cd})`
    - `(:RealEstateMonthlySummary {summary_key})`
    - `(:RealEstateRegion)-[:HAS_MONTHLY_SUMMARY]->(:RealEstateMonthlySummary)`
  - 범위 동기화 결과(202403~202602, apartment/sale):
    - summary nodes `3322`, region nodes `139`, 관계 `3322`
  - 코드:
    - `hobot/service/graph/real_estate_loader.py`
    - `hobot/service/macro_trading/scheduler.py`
- 완료: KR 부동산 통합 조회 API 추가 (`RDB 상세 + Graph 집계`)
  - 엔드포인트:
    - `GET /api/macro/real-estate?view=detail|monthly|region`
    - `GET /api/macro/real-estate/detail`
    - `GET /api/macro/real-estate/monthly`
    - `GET /api/macro/real-estate/regions`
  - 조회 라우팅:
    - `detail` -> MySQL `kr_real_estate_transactions`
    - `monthly/region` -> Neo4j `RealEstateMonthlySummary`
    - Neo4j 실패 시 MySQL `kr_real_estate_monthly_summary` 폴백
  - 코드/테스트:
    - `hobot/service/macro_trading/real_estate_api.py`
    - `hobot/tests/test_phase2_real_estate_query_api.py`
- 완료: 월간 지표 공시 지연 시 look-ahead 누수 방지 테스트 추가
  - `hobot/tests/test_phase2_multifrequency_alignment.py`
