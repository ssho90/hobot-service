# 계획

## 목표
- 한국 부동산 질의에서 수집된 정량 데이터(실거래/월간 집계)가 답변 본문에 반영되도록 GraphRAG 경로를 수정한다.

## 작업 범위
1. SQL branch 실행 결과를 프롬프트 컨텍스트에 포함
2. 정형 근거(structured citations)를 진술 필터 지원 토큰에 반영
3. 부동산 SQL 템플릿을 실제 테이블 스키마에 정렬
4. 지역 코드 필터(SEOUL/GYEONGGI/코드 prefix) SQL 매칭 보강
5. 단위 테스트 추가

## 검증
- response_generator 관련 신규/기존 단위 테스트 3건 실행
- 수정 파일 py_compile 검증
