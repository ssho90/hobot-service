# 구현 로그

## 변경 사항
- 신규 파일
  - `hobot/service/kakao/skill_api.py`
  - `hobot/service/kakao/__init__.py`
  - `hobot/tests/test_kakao_skill_api.py`
- 수정 파일
  - `hobot/main.py` (카카오 스킬 라우터 include)

## 구현 포인트
- 엔드포인트: `POST /api/kakao/skill/chatbot`
- 입력 파싱:
  - `userRequest.utterance`
  - `action.clientExtra/params/detailParams`에서 선택 옵션(`country_code`, `region_code`, `property_type`, `time_range`) 추출
- 내부 호출:
  - `generate_graph_rag_answer(GraphRagAnswerRequest(...))`
- 출력 변환:
  - 카카오 OpenBuilder `version: "2.0"` + `template.outputs[].simpleText.text`
- 보안:
  - `KAKAO_SKILL_WEBHOOK_SECRET` 설정 시 `X-Webhook-Secret` 헤더 검증

## 테스트
- 실행 명령:
  - `cd hobot && PYTHONPATH=. ../.venv/bin/python -m unittest discover -s tests -p 'test_kakao_skill_api.py' -v`
- 결과:
  - 2 tests, OK
