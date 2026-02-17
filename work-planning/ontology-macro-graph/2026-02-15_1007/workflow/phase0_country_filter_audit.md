# Phase 0 Country Filter Audit

작성일: 2026-02-15  
범위: 트레이딩 경로(`macro_trading`) + 전략 그래프 컨텍스트(`graph/strategy`) + QA 경로(`graph/rag`)

## 1. 결론 요약
- 트레이딩 경로는 Phase 0에서 `US only` 강제가 코드로 반영됨.
- 다만 QA 경로는 현재 `country` 중심 필터가 많아 `country_code` 정규화는 Phase 1에서 필수.
- 수집 레이어(`news_collector`)는 `country` 문자열 기반 저장이 주 경로이므로, `country_code` 병행 저장 설계가 필요.

## 2. Phase 0 반영 사항
### 2.1 트레이딩 경로 US 강제
- `hobot/service/macro_trading/ai_strategist.py`
  - `_enforce_trading_news_scope` 추가: 입력 뉴스에서 비-US/국가 불명 데이터 제거
  - `_is_chatbot_analysis_payload` + `block_chatbot_auto_ingestion` 추가: QA/챗봇 payload 자동 유입 차단
  - `collect_economic_news`, `collect_news_node`, `analyze_and_decide`에 스코프 정규화 연결
  - 저장 메타(`decision_meta`)에 `analysis_route/scope_version/analysis_country_code` 기록
- `hobot/service/graph/strategy/graph_context_provider.py`
  - `_enforce_trading_scope_country` 추가: 전략 컨텍스트 요청 국가를 US로 강제
  - `build_strategy_context`에서 scope 로그 출력

### 2.2 회귀 테스트
- `hobot/service/macro_trading/tests/test_ai_strategist_multi_agent_helpers.py`
  - 트레이딩 뉴스 스코프 강제 테스트 2건 추가
- `hobot/service/macro_trading/tests/test_graph_context_provider_filters.py`
  - 전략 컨텍스트 US 강제 테스트 2건 추가

## 3. 혼용 현황(핵심)
### 3.1 혼용 허용(임시, 전략 컨텍스트)
- `hobot/service/graph/strategy/graph_context_provider.py`
  - 쿼리에서 `country`와 `country_code`를 OR로 병행 사용
  - 목적: 기존 데이터(`country`) 호환 + 신규 데이터(`country_code`) 대응

### 3.2 `country` 단독 의존(우선 전환 대상)
- `hobot/service/graph/rag/context_api.py`
  - 주요 조회 쿼리 다수가 `d.country = $country` 또는 `e.country = $country` 패턴
- `hobot/service/graph/rag/response_generator.py`
  - 컨텍스트/응답 빌드에서 `country` 기반 필터/메타 사용
- `hobot/service/macro_trading/collectors/news_collector.py`
  - 원천 추출/저장이 `country` 문자열 중심

## 4. Phase 1 백로그(우선순위)
1. `graph/rag/context_api.py`  
`country` 입력을 `country_code`로 정규화하고 쿼리를 `country_code` 우선 + `country` 호환으로 이행
2. `graph/rag/response_generator.py`  
응답 메타와 필터에 `country_code` 추가, 내부 조건식을 `country_code` 중심으로 전환
3. `macro_trading/collectors/news_collector.py`  
수집 시점 `country_code` 컬럼 저장(정규화 함수 적용), `country`는 raw 필드로 유지
4. DB/Graph 스키마  
`country_code` 인덱스/제약 추가, `country`는 호환 필드로 단계적 축소

## 5. 리스크 메모
- 트레이딩 경로는 US 고정이므로 즉시 운영 리스크는 낮아졌음.
- QA 경로에서 `country` 문자열 불일치가 남아 있어 US/KR 비교 질의 정확도 편차 가능성이 있음.
