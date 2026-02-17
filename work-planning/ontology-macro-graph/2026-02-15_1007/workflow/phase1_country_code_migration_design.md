# Phase 1 Country Migration Design (`country` -> `country_code`)

작성일: 2026-02-15  
버전: v1.0

## 1. 목적
- 국가 식별자 기준을 `country_code`로 통일한다.
- 기존 `country` 저장 데이터와 질의 호환성을 유지하면서 점진 전환한다.

## 2. 범위
- Graph: `Document`, `Event`, `GraphRagApiCall` 등 국가 속성 보유 노드
- Ingestion: 뉴스 수집/적재 경로(`news_loader`, `news_collector`)
- Query: Strategy/GraphRAG 조회 경로

## 3. 호환 전략
- 쓰기 경로: `country_code` 우선 저장 + `country` 원문 유지
- 읽기 경로: `country_code` 우선 필터 + `country` fallback OR 조건 유지
- 단계 완료 후 `country`는 raw/legacy 의미로 축소

## 4. Neo4j 제약조건/인덱스 변경안
## 4.1 제약조건
```cypher
CREATE CONSTRAINT document_doc_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.doc_id IS UNIQUE;

CREATE CONSTRAINT event_event_id_unique IF NOT EXISTS
FOR (e:Event) REQUIRE e.event_id IS UNIQUE;

CREATE CONSTRAINT graphrag_call_id_unique IF NOT EXISTS
FOR (c:GraphRagApiCall) REQUIRE c.call_id IS UNIQUE;
```

## 4.2 인덱스
```cypher
CREATE INDEX document_country_code_idx IF NOT EXISTS
FOR (d:Document) ON (d.country_code);

CREATE INDEX event_country_code_idx IF NOT EXISTS
FOR (e:Event) ON (e.country_code);

CREATE INDEX graphrag_call_country_code_idx IF NOT EXISTS
FOR (c:GraphRagApiCall) ON (c.country_code);

CREATE INDEX document_country_legacy_idx IF NOT EXISTS
FOR (d:Document) ON (d.country);

CREATE INDEX event_country_legacy_idx IF NOT EXISTS
FOR (e:Event) ON (e.country);
```

## 5. 백필 실행 순서
1. 사전 점검
- 전체 건수 및 null 비율 스냅샷 수집
- `country` 값 분포 상위 200개 추출

2. 매핑 테이블 확정
- `country_mapping.py` 기준으로 raw -> code 매핑표 동결
- 미매핑 값(`unknown_set`) 분리

3. Document 백필
```cypher
MATCH (d:Document)
WHERE d.country_code IS NULL AND d.country IS NOT NULL
SET d.country_code = $normalized_code
```
- 배치 단위: 5,000 nodes
- 실패 시 배치 재시도 3회 (1m/5m/15m)

4. Event 백필
```cypher
MATCH (e:Event)
WHERE e.country_code IS NULL AND e.country IS NOT NULL
SET e.country_code = $normalized_code
```
- 배치 단위: 5,000 nodes
- 실패 시 배치 재시도 3회

5. 로그/분석 노드 백필
- `GraphRagApiCall.country_code` 누락건 보정
- 보정 불가 건은 null 유지 + `country_mapping_missing=true`

6. 검증
- 전/후 쿼리 동일성 샘플 검증
- 국가 필터 회귀 테스트 수행

## 6. 롤백 포인트
- 롤백 단위: 배치 Job ID
- 각 배치 실행 전 스냅샷 기록
  - 대상 레코드 ID 목록
  - 이전 `country_code` 값
- 롤백 쿼리
```cypher
UNWIND $rows AS row
MATCH (n)
WHERE id(n) = row.node_id
SET n.country_code = row.prev_country_code
```

## 7. 재시도/장애 대응
- 일시 오류: 동일 배치 최대 3회 재시도
- 매핑 오류: 해당 raw 값을 `country_mapping_backlog`로 이관
- 장기 장애: `country_code` 미보정 노드 제외 필터를 QA path에서 경고로 노출

## 8. 성공 기준 (Phase 1)
- 핵심 노드(`Document`, `Event`)에서 `country_code` 커버리지 99% 이상
- GraphRAG/Strategy 경로가 `country_code` 우선 질의로 동작
- legacy `country`와의 기본 샘플 질의 결과 일관성 확보

## 9. 영향 파일
- `hobot/service/graph/normalization/country_mapping.py`
- `hobot/service/graph/rag/context_api.py`
- `hobot/service/graph/rag/response_generator.py`
- `hobot/service/graph/monitoring/graphrag_metrics.py`
- `hobot/service/macro_trading/collectors/news_collector.py`
