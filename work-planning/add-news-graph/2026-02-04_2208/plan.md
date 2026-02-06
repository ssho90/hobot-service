# Ontology 메뉴 하위 화면 구성 및 News Graph 연결 계획

## 1. 개요
* **목표**: Ontology 메뉴를 "Architecture Graph"와 "News Graph"로 분리하고, News Graph는 새로운 Neo4j 도메인에 연결.
* **기간**: 2026-02-04
* **담당**: Antigravity

## 2. 작업 내용

### 2.1 Backend (Python)
* [x] `hobot/main.py` 수정
    * `Neo4jQueryRequest` 모델에 `database` 필드 추가 (기본값: "architecture")
    * `get_neo4j_driver` 함수가 `database` 인자에 따라 다른 드라이버("architecture" 또는 "news")를 반환하도록 수정
    * `_neo4j_news_driver` 싱글톤 추가
    * APi 엔드포인트 `/api/neo4j/query`, `/api/neo4j/health` 수정

### 2.2 Frontend (React)
* [x] `hobot-ui-v2/src/services/neo4jService.ts` 수정
    * `runCypherQuery`, `checkNeo4jHealth` 함수에 `database` 파라미터 추가
* [x] `hobot-ui-v2/src/components/OntologyPage.tsx` 수정
    * `mode` prop 추가 ('architecture' | 'news')
    * `mode`에 따라 쿼리 실행 시 `database` 파라미터 전달
    * UI 타이틀 및 예제 질문을 모드에 맞게 변경
* [x] `hobot-ui-v2/src/components/Header.tsx` 수정
    * Ontology 메뉴를 Dropdown으로 변경
    * 하위 메뉴: "Architecture Graph", "News Graph" 추가
* [x] `hobot-ui-v2/src/App.tsx` 수정
    * 라우트 추가: `/ontology/architecture`, `/ontology/news`
    * `/ontology` 접속 시 리다이렉트 처리

### 2.3 Deployment
* [x] `.github/workflows/deploy.yml` 수정
    * `NEO4J_NEWS_URI` Secret 환경변수 추가
* [x] `.github/deploy/deploy.sh` 수정
    * `NEO4J_NEWS_URI` export 및 `.env` 파일 생성 로직 추가

## 3. 검증 계획
* 배포 후 각 페이지 접속 테스트
* Architecture Graph가 기존 데이터(Localhost/Existing)를 잘 불러오는지 확인
* News Graph가 새로운 데이터(News Neo4j)를 잘 불러오는지 확인
