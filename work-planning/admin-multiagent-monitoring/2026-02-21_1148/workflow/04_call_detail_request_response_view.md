# 04. 호출 상세 Request/Response 확장

- 작업 일시: 2026-02-21
- 목적: Admin Multi-Agent 모니터링의 `호출 상세`에서 각 호출의 LLM request/response 원문을 확인 가능하게 개선.

## 변경 내용
- 대상 파일: `/hobot-ui-v2/src/components/admin/AdminMultiAgentMonitoring.tsx`
- 구현:
  - 호출 행 우측에 `화살표 토글 버튼` + `Detail 버튼` 추가
  - 두 버튼 모두 동일 토글 동작(열기/닫기)
  - 확장 시 하단 행에 `LLM Request`, `LLM Response` 박스 출력
  - 긴 텍스트 스크롤 처리(`max-h`, `overflow-auto`)
  - run 변경/재조회 시 확장 상태 초기화

## 검증
- `cd hobot-ui-v2 && npm run build` 성공
- 번들 생성 확인: `AdminMultiAgentMonitoring-*.js`

## 비고
- 백엔드 `/api/admin/multi-agent-monitoring/calls`는 이미 `request_prompt`, `response_prompt` 필드를 제공하고 있어 프론트 확장만으로 요구사항 충족.
