# 02 구현

## 백엔드
- 파일: `/Users/ssho/project/hobot-service/hobot/service/graph/rag/response_generator.py`
- 변경:
  - import 추가
    - `StreamingResponse`, `jsonable_encoder`
  - 사용자 친화형 텍스트 빌더 추가
    - `_dedupe_friendly_points`
    - `_build_friendly_chat_text`
    - `_iter_text_chunks`
  - 신규 엔드포인트 추가
    - `POST /graph/rag/answer/stream`
    - NDJSON 이벤트 형식
      - `started`: 시작 알림
      - `delta`: 텍스트 청크
      - `done`: 최종 `GraphRagAnswerResponse` 전체 payload
      - `error`: 에러 메시지

## 프론트
- 파일: `/Users/ssho/project/hobot-service/hobot-ui-v2/src/services/graphRagService.ts`
  - `streamGraphRagAnswer` 추가
  - NDJSON 라인 파싱 + 이벤트 콜백 전달
- 파일: `/Users/ssho/project/hobot-service/hobot-ui-v2/src/components/OntologyPage.tsx`
  - `buildFriendlyMacroMessage` 추가(폴백/보정용)
  - `handleMacroQuestion`를 스트리밍 기반으로 변경
    - 빈 assistant 메시지 먼저 추가
    - `delta` 수신 시 실시간 누적 렌더링
    - 스트리밍 실패 시 기존 `/answer` API 폴백
    - `done` 수신 후 기존 그래프/근거/RAG 메타 연동 유지
