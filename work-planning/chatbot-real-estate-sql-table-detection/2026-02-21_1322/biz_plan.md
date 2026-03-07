# Plan

## 목표
- "한국 부동산 가격 전망" 질의에서 StructuredDataContext가 비는 원인을 확인하고 수정한다.

## 작업 항목
1. DB 실데이터/로그 기준으로 원인 재현
2. live executor SQL 테이블/컬럼 탐지 로직 수정
3. 회귀 테스트 추가 및 스모크 검증
