# 06_conditional_parallel_criteria

## 요청
- "조건부 병렬"이 무엇인지 구체 조건을 문서에 명시.

## 반영
- `/Users/ssho/project/hobot-service/work-planning/chatbot-multi-agent/2026-02-20_1251/plan.md`
  - 2.2 섹션에 아래 항목 추가:
    - 조건부 병렬 판정 Truth Table (`SQL 필요`, `Graph 필요`)
    - `SQL 필요=true` 조건
    - `Graph 필요=true` 조건
    - 실제 질의 예시 3건(병렬/SQL 단일/Graph 단일)

## 효과
- Supervisor/에이전트 구현 시 병렬 호출 트리거가 모호하지 않음.
- 운영/디버깅 시 "왜 병렬로 실행됐는지" 설명 가능.
