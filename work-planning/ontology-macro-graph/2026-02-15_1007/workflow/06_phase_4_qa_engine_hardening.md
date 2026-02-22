# Phase 4 상세 계획: QA 엔진 고도화

## 1. 목표
- US/KR 단일국가/비교/전이 경로/KR 부동산 질의를 표준 스키마로 처리한다.
- 근거 인용과 불확실성 표기를 강제해 환각 리스크를 낮춘다.
- 데이터 부재 시 C안(선응답 + 수집 안내 + 후속 보강) 정책을 제품 동작으로 고정한다.

## 2. 기간
- 권장 기간: 2026-04-27 ~ 2026-05-15 (2~3주)

## 3. 작업 스트림
### 3.1 질의 스키마/파서 확장
- [x] `country in {US, KR, US-KR}`, `compare_mode`, `region_code`, `property_type` 파싱 구현
- [x] 행정동 질의를 법정동 코드 집합으로 확장하는 규칙 적용
- [x] 질의 타입별 라우팅(단일국가/비교/전이/부동산) 구현

예상 대상 코드
- `hobot/service/graph/rag/context_api.py`
- `hobot/service/graph/rag/response_generator.py`

### 3.2 답변 템플릿/가드레일
- [x] 미국-한국 비교 템플릿 구현
- [x] KR 부동산 지역/유형 템플릿 구현
- [x] 추천/타이밍 질문은 조건형 시나리오 출력으로 강제

### 3.3 근거 인용/검증 파이프라인
- [x] 답변별 근거 3~10개 인용 강제
- [x] 근거 없는 문장 필터링 규칙 구현
- [x] 확신도(High/Medium/Low + score) 산출 로직 연결

예상 대상 코드
- `hobot/service/graph/rag/response_generator.py`
- `hobot/service/graph/impact/quality_metrics.py`

### 3.4 데이터 부재 대응 정책(C안)
- [x] `data_freshness`, `collection_eta_minutes`, `used_evidence_count` 응답 필드 추가
- [보류] 온디맨드 수집 상태와 QA 응답 연결
- [x] 수집 완료 전 C안 가드레일(선응답 + 수집 안내) 동작 구현
- [x] Top50 범위 외 질의에 대해 “현재 수집 범위 밖 데이터 미보유” 응답 템플릿 고정

### 3.5 필수 질문 6개 JSON 스키마 검증기
- [x] Q1~Q6 답변 형식 검증기 구현
- [x] 필수 필드/타입/가드레일 자동 검증
- [x] 회귀 테스트에 스키마 검증 단계 추가

예상 대상 테스트
- `hobot/tests/test_phase_d_response_generator.py`
- `hobot/tests/test_phase_d_context_api.py`

## 4. 완료 기준 (DoD)
- Q1~Q6 질의가 표준 JSON 스키마를 만족하고 근거 인용이 누락되지 않는다.
- 데이터 부족 상황에서도 C안 정책에 따라 사용자가 즉시 상태를 이해할 수 있다.
- US-KR 비교 질의 P95 응답시간 목표(<8초) 측정이 가능해진다.

## 5. 리스크/대응
- 리스크: 템플릿 고정으로 답변 유연성 저하
- 대응: 템플릿은 필수 메타만 강제하고 본문은 유연 생성 허용
- 리스크: 근거 인용 강제로 응답 지연 증가
- 대응: 후보 회수 단계에서 우선순위 캐시/인덱스 최적화 병행

## 6. Phase 5 인계 항목
- Q1~Q6 회귀 테스트 결과 리포트
- QA 응답 메타 필드 관측 대시보드 샘플
- 지연 구간 프로파일링 결과

---

## 진행 현황 업데이트 (2026-02-18, 1차)
- [x] QA 응답 메타 필드 확장
  - 구현 파일:
    - `hobot/service/graph/rag/response_generator.py`
  - 반영 항목:
    - `GraphRagAnswerResponse`에 `data_freshness`, `collection_eta_minutes`, `used_evidence_count` 추가
    - `context_meta`에도 동일 메타 반영
- [x] C안 데이터 부재 가드레일 적용
  - 근거(citation) 0건 시 결론/불확실성/핵심포인트를 C안 템플릿으로 강제
  - 기본 ETA: `GRAPH_RAG_COLLECTION_ETA_MINUTES` (기본 120분)
- [x] 데이터 신선도 산출 로직 추가
  - citation `published_at` 기반 신선도 판정(`fresh/warning/stale/missing/unknown`)
  - 임계치 env:
    - `GRAPH_RAG_DATA_FRESHNESS_WARN_HOURS` (기본 72)
    - `GRAPH_RAG_DATA_FRESHNESS_FAIL_HOURS` (기본 168)
- [x] 테스트 추가/갱신
  - `hobot/tests/test_phase_d_response_generator.py`
    - 응답 메타 필드 존재 검증
    - 무근거 질의 시 C안 가드레일 동작 검증
  - 실행 결과:
    - `test_phase_d_response_generator`: `Ran 9 tests ... OK`
    - `test_phase_d_context_api`: `Ran 8 tests ... OK`

## 진행 현황 업데이트 (2026-02-18, 2차)
- [x] 근거 인용 수 강제(3~10) 구현
  - 구현 파일:
    - `hobot/service/graph/rag/response_generator.py`
  - 반영 항목:
    - `GRAPH_RAG_MIN_CITATIONS`(기본 3), `GRAPH_RAG_MAX_CITATIONS`(기본 10) 도입
    - LLM 인용이 부족한 경우 컨텍스트 근거를 보강해 최소 근거 수 충족 시도
    - 최종 인용 목록을 최대 근거 수로 제한
- [x] 근거 없는 문장 필터링 + 확신도 산출 로직 연결
  - 반영 항목:
    - 핵심 포인트(`key_points`)에 대해 근거 토큰 매칭 기반 필터 적용
    - 문장 필터 통계(`statement_filter`)를 `context_meta`와 분석 실행 메타에 저장
    - 근거수/신선도/근거 매칭률 기반 `confidence(level, score)` 산출
- [x] Q1~Q6 스키마 검증기 구현 및 회귀 테스트 반영
  - 반영 항목:
    - `question_id`(선택) 지원 + 질의 텍스트 기반 Q1~Q6 식별
    - `required_question_schema` 생성 및 `required_question_schema_validation` 자동 검증
    - 직접 매수/매도 지시 문구 감지 시 가드레일 검증 실패 처리
  - 테스트:
    - `hobot/tests/test_phase_d_response_generator.py`
      - Q1 스키마 검증 성공 케이스 추가
      - Q6 직접 매수/매도 지시 검증 실패 케이스 추가
      - 근거 없는 핵심 포인트 제거 통계 검증 추가
    - 실행 결과:
      - `test_phase_d_response_generator`: `Ran 12 tests ... OK`
    - `test_phase_d_context_api`: `Ran 8 tests ... OK`

## 진행 현황 업데이트 (2026-02-18, 3차)
- [x] 챗봇 질의 멀티 에이전트 라우팅(초기 버전) 적용
  - 구현 파일:
    - `hobot/service/graph/rag/response_generator.py`
  - 반영 항목:
    - `question_id_agent`(명시 Q1~Q6), `keyword_agent`, `scope_agent` 3개 에이전트 점수 합산 라우터 추가
    - 경량 LLM 라우터 에이전트(`llm_router_agent`) 추가: `gemini-3-flash-preview` 사용
    - 라우팅 결과(`selected_type`, `selected_question_id`, `confidence_level`)를 `query_route` 메타로 저장
    - 라우팅 결과를 Prompt에 주입해 질의 타입별 응답 가이던스 적용
    - 기존 검증기(Q1~Q6 스키마 검증)와 라우터 연결
- [x] 회귀 테스트 확장
  - `hobot/tests/test_phase_d_response_generator.py`
    - 명시 question_id 우선 라우팅 검증
    - 질의 텍스트 기반 자동 분류(compare_outlook/Q2) 검증

## 진행 현황 업데이트 (2026-02-18, 4차)
- [x] 질의 스키마/파서 확장(1차)
  - 구현 파일:
    - `hobot/service/graph/rag/context_api.py`
    - `hobot/service/graph/rag/response_generator.py`
  - 반영 항목:
    - `GraphRagContextRequest` / `GraphRagAnswerRequest`에 `compare_mode`, `region_code`, `property_type` 필드 추가
    - `country_code=US-KR` 스코프 허용 및 컨텍스트 쿼리에서 `country_codes=['US','KR']`로 필터 확장
    - 질의 텍스트 기반 `parsed_scope(compare_mode, region_code, property_type)` 자동 파싱 추가
    - `required_question_schema.scope`에 `region_code`, `property_type` 반영
- [x] 테스트 보강
  - `hobot/tests/test_phase_d_context_api.py`
    - `US-KR` 스코프 확장 파라미터 검증
    - 파서(`compare_mode/region_code/property_type`) 결과 검증
  - `hobot/tests/test_phase_d_response_generator.py`
    - `to_context_request` 필드 전달 검증
    - `US-KR` 스코프 허용 검증

## 진행 현황 업데이트 (2026-02-18, 5차)
- [x] 행정동 질의 → 법정동 코드(앞 5자리 LAWD_CD) 집합 확장 규칙 적용
  - 구현 파일:
    - `hobot/service/graph/rag/kr_region_scope.py`
    - `hobot/service/graph/rag/context_api.py`
  - 반영 항목:
    - 한국 지역명/행정구역명(예: 서울, 서울 강남구, 성남시, 수원시)을 LAWD 코드 집합으로 해석하는 규칙 추가
    - 질의 텍스트에서 부동산 문맥일 때 지역 표현을 자동 인식해 `parsed_scope.region_code`를 코드 CSV로 정규화
    - `parsed_scope.region_group_count` 추가로 단일 지역 집합 vs 복수 지역 비교를 구분
    - `compare_mode` 자동 판정에서 `region_group_count`를 사용해 지역 비교 판정 정확도 개선
- [x] 테스트 보강
  - `hobot/tests/test_phase_d_context_api.py`
    - 서울 질의 시 코드 집합 파싱 검증
    - 성남시/수원시 질의 시 다중 코드 확장 및 `region_compare` 판정 검증
  - 실행 결과:
    - `tests/test_phase_d_context_api.py`: `Ran 11 tests ... OK`
    - `tests/test_phase_d_response_generator.py`: `Ran 16 tests ... OK`

## 진행 현황 업데이트 (2026-02-18, 6차)
- [x] 답변 템플릿/가드레일(3.2) 구현
  - 구현 파일:
    - `hobot/service/graph/rag/response_generator.py`
  - 반영 항목:
    - 라우팅 가이던스 강화:
      - US-KR 비교 질의 시 `US-KR 비교 템플릿` 지시를 프롬프트에 추가
      - KR 부동산 질의 시 `지역/유형` 컨텍스트를 포함한 템플릿 지시를 프롬프트에 추가
    - 추천/타이밍 질의 조건형 시나리오 강제:
      - `sector_recommendation`/`timing_scenario`(Q4/Q6) 질의에서 base/bull/bear 시나리오 중심 핵심 포인트로 보정
      - 직접 매수/매도 표현은 후처리에서 중립 표현으로 정규화
      - 메타 필드 `conditional_scenario_enforced` 추가
- [x] 테스트 보강
  - `hobot/tests/test_phase_d_response_generator.py`
    - US-KR 비교 템플릿 가이던스 프롬프트 포함 검증
    - KR 부동산 템플릿 가이던스 프롬프트 포함 검증
    - Q6 직접 매수/매도 문구 입력 시 조건형 시나리오 보정 검증

## 진행 현황 업데이트 (2026-02-19, 7차)
- [x] US 개별종목 질의 전용 라우트(`us_single_stock`) 추가
  - 구현 파일:
    - `hobot/service/graph/rag/response_generator.py`
  - 반영 항목:
    - 회사명/티커 감지 시 `us_single_stock_agent`가 `us_single_stock` 라우트를 강제
    - 감지 규칙: 회사명 힌트 사전 + 티커 패턴 + (가능 시) `corporate_entity_registry/aliases` 조회
    - 복수 종목 감지 시 강제 라우팅을 적용하지 않고 기존 비교 라우트 유지
    - `question_id` 명시 시 기존 우선순위(명시 라우트) 유지
    - 라우팅 가이던스에 US 개별종목 지시(종목 직접 근거 우선, 근거 부족 명시) 추가
- [x] 테스트 보강
  - `hobot/tests/test_phase_d_response_generator.py`
    - 회사명 기반 강제 라우팅 검증: `"팔란티어 주가 어때?" -> us_single_stock`
    - 티커 기반 강제 라우팅 검증: `"PLTR 주가 어때?" -> us_single_stock`
    - 기존 비교 질의 회귀 검증 유지: `"스노우플레이크와 팔란티어..." -> compare_outlook`
  - 실행 결과:
    - `tests/test_phase_d_response_generator.py`: `Ran 20 tests ... OK`

## 진행 현황 업데이트 (2026-02-19, 8차)
- [x] `us_single_stock` 라우트용 종목 포커스 컨텍스트 리트리벌 추가
  - 구현 파일:
    - `hobot/service/graph/rag/context_api.py`
  - 반영 항목:
    - `GraphRagContextRequest`에 `route_type`, `focus_symbols`, `focus_companies` 입력 필드 확장
    - `us_single_stock` 라우트에서만 동작하는 종목 전용 문서 조회 쿼리(`phase_d_documents_for_us_single_stock`) 추가
    - 종목 매칭 점수(`stock_focus_score`)를 하이브리드 병합 점수에 반영
    - 리트리벌 메타에 `stock_focus_docs`, `weights.stock_focus` 추가
    - `parsed_scope`/`meta`에 라우트/포커스 심볼 정보 반영
- [x] 테스트 보강
  - `hobot/tests/test_phase_d_context_api.py`
    - `phase_d_documents_for_us_single_stock` 스텁 응답 추가
    - `us_single_stock` 라우트 입력 시 종목 문서 포함/쿼리 호출 검증 추가
  - 실행 결과:
    - `tests/test_phase_d_context_api.py`: `Ran 12 tests ... OK`
    - `tests/test_phase_d_response_generator.py`: `Ran 20 tests ... OK`

## 진행 현황 업데이트 (2026-02-19, 9차)
- [x] `us_single_stock` 답변 템플릿 강제(가격/변동률/실적/밸류/리스크)
  - 구현 파일:
    - `hobot/service/graph/rag/response_generator.py`
  - 반영 항목:
    - `US_SINGLE_STOCK_TEMPLATE_SPECS` 기반 섹션 템플릿 정의
    - 라우트 후처리 `_enforce_us_single_stock_template_output` 추가
      - 각 섹션은 인용 근거 텍스트에서 우선 추출
      - 근거가 없으면 섹션별 `근거 불충분` 문구로 보강
    - 프롬프트 라우팅 가이던스 강화:
      - `key_points`에 4개 라벨 섹션을 반드시 포함하도록 지시
    - 응답 메타 확장:
      - `us_single_stock_template_enforced`
      - `us_single_stock_missing_sections`
- [x] 테스트 보강
  - `hobot/tests/test_phase_d_response_generator.py`
    - 회사명 감지 케이스(`팔란티어`)에서
      - 템플릿 프롬프트 문구 포함 검증
      - `key_points` 4개 라벨 섹션 강제 검증
      - 템플릿 적용 메타 플래그 검증
  - 실행 결과:
    - `tests/test_phase_d_response_generator.py`: `Ran 20 tests ... OK`
    - `tests/test_phase_d_context_api.py`: `Ran 12 tests ... OK`

## 진행 현황 업데이트 (2026-02-19, 10차)
- [x] US 개별종목 스모크 테스트(PLTR/NVDA/AAPL) 추가
  - 구현 파일:
    - `hobot/tests/test_phase_d_response_generator.py`
  - 반영 항목:
    - 티커 루프 기반 스모크 테스트 추가:
      - `PLTR`, `NVDA`, `AAPL` 질의에서 `us_single_stock` 라우트 유지 검증
      - 4개 섹션 템플릿 적용 및 누락 섹션 없음 검증
- [x] `가격/변동률` 섹션 수치 근거 우선 로직 보강
  - 구현 파일:
    - `hobot/service/graph/rag/response_generator.py`
  - 반영 항목:
    - 종목 포커스 용어(`matched_symbols`, `matched_companies`) 추출 로직 추가
    - 근거 문장 점수화 로직 추가(심볼/회사명 매칭, `%`/`$` 수치 신호, 가격 동사)
    - `가격/변동률` 섹션은 수치 신호가 있는 문장만 후보로 채택
    - 수치 우선 선택 회귀 테스트 추가(`7.2%` 문장 선택)
  - 실행 결과:
    - `tests/test_phase_d_response_generator.py`: `Ran 22 tests ... OK`
    - `tests/test_phase_d_context_api.py`: `Ran 12 tests ... OK`
