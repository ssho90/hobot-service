# Phase 2.5 상세 계획: 한국 주식/기업 데이터 확장 (P2/P3)

## 1. 목표
- P2(주식 마이크로)와 P3(기업 펀더멘털) 데이터 파이프라인을 KR 중심으로 확장하고 US 경로와 정합성을 맞춘다.
- `symbol`/`corp_code`/섹터 분류를 표준화해 기업 단위 질의/비교 기반을 구축한다.
- Top 50 상시 수집 체계와 Tier 운영 기본 구조를 완성한다.

## 2. 기간
- 권장 기간: 2026-03-23 ~ 2026-04-03 (2주)

## 3. 작업 스트림
### 3.1 P2 수집기 구축 (KRX/금융위 기반)
- [ ] 투자자별 순매수/공매도/신용융자 일간 수집 파이프라인 구현
- [ ] 지수/업종 데이터와 종목 단위 데이터 결합
- [ ] 결측/휴장일 처리 규칙 표준화

### 3.2 P3 수집기 구축 (Open DART + US Financials)
- [x] Open DART 재무제표 수집기 구현(사업/반기/분기 보고서 코드 포함)
- [x] 기업코드 캐시/갱신 로직 구현
- [x] 실적 공시 이벤트 적재 시 `actual vs expected` + `earnings surprise` 구조 반영
- [x] US Top50 실적 이벤트(예정/확정) 수집 경로 운영 연결
- [x] US `yfinance for US Financials` 경로 유지 및 재무 컬럼 정합성 검증

참고 문서
- `hobot/docs/api_specification/dart/api_description_dart.md`

구현 메모 (2026-02-15)
- 신규 수집기: `hobot/service/macro_trading/collectors/kr_corporate_collector.py`
  - `corpCode.xml` 캐시 테이블: `kr_dart_corp_codes`
  - 주요계정 테이블: `kr_corporate_financials`
  - 공시 이벤트 테이블: `kr_corporate_disclosures`
    - `metric_actual_json`, `metric_expected_json`, `metric_surprise_json`, `surprise_label`
  - 시장기대값 테이블: `kr_corporate_earnings_expectations`
  - Open DART `fnlttMultiAcnt.json` 배치 수집(최대 100 corp_code/호출)
  - Open DART `list.json` 공시 수집 + 실적 이벤트 분류/기간 추론(연도/분기)
  - 실제값(actual): `kr_corporate_financials`에서 매출/영업이익/순이익 추출
  - 기대값(expected): `kr_corporate_earnings_expectations` 참조
  - 기대값 자동 적재:
    - 외부 JSON feed(`KR_EARNINGS_EXPECTATION_FEED_URL`) 입력 지원
    - `.env` URL이 없어도 기본 내부 feed(`internal://kr-top50-ondemand`) 사용
      - 범위: Top50(네이버 시총 페이지 크롤링: `sise_market_sum.naver`, KOSPI) 고정 스냅샷
      - Top50은 스냅샷 테이블(`kr_top50_universe_snapshot`) 최신 버전을 고정 기준으로 사용
        - 컬럼: `snapshot_date`, `market`, `rank_position`, `stock_code`, `stock_name`, `corp_code`
      - 크롤링 실패 시 fallback: 최근 사업보고서 매출 기준 Top50
      - 소스: `kr_corporate_earnings_expectations`의 `feed/consensus_feed/manual` 우선
    - 정책 기본값: feed 필수(`require_feed_expectations=True`)
    - 내부 baseline(동일 분기 과거 N년 평균, 기본 3년)은 기본 비활성(`allow_baseline_fallback=False`)이며 필요 시에만 fallback으로 사용
  - 서프라이즈: `(actual-expected)/abs(expected)`로 `beat/meet/miss` 계산
- 스케줄러 진입점 추가:
  - `collect_kr_corporate_fundamentals(bsns_year, reprt_code, ...)`
  - `capture_kr_top50_snapshot(snapshot_date, market, limit, ...)`
  - `collect_kr_corporate_disclosure_events(start_date, end_date, expectation_rows=..., auto_expectations=True, expectation_feed_url=..., ...)`
  - 위치: `hobot/service/macro_trading/scheduler.py`
- Admin 연동:
  - `/admin/indicators` (`/api/admin/macro-indicators/status`)에서 corporate 수집 항목 상태를 함께 관리
  - 코드: `KR_DART_CORP_CODES`, `KR_DART_FINANCIALS_Q1/H1/Q3/Y`, `KR_DART_DISCLOSURE_EARNINGS`, `KR_DART_EARNINGS_EXPECTATION`
  - `KR_DART_EARNINGS_EXPECTATION` 항목에 최근 기대값 소스 표시(`feed/baseline/manual` 집계)
- 모듈 export 반영:
  - `hobot/service/macro_trading/collectors/__init__.py`
  - `hobot/service/macro_trading/__init__.py`
- 단위 테스트:
  - `hobot/service/macro_trading/tests/test_kr_corporate_collector.py`

진행 현황 업데이트 (2026-02-16)
- [x] 기대값(feed) 정책을 기본 강제 모드로 고정
  - `require_feed_expectations=True`, `allow_baseline_fallback=False`
- [x] `.env` 수동 URL 없이 동작하도록 내부 feed 기본값 적용
  - `internal://kr-top50-ondemand`
- [x] Top50 고정 스냅샷을 JSON에서 DB 테이블로 전환
  - 신규 테이블: `kr_top50_universe_snapshot`
  - 컬럼: `snapshot_date`, `market`, `rank_position`, `stock_code`, `stock_name`, `corp_code`, `source_url`, `captured_at`
- [x] Top50 스냅샷 캡처 진입점 추가
  - `capture_kr_top50_snapshot(...)`
- [x] 기대값 feed 입력원에 네이버 종목 페이지 컨센서스 파서 연동
  - 분기(E) 기준 `매출액/영업이익/당기순이익`을 `consensus_feed`로 적재
- [x] `/admin/indicators`에서 `KR_DART_EARNINGS_EXPECTATION` 최근 소스 표시
  - `feed / baseline / manual` 집계 표시
- [x] 검증 완료
  - 단위테스트(`test_kr_corporate_collector`) 통과
  - 실 DB에서 Top50 스냅샷 50건 저장 및 내부 feed 경로 동작 확인

진행 현황 업데이트 (2026-02-17)
- [x] Top50 실적발표 감시 핫패스 추가
  - `run_kr_top50_earnings_hotpath(...)` 구현
  - 공시 수집 결과에 `new_earnings_events`(신규 실적 이벤트) 요약 추가
  - 신규 실적 이벤트 발생 시 해당 기업/분기 기준으로 `collect_kr_corporate_fundamentals(...)` 즉시 실행
- [x] 스케줄러 자동 실행 경로 추가
  - `setup_kr_top50_earnings_scheduler()` 등록
  - 기본 주기 실행 + 환경변수 제어
    - `KR_TOP50_EARNINGS_WATCH_ENABLED` (기본 1)
    - `KR_TOP50_EARNINGS_WATCH_INTERVAL_MINUTES` (기본 5)
    - `KR_TOP50_EARNINGS_WATCH_LOOKBACK_DAYS` (기본 1)
    - `KR_TOP50_EARNINGS_IMMEDIATE_FUNDAMENTALS` (기본 1)
- [x] 테스트 추가
  - `hobot/service/macro_trading/tests/test_scheduler_kr_top50_earnings.py`

진행 현황 업데이트 (2026-02-17, 2차)
- [x] Top50 월간 스냅샷 갱신 잡 추가
  - `run_kr_top50_monthly_snapshot_job(...)` 구현
  - 매일 지정 시각 실행 + day-of-month 조건 만족 시에만 스냅샷 생성
  - 직전 스냅샷 대비 diff(편입/편출/순위변동) 요약 생성
- [x] 스케줄러 자동 등록
  - `setup_kr_top50_snapshot_scheduler()` 추가
  - 환경변수:
    - `KR_TOP50_SNAPSHOT_ENABLED` (기본 1)
    - `KR_TOP50_SNAPSHOT_SCHEDULE_TIME` (기본 06:10)
    - `KR_TOP50_SNAPSHOT_DAY_OF_MONTH` (기본 1)
    - `KR_TOP50_SNAPSHOT_MARKET` (기본 KOSPI)
    - `KR_TOP50_SNAPSHOT_LIMIT` (기본 50)
- [x] Admin indicator 상태 노출 확장
  - 코드: `KR_TOP50_UNIVERSE_SNAPSHOT`
  - `/admin/indicators`에서 최신 스냅샷 일자/건수 health 점검 가능
- [x] 테스트 추가
  - `hobot/service/macro_trading/tests/test_scheduler_kr_top50_snapshot.py`
  - `hobot/service/macro_trading/tests/test_kr_corporate_collector.py`에 Top50 diff 테스트 2건 추가

진행 현황 업데이트 (2026-02-17, 3차)
- [x] US Top50 실적 이벤트 수집 경로를 운영 스케줄러에 연결
  - 신규 수집 실행 경로:
    - `run_us_top50_earnings_hotpath(...)`
    - `run_us_top50_earnings_hotpath_from_env()`
  - 신규 스케줄러:
    - `setup_us_top50_earnings_scheduler()`
    - `start_all_schedulers()` 자동 등록
  - 환경변수:
    - `US_TOP50_EARNINGS_WATCH_ENABLED` (기본 1)
    - `US_TOP50_EARNINGS_WATCH_INTERVAL_MINUTES` (기본 5)
    - `US_TOP50_EARNINGS_WATCH_LOOKBACK_DAYS` (기본 30)
    - `US_TOP50_EARNINGS_WATCH_LOOKAHEAD_DAYS` (기본 120)
    - `US_TOP50_EARNINGS_INCLUDE_EXPECTED` / `US_TOP50_EARNINGS_INCLUDE_CONFIRMED` (기본 1/1)
    - `US_SEC_MAPPING_REFRESH` (기본 1), `US_SEC_MAPPING_MAX_AGE_DAYS` (기본 30)
- [x] `/admin/indicators` 상태 노출 확장(US corporate)
  - `US_SEC_CIK_MAPPING`
  - `US_TOP50_EARNINGS_EVENTS_CONFIRMED`
  - `US_TOP50_EARNINGS_EVENTS_EXPECTED`
- [x] SEC submissions 호출 안정화
  - `Host` 헤더 강제 지정 제거(`data.sec.gov` 404 회피)
- [x] 런타임 `yfinance` 의존성 배포 환경 반영(`hobot/requirements.txt` + `.venv` 설치 확인)
- [x] 테스트 추가
  - `hobot/service/macro_trading/tests/test_scheduler_us_top50_earnings.py`
  - `hobot/service/macro_trading/tests/test_us_corporate_collector.py`
  - `hobot/service/macro_trading/tests/test_indicator_health.py`에 US corporate registry 노출 테스트 추가

진행 현황 업데이트 (2026-02-17, 4차)
- [x] US 재무제표 canonical 스키마/수집 경로 구현
  - 신규 테이블: `us_corporate_financials`
    - 키: `symbol + statement_type + statement_cadence + period_end_date + account_key`
    - 컬럼: `fiscal_year`, `fiscal_period(Q1~Q4/FY)`, `account_label`, `value_numeric`, `currency`, `as_of_date`, `metadata_json`
  - 신규 수집 경로:
    - `USCorporateCollector.collect_financials(...)`
    - `run_us_top50_financials_hotpath(...)`
    - `run_us_top50_financials_hotpath_from_env()`
  - 신규 스케줄러:
    - `setup_us_top50_financials_scheduler()` (기본: 매일 06:40)
    - `start_all_schedulers()` 자동 등록
  - 환경변수:
    - `US_TOP50_FINANCIALS_ENABLED` (기본 1)
    - `US_TOP50_FINANCIALS_SCHEDULE_TIME` (기본 06:40)
    - `US_TOP50_FINANCIALS_MAX_SYMBOL_COUNT` (기본 50)
    - `US_TOP50_FINANCIALS_MAX_PERIODS_PER_STATEMENT` (기본 12)
- [x] `/admin/indicators` 상태 노출 확장
  - `US_TOP50_FINANCIALS` 코드 추가
- [x] 수집 안정화 보강
  - SEC headers에서 `Host` 강제 제거(`data.sec.gov` 404 회피)
  - yfinance NaN/Inf 값 방어(`_safe_float`)
- [x] 의존성 반영
  - `hobot/requirements.txt`: `yfinance`, `lxml`
- [x] 테스트 추가
  - `hobot/service/macro_trading/tests/test_scheduler_us_top50_financials.py`
  - `hobot/service/macro_trading/tests/test_us_corporate_collector.py` 재무 row 변환/요약 테스트 확장
- [x] 실배치 검증(터널 연결 상태)
  - 실행일시: 2026-02-17
  - `run_us_top50_financials_hotpath(max_symbol_count=50, max_periods_per_statement=4)`:
    - fetched_rows=63,952 / upserted_rows=64,502 / failed_symbols=0
    - statement별: IS(annual 8,728, quarterly 8,043), BS(annual 13,950, quarterly 12,588), CF(annual 10,945, quarterly 9,698)
  - `run_us_top50_earnings_hotpath(max_symbol_count=50)`:
    - api_requests=50 / confirmed_rows=2,840 / expected_rows=84 / upserted_rows=3,013 / failed_symbols=0
  - 적재 결과 테이블:
    - `us_corporate_financials`: 63,952 rows (`max_period`=2026-01-31)
    - `us_corporate_earnings_events`: 2,924 rows (confirmed 2,840 / expected 84, `max_event_date`=2026-05-14)
  - `/admin/indicators` backend 상태:
    - `US_TOP50_FINANCIALS`, `US_SEC_CIK_MAPPING`, `US_TOP50_EARNINGS_EVENTS_CONFIRMED`, `US_TOP50_EARNINGS_EVENTS_EXPECTED` 모두 healthy 확인

진행 현황 업데이트 (2026-02-17, 5차)
- [x] Tier 상태 저장 스키마/동기화 경로 구현 (Tier-1 운영, Tier-2/3 schema-ready)
  - 신규 수집기: `hobot/service/macro_trading/collectors/corporate_tier_collector.py`
  - 신규 테이블: `corporate_tier_state`
    - 키: `as_of_date + country_code + symbol + tier_level + tier_source`
    - 현재 적재 범위: KR Top50 최신 스냅샷 + US 고정 Top50 (각 50)
  - 신규 스케줄러:
    - `sync_uskr_tier_state(...)`
    - `sync_uskr_tier_state_from_env()`
    - `setup_uskr_tier_state_scheduler()` (기본: 매일 06:50)
  - 환경변수:
    - `USKR_TIER_STATE_ENABLED` (기본 1)
    - `USKR_TIER_STATE_SCHEDULE_TIME` (기본 06:50)
    - `USKR_TIER_STATE_KR_MARKET` (기본 KOSPI)
    - `USKR_TIER_STATE_KR_LIMIT` (기본 50)
    - `USKR_TIER_STATE_US_LIMIT` (기본 50)
- [x] `/admin/indicators` 상태 노출 확장(Tier 운영)
  - `KR_TOP50_TIER_STATE`
  - `US_TOP50_TIER_STATE`
- [x] 단위 테스트/실배치 검증
  - 테스트: `test_corporate_tier_collector.py`, `test_scheduler_uskr_tier_state.py`, `test_indicator_health.py`
  - 실배치 결과(2026-02-17): KR 50 + US 50 = 총 100건 active 동기화 확인

진행 현황 업데이트 (2026-02-17, 6차)
- [x] Company PK `(country_code, symbol)` canonical registry 적용
  - 신규 수집기: `hobot/service/macro_trading/collectors/corporate_entity_collector.py`
  - 신규 테이블:
    - `corporate_entity_registry` (PK 성격 unique: `country_code + symbol`)
    - `corporate_entity_aliases` (alias 정규화: `alias_normalized`)
  - 보정: `corp_code/cik`는 unique 제약이 아닌 index로 유지
    - 이유: 다중 클래스 종목(예: 동일 CIK 공유)에서 1:N 심볼이 가능하기 때문
- [x] Tier-1 기반 기업 alias 정규화 경로 구현
  - 소스: `corporate_tier_state` active Tier-1 (KR/US)
  - alias 타입: `symbol`, `symbol_compact`, `company_name`, `corp_code`, `cik`
  - 스케줄러:
    - `sync_uskr_corporate_entity_registry(...)`
    - `sync_uskr_corporate_entity_registry_from_env()`
    - `setup_uskr_entity_registry_scheduler()` (기본: 매일 06:55)
  - 환경변수:
    - `USKR_ENTITY_REGISTRY_ENABLED` (기본 1)
    - `USKR_ENTITY_REGISTRY_SCHEDULE_TIME` (기본 06:55)
    - `USKR_ENTITY_REGISTRY_COUNTRIES` (기본 KR,US)
    - `USKR_ENTITY_REGISTRY_TIER_LEVEL` (기본 1)
    - `USKR_ENTITY_REGISTRY_SOURCE` (기본 tier1_sync)
- [x] `/admin/indicators` 상태 코드 확장
  - `KR_TOP50_ENTITY_REGISTRY`
  - `US_TOP50_ENTITY_REGISTRY`

진행 현황 업데이트 (2026-02-17, 7차)
- [x] KR `corp_code` 매핑 검증 리포트 자동화 구현
  - 신규 리포트 테이블: `kr_corp_code_mapping_reports`
  - 신규 검증 경로:
    - `validate_top50_corp_code_mapping(...)` (`KRCorporateCollector`)
    - `validate_kr_top50_corp_code_mapping(...)` (`scheduler`)
    - `validate_kr_top50_corp_code_mapping_from_env()` (`scheduler`)
  - 검증 항목:
    - `snapshot_missing_corp_count`
    - `snapshot_missing_in_dart_count`
    - `snapshot_corp_code_mismatch_count`
    - `dart_duplicate_stock_count`
- [x] 스케줄러 자동 등록
  - `setup_kr_corp_code_mapping_validation_scheduler()` (기본: 매일 06:15)
  - 환경변수:
    - `KR_CORP_MAPPING_VALIDATION_ENABLED` (기본 1)
    - `KR_CORP_MAPPING_VALIDATION_SCHEDULE_TIME` (기본 06:15)
    - `KR_CORP_MAPPING_VALIDATION_MARKET` (기본 KOSPI)
    - `KR_CORP_MAPPING_VALIDATION_TOP_LIMIT` (기본 50)
    - `KR_CORP_MAPPING_VALIDATION_PERSIST` (기본 1)
- [x] `/admin/indicators` 상태 코드 확장
  - `KR_TOP50_CORP_CODE_MAPPING_VALIDATION`
- [x] 품질 이슈 보정
  - `corporate_entity_registry`에서 `corp_code/cik` unique 제약 제거 후 index로 유지
  - 다중 클래스 종목(동일 CIK 공유) 케이스에서 US 50건 보존 확인

진행 현황 업데이트 (2026-02-17, 8차)
- [x] Top50 리밸런싱 변동 대비 연속성(grace window) 수집 경로 적용
  - 목적: 월간 편입/편출 변동으로 기업 재무/실적 시계열이 끊기는 문제 완화
  - 기준: `corporate_tier_state` 최근 이력(lookback window)에서 심볼 유니버스 확장
  - KR 실적 핫패스:
    - `run_kr_top50_earnings_hotpath(...)`에서 Tier grace 심볼 -> `corp_code` 변환 후 공시 수집 범위 확장
  - US 실적/재무 핫패스:
    - `run_us_top50_earnings_hotpath(...)`
    - `run_us_top50_financials_hotpath(...)`
    - grace 심볼 병합 시 `effective_max_symbol_count`를 동적으로 상향해 절단(truncation) 방지
- [x] 운영 가시성 필드 추가
  - 결과 요약에 `grace_universe_enabled`, `grace_symbol_count`/`grace_corp_code_count`, `effective_max_symbol_count` 반영
- [x] 테스트 보강
  - `test_scheduler_kr_top50_earnings.py`: grace corp_code 범위 적용 검증
  - `test_scheduler_us_top50_financials.py`: grace 심볼 확장/상한 반영 검증
  - `test_scheduler_us_top50_earnings.py`: grace 심볼 확장/상한 반영 검증

정책 메모 (연속성)
- Top50는 월간 리밸런싱으로 운영하되, 실시간 수집 유니버스는 최근 Tier 이력 기반 grace window를 포함한다.
- 이를 통해 편출 직후 기업의 분기/연간 시계열 연속성 저하를 최소화한다.

진행 현황 업데이트 (2026-02-17, 9차)
- [x] 실DB(터널링) 기준 grace 유니버스 반영 실행 검증 완료
  - KR 실적 핫패스(`run_kr_top50_earnings_hotpath_from_env`)
    - `grace_corp_code_count=49`
    - `disclosure_api_requests=49`
    - `new_earnings_event_count=0`, `failed_requests=0`
  - US 실적 핫패스(`run_us_top50_earnings_hotpath_from_env`)
    - `grace_symbol_count=50`, `effective_max_symbol_count=150`
    - `target_symbol_count=50`, `api_requests=50`
    - `expected_rows=86`, `confirmed_rows=2840`, `upserted_rows=5852`, `failed_symbols=0`
  - US 재무 핫패스(`run_us_top50_financials_hotpath_from_env`)
    - `grace_symbol_count=50`, `effective_max_symbol_count=150`
    - `target_symbol_count=50`
    - `fetched_rows=73864`, `upserted_rows=137816`, `failed_symbols=0`

진행 현황 업데이트 (2026-02-17, 10차)
- [x] US Top50 월간 리밸런싱(스냅샷+diff) 자동화 구현
  - 신규 테이블: `us_top50_universe_snapshot`
    - 키: `market + snapshot_date + rank_position` / `market + snapshot_date + symbol`
    - 컬럼: `symbol`, `company_name`, `cik`, `market_cap`, `source_url`, `captured_at`
  - 신규 수집/비교 경로:
    - `capture_us_top50_snapshot(...)`
    - `run_us_top50_monthly_snapshot_job(...)`
    - `run_us_top50_monthly_snapshot_job_from_env()`
  - 신규 스케줄러:
    - `setup_us_top50_snapshot_scheduler()` (기본: 매일 06:20, target day-of-month 조건)
  - 동작 정책:
    - 기본 라인업: `US_TOP50_FIXED_SYMBOLS`
    - 선택 옵션: `US_TOP50_REBALANCE_CANDIDATES`를 지정하면 후보군 내 시총 기준 정렬 후 Top N 스냅샷
  - 환경변수:
    - `US_TOP50_SNAPSHOT_ENABLED` (기본 1)
    - `US_TOP50_SNAPSHOT_SCHEDULE_TIME` (기본 06:20)
    - `US_TOP50_SNAPSHOT_DAY_OF_MONTH` (기본 1)
    - `US_TOP50_SNAPSHOT_MARKET` (기본 US)
    - `US_TOP50_SNAPSHOT_LIMIT` (기본 50)
    - `US_TOP50_SNAPSHOT_SOURCE_URL` (기본 `internal://us-top50-fixed`)
    - `US_TOP50_REBALANCE_CANDIDATES` (선택)
    - `US_TOP50_SNAPSHOT_RANK_BY_MARKET_CAP` (기본 1)
    - `US_TOP50_SNAPSHOT_REFRESH_SEC_MAPPING` (기본 1)
- [x] `/admin/indicators` 상태 노출 확장
  - `US_TOP50_UNIVERSE_SNAPSHOT`
- [x] 테스트 추가
  - `test_scheduler_us_top50_snapshot.py`
  - `test_us_corporate_collector.py` snapshot diff 로직 검증

진행 현황 업데이트 (2026-02-17, 11차)
- [x] 실DB(터널링) 기준 US 월간 스냅샷 잡 1회 실행 검증
  - 실행: `run_us_top50_monthly_snapshot_job(target_day_of_month=today.day)`
  - 결과:
    - `status=completed`
    - `capture_saved_rows=50`
    - `capture_row_count=50`
    - `capture_candidate_count=50`
    - `diff_added_count=50` (초기 스냅샷)
    - `diff_removed_count=0`
    - `diff_rank_changed_count=0`

### 3.3 기업 식별자/섹터 정합성
- [x] Company PK 규칙 `(country_code, symbol)` 적용
- [x] KR `corp_code`/`dart_code` 속성 매핑 검증
- [x] CompanyAlias 기반 한글/영문 동의어 정규화 (Tier-1 source 기준)

예상 대상 코드
- `hobot/service/graph/nel/alias_dictionary.py`
- `hobot/service/graph/nel/nel_pipeline.py`

### 3.4 Top 50 리밸런싱/티어 운영
- [x] US Top 50 + 코스피 Top 50 월 1회 갱신 배치 구현
- [x] Tier-1/2/3 상태 저장 테이블 설계 (Tier-1 운영 적용, Tier-2/3 추후 확장)
- [x] 상시 수집 규칙 적용 (KR/US 실적 감시 5분 주기, Tier daily 동기화)
- [보류] 온디맨드 승격 규칙 적용 (추후 구현)

예상 대상 코드
- `hobot/service/graph/scheduler/weekly_batch.py`
- `hobot/service/graph/news_loader.py`

### 3.5 테스트/운영 검증
- [x] P2 일간 수집 성공률 모니터링 지표 추가
- [x] DART 분기 반영 지연(D+1) 준수 여부 점검 자동화
- [x] 종목코드/기업코드 불일치 케이스 회귀 테스트 구축

## 4. 완료 기준 (DoD)
- KR P2/P3 파이프라인이 일간/분기 운영 주기에서 안정 동작한다.
- `symbol`/`corp_code`/섹터 정합성 리포트가 운영 지표로 제공된다.
- Top 50 리밸런싱과 티어 관리가 스케줄러에서 자동 실행된다.

## 5. 리스크/대응
- 리스크: DART 응답 지연/제한
- 대응: 캐시 + 재시도 + 지연 알림 규칙으로 완화
- 리스크: 종목코드 변경/상장폐지 처리 누락
- 대응: 월간 리밸런싱 시 코드 상태 검증 배치 동시 실행

## 6. Phase 3 인계 항목
- Tier-1 대상 기업 리스트(US/KR) 최신본
- 기업 식별자 매핑 테이블 v1
- P2/P3 파이프라인 SLA 기초 리포트

## 7. 다음 작업 우선순위 (실행 기준)
1. P2 일간 수집 성공률 모니터링 지표 추가
2. DART 분기 반영 지연(D+1) 준수 여부 점검 자동화
3. Top50 월간 스냅샷 결과 알림 연동(예: Slack)은 보류

정책 메모 (2026-02-17)
- Top50 월간 스냅샷 Slack 연동은 현재 단계에서 스킵(보류)한다.

진행 현황 업데이트 (2026-02-17, 12차)
- [x] P2 일간 수집 성공률 모니터링 지표 추가
  - 신규 집계 테이블: `macro_collection_run_reports`
    - 키: `report_date + job_code`
    - 누적 항목: `run_count`, `success_run_count`, `failed_run_count`, `success_count`, `failure_count`
    - 최근 상태: `last_success_rate_pct`, `last_status`, `last_error`, `last_run_*`, `details_json`
  - 스케줄 실행 리포트 기록 경로 추가
    - `run_kr_top50_earnings_hotpath_from_env()` -> `KR_TOP50_EARNINGS_WATCH`
    - `run_us_top50_earnings_hotpath_from_env()` -> `US_TOP50_EARNINGS_WATCH`
  - `/admin/indicators` 상태 코드 확장
    - `KR_TOP50_EARNINGS_WATCH_SUCCESS_RATE`
    - `US_TOP50_EARNINGS_WATCH_SUCCESS_RATE`
  - health note에 일간 실행 횟수/성공·실패 실행 수/요청 성공 건수/최근 오류 표시
  - 테스트 추가
    - `test_scheduler_kr_top50_earnings.py` (성공/실패 리포트 기록)
    - `test_scheduler_us_top50_earnings.py` (성공/실패 리포트 기록)
    - `test_indicator_health.py` (신규 코드 노출 + note 포맷)

진행 현황 업데이트 (2026-02-17, 13차)
- [x] DART 분기 반영 지연(D+1) 준수 여부 점검 자동화
  - 신규 리포트 테이블: `kr_dart_dplus1_sla_reports`
    - 키: `report_date + market + top_limit + lookback_days`
    - 핵심 지표: `checked_event_count`, `met_sla_count`, `violated_sla_count`, `missing_financial_count`, `late_financial_count`
  - 신규 점검 경로:
    - `KRCorporateCollector.validate_dart_disclosure_dplus1_sla(...)`
    - `scheduler.validate_kr_dart_disclosure_dplus1_sla(...)`
    - `scheduler.validate_kr_dart_disclosure_dplus1_sla_from_env()`
  - 신규 스케줄러:
    - `setup_kr_dart_dplus1_sla_scheduler()` (기본 매일 06:25)
  - 환경변수:
    - `KR_DART_DPLUS1_SLA_ENABLED` (기본 1)
    - `KR_DART_DPLUS1_SLA_SCHEDULE_TIME` (기본 06:25)
    - `KR_DART_DPLUS1_SLA_MARKET` (기본 KOSPI)
    - `KR_DART_DPLUS1_SLA_TOP_LIMIT` (기본 50)
    - `KR_DART_DPLUS1_SLA_LOOKBACK_DAYS` (기본 30)
    - `KR_DART_DPLUS1_SLA_PERSIST` (기본 1)
  - `/admin/indicators` 상태 코드 확장:
    - `KR_DART_DPLUS1_SLA` (위반 건수 + 점검 요약 note 표시)
  - 테스트 추가:
    - `test_scheduler_kr_dart_dplus1_sla.py`
    - `test_indicator_health.py` (D+1 SLA note 포맷 검증)

진행 현황 업데이트 (2026-02-18, 14차)
- [x] 종목코드/기업코드 매핑 검증 회귀 테스트 보강 완료
  - `test_kr_corporate_collector.py`
    - `validate_top50_corp_code_mapping` 이슈 케이스(누락/불일치/중복) 회귀 검증 추가
  - `test_scheduler_kr_corp_code_mapping_validation.py`
    - 스케줄러-수집기 인자 전달/환경변수 파싱 검증 유지 확인
- [x] D+1 `no_events` 원인 점검 및 커버리지 보강 완료
  - 원인: Top50 대상 기간에 `is_earnings_event=1` 공시가 없어 `checked_event_count=0` 발생
  - 보강:
    - D+1 점검 시 `event_type=periodic_report` 또는 `분기/반기/사업보고서`까지 점검 대상 포함
    - 공시가 비어있을 때 `only_earnings=False` 하이드레이션 수행 후 재조회
    - 환경변수 확장:
      - `KR_DART_DPLUS1_SLA_HYDRATE_IF_EMPTY` (기본 1)
      - `KR_DART_DPLUS1_SLA_HYDRATE_PAGES` (기본 2)
      - `KR_DART_DPLUS1_SLA_HYDRATE_PAGE_COUNT` (기본 100)
  - 테스트:
    - `test_kr_corporate_collector.py`
      - 하이드레이션 + 주기보고서 포함 시나리오 추가
    - `test_scheduler_kr_dart_dplus1_sla.py`
      - 신규 하이드레이션 환경변수 전달 검증 추가
  - 검증 실행:
    - 단위 테스트 30건 통과 (`unittest`)
    - 실DB 스모크(2026-02-18):
      - 기본 lookback(30일): `status=no_events`, `hydrate_attempted=true` 확인
      - 확장 lookback(120일): `checked_event_count=49`로 점검 경로 동작 확인

## 8. 운영 범위 정책 (2026-02-16)
- KR 기업 질의 데이터 범위는 Top50 고정 스냅샷으로 제한한다.
- Top50 외 기업 질의는 “현재 수집 범위(Top50) 밖으로 데이터 미보유” 정책으로 응답한다.
- 온디맨드 수집 구현은 보류하며, 별도 승인 시점에 재개한다.
