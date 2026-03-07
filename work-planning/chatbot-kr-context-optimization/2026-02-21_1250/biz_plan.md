# KR 질문 컨텍스트 최적화 + 미국 08:30 브리핑 재사용

## 목표
- 한국 부동산/경제/주가 질의에서 불필요한 글로벌 컨텍스트 과다 주입을 줄인다.
- 미국 참조가 필요한 경우, 매일 08:30 미국 거시경제 분석 요약을 우선 참조한다.

## 작업 범위
1. GraphRAG Context 스코프 기본값 보정
- `real_estate_detail` 및 KR 힌트 질의에서 `country_code=KR` 기본 적용
- `us_single_stock` 기본 `US` 정책은 유지

2. Supervisor 프롬프트 컨텍스트 최적화
- KR 스코프 질의에 한해 이벤트/지표/스토리/링크 프롬프트 주입량 축소

3. 미국 08:30 브리핑 재사용
- `ai_strategy_decisions`에서 as_of_date 기준 최신 분석 요약을 로드
- 프롬프트에 `[USMacroReference0830]` 블록으로 주입
- structured citation / context_meta / raw_model_output에 추적 정보 기록

4. 테스트
- `test_phase_d_context_api.py`: KR 기본 스코프 회귀 테스트 추가
- `test_phase_d_response_generator.py`: 08:30 브리핑 주입 테스트 추가

## 검증 기준
- KR 부동산 질의의 `resolved_country_code`가 KR로 고정되는지
- 프롬프트에 `USMacroReference0830`가 주입되는지
- 기존 Phase D 단위테스트가 통과하는지
