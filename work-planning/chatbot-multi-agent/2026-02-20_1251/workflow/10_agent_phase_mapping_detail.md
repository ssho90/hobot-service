# 10_agent_phase_mapping_detail

## 요청
- "각 agent를 만드는 단계가 각 phase에 녹아있는지"를 명확히 하고, 부족하면 plan에 추가.

## 반영 파일
- `/Users/ssho/project/hobot-service/work-planning/chatbot-multi-agent/2026-02-20_1251/plan.md`

## 반영 내용
1. `13.10 Agent 생성 단계 매핑 (Phase 반영 명시)` 추가
- Supervisor/Macro/Equity/RealEstate/Ontology를 Phase 2~6별로 매핑.
- 각 agent의 현재 상태(부분 완료/미착수) 명시.

2. `13.11 Agent별 상세 구현 백로그 (파일/테스트 단위)` 추가
- 각 agent별로 파일 경로(기존/신규 예정), Phase별 구현 작업, 테스트 파일 계획을 명시.

3. `13.12 Agent 생성 완료 정의 (공통 DoD)` 추가
- 엔트리 함수/계약/로그/회귀 통과 기준을 공통 완료 정의로 고정.

## 핵심 변화
- 기존에는 agent 생성이 Phase에 암묵적으로 분산되어 있었음.
- 현재는 "어느 Phase에서 어떤 agent를 어떤 파일로 만든다"가 명시적으로 추적 가능해짐.
