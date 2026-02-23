# [Phase 5] 정량적 KPI 검증 및 로컬 모의 테스트

## 1. 개요
* 앞서 `response_generator.py`에 적용한 도메인 에이전트 다이어트 프롬프트(`_build_agent_execution_prompt`) 및 재시도(Retry)/안전장치(Fallback) 로직을 평가합니다.
* 파이썬 스크립트(`test_fallback_parser.py`)를 만들어 정상적인 LLM JSON 반환, 에러 발생 시 빈 JSON (Fallback) 반환 등을 검사합니다.

## 2. 시뮬레이션 항목
1. **정상 파싱 테스트**: 올바른 JSON 문자열이 들어왔을 때, Pydantic 형태(Dict)로 정확히 변환되어 모든 필수 키(`primary_trend`, `confidence_score` 등)가 채워지는지 확인.
2. **에러(Fallback) 파싱 테스트**: LLM이 비정상적인 데이터(깨진 JSON, None 등)를 뱉었을 때 `Exception`이 전파되지 않고 지정된 규격의 Empty JSON 세트를 반환하는지 테스트.
3. **토큰 추정**: 새로운 `DomainInsights` 구조체를 사용할 경우, 기존에 길었던 Markdown 대비 Token 길이가 얼마나 감소하는지 비교 점검.

## 3. 진행
* 테스트용 스크립트 작성 및 런타임 검증을 시작합니다.
