# 14) plan.md 반영: GeneralKnowledge Agent (phase + mermaid)

## 요청
- `plan.md`에 방금 구현한 일반 질의 경로를 반영.
- phase 현황과 mermaid 차트에도 포함.

## 반영 내용
1. 아키텍처 mermaid 갱신
   - `GeneralKnowledge Agent` 노드 추가.
   - `Supervisor -> GeneralKnowledge Agent` 경로 추가.
   - `GeneralKnowledge Agent -> Gemini-3-Flash-Preview` direct LLM 경로 추가.
2. Phase 현황 갱신
   - Phase 2 현재 상태에 `llm_direct(general_knowledge)` 분기 연결 완료 반영.
   - Phase 2 상세 섹션에 진행 현황 문구 추가.
3. 완료 작업(13.2) 갱신
   - `Phase 2 3차 착수 완료` 항목 추가(라우팅/실행/테스트/로그 포함).
4. Agent phase 매핑(13.10) 갱신
   - `Supervisor Agent`에 `llm_direct` 분기 반영.
   - `GeneralKnowledge Agent` 행 추가.
5. Agent 상세 백로그(13.11) 갱신
   - `GeneralKnowledge Agent` 항목 신규 추가(Phase 2/3/4 + 테스트).

## 영향
- 문서와 실제 구현 상태의 정합성이 개선됨.
- 일반 질의 처리 경로(내부 DB 미조회 + flash 모델 direct 응답)가 계획서에 명시됨.
