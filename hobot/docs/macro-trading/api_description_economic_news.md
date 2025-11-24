# 경제 뉴스 API 파라미터 설명

이 문서는 `/api/macro-trading/economic-news` API 응답값의 각 파라미터에 대한 상세 설명입니다. LLM이 경제 뉴스 데이터를 분석할 때 참고할 수 있도록 작성되었습니다.

## API 엔드포인트

```
GET /api/macro-trading/economic-news
```

### 요청 파라미터

- **hours** (integer, 선택, 기본값: 24)
  - **의미**: 조회할 시간 범위 (과거 N시간)
  - **범위**: 1 ~ 168 (최대 7일)
  - **예시**: `24` (최근 24시간), `48` (최근 48시간), `168` (최근 7일)

---

## API 응답 구조

### 성공 응답

```json
{
  "status": "success",
  "timestamp": "2024-12-19 10:30:00",
  "hours": 24,
  "total_count": 10,
  "news": [
    {
      "id": 1,
      "title": "US Stocks Rebound, Still Post Weekly Losses",
      "link": "https://tradingeconomics.com/united-states/stock-market",
      "country": "United States",
      "category": "Stock Market",
      "description": "US stocks sharply rebounded on Friday...",
      "published_at": "2024-12-19 08:00:00",
      "collected_at": "2024-12-19 10:00:00",
      "source": "TradingEconomics Stream",
      "created_at": "2024-12-19 10:00:00"
    },
    {
      "id": 2,
      "title": "Fed Keeps Rates Unchanged",
      "link": "https://tradingeconomics.com/united-states/interest-rate",
      "country": "United States",
      "category": "Interest Rate",
      "description": "The Federal Reserve kept interest rates...",
      "published_at": "2024-12-19 09:15:00",
      "collected_at": "2024-12-19 10:00:00",
      "source": "TradingEconomics Stream",
      "created_at": "2024-12-19 10:00:00"
    }
  ]
}
```

---

## 응답 파라미터 상세 설명

### 최상위 필드

- **status** (string)
  - **의미**: API 응답 상태
  - **값**: `"success"` (성공 시)

- **timestamp** (string, "YYYY-MM-DD HH:MM:SS")
  - **의미**: API 응답 생성 시간
  - **예시**: `"2024-12-19 10:30:00"`

- **hours** (integer)
  - **의미**: 조회한 시간 범위
  - **예시**: `24`, `48`, `168`

- **total_count** (integer)
  - **의미**: 반환된 뉴스 개수
  - **해석**: `news` 배열의 길이와 동일

- **news** (array)
  - **의미**: 뉴스 목록
  - **정렬**: 발행 시간 내림차순 (최신 뉴스가 먼저)
  - **각 뉴스 객체 구조**:
    - **id** (integer)
      - **의미**: 뉴스 고유 ID (데이터베이스 기본키)
    
    - **title** (string)
      - **의미**: 뉴스 제목
      - **해석**: 뉴스의 핵심 내용을 요약
      - **예시**: "US Stocks Rebound, Still Post Weekly Losses"
    
    - **link** (string, nullable)
      - **의미**: 원본 뉴스 링크 (TradingEconomics)
      - **형식**: URL 문자열
      - **예시**: "https://tradingeconomics.com/united-states/stock-market"
    
    - **country** (string, nullable)
      - **의미**: 뉴스가 관련된 국가
      - **예시**: "United States", "China", "Euro Area", "Japan"
      - **해석**: 
        - 해당 국가의 경제 상황을 반영
        - 글로벌 경제 분석 시 중요
    
    - **category** (string, nullable)
      - **의미**: 뉴스 카테고리/주제
      - **예시**: 
        - "Stock Market": 주식 시장
        - "Interest Rate": 금리
        - "GDP Annual Growth Rate": GDP 성장률
        - "Inflation Rate": 인플레이션
        - "Unemployment Rate": 실업률
        - "Trade Balance": 무역수지
      - **해석**: 
        - 경제 지표별 분류
        - 특정 경제 영역의 변화를 나타냄
    
    - **description** (string, nullable)
      - **의미**: 뉴스 본문/요약
      - **해석**: 
        - 뉴스의 상세 내용
        - 정성 분석에 중요한 정보 포함
    
    - **published_at** (string, "YYYY-MM-DD HH:MM:SS")
      - **의미**: 뉴스 발행 시간
      - **형식**: "2024-12-19 10:15:00"
      - **해석**: 
        - 실제 뉴스가 발행된 시간
        - 시간대별 뉴스 밀도 분석에 사용
    
    - **collected_at** (string, "YYYY-MM-DD HH:MM:SS")
      - **의미**: 뉴스가 시스템에 수집된 시간
      - **형식**: "2024-12-19 10:00:00"
      - **해석**: 
        - 데이터베이스에 저장된 시간
        - 데이터 수집 시점 파악에 사용
    
    - **source** (string)
      - **의미**: 뉴스 출처
      - **값**: "TradingEconomics Stream"
    
    - **created_at** (string, "YYYY-MM-DD HH:MM:SS")
      - **의미**: 데이터베이스 레코드 생성 시간
      - **형식**: "2024-12-19 10:00:00"
