# 작업 계획

## 목표
- Multi-Agent 모니터링에서 `graph_rag_agent_execution` 항목의 토큰 사용량이 0으로만 표시되는 문제를 개선한다.

## 구현 항목
1. `response_generator.py`의 에이전트 실행 로깅 경로에서 토큰 하드코딩(0)을 제거한다.
2. 요청/응답 payload 기반 토큰 추정 함수를 추가하고, 추정치로 `prompt/completion/total`을 기록한다.
3. 추정치 기반임을 `metadata_json`에 명시한다.
4. 단위 테스트로 추정 함수의 기본 동작(양수 토큰, 합계 일치)을 검증한다.

## 검증
- `py_compile` 문법 확인
- 타겟 단위 테스트 1건 실행
