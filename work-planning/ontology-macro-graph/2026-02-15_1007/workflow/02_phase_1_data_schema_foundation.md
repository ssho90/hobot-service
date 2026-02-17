# Phase 1 상세 계획: 데이터/스키마 기반 공사

## 1. 목표
- `country_code`를 Canonical 식별자로 확정하고 데이터/그래프/질의 레이어에 일관 적용한다.
- US/KR 운영 범위를 고정하고 데이터 품질 리포팅 체계를 만든다.
- Phase 2 확장을 위한 코드 사전/스키마/마이그레이션 기반을 완성한다.

## 2. 기간
- 권장 기간: 2026-02-16 ~ 2026-02-27 (2주)

## 3. 작업 스트림
### 3.1 소스 인벤토리/라이선스 매트릭스
- [x] 현재 수집 소스와 후보 소스를 US/KR 기준으로 정리
- [x] 라이선스/비용/갱신주기/장애복구 경로를 표준 항목으로 문서화
- [x] P0~P4 도메인별 1순위/2순위 소스 확정

예상 산출물
- `work-planning/ontology-macro-graph/2026-02-15_1007/workflow/phase1_source_inventory.md`

### 3.2 표준 코드/용어 사전
- [x] `country_code`, `symbol`, `corp_code`, `dart_code`, `region_code` 사전 확정
- [x] KR 부동산 지역 Canonical 규칙(법정동 10자리) 운영 명세 작성
- [x] CompanyAlias/RegionAlias 규칙 초안 작성

예상 산출물
- `work-planning/ontology-macro-graph/2026-02-15_1007/workflow/phase1_data_dictionary.md`

### 3.3 스키마/마이그레이션 설계
- [x] `country` -> `country_code` 전환 설계서 작성
- [x] Neo4j 제약조건/인덱스 변경안 작성
- [x] 백필 실행 순서(배치 단위, 재시도, 롤백 포인트) 정의
- [x] QA GraphRAG 경로 `country_code` 우선 + `country` fallback 1차 전환 적용

예상 대상 코드
- `hobot/service/graph/normalization/country_mapping.py`
- `hobot/service/graph/neo4j_client.py`
- `hobot/service/graph/schemas/extraction_schema.py`

예상 산출물
- `work-planning/ontology-macro-graph/2026-02-15_1007/workflow/phase1_country_code_migration_design.md`

### 3.4 품질 리포트 자동화
- [x] 누락/오분류 국가 데이터 리포트 생성 쿼리 구현
- [x] 주간 품질 스냅샷(매핑 정확도, 누락률) 저장
- [x] QA 경로에서 스코프 위반 데이터 경고 추가
- [x] GraphRAG API 호출 로그에 `country_code` 필드 저장 추가

예상 대상 코드
- `hobot/service/graph/monitoring/graphrag_metrics.py`
- `hobot/service/graph/impact/quality_metrics.py`

### 3.5 테스트/검증
- [x] 국가 필터 정합성 회귀 테스트 추가
- [x] 마이그레이션 전후 샘플 질의 결과 동일성 검증 (legacy `country` vs `country_code` 기본 케이스)
- [x] US/KR 범위 외 입력 차단 테스트 추가

예상 대상 테스트
- `hobot/service/macro_trading/tests/test_graph_context_provider_filters.py`
- `hobot/tests/test_phase_b_dod.py`
- `hobot/tests/test_phase_c_quality_metrics.py`
- `hobot/tests/test_phase_d_context_api.py`
- `hobot/tests/test_phase_d_response_generator.py`
- `hobot/tests/test_phase_d_monitoring.py`

## 4. 완료 기준 (DoD)
- `country_code` 표준화 설계/백필 계획이 승인되고, 파일별 수정 대상이 확정된다.
- 품질 리포트에서 국가 매핑 정확도 기준선(99% 목표 추적)이 측정 가능하다.
- Phase 2 수집기 개발에 필요한 코드 사전/용어 사전이 확정된다.

## 5. 리스크/대응
- 리스크: 기존 `country` 기반 쿼리와 충돌
- 대응: 호환 레이어를 임시 유지하고 점진 전환 일정 운영
- 리스크: 소스별 코드 체계 상이
- 대응: Alias 테이블과 정규화 함수로 단일 Canonical 매핑 강제

## 6. Phase 2 인계 항목
- 확정된 US/KR 지표 최소 세트(국가별 25~35개)
- 표준 코드 매핑 테이블 v1
- 마이그레이션 영향 범위 및 우선순위 리스트

## 7. 진행 로그 (2026-02-15)
- 완료: QA 컨텍스트/응답 경로에서 `country_code` 우선 필터 로직 도입
  - `hobot/service/graph/rag/context_api.py`
  - `hobot/service/graph/rag/response_generator.py`
- 완료: GraphRAG 호출 모니터링 로그에 `country_code` 저장 필드 추가
  - `hobot/service/graph/monitoring/graphrag_metrics.py`
- 완료: 회귀 테스트 보강
  - `hobot/tests/test_phase_d_context_api.py`
  - `hobot/tests/test_phase_d_response_generator.py`
- 완료: 소스 인벤토리/라이선스 매트릭스 문서화
  - `work-planning/ontology-macro-graph/2026-02-15_1007/workflow/phase1_source_inventory.md`
- 완료: 표준 코드/용어 사전 및 Alias 규칙 초안 작성
  - `work-planning/ontology-macro-graph/2026-02-15_1007/workflow/phase1_data_dictionary.md`
- 완료: `country -> country_code` 마이그레이션 설계서/백필/롤백 계획 작성
  - `work-planning/ontology-macro-graph/2026-02-15_1007/workflow/phase1_country_code_migration_design.md`
- 완료: 국가 품질 리포트/주간 스냅샷 자동화 추가
  - `hobot/service/graph/impact/quality_metrics.py`
  - `hobot/service/graph/scheduler/weekly_batch.py`
- 완료: QA 경로 스코프 위반 경고 및 범위 외 입력 차단 가드 추가
  - `hobot/service/graph/rag/context_api.py`
  - `hobot/service/graph/rag/response_generator.py`
- 완료: 스코프 차단/경고 테스트 보강
  - `hobot/tests/test_phase_c_quality_metrics.py`
  - `hobot/tests/test_phase_d_monitoring.py`
  - `hobot/service/macro_trading/tests/test_graph_context_provider_filters.py`
