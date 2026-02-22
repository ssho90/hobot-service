# Neo4j Document url 속성 경고 제거

## 목표
- GraphRAG 쿼리에서 `property key does not exist: url` 경고 제거
- 기능 변화 없이 로그 노이즈만 해소

## 작업
1. `coalesce(d.url, d.link)` 사용처 전수 탐색
2. 동적 속성 접근 `coalesce(d['url'], d.link)`로 교체
3. 변경 내역 확인 및 안내
