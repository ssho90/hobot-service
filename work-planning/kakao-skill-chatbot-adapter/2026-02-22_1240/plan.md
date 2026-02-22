# 카카오톡 스킬 어댑터 구현 계획

- 목표: `/api/kakao/skill/chatbot` 엔드포인트 신설
- 요구사항:
  - 카카오 OpenBuilder 요청(`userRequest.utterance`) 파싱
  - 기존 GraphRAG 챗봇 로직 재사용
  - 카카오 `version: 2.0` 응답 포맷 반환
  - 선택적 웹훅 시크릿 검증
- 작업 단계:
  1. 카카오 스킬 라우터 모듈 생성
  2. 메인 API 라우터에 include
  3. 단위 테스트 추가 및 실행
