# 03 검증

## 문법 검증
- 명령: `PYTHONPYCACHEPREFIX=/tmp/pythoncache python3 -m py_compile hobot/service/graph/rag/response_generator.py`
- 결과: 성공

## 동작 검증 가이드
1. 챗봇에서 주식 질의(예: "팔란티어 주가 요즘 어때?") 실행
2. `/admin/multi-agent`에서 해당 run 선택
3. `호출 상세`에 다음이 함께 보이는지 확인
   - `graph_rag_router_intent / router_intent_classifier`
   - `graph_rag_agent_execution / equity_analyst_agent` (sql/graph 분기별)
   - `graph_rag_answer / supervisor_agent`
