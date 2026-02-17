# Phase 1 Data Dictionary v1

작성일: 2026-02-15  
적용 범위: US/KR Macro Graph + KR Real Estate

## 1. Canonical 식별자 사전
| 필드 | 타입 | Canonical 규칙 | 예시 | 비고 |
| :--- | :--- | :--- | :--- | :--- |
| `country_code` | string(2~8) | ISO 3166-1 alpha-2 우선 (`US`, `KR`), 특수값 `GLOBAL`, `EU` 허용 | `US`, `KR`, `GLOBAL` | Graph/QA 필터 기준 키 |
| `symbol` | string | 국가별 거래소 표준 종목코드 | `AAPL`, `005930` | Company PK 일부 (`country_code`, `symbol`) |
| `corp_code` | string | KR 기업 고유 식별(공시 연계) | `00126380` | KR 위주 사용 |
| `dart_code` | string | Open DART 식별 코드 | `00126380` | `corp_code`와 동일값 사용 가능 |
| `region_code` | string(10) | KR 지역 Canonical은 법정동 10자리 | `1168010100` | 부동산 도메인 핵심 키 |

## 2. 국가 코드 정규화 규칙
- 입력이 국가명(`United States`, `South Korea`)이면 `country_code`로 변환 저장
- 원문 문자열은 `country_raw` 또는 legacy `country`에 보존
- 쿼리는 `country_code` 우선, legacy `country` fallback 허용
- 스코프 제한(Phase 1 기준): `country_code IN ('US', 'KR')`
- `GLOBAL`, `EU`는 보조 분석용으로만 허용하고 트레이딩 의사결정 경로에는 사용 금지

## 3. 회사 식별 규칙 (Company)
- Primary Key: `(country_code, symbol)`
- KR 기업은 `corp_code`/`dart_code`를 필수 보조키로 저장
- US 기업은 `symbol` 중심, 필요시 `isin` 보조 저장
- 동일 기업 다국어 표기는 Alias 테이블로 분리

## 4. KR 부동산 지역 Canonical 규칙
- Canonical 지역 키는 `legal_dong_code_10` (법정동 10자리)
- 행정동/민간 코드 질의는 `RegionAlias -> RealEstateRegion` 매핑 후 확장 조회
- 지역 계층 필드
  - `sido_code` (2자리)
  - `sigungu_code` (5자리)
  - `legal_dong_code_10` (10자리)
- 질의 입력 예시
  - 입력: `판교동(행정동)`
  - 확장: 대응되는 법정동 코드 집합 조회 후 병합 집계

## 5. Alias 모델 초안
### 5.1 CompanyAlias
| 필드 | 타입 | 설명 |
| :--- | :--- | :--- |
| `alias_id` | string | alias 레코드 ID |
| `country_code` | string | `US`/`KR` |
| `symbol` | string | Canonical 종목코드 |
| `alias` | string | 별칭 원문 |
| `alias_lang` | string | `en`, `ko` |
| `alias_type` | string | `official`, `common`, `ticker`, `legacy` |
| `confidence` | float | 0~1 매핑 신뢰도 |

- 규칙
  - 하나의 alias는 1개 canonical 회사로만 매핑
  - 충돌 alias는 `confidence` 우선 + 수동 승인 플래그 필요

### 5.2 RegionAlias
| 필드 | 타입 | 설명 |
| :--- | :--- | :--- |
| `alias_id` | string | alias 레코드 ID |
| `region_code` | string | Canonical 법정동 10자리 |
| `alias` | string | 지역명/기관코드 별칭 |
| `alias_type` | string | `legal_name`, `admin_name`, `agency_code`, `legacy` |
| `source` | string | 매핑 출처 |
| `confidence` | float | 0~1 매핑 신뢰도 |

- 규칙
  - `alias_type=admin_name`은 1:N 매핑 허용 (행정동 -> 복수 법정동)
  - 1:N 매핑은 질의 시 집합 확장 규칙을 통해 병합

## 6. 저장/검증 규칙
- 수집 단계에서 정규화 실패 시 `country_code=NULL` 허용, `normalization_error` 기록
- QA/리포트 단계에서 `country_code IS NULL` 건수를 누락률로 추적
- `country_code`와 `country` 불일치 시 품질 경고(`country_mismatch`)로 분류
- 새 코드 체계 도입 시 사전 문서(versioned) 우선 업데이트

## 7. 버전 정책
- 문서 버전: `v1.0`
- 변경 조건
  - 식별자 추가/타입 변경
  - Canonical 규칙 변경
  - Alias 충돌 해결 정책 변경
- 변경 시 영향 범위(수집기/그래프/QA/리포트)와 마이그레이션 노트를 함께 기록
