# 정량 시그널 API 파라미터 설명 (프롬프트용)

## API 응답 구조

```json
{
  "status": "success",
  "timestamp": "2025-11-22 19:02:13",
  "signals": {
    "yield_curve_spread_trend": { ... },
    "real_interest_rate": 0.37,
    "taylor_rule_signal": 1.67,
    "net_liquidity": { ... },
    "high_yield_spread": { ... },
    "additional_indicators": { ... }
  },
  "parameters": { ... }
}
```

---

## signals.yield_curve_spread_trend

**의미**: 장단기 금리차(스프레드) 추세 분석으로 경기 사이클과 금리 정책 방향 판단

- **spread** (%): 현재 장단기 금리차 = DGS10 - DGS2. 양수면 정상, 음수면 역전(경기 침체 신호). 값이 클수록 스프레드 넓음(경기 확장), 작을수록 좁음(경기 둔화)
- **spread_fast** (%): 스프레드 20일 이동평균 (단기 추세)
- **spread_slow** (%): 스프레드 120일 이동평균 (장기 추세)
- **yield_trend** (%): DGS10의 200일 이동평균 (금리 대세 기준선)
- **current_dgs10** (%): 현재 10년물 국채 금리 (장기 금리, 경기 전망 반영)
- **current_dgs2** (%): 현재 2년물 국채 금리 (단기 금리, 연준 정책 반영)
- **spread_trend**: "Steepening"(확대) 또는 "Flattening"(축소). spread_fast와 spread_slow 비교
- **spread_trend_kr**: 한글 번역 ("확대" 또는 "축소")
- **yield_regime**: "Rising"(상승) 또는 "Falling"(하락). current_dgs10과 yield_trend 비교
- **yield_regime_kr**: 한글 번역 ("금리 상승 추세" 또는 "금리 하락 추세")
- **regime**: 4가지 국면
  - "Bull Steepening": 스프레드 확대 + 금리 하락 → 경기 부양 기대
  - "Bear Steepening": 스프레드 확대 + 금리 상승 → 인플레/재정 공포
  - "Bull Flattening": 스프레드 축소 + 금리 하락 → 경기 둔화 초기
  - "Bear Flattening": 스프레드 축소 + 금리 상승 → 강력한 긴축
- **regime_kr**: regime의 한글 번역 및 해석

---

## signals.real_interest_rate

**의미**: 실질 금리 = 명목 금리(DGS10) - CPI 증가율

- **타입**: float (%)
- **해석**: 
  - 양수: 실질 금리 양수 → 통화 정책이 경기 과열 억제 효과
  - 음수: 실질 금리 음수 → 통화 정책 완화적, 자산 가격 상승 압력
  - 값이 클수록 통화 긴축 강도 높음

---

## signals.taylor_rule_signal

**의미**: 테일러 준칙에 따른 목표 금리와 현재 금리 차이 = Target_Rate - FEDFUNDS

- **타입**: float (%)
- **계산식**: Target_Rate = r* + π + 0.5(π - π*) + 0.5(y - y*)
  - r*: 자연 이자율 (기본 2.0%)
  - π: 현재 PCE 인플레이션율
  - π*: 목표 인플레이션율 (기본 2.0%)
  - y - y*: GDP 갭 (현재 0으로 가정)
- **해석**:
  - 양수: 목표 금리 > 현재 금리 → 금리 인상 여지, 통화 긴축 필요
  - 음수: 목표 금리 < 현재 금리 → 금리 인하 여지, 통화 완화 가능
  - 절댓값이 클수록 정책 조정 필요성 높음

---

## signals.net_liquidity

**의미**: 연준 순유동성 = WALCL - WTREGEN - RRPONTSYD (시장에 공급되는 실제 유동성)

- **net_liquidity** (Millions of Dollars): 순유동성 절대값. 값이 클수록 유동성 풍부, 작을수록 부족. 증가 추세면 자산 가격 상승 압력, 감소 추세면 하락 압력
- **ma_trend**: 이동평균 추세 방향
  - 1: 상승 추세 (유동성 공급 확대 → 자산 매수 신호)
  - -1: 하락 추세 (유동성 공급 축소 → 자산 매도 신호)
  - 0: 보합
- **ma_value** (Millions of Dollars): 4주 이동평균값 (단기 변동성 제거한 추세)

---

## signals.high_yield_spread

**의미**: 하이일드 채권 스프레드 (시장 위험 선호도와 유동성 상태)

- **spread** (%): 하이일드 채권과 국채 간 금리 차이
  - 3.5% 미만: 매우 낮음 (유동성 매우 풍부)
  - 5.0% 이상: 경계 수준 (유동성 경색 시작)
  - 10.0% 이상: 위기 수준 (금융 위기)
- **signal**: 유동성 상태 신호
  - 1: Greed (탐욕) → 주식 적극 매수 신호
  - 0: Fear/Neutral (공포/중립) → 주식 비중 축소 고려
  - -1: Panic (공황) → 전량 현금/달러/국채 전환 고려
- **signal_name**: "Greed", "Fear", "Neutral", "Panic"
- **week_change** (%): 전주 대비 스프레드 변화율. 양수면 위험 회피 증가, 음수면 위험 선호 증가

---

## signals.additional_indicators

**의미**: 추가 거시경제 지표 (실업률, 고용 등)

- **타입**: object (dictionary)
- **가능한 지표**:
  - `unemployment_rate`: 실업률 (%)
  - `payroll_growth`: 비농업 고용 전월 대비 증가율 (%)
- **참고**: 데이터 없으면 빈 객체 `{}`

---

## parameters

**의미**: 시그널 계산에 사용된 파라미터

- **natural_rate** (%): 자연 이자율 (r*), 기본값 2.0%, 테일러 준칙 계산용
- **target_inflation** (%): 목표 인플레이션율 (π*), 기본값 2.0%, 테일러 준칙 계산용
- **liquidity_ma_weeks**: 순유동성 이동평균 기간 (주), null이면 설정 파일 값 사용 (일반적으로 4주)

---

## 분석 가이드

1. **금리 곡선**: `yield_curve_spread_trend.regime`으로 경기 사이클 국면 파악
   - Bull Flattening → 방어적 자산 배분
   - Bear Steepening → 인플레 헤지 자산

2. **통화 정책**: `taylor_rule_signal` 양수면 금리 인상 압력, `real_interest_rate`로 통화 정책 강도 파악

3. **유동성**: `net_liquidity.ma_trend` -1이면 유동성 축소, `high_yield_spread.signal` 1이면 유동성 풍부

4. **시장 심리**: `high_yield_spread.spread` 작을수록 위험 선호도 높음, `week_change` 급격한 변화는 변동성 증가 신호

5. **모순 신호**: 서로 다른 지표가 반대 신호를 보이면 전환기일 수 있으므로 주의 깊게 관찰

