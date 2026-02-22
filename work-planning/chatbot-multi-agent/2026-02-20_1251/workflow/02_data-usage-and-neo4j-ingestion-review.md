# Data Usage & Neo4j Ingestion Review Log

## 목적
- `collected-data-list.md`의 61개 수집 데이터를 Multi-Agent 활용 관점으로 `plan.md`에 반영.
- Neo4j 적재 전략(무엇을 투영하고 무엇을 RDB에 유지할지) 검토 결과를 명시.

## 반영 내용
1. 카테고리별 에이전트 매핑 추가
- 한국 경제/한국 주식/한국 부동산/미국 경제/미국 주식/공통·글로벌로 분류.
- 각 카테고리별 1차 담당 에이전트, 협업 에이전트, 기본 Tool 전략 정의.

2. Supervisor 라우팅 규칙 강화
- 종목/거시/부동산/복합 질의별 병렬 호출 규칙 명시.
- 이벤트-테마-지표 체인 질의 시 Ontology Agent 병행 호출 고정.

3. 응답 계약(Response Contract) 추가
- `as_of_date`, `data_freshness`, `citations`, `uncertainty` 필수 필드화.

4. Neo4j 적재 전략 검토 결과 추가
- Raw Full Data는 MySQL 유지, 그래프 질의용 Projection을 Neo4j에 적재하는 하이브리드 방식 채택.
- 기존 구현(`IndicatorLoader`, `NewsLoader`, `RealEstateSummaryLoader`)과 신규 필요 영역(주식 그래프 투영) 분리 명시.

5. Neo4j 확장 스키마/태스크 정의
- `Company`, `EquityUniverseSnapshot`, `EquityDailyBar`, `EarningsEvent` 라벨 및 관계 제안.
- 고유 제약/인덱스, 배치 순서, 운영 체크포인트 추가.

## 참고 코드 근거
- `hobot/service/graph/indicator_loader.py`
- `hobot/service/graph/news_loader.py`
- `hobot/service/graph/real_estate_loader.py`
- `hobot/service/macro_trading/collectors/corporate_event_collector.py`
