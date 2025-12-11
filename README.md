# 🚀 Stockoverflow - AI 기반 거시경제 자동매매 시스템

> **AI 기반 거시경제 자동매매 시스템**  
> 연준 금리, 인플레이션, 유동성 지표를 실시간 분석하여 포트폴리오를 자동으로 리밸런싱하는 지능형 투자 시스템

**🌐 서비스 도메인**: [https://stockoverflow.org](https://stockoverflow.org)

---

## 💡 서비스 소개

**Stockoverflow**는 거시경제 지표와 AI를 활용한 자동 포트폴리오 관리 시스템입니다. 연준의 금리 정책, 인플레이션 추이, 시장 유동성 등 핵심 거시경제 데이터를 실시간으로 분석하고, Gemini AI가 이를 종합 판단하여 최적의 자산 배분을 결정합니다.

### 🎯 핵심 가치

- **데이터 기반 의사결정**: FRED API를 통한 실시간 거시경제 지표 수집 및 분석
- **AI 전략가**: AI가 정량 시그널과 정성 뉴스를 종합하여 포트폴리오 전략 수립
- **자동 실행**: 임계값 기반 자동 리밸런싱으로 감정 없는 투자 실행
- **리스크 관리**: 일일/월간 손실 한도, 드라이런 모드 등 안전장치 내장

---

## 🌟 주요 기능

### 📊 정량 시그널 분석
- **장단기 금리차 추세 추종**: 금리 곡선의 변화를 통해 경기 사이클 판단
  - DGS10 - DGS2 스프레드 계산
  - 20일/120일 이동평균으로 단기/장기 추세 파악
  - 200일 이동평균으로 금리 대세 판단
  - 4가지 국면: Bull/Bear Steepening, Bull/Bear Flattening
- **실질 금리 계산**: 명목 금리에서 인플레이션을 차감한 실제 수익률 분석
  - 계산식: DGS10 (명목 금리) - CPI 증가율 (연율화)
- **테일러 준칙 신호**: 연준의 목표 금리와 현재 금리 차이 분석
  - 계산식: Target_Rate - FEDFUNDS (현재 연준 금리)
  - Target_Rate = r* + π + 0.5(π - π*) + 0.5(y - y*)
- **연준 순유동성**: 시장에 실제 공급된 유동성 추적
  - 계산식: WALCL (연준 자산) - WTREGEN (재무부 일반계정) - RRPONTSYD (역레포)
  - 이동평균 추세로 유동성 공급 방향 판단
- **하이일드 스프레드**: 유동성 위기 조기 감지
  - BAMLH0A0HYM2 지표 기반 Greed/Fear/Panic 구간 판단
  - 전주 대비 변화율로 위험 심리 변화 추적
- **물가 지표**: 인플레이션 추이 분석
  - Core PCE (PCEPILFE): 지난 10개 데이터를 날짜와 함께 제공
  - CPI (CPIAUCSL): 지난 10개 데이터를 날짜와 함께 제공
- **고용 지표**: 노동 시장 동향 분석
  - 실업률 (UNRATE): 지난 10개 데이터를 날짜와 함께 제공
  - 비농업 고용 (PAYEMS): 지난 10개 데이터를 날짜와 함께 제공

### 📰 정성 분석
- **경제 뉴스 수집**: TradingEconomics에서 지난 1주일간 특정 국가 뉴스 자동 수집
  - 필터링 국가: Crypto, Commodity, Euro Area, China, United States
  - 1시간마다 자동 수집하여 DB에 저장
- **LLM 요약**: Gemini AI가 뉴스를 분석하여 핵심 정책 변화점 추출
  - AI 전략가 분석 시 지난 1주일간 필터링된 국가 뉴스만 사용
  - 정량 시그널에 비해 낮은 비중으로 참고
- **이벤트 추적**: CPI, FOMC, 실업률 등 주요 경제 이벤트 모니터링

### 🤖 AI 전략가
- **LangGraph 기반 워크플로우**: 순차적 실행 보장 및 에러 핸들링 개선
- **종합 판단**: FRED 정량 시그널 + 물가 지표 + 경제 뉴스를 종합하여 포트폴리오 목표 비중 결정
- **자산군별 배분**: 주식(Stocks), 채권(Bonds), 대체투자(Alternatives), 현금(Cash) 최적 비중 산출
- **JSON 구조화 출력**: Pydantic을 통한 엄격한 스키마 검증

#### AI 분석 워크플로우 (LangGraph)
```
START
  ↓
[1] FRED 시그널 수집
  ↓
[2] 경제 뉴스 수집 (지난 20일, 특정 국가)
  ↓
[3] 뉴스 LLM 요약 (gemini-3.0-pro)
  ↓
[4] AI 분석 및 전략 결정 (gemini-3-pro-preview)
  ↓
[5] 결과 저장
  ↓
END
```

**각 단계 설명:**
1. **FRED 시그널 수집**: 금리차, 실질금리, 테일러준칙, 유동성, 하이일드 스프레드, 물가/고용 지표 계산
2. **경제 뉴스 수집**: 지난 20일간 Crypto, Commodity, Euro Area, China, United States 국가 뉴스 수집
3. **뉴스 LLM 요약**: gemini-3.0-pro로 주요 경제 지표 변화, 경제 흐름, 주요 이벤트 도출 및 요약
4. **AI 분석**: 정제된 뉴스 요약과 FRED 시그널을 종합하여 포트폴리오 목표 비중 결정
5. **결과 저장**: AI 의사결정을 DB에 저장하여 리밸런싱 봇이 참조

### ⚙️ 자동 실행
- **임계값 기반 리밸런싱**: 목표 비중과 실제 비중의 편차가 5% 이상일 때 자동 실행
- **스마트 매매**: 매도 우선 → 매수 실행 순서로 거래 비용 최소화
- **안전장치**: 일일/월간 손실 한도, 수동 승인 모드, 드라이런 모드

---

## 🏗️ 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    Stockoverflow Trading System             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  모듈 1:     │  │  모듈 2:     │  │  모듈 3:     │     │
│  │  정량 시그널 │  │  정성 분석   │  │  계좌 손익   │     │
│  │  (FRED API)  │  │  (뉴스 수집) │  │  (KIS API)   │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                  │                  │            │
│         └──────────────────┼──────────────────┘            │
│                            │                                │
│                   ┌────────▼────────┐                       │
│                   │  모듈 4:       │                       │
│                   │  AI 전략가     │                       │
│                   │  (Gemini LLM)  │                       │
│                   └────────┬───────┘                       │
│                            │                                │
│                   ┌────────▼────────┐                       │
│                   │  모듈 5:       │                       │
│                   │  리밸런싱 봇   │                       │
│                   │  (KIS API)     │                       │
│                   └─────────────────┘                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 데이터 흐름

1. **데이터 수집** (매일 09:00)
   - FRED API: 금리, 인플레이션, 유동성 지표
   - TradingEconomics: 경제 뉴스 (1시간마다)
   - KIS API: 계좌 상태 및 손익

2. **AI 분석** (매일 08:30) - LangGraph 워크플로우
   - FRED 정량 시그널 계산
   - 지난 20일간 특정 국가 뉴스 수집
   - 뉴스 LLM 요약 (gemini-3.0-pro)
   - 종합 분석 및 포트폴리오 목표 비중 결정 (gemini-3-pro-preview)
   - 결과 저장

3. **자동 실행** (15:00)
   - 편차 계산 (목표 vs 실제)
   - 임계값(5%) 초과 시 리밸런싱 실행
   - 거래 이력 저장

---

## 🛠️ 기술 스택

### Backend
- **FastAPI**: 고성능 비동기 웹 프레임워크
- **Python 3.12+**: 메인 프로그래밍 언어
- **MySQL**: 데이터 영구 저장 (거시경제 지표, 뉴스, 거래 이력)
- **Pydantic V2**: 설정 및 데이터 검증
- **Selenium**: JavaScript 렌더링이 필요한 웹 크롤링

### AI/ML
- **Google Gemini 3.0 Pro**: 뉴스 요약 및 정제
- **Google Gemini 3 Pro Preview**: 포트폴리오 전략 결정
- **LangChain**: LLM 통합 및 프롬프트 관리
- **LangGraph**: 워크플로우 관리 및 순차 실행 보장

### 데이터 소스
- **FRED API**: 연준 거시경제 지표 (금리, 인플레이션, 유동성)
- **TradingEconomics**: 경제 뉴스 및 이벤트
- **KIS API**: 한국투자증권 계좌 조회 및 매매

### 인프라
- **AWS EC2**: 서버 호스팅
- **Gunicorn + Uvicorn**: 프로덕션 ASGI 서버
- **Schedule**: 작업 스케줄링

### 주요 라이브러리
```python
# 데이터 처리
pandas, numpy          # 데이터 분석 및 계산
fredapi               # FRED API 클라이언트
beautifulsoup4        # 웹 크롤링
selenium              # JavaScript 렌더링
webdriver-manager     # ChromeDriver 자동 관리

# 데이터베이스
pymysql               # MySQL 연결

# AI/LLM
langchain-google-genai # Gemini 통합
```

---

## 📁 프로젝트 구조

```
hobot-service/
├── hobot/
│   ├── main.py                          # FastAPI 애플리케이션
│   ├── service/
│   │   ├── macro_trading/              # 거시경제 자동매매 모듈
│   │   │   ├── collectors/            # 데이터 수집
│   │   │   │   ├── fred_collector.py  # FRED API 수집기
│   │   │   │   └── news_collector.py  # 경제 뉴스 수집기
│   │   │   ├── signals/               # 정량 시그널 계산
│   │   │   │   └── quant_signals.py   # 금리차, 실질금리, 테일러준칙 등
│   │   │   ├── config/                # 설정 관리
│   │   │   │   └── config_loader.py   # Pydantic 기반 설정 검증
│   │   │   ├── scheduler.py           # 자동 스케줄러
│   │   │   └── scripts/               # 초기 데이터 적재
│   │   ├── database/                  # 데이터베이스 관리
│   │   │   └── db.py                  # MySQL 연결 및 초기화
│   │   └── kis/                       # 한국투자증권 API
│   ├── requirements.txt               # Python 의존성
│   └── docs/
│       └── macro-trading/             # 상세 문서
│           ├── implementation_plan.md # 구현 계획서
│           └── database_schema.sql    # DB 스키마
```

---

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 저장소 클론
git clone <repository-url>
cd hobot-service/hobot

# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate    # Windows

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일 생성:

```env
# FRED API
FRED_API_KEY=your_fred_api_key

# 데이터베이스
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=hobot

# Gemini API
GOOGLE_API_KEY=your_google_api_key

# KIS API
KIS_APP_KEY=your_kis_app_key
KIS_APP_SECRET=your_kis_app_secret
```

### 3. 데이터베이스 초기화

```bash
# 데이터베이스 스키마 생성
mysql -u root -p < docs/macro-trading/database_schema.sql

# 초기 데이터 적재 (FRED 5년치 + 뉴스 48시간)
python -m service.macro_trading.scripts.initial_data_load
```

### 4. 서버 실행

```bash
# 개발 모드
./start_dev.sh

# 프로덕션 모드
./start_server.sh
```

---

## 📡 API 엔드포인트

**기본 URL**: `https://stockoverflow.org`

### 거시경제 데이터

- `GET /api/macro-trading/quantitative-signals`  
  정량 시그널 조회 (장단기 금리차, 실질금리, 테일러준칙, 유동성 등)  
  예시: `https://stockoverflow.org/api/macro-trading/quantitative-signals`

- `GET /api/macro-trading/economic-news?hours=24`  
  최근 N시간 내 경제 뉴스 조회  
  예시: `https://stockoverflow.org/api/macro-trading/economic-news?hours=24`

- `GET /api/macro-trading/fred-data`  
  FRED 지표 데이터 조회  
  예시: `https://stockoverflow.org/api/macro-trading/fred-data?indicator_code=DGS10&days=365`

### 계좌 및 거래

- `GET /api/macro-trading/account-snapshots`  
  계좌 상태 스냅샷 조회  
  예시: `https://stockoverflow.org/api/macro-trading/account-snapshots`

- `GET /api/macro-trading/rebalancing-history`  
  리밸런싱 실행 이력 조회  
  예시: `https://stockoverflow.org/api/macro-trading/rebalancing-history`

### API 문서
- `GET /docs` - Swagger UI  
  예시: `https://stockoverflow.org/docs`
- `GET /redoc` - ReDoc  
  예시: `https://stockoverflow.org/redoc`

---

## 🔧 주요 모듈 설명

### 1. 정량 시그널 계산 (`signals/quant_signals.py`)

거시경제 지표를 기반으로 투자 시그널을 계산합니다.

**지원 시그널:**
- 장단기 금리차 추세 추종 (Bull/Bear Steepening/Flattening)
- 실질 금리 (명목 금리 - 인플레이션)
- 테일러 준칙 신호
- 연준 순유동성 (WALCL - TGA - RRP)
- 하이일드 스프레드 (Greed/Fear/Panic 구간)

### 2. 데이터 수집 (`collectors/`)

**FRED Collector:**
- 연준 거시경제 지표 자동 수집
- 중복 방지 및 데이터 보간
- 매일 09:00 자동 실행

**News Collector:**
- TradingEconomics 뉴스 수집
- Selenium을 통한 JavaScript 렌더링
- 1시간마다 자동 실행

### 3. AI 전략가 (LangGraph 기반)

LangGraph를 사용하여 워크플로우를 관리하며, Gemini LLM이 FRED 정량 시그널, 물가 지표, 정제된 경제 뉴스를 종합하여 포트폴리오 목표 비중을 결정합니다.

**워크플로우:**
- **노드 1 (collect_fred)**: FRED 정량 시그널 수집
- **노드 2 (collect_news)**: 경제 뉴스 수집 (지난 20일, 특정 국가)
- **노드 3 (summarize_news)**: 뉴스 LLM 요약 (gemini-3.0-pro)
- **노드 4 (analyze)**: AI 분석 및 전략 결정 (gemini-3-pro-preview)
- **노드 5 (save_decision)**: 결과 저장

**입력:**
- FRED 정량 시그널 (금리차, 실질금리, 유동성 등)
- 물가 지표 (Core PCE, CPI) - 지난 10개 데이터
- 고용 지표 (실업률, 비농업 고용) - 지난 10개 데이터
- 정제된 경제 뉴스 요약 (LLM으로 주요 지표 변화, 흐름, 이벤트 도출)

**출력:**
- 자산군별 목표 비중 (Stocks, Bonds, Alternatives, Cash)
- 분석 요약 및 판단 근거
- 자산군별 추천 섹터/카테고리

### 4. 리밸런싱 봇 (예정)

목표 비중과 실제 비중의 편차가 임계값(5%)을 초과하면 자동으로 리밸런싱을 실행합니다.

---

## 📊 데이터베이스 스키마

### 핵심 테이블

- `fred_data`: FRED 거시경제 지표 (금리, 인플레이션, 유동성)
- `economic_news`: TradingEconomics 뉴스
- `ai_strategy_decisions`: AI가 결정한 포트폴리오 목표 비중
- `rebalancing_history`: 리밸런싱 실행 이력
- `account_snapshots`: 일별 계좌 상태 스냅샷

상세 스키마는 [`docs/macro-trading/database_schema.sql`](hobot/docs/macro-trading/database_schema.sql) 참고

---

## 🔐 보안 및 안전장치

- **손실 한도**: 일일 5%, 월간 15% 손실 시 자동 중지
- **수동 승인 모드**: 중요한 거래는 수동 승인 필요
- **드라이런 모드**: 실제 매매 없이 시뮬레이션만 실행
- **로그 기록**: 모든 거래 및 의사결정 이력 저장

---

## 📈 성과 추적

- **계좌 스냅샷**: 매일 자동으로 계좌 상태 저장
- **리밸런싱 이력**: 모든 거래 내역 및 편차 추적
- **AI 의사결정 이력**: 전략 변경 이유 및 분석 요약 저장

---

## 🧪 테스트

```bash
# 정량 시그널 계산 테스트 (DB 없이)
python -m service.macro_trading.tests.test_quant_signals_no_db

# 뉴스 수집 테스트 (DB 없이)
python -m service.macro_trading.tests.test_news_collector_no_db

# 설정 파일 검증
python -m service.macro_trading.tests.test_config
```

---

## 📚 문서

- [구현 계획서](hobot/docs/macro-trading/implementation_plan.md) - 전체 개발 계획 및 진행 상황
- [데이터베이스 스키마](hobot/docs/macro-trading/database_schema.sql) - 테이블 구조
- [정량 시그널 설명](hobot/docs/macro-trading/quantitative_signals_description.md) - 각 시그널의 의미 및 해석
- [EC2 Selenium 설정](hobot/docs/macro-trading/EC2_SELENIUM_SETUP.md) - 서버 환경 설정 가이드

---

## 🎯 개발 로드맵

- [x] Phase 1: 기초 인프라 (DB, 설정, 로깅)
- [x] Phase 2: 데이터 수집 모듈 (FRED, 뉴스, 계좌)
- [ ] Phase 3: AI 전략가 (Gemini LLM 통합)
- [ ] Phase 4: 실행 봇 (자동 리밸런싱)
- [ ] Phase 5: 백테스팅 프레임워크
- [ ] Phase 6: 통합 및 테스트

---

## 🤝 기여하기

이슈를 생성하거나 Pull Request를 보내주세요!

---

## 📄 라이선스

MIT License

---

**Built with ❤️ for intelligent macro trading**
