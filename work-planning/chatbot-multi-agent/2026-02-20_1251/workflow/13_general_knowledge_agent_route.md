# 13) General Knowledge Agent 라우팅 추가

## 배경
- 요구사항: `"오늘 날씨가 뭐야?"` 같은 일반 질의는 내부 SQL/Neo4j를 조회하지 않고, LLM 자체 지식으로 즉답.
- 모델 고정: `gemini-3-flash-preview`.

## 구현 내용
1. 라우팅
   - `general_knowledge` 타입 감지 규칙 추가.
   - 일반 질의는 `selected_type=general_knowledge`로 단축 라우팅.
2. 실행 전략
   - `general_knowledge`는 `sql_need=false`, `graph_need=false`.
   - Supervisor branch에 `llm_direct` 추가.
3. 에이전트
   - `general_knowledge_agent` stub 추가 및 registry 등록.
4. 응답 생성
   - `generate_graph_rag_answer`에서 일반 질의는 컨텍스트 빌드/내부 조회 없이 direct LLM 호출.
   - 응답 모델을 `gemini-3-flash-preview`로 강제.
   - `context_meta.policy=general_knowledge_direct_llm`로 식별.

## 검증
- 실행:
  - `cd /Users/ssho/project/hobot-service/hobot && PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py`
- 결과:
  - `Ran 37 tests ... OK`
  - 로컬 MySQL 미연결 경고 로그는 기존 테스트 환경 이슈로 지속.
