# 수정 로그

## 원인
- 카카오 스킬 테스트 JSON은 기본적으로 `userRequest.utterance`에 "발화 내용" 템플릿 문자열이 들어감
- 기존 `_extract_utterance`는 `userRequest.utterance`를 무조건 우선 사용해서 `action.params.question`이 있어도 무시됨

## 수정
- 파일: `hobot/service/kakao/skill_api.py`
- 변경:
  - 테스트 placeholder 세트(`발화 내용`, `발화내용`, `utterance`) 추가
  - `action.params.question/utterance` + `action.detailParams.question.value/utterance.value` 파싱 추가
  - `userRequest.utterance`가 placeholder이면 `action` 값을 우선 채택

## 검증
- 파일: `hobot/tests/test_kakao_skill_api.py`
- 신규 테스트:
  - `test_kakao_skill_prefers_action_question_when_utterance_is_placeholder`
- 실행:
  - `cd hobot && PYTHONPATH=. ../.venv/bin/python -m unittest discover -s tests -p 'test_kakao_skill_api.py' -v`
- 결과: `Ran 3 tests ... OK`
