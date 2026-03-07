# 런타임 검증 리포트 (실질 값 반영 확인)

## 검증 목적
- `equity_analysis` 키 존재 여부가 아니라, 실제 MA/추세/실적반응 값이 채워지는지 확인.
- US 단일종목 질의에서 KR 테이블 선조회 문제(빈 결과) 해소 여부 확인.

## 🔴 에러 원인
- `equity_analyst_agent` SQL 실행 로직이 “존재하는 첫 번째 테이블”을 선택하여,
  KR/US 테이블이 모두 있을 때 `kr_top50_daily_ohlcv`를 먼저 조회함.
- 결과적으로 `AAPL/NVDA` 같은 US 심볼도 KR 테이블 조건으로 조회되어 빈 결과(`row_count=0`)가 발생했고,
  `equity_analysis`는 구조만 있고 내부 값(MA/returns/events)은 전부 `null`로 내려갔음.

## 수정 후 SQL 툴 단독 검증
실행: `execute_live_tool(agent_name='equity_analyst_agent', branch='sql', ...)`

| 심볼 | 선택 테이블 | row_count | bars_available | MA20/60/120 | 실적 이벤트 |
|---|---|---:|---:|---|---:|
| PLTR | `us_top50_daily_ohlcv` | 0 | 0 | null | 0 |
| AAPL | `us_top50_daily_ohlcv` | 5 | 252 | 264.8957 / 268.2152 / 261.5309 | 3 |
| NVDA | `us_top50_daily_ohlcv` | 5 | 252 | 186.2150 / 184.1645 / 184.1487 | 3 |

비고:
- `PLTR`은 현재 `us_top50_daily_ohlcv` 미수집(심볼 자체 없음)으로 계속 빈 결과가 정상.
- `AAPL/NVDA`는 값이 정상 채워짐.

## E2E 멀티에이전트 검증 (수정 전/후 비교)

### AAPL
- 수정 전 run: `codex-eq-report-5a69e03412`
  - `equity_analysis.ma20/60/120 = null`
  - `equity_analysis.earnings_reaction.event_count = 0`
- 수정 후 run: `codex-eq-final-dcfccefca5`
  - `trend_short_term=하락`, `trend_long_term=중립`
  - `ma20=264.8957`, `ma60=268.2152`, `ma120=261.5309`
  - `latest_event_day_pct_from_pre_close=0.46`
  - `latest_post_1d_pct_from_event_close=4.06`
  - `latest_post_5d_pct_from_event_close=7.18`

### NVDA
- 수정 전 run: `codex-eq-report-b3dbce30d1`
  - `equity_analysis.ma20/60/120 = null`
  - `equity_analysis.earnings_reaction.event_count = 0`
- 수정 후 run: `codex-eq-final-c272e25105`
  - `trend_short_term=상승`, `trend_long_term=상승`
  - `ma20=186.215`, `ma60=184.1645`, `ma120=184.1487`
  - `latest_event_day_pct_from_pre_close=2.85`
  - `latest_post_1d_pct_from_event_close=-3.15`
  - `latest_post_5d_pct_from_event_close=-3.36`

## 토큰/지연(수정 후, 실제 llm_usage_logs 집계)

### run_id: `codex-eq-final-dcfccefca5` (AAPL)
- 합계: prompt `5,668`, completion `10,375`, total `16,043`, duration_sum `71,990ms`
- 에이전트별:
  - `router_intent_classifier` (`gemini-2.5-flash`): `943` tokens / `4,358ms`
  - `query_rewrite_utility` (`gemini-2.5-flash`): `1,448` / `7,504ms`
  - `query_normalization_utility` (`gemini-2.5-flash`): `1,208` / `4,550ms`
  - `equity_analyst_agent` (`gemini-3-flash-preview`): `4,172` / `27,691ms`
  - `supervisor_agent` (`gemini-3.1-pro-preview`): `5,907` / `18,346ms`
  - `citation_postprocess_utility` (`gemini-2.5-flash`): `2,365` / `9,541ms`

### run_id: `codex-eq-final-c272e25105` (NVDA)
- 합계: prompt `5,661`, completion `10,461`, total `16,122`, duration_sum `63,803ms`
- 에이전트별:
  - `router_intent_classifier` (`gemini-2.5-flash`): `360` / `1,422ms`
  - `query_rewrite_utility` (`gemini-2.5-flash`): `1,032` / `4,600ms`
  - `query_normalization_utility` (`gemini-2.5-flash`): `1,085` / `3,896ms`
  - `equity_analyst_agent` (`gemini-3-flash-preview`): `1,463` / `9,364ms`
  - `supervisor_agent` (`gemini-3.1-pro-preview`): `6,382` / `22,401ms`
  - `citation_postprocess_utility` (`gemini-2.5-flash`): `5,800` / `22,120ms`
