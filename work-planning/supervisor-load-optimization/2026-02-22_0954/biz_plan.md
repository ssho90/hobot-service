# Supervisor 부하 최적화 계획

## 목표
- `supervisor_agent` 입력 프롬프트 토큰 과다 문제를 완화한다.
- 전문 에이전트 결과를 우선 활용하는 "병합 중심" 구조로 전환한다.
- 한국 부동산 질의에서 과도한 글로벌 컨텍스트 주입을 줄인다.

## 작업 범위
1. 프롬프트 경량화
- RoutingDecision를 축약 형태로 주입
- GraphContext 링크/증거 텍스트 길이 축소
- StructuredDataContext를 요약본으로 주입
- 프롬프트 예산(토큰 추정) 초과 시 단계적 축소

2. 조건부 병렬 보수화
- `real_estate_detail` 기본 전략을 `sql_need=true`, `graph_need=false`로 조정
- 필요 시에만 그래프 확장

3. 컨텍스트 조회량 축소
- `graph_need=false` 시 context 조회 top-k를 자동 축소
- `real_estate_detail`에서 그래프 비필수일 때 조회량 추가 축소

4. 검증
- 단위 테스트 실행
- 회귀 실패 여부 확인

## 산출물
- `/Users/ssho/project/hobot-service/hobot/service/graph/rag/response_generator.py`
- 관련 테스트 결과 로그
