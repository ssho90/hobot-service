# Phase 0 상세 계획: US Focus 안정화

## 1. 목표
- 트레이딩 의사결정 경로를 `US equities first`로 강제한다.
- 트레이딩 엔진(US 제한)과 QA 챗봇(US/KR 확장)의 진입점 경계를 코드/운영 정책으로 분리한다.
- 국가 필터 혼용(`country` vs `country_code`) 리스크를 즉시 식별한다.

## 2. 기간
- 권장 기간: 2026-02-16 ~ 2026-02-18 (3일)

## 3. 작업 스트림
### 3.1 진입점 경계 하드닝
- [x] 트레이딩 경로 입력 국가 제한 확인 및 강제 (`US`만 허용)
- [x] 챗봇 분석 결과가 트레이딩 엔진에 자동 유입되지 않도록 차단 플래그 적용
- [x] 운영 환경에서 경로별 스코프 로그 필드(`scope_version`, `country_code`) 표준화

예상 대상 코드
- `hobot/service/macro_trading/ai_strategist.py`
- `hobot/service/strategy_manager.py`
- `hobot/service/graph/strategy/decision_mirror.py`

### 3.2 국가 필터 긴급 점검
- [x] `country` 사용처 전수 스캔
- [x] `country_code` 표준화 필요 항목 목록화
- [x] Phase 1 마이그레이션 입력용 이슈 백로그 작성

예상 산출물
- `work-planning/ontology-macro-graph/2026-02-15_1007/workflow/phase0_country_filter_audit.md`

### 3.3 스모크 테스트/회귀 보호선
- [x] US 트레이딩 시나리오 정상 동작 확인
- [x] KR 질의가 챗봇에서만 처리되는지 확인
- [x] 스코프 충돌(US 제한 정책이 QA 응답을 잘못 제한하는 문제) 회귀 테스트 추가

예상 대상 테스트
- `hobot/service/macro_trading/tests/test_graph_context_provider_filters.py`
- `hobot/tests/test_phase_d_context_api.py`

## 4. 완료 기준 (DoD)
- 트레이딩 엔진 경로에서 US 외 국가가 입력되면 차단 또는 무시 처리된다.
- 챗봇 경로는 US/KR 질의를 처리하되, 트레이딩 엔진 정책과 분리 동작한다.
- 국가 필터 혼용 목록과 수정 우선순위가 문서화되어 Phase 1 착수 조건을 충족한다.

## 5. Phase 1 인계 항목
- `country`/`country_code` 혼용 파일 리스트
- 스코프 충돌 회귀 테스트 결과
- 경계 규칙 운영 로그 샘플(정상/차단 케이스)

## 6. 진행 로그 (2026-02-15)
- 완료: `ai_strategist.py`에 US scope 강제(`_enforce_trading_news_scope`) 및 스코프 메타 저장 추가
- 완료: `graph_context_provider.py`에 전략 컨텍스트 US 강제(`_enforce_trading_scope_country`) 추가
- 완료: QA/챗봇 payload 자동 유입 차단 플래그(`block_chatbot_auto_ingestion`) 및 경계 가드(`_is_chatbot_analysis_payload`) 추가
- 완료: `phase0_country_filter_audit.md` 생성 및 Phase 1 전환 백로그 정리
- 완료: 단위 테스트 추가
  - `test_enforce_trading_news_scope_filters_non_us_news`
  - `test_enforce_trading_news_scope_sets_default_target_country`
  - `test_is_chatbot_analysis_payload_detects_route`
  - `test_is_chatbot_analysis_payload_detects_qa_shape`
  - `test_enforce_trading_scope_country_forces_us`
  - `test_build_strategy_context_forces_us_even_when_non_us_requested`
  - `test_kr_country_filter_propagates_in_qa_context`
