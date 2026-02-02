
### 📋 AI 작업 지시서: 비트코인 반감기 사이클 차트 구현

**[Role]**
너는 시각화에 강점이 있는 Senior Full-stack Developer야.

**[Goal]**
React(Frontend)와 Python(Backend)을 사용하여 첨부한 이미지와 동일한 로직의 **'비트코인 반감기 사이클 로그 차트'**를 웹 컴포넌트로 구현해줘.

**[1. Concept & Logic]**
첨부한 이미지는 비트코인의 4년 주기(반감기) 패턴을 로그 스케일(Log Scale)로 분석한 차트야.

* **핵심 로직:** 비트코인은 반감기 → 고점 → 저점을 반복하며, 시간이 지날수록 상승 기울기(Slope)가 완만해지는 경향이 있어.
* **표현 방식:**
* Y축: **Log Scale** (필수)
* 데이터 포인트: 과거의 확정된 고점/저점(History)과 미래의 예측된 고점/저점(Prediction)을 연결.
* **Real-time Feature:** 그래프 위에 **'현재 실시간 가격'**을 빨간색 점(Pulsing Dot)으로 표시하여, 현재 시장이 사이클의 어디에 위치해 있는지 직관적으로 보여줘야 함.



**[2. Tech Stack]**

* **Frontend:** React, `recharts` (차트 라이브러리)
* **Backend:** Python (FastAPI 또는 Flask)

**[3. Data Structure (Backend)]**
백엔드에서는 `/api/bitcoin-cycle` 엔드포인트를 통해 다음 두 가지 데이터를 합쳐서 보내줘.

1. **Static Cycle Data (JSON):**
* 아래 데이터를 하드코딩해서 사용해. (과거 데이터 + 내가 분석한 예측 데이터임)


```json
[
  {"date": "2012-11", "price": 12, "type": "history", "event": "1st Halving"},
  {"date": "2013-12", "price": 1209, "type": "history", "event": "Peak"},
  {"date": "2015-01", "price": 180, "type": "history", "event": "Bottom"},
  {"date": "2016-07", "price": 650, "type": "history", "event": "2nd Halving"},
  {"date": "2017-12", "price": 19328, "type": "history", "event": "Peak"},
  {"date": "2018-12", "price": 3222, "type": "history", "event": "Bottom"},
  {"date": "2020-05", "price": 8600, "type": "history", "event": "3rd Halving"},
  {"date": "2021-11", "price": 66459, "type": "history", "event": "Peak"},
  {"date": "2022-11", "price": 15653, "type": "history", "event": "Bottom"},
  {"date": "2024-04", "price": 63000, "type": "history", "event": "4th Halving"},
  {"date": "2025-08", "price": 125000, "type": "prediction", "event": "Peak (Exp)"},
  {"date": "2026-10", "price": 45000, "type": "prediction", "event": "Bottom (Exp)"},
  {"date": "2028-04", "price": 70000, "type": "prediction", "event": "5th Halving"},
  {"date": "2029-08", "price": 200000, "type": "prediction", "event": "Peak (Exp)"}
]

```


2. **Dynamic Data:**
* 외부 API (CoinGecko 등)를 호출해서 BTC의 실시간 가격을 가져와서 `current_price` 객체로 추가해줘.



**[4. Visualization Details (Frontend)]**

* **X축:** 날짜 (Time Scale)
* **Y축:** 가격 (Logarithmic Scale) - `$1k`, `$10k`, `$100k` 단위 포맷팅.
* **Line Style:**
* History 구간: **검은색 실선**
* Prediction 구간: **검은색 점선** (과거 데이터와 끊기지 않고 자연스럽게 연결되도록 처리)


* **Current Price:**
* 실시간 가격 위치에 **빨간색 점**을 찍고, CSS Animation을 넣어 **두근거리는(Pulsing) 효과**를 줄 것.
* 점 옆에 "Current: $Price" 텍스트 라벨 표시.



**[Request]**
1. 위 내용을 바탕으로 Frontend와 Backend 코드를 작성해줘.
2. 기존 Dashboard의 메뉴에 아래쪽으로 "Bitcoin Cycle" 섹션을 만들어줘. 
