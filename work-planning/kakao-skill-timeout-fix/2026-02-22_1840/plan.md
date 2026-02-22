# 카카오 스킬 타임아웃(5초) 대응 계획

## 목표
- 카카오 스킬 테스트에서 5초 타임아웃으로 실패하는 문제를 해결한다.
- 카카오 요청이 `callbackUrl`을 제공할 때 즉시 `useCallback`으로 응답하고 백그라운드에서 최종 답변을 전달한다.
- `callbackUrl` 미제공 시에도 타임아웃 대신 즉시 안내 메시지를 반환한다.

## 작업 항목
1. `/api/kakao/skill/chatbot`에 callback 비동기 응답 경로 추가
2. callback 미설정 시 빠른 실패 방지 가드 추가(`KAKAO_SKILL_REQUIRE_CALLBACK`)
3. 단위 테스트 확장 및 회귀 검증

## 검증
- `test_kakao_skill_api.py` 전체 통과
- callback URL 포함 케이스에서 `useCallback: true` 응답 확인
- callback 필수 모드에서 동기 LLM 미호출 확인
