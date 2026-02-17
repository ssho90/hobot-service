# Phase 2 P4 Real Estate Canonical Schema Spec

작성일: 2026-02-15  
적용 범위: KR 실거래(매매/전세/월세) 수집 파이프라인

## 1. Canonical 필드
| 필드 | 타입 | 설명 | 규칙 |
| :--- | :--- | :--- | :--- |
| `source` | string | 데이터 원천 식별자 | 예: `MOLIT`, `REB`, `KOSIS` |
| `source_record_id` | string | 원천 레코드 고유키 | 원천 ID 없으면 raw payload 해시 |
| `country_code` | string | 국가 코드 | 항상 `KR` |
| `region_code` | string(10) | 지역 코드 | 법정동 10자리 canonical, 5자리 입력은 `00000` 패딩 |
| `property_type` | string | 부동산 유형 | `apartment`, `multi_family`, `officetel`, `single_family`, `unknown` |
| `transaction_type` | string | 거래 유형 | `sale`, `jeonse`, `monthly_rent`, `rent`, `unknown` |
| `contract_date` | date | 계약일 | 원천 날짜 파싱 실패 시 null 허용 |
| `effective_date` | date | 효력일 | 기본값 `contract_date` |
| `published_at` | datetime | 공표/수집 시각 | 없으면 `effective_date 00:00:00` |
| `as_of_date` | date | 조회 기준일 | 적재 실행일 |
| `price` | bigint | 거래가(매매) | canonical 단위는 `원(KRW)` |
| `deposit` | bigint | 보증금(전세/월세) | canonical 단위는 `원(KRW)` |
| `monthly_rent` | bigint | 월세금 | canonical 단위는 `원(KRW)` |
| `area_m2` | decimal | 전용면적(㎡) | 소수 허용 |
| `floor_no` | int | 층수 | null 허용 |
| `build_year` | int | 건축년도 | null 허용 |
| `metadata_json` | json | 원천 raw payload | 디버깅/추적용 보존 |

## 2. 품질 규칙
- `region_code` 미정규화 레코드는 저장하지 않고 `skipped_rows`로 집계
- `source + source_record_id`를 upsert 키로 사용하여 중복 방지
- `transaction_type=unknown`, `property_type=unknown`은 허용하되 모니터링 경고 대상으로 집계
- 가격/면적 파싱 실패는 null 허용, 원문은 `metadata_json`로 보존
- `MOLIT` 금액 필드(`dealAmount` 등)는 만원 단위이므로 적재 시 `*10,000` 환산 후 저장

## 3. 지연/결측 대응
- 실거래 신고 지연 대응: `effective_date`와 `published_at` 분리 저장
- 월 단위 공표 지표(REB/KOSIS) 결합 시 `merge_asof(backward)` 기준으로 daily anchor에 정렬
- 운영 리포트에서 `as_of_date` 기준 freshness/missing-rate와 함께 점검

## 4. 지역 적재 범위 정책 (2026-02-15)
- 기본 적재 범위:
  - 서울: 전 시군구(25개) 전수 적재
  - 경기: 전 시군구 전수 적재
  - 지방: 주요 도시 중심 선별 적재(6대 광역시/세종 + 권역별 핵심 도시)
- 구현 정책 키:
  - `seoul_gyeonggi_all_major_cities` (기본값)
  - `seoul_gyeonggi_all`
  - `major_cities_only`
- 운영 오버라이드:
  - `MOLIT_REGION_SCOPE`: 정책 키 선택
  - `MOLIT_TARGET_LAWD_CODES`: `LAWD_CD` CSV를 직접 지정하면 위 정책보다 우선

## 5. 서빙 집계 테이블 (RDB 상세 + Graph 집계 전략)
- 상세 조회는 `kr_real_estate_transactions`(RDB 원본)에서 처리
- 지역/월 집계는 `kr_real_estate_monthly_summary`를 사용

### 5.1 `kr_real_estate_monthly_summary` 스키마 요약
| 필드 | 타입 | 설명 |
| :--- | :--- | :--- |
| `stat_ym` | char(6) | 집계 월 (`YYYYMM`) |
| `lawd_cd` | char(5) | 시군구 5자리 코드 |
| `property_type` | string | `apartment` 등 |
| `transaction_type` | string | `sale` 등 |
| `tx_count` | int | 월 거래 건수 |
| `avg_price` | decimal | 월 평균 거래가 |
| `avg_price_per_m2` | decimal | 월 평균 ㎡당 거래가 |
| `avg_area_m2` | decimal | 월 평균 전용면적 |
| `min_price` | bigint | 월 최저 거래가 |
| `max_price` | bigint | 월 최고 거래가 |
| `total_price` | bigint | 월 거래가 합계 |
| `as_of_date` | date | 집계 기준일 |

### 5.2 운영 규칙
- 집계 키: `(stat_ym, lawd_cd, property_type, transaction_type)` upsert
- 기본 집계 시나리오: `property_type=apartment`, `transaction_type=sale`
- Graph로 적재 시에는 이 집계 테이블을 source로 사용하고, 원본 건별 row는 Graph에 직접 밀어넣지 않는다.

## 6. Graph 동기화 모델
- 동기화 원천: `kr_real_estate_monthly_summary`
- 동기화 대상:
  - `(:RealEstateRegion {country_code, lawd_cd})`
  - `(:RealEstateMonthlySummary {summary_key})`
  - `(:RealEstateRegion)-[:HAS_MONTHLY_SUMMARY]->(:RealEstateMonthlySummary)`
- `RealEstateMonthlySummary` 주요 속성:
  - `stat_ym`, `obs_date`, `property_type`, `transaction_type`
  - `tx_count`, `avg_price`, `avg_price_per_m2`, `avg_area_m2`
  - `min_price`, `max_price`, `total_price`, `as_of_date`
- 운영 함수:
  - Python loader: `hobot/service/graph/real_estate_loader.py`
  - Scheduler entrypoint: `sync_kr_real_estate_summary_to_graph(...)`

## 7. 조회 API 계약 (RDB 상세 + Graph 집계)
- 라우터: `hobot/service/macro_trading/real_estate_api.py`
- 기본 경로: `/api/macro/real-estate`

### 7.1 Unified 조회
- `GET /api/macro/real-estate`
- 주요 파라미터:
  - `view`: `detail` | `monthly` | `region`
  - `start_ym`, `end_ym`: `YYYYMM`
  - `lawd_codes`: CSV (`11110,41135`)
  - `property_type` (기본 `apartment`)
  - `transaction_type` (기본 `sale`)
  - `limit`, `offset`
- 라우팅 규칙:
  - `detail` -> MySQL `kr_real_estate_transactions`
  - `monthly`/`region` -> Neo4j `RealEstateMonthlySummary`
  - Neo4j 실패 시 MySQL `kr_real_estate_monthly_summary` 자동 폴백 (`fallback_used=true`)

### 7.2 Alias 엔드포인트
- `GET /api/macro/real-estate/detail`
- `GET /api/macro/real-estate/monthly`
- `GET /api/macro/real-estate/regions`

## 8. REB/KOSIS 보조지표 수집 운영 메모
- 구현 위치: `hobot/service/macro_trading/collectors/kr_macro_collector.py`
- 전용 지표 코드:
  - `KR_HOUSE_PRICE_INDEX`
  - `KR_JEONSE_PRICE_RATIO`
  - `KR_UNSOLD_HOUSING`
  - `KR_HOUSING_SUPPLY_APPROVAL`
- 실행 진입점:
  - `collect_kr_real_estate_supplemental_data(days=3650)`
- KOSIS 파라미터 정책:
  - 기본 운영 파라미터는 코드에 내장(키만 있으면 동작)
  - 필요 시 환경변수/JSON으로 override:
    - 예: `KOSIS_KR_HOUSE_PRICE_ORG_ID`, `KOSIS_KR_HOUSE_PRICE_TBL_ID`, `KOSIS_KR_HOUSE_PRICE_ITM_ID`
    - 예: `KOSIS_KR_HOUSE_PRICE_INDEX_PARAMS_JSON='{"objL1":"00"}'`
- 통계 목록(테이블/카테고리) 탐색:
  - `https://kosis.kr/openapi/statisticsList.do?method=getList`
  - 실사용 예: `vwCd=MT_ZTITLE`, `parentListId=I1`
- 미분양(`KR_UNSOLD_HOUSING`) 처리 규칙:
  - `DT_MLTM_2082` 월별 응답에서 `C2_NM='계'` 행만 채택
  - 동일 월의 시도별 값을 합산(sum)해 전국 월별 시계열로 적재
  - 운영 보정:
    - 최소 시작월 `202410`로 clamp (해당 테이블 과거 시작월 조회 시 빈 응답 방지)
    - 최신월 미공표 구간은 `endPrdDe`를 자동으로 과거 월로 후퇴하여 재조회
- 보안 로그 규칙:
  - KOSIS/MOLIT 요청 URL 로그에서 `apiKey`, `serviceKey`는 마스킹(`***REDACTED***`)
