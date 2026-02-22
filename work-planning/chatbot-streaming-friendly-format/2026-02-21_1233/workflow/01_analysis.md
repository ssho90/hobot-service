# 01 분석

- 현재는 `/api/graph/rag/answer` 단건 JSON 응답이라 채팅창이 완료 시점에 한 번에 렌더링됨.
- `OntologyPage`는 `handleMacroQuestion`에서 최종 텍스트를 직렬로 붙여 출력해 가독성(중복/영문 혼재/긴 문장) 문제가 큼.
- 개선 필요:
  - 전송 계층: stream endpoint + 클라이언트 파서
  - 표현 계층: 사용자 친화형 메시지 템플릿
