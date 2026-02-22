# 03_feedback_review_acceptance

## 검토 대상
사용자 피드백 3건:
1. Text2Cypher 스키마 프롬프트에 방향성 강제 주입
2. LangGraph State 스키마 정의
3. RDB ↔ Neo4j 동기화 시차(lag window) 대응

## 판단 결과
1. 수용
- 이유: Text2Cypher 실패의 대표 원인이 관계 방향 혼동이며, 방향 포함 스키마 + few-shot은 재현 가능한 예방책.

2. 수용
- 이유: Supervisor 중심 병렬 오케스트레이션에서 상태 계약이 없으면 fallback/정합성 검증 로직이 불안정해짐.

3. 조건부 수용
- 이유: 이벤트 기반 Projection 트리거는 타당.
- 단, 시차 fallback의 1순위는 Web Search가 아니라 RDB 직접 조회여야 정형 데이터 정확도 보장 가능.

## 반영 내용
- plan.md 반영 섹션:
  - 2.2 Fallback 규칙
  - 2.4 LangGraph State 계약 (신규)
  - 3.B Text2Cypher (방향성/퓨샷/재검증)
  - 6. KPI (방향성 오류 지표)
  - 9.4 수집/동기화 (이벤트 기반 + 백필)
  - 9.5 운영 체크포인트 (lag 측정, fallback 우선순위)
  - 10. Neo4j 확장 구현 태스크 (State/Projection/Text2Cypher 고도화)
