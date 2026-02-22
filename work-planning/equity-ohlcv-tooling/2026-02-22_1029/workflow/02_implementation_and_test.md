# 구현/검증 기록

## 구현 사항
1. Equity SQL 템플릿 컬럼 후보 보강
- 파일: `hobot/service/graph/rag/templates/equity_query_templates.py`
- 변경: `open_price/high_price/low_price/close_price/adjusted_close`를 `select_candidates`에 추가.
- 목적: 실제 RDB 스키마(`*_price`)에서 OHLCV 컬럼 인식 실패 방지.

2. Equity OHLCV 가공 로직 추가
- 파일: `hobot/service/graph/rag/agents/live_executor.py`
- 추가 함수:
  - `_build_equity_ohlcv_analysis`
  - `_build_equity_earnings_reaction_analysis`
  - `_classify_equity_trend`, `_moving_average`, `_to_calendar_date` 등 보조 함수
- 계산 항목:
  - MA20/MA60/MA120
  - 단기/장기 추세 분류(상승/하락/중립)
  - 최근 수익률(1/5/20/60/120일)
  - 실적 이벤트 전후 반응(이벤트일/익일/5일 변동률)
- SQL 실행 결과(`tool_probe`)에 `equity_analysis` 포함하도록 연결.

3. Supervisor 입력 컨텍스트 반영
- 파일: `hobot/service/graph/rag/response_generator.py`
- 변경:
  - `_build_structured_data_context`에서 `tool_probe.equity_analysis`를 구조화하여 `datasets[].equity_analysis`로 포함.
  - `_compact_structured_data_for_prompt`에서 `equity_analysis` 요약을 프롬프트 입력으로 전달.
  - supervisor 프롬프트 규칙에 “equity_analysis 존재 시 MA 기반 추세/실적 반응 명시” 룰 추가.

4. 단위 테스트 추가
- 파일: `hobot/tests/test_phase_d_live_executor.py`
  - MA/실적반응 계산 케이스 추가
  - 심볼 필터 누락시 degraded 케이스 추가
  - 국가/심볼 기준 SQL 템플릿 우선순위 케이스 추가
- 파일: `hobot/tests/test_phase_d_response_generator.py`
  - `equity_analysis`가 StructuredDataContext에 포함되는지 검증 케이스 추가

5. SQL 템플릿 선택 로직 보정(US/KR 혼선 방지)
- 파일: `hobot/service/graph/rag/agents/live_executor.py`
- 원인:
  - 기존 로직은 `equity_analyst_agent`의 첫 번째 존재 테이블을 무조건 선택.
  - KR/US 테이블이 모두 존재할 때 `kr_top50_daily_ohlcv`가 먼저 선택되어 US 심볼(`AAPL/NVDA`)도 빈 결과가 발생.
- 변경:
  - `_prioritize_sql_specs` 추가: `country_code`, `selected_type(us_single_stock)`, `focus_symbol` 기반으로 템플릿 우선순위 정렬.
  - 빈 결과면 다음 템플릿으로 자동 폴백하도록 루프 처리.
  - `attempts` 메타를 반환해 어떤 테이블을 시도했는지 추적 가능.

## 검증
실행 명령:
```bash
cd /Users/ssho/project/hobot-service/hobot && \
PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_live_executor.py && \
PYTHONPATH=. ../.venv/bin/python tests/test_phase_d_response_generator.py
```

결과:
- `test_phase_d_live_executor.py`: `Ran 8 tests ... OK`
- `test_phase_d_response_generator.py`: `Ran 55 tests ... OK (skipped=2)`

비고:
- 샌드박스 네트워크 제약으로 테스트 중 MySQL/외부 LLM 연결 경고 로그는 출력되었으나, 테스트 자체는 정상 통과.
