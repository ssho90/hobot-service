# Chatbot Streaming + Friendly Format 개선 계획

## 목표
- Macro 챗봇 답변을 스트리밍으로 표시한다.
- 사용자 가독성을 높이기 위해 친근한 말투, 이모티콘, 문단/불릿 중심 포맷을 적용한다.

## 구현 범위
1. 백엔드 GraphRAG 스트리밍 엔드포인트 추가
   - `POST /api/graph/rag/answer/stream`
   - NDJSON 이벤트(`started`, `delta`, `done`, `error`) 전송
2. 프론트 스트림 소비 로직 추가
   - `OntologyPage` Macro 모드에서 스트리밍 수신 후 실시간 메시지 업데이트
3. 사용자 친화형 메시지 포맷 적용
   - 한줄 요약 + 핵심포인트 + 참고(불확실성) 섹션

## 검증
- Python 문법 체크
- Frontend build
- 스트림 이벤트 파싱/표시 수동 확인
