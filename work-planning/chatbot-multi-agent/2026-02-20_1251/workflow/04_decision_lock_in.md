# 04_decision_lock_in

## 배경
사용자가 Multi-Agent 설계의 핵심 의사결정 3건을 확정:
1. 문서 근거(`citations`)와 SQL 정형 근거(`structured_citations`) 분리
2. 종목 식별자 `security_id` 정규키 통합
3. 기본 실행정책을 조건부 병렬로 고정

## 반영 범위
- `/Users/ssho/project/hobot-service/work-planning/chatbot-multi-agent/2026-02-20_1251/plan.md`

## 반영 상세
1. `structured_citations` 도입
- State 계약(2.4)과 응답 계약(8.3)에 `structured_citations[]` 추가.
- Tool 실행 정책(8.4)에 문서/SQL 근거 분리 규칙 추가.

2. `security_id` 통합
- 주식 Neo4j 적재 설계(9.2)에 `security_id = "{country_code}:{native_code}"` 표준 추가.
- 스키마/인덱스 권장안(9.3)에서 `Company(security_id)`, `EquityDailyBar(security_id, trade_date)` 기준으로 정리.

3. 조건부 병렬 정책 고정
- RDB 융합 전략(2.2)을 "항상 병렬" 표현에서 "조건부 병렬"로 수정.
- Tool 정책(8.4)에서 `parallel_tool_calls=True`를 조건 충족 시에만 활성화하도록 명시.

## 후속 구현 체크리스트
- API 스키마: `structured_citations[]` 필드 추가
- 에이전트 출력/저장: 문서 근거와 SQL 근거 분리 저장
- 회귀 테스트: `citations`/`structured_citations` 최소 검증 케이스 추가
