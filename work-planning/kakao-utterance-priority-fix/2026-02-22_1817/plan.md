# Kakao Skill utterance 우선순위 수정

## 목표
- 카카오 스킬 테스트에서 `question` 파라미터가 실제 질의로 전달되도록 보정

## 작업
1. `skill_api._extract_utterance` 우선순위 로직 개선
2. 카카오 테스트 placeholder(`발화 내용`) 감지 시 `action.params.question` 우선
3. 단위 테스트 추가/실행
