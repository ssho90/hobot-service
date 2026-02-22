# 03 검증

## 백엔드 문법 체크
- 명령: `PYTHONPYCACHEPREFIX=/tmp/pythoncache python3 -m py_compile hobot/service/graph/rag/response_generator.py`
- 결과: 성공

## 프론트 빌드
- 명령: `cd hobot-ui-v2 && npm run build`
- 결과: 성공

## 수동 확인 포인트
1. `/ontology/macro`에서 질문 전송
2. assistant 버블이 한 번에 완성되지 않고 텍스트가 점진적으로 표시되는지 확인
3. 문장 포맷이 `한눈에 요약 / 핵심 포인트 / 참고해요` 구조로 가독성 있게 보이는지 확인
4. 스트림 중 오류 시 기존 단건 API로 폴백되는지 확인
