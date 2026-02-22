# us-single-stock-trend-alignment 계획

- 목표: US 단일종목 답변이 이벤트 직후 급등 문장만 반영해 실제 최근 하락 추세와 어긋나는 문제를 완화한다.
- 범위:
  - `response_generator.py`의 us_single_stock 인용 보강 로직 개선
  - 결론 문구와 최근 focus 근거의 방향 충돌 시 보정 가드레일 추가
  - 회귀/신규 단위 테스트 추가
- 비범위:
  - 데이터 수집 파이프라인 전면 개편
  - 외부 가격 API 신규 연동

## 작업 단계
1. 인용 보강 로직에서 최신/하락 focus evidence 주입 보장
2. 결론 보정 로직 추가(최근 하락 우세 + 낙관 결론 충돌 시)
3. 테스트 추가 및 실행
4. workflow 로그 기록
