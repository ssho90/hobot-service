# FRED 데이터 및 경제 뉴스 초기 적재 가이드

## 📊 초기 적재가 필요한 데이터

시스템을 처음 실행할 때, 다음 데이터들이 DB에 저장되어 있어야 정량 시그널 계산과 AI 전략가가 정상적으로 작동합니다.

### 필수 데이터 (최소 250일 이상)

**장단기 금리차 추세 추종 전략**을 위해서는 최소 **250일** 이상의 과거 데이터가 필요합니다:

1. **DGS10** (미국 10년 국채 금리)
   - 최소 필요: 250일
   - 이유: 200일 이동평균 계산을 위해

2. **DGS2** (미국 2년 국채 금리)
   - 최소 필요: 250일
   - 이유: Spread 계산 및 이동평균 계산을 위해

### 권장 데이터 (과거 5년 이상)

다른 정량 시그널 계산을 위해서는 다음 데이터들도 권장됩니다:

3. **FEDFUNDS** (연준 금리)
   - 테일러 준칙 계산에 필요

4. **CPIAUCSL** (CPI)
   - 실질 금리 계산에 필요
   - 월별 데이터이므로 과거 1-2년이면 충분

5. **PCEPI** (PCE)
   - 테일러 준칙 계산에 필요
   - 월별 데이터이므로 과거 1-2년이면 충분

6. **WALCL, WTREGEN, RRPONTSYD** (유동성 지표)
   - 연준 순유동성 계산에 필요
   - 주간/일별 데이터이므로 과거 1년이면 충분

7. **BAMLH0A0HYM2** (하이일드 스프레드)
   - 하이일드 스프레드 평가에 필요
   - 일별 데이터이므로 과거 1년이면 충분

8. **UNRATE, PAYEMS** (고용 지표)
   - 추가 지표로 사용
   - 월별 데이터이므로 과거 1-2년이면 충분

### 경제 뉴스 데이터

**TradingEconomics 스트림 뉴스**는 AI 전략가의 정성 분석에 사용됩니다:

- **최소 필요**: 최근 24-48시간 내 뉴스
- **권장**: 최근 48시간 내 뉴스
- **수집 주기**: 초기 적재 후 매 1시간마다 자동 수집
- **데이터 소스**: TradingEconomics Stream (https://tradingeconomics.com/stream)

---

## 🚀 초기 적재 실행 방법

### 방법 1: 초기 적재 스크립트 실행 (권장)

**FRED 데이터 + 뉴스 동시 수집 (기본값):**
```bash
cd hobot
python -m service.macro_trading.scripts.initial_data_load
```

이 명령은 다음을 수행합니다:
- FRED 데이터: 과거 5년 수집 (기본값)
- 경제 뉴스: 최근 48시간 수집 (기본값, Selenium 사용)

**과거 10년 FRED 데이터 + 뉴스 수집:**
```bash
python -m service.macro_trading.scripts.initial_data_load --years 10
```

**뉴스만 수집 (FRED 건너뛰기):**
```bash
python -m service.macro_trading.scripts.initial_data_load --skip-fred
```

**FRED만 수집 (뉴스 건너뛰기):**
```bash
python -m service.macro_trading.scripts.initial_data_load --skip-news
```

**뉴스 수집 시간 범위 지정:**
```bash
# 최근 24시간 뉴스만 수집
python -m service.macro_trading.scripts.initial_data_load --news-hours 24

# 최근 72시간 뉴스 수집
python -m service.macro_trading.scripts.initial_data_load --news-hours 72
```

**Selenium 없이 뉴스 수집 (requests만 사용):**
```bash
# 주의: JavaScript 렌더링이 필요한 페이지이므로 뉴스를 가져오지 못할 수 있습니다.
python -m service.macro_trading.scripts.initial_data_load --no-selenium
```

**모든 옵션 조합 예시:**
```bash
# 과거 10년 FRED + 최근 24시간 뉴스 (Selenium 사용)
python -m service.macro_trading.scripts.initial_data_load --years 10 --news-hours 24
```

### 방법 2: Python 스크립트로 직접 실행

**FRED 데이터 수집:**
```python
from service.macro_trading.collectors.fred_collector import get_fred_collector
from datetime import date, timedelta

collector = get_fred_collector()

# 과거 5년 데이터 수집
end_date = date.today()
start_date = end_date - timedelta(days=5 * 365)

results = collector.collect_all_indicators(
    start_date=start_date,
    end_date=end_date,
    skip_existing=True
)

print("수집 결과:")
for indicator, count in results.items():
    print(f"  {indicator}: {count}개")
```

**경제 뉴스 수집:**
```python
from service.macro_trading.collectors.news_collector import get_news_collector

collector = get_news_collector()

# 최근 48시간 뉴스 수집 (Selenium 사용)
saved, skipped = collector.collect_recent_news(hours=48, use_selenium=True)

print(f"수집 결과: {saved}개 저장, {skipped}개 건너뜀")
```

### 방법 3: 스케줄러 함수 직접 호출

**FRED 데이터 수집:**
```python
from service.macro_trading.scheduler import collect_all_fred_data

# 즉시 실행 (스케줄 대기 없이)
results = collect_all_fred_data()
```

**경제 뉴스 수집:**
```python
from service.macro_trading.scheduler import collect_recent_news

# 최근 2시간 뉴스 수집 (스케줄러 기본값)
saved, skipped = collect_recent_news()
```

---

## ⚙️ 실행 전 확인 사항

1. **환경변수 설정**
   ```bash
   # .env 파일에 다음이 설정되어 있는지 확인
   FRED_API_KEY=your_api_key_here
   
   # 데이터베이스 연결 정보
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_password
   DB_NAME=hobot
   ```

2. **데이터베이스 연결 확인**
   - MySQL 데이터베이스가 실행 중인지 확인
   - `fred_data` 테이블이 생성되어 있는지 확인
   - `economic_news` 테이블이 생성되어 있는지 확인

3. **필요 패키지 설치**
   ```bash
   pip install fredapi pandas numpy pymysql python-dotenv
   pip install selenium beautifulsoup4 requests
   pip install webdriver-manager  # ChromeDriver 자동 관리
   ```

4. **Selenium 환경 (뉴스 수집 시)**
   - Chrome 브라우저가 설치되어 있어야 합니다
   - `webdriver-manager`가 자동으로 ChromeDriver를 다운로드합니다
   - EC2 환경에서는 추가 설정이 필요할 수 있습니다 (참고: [EC2_SELENIUM_SETUP.md](./EC2_SELENIUM_SETUP.md))

---

## 📈 예상 소요 시간

### FRED 데이터 수집
- **과거 1년 데이터**: 약 5-10분
- **과거 5년 데이터**: 약 20-30분
- **과거 10년 데이터**: 약 40-60분

*FRED API 호출 제한과 네트워크 속도에 따라 달라질 수 있습니다.*

### 경제 뉴스 수집
- **최근 24시간 뉴스**: 약 2-5분
- **최근 48시간 뉴스**: 약 3-7분
- **최근 72시간 뉴스**: 약 5-10분

*Selenium을 사용하여 JavaScript 렌더링이 필요한 페이지를 크롤링하므로 시간이 걸릴 수 있습니다.*

---

## ✅ 초기 적재 완료 확인

초기 적재가 완료되면 다음을 확인하세요:

### FRED 데이터 확인

1. **데이터 개수 확인**
   ```sql
   SELECT indicator_code, COUNT(*) as count
   FROM fred_data
   GROUP BY indicator_code
   ORDER BY indicator_code;
   ```

2. **최소 데이터 요구사항 확인**
   ```sql
   -- DGS10 최근 250일 데이터 확인
   SELECT COUNT(*) as count
   FROM fred_data
   WHERE indicator_code = 'DGS10'
   AND date >= DATE_SUB(CURDATE(), INTERVAL 250 DAY);
   ```

3. **정량 시그널 계산 테스트**
   ```python
   from service.macro_trading.signals.quant_signals import QuantSignalCalculator
   
   calculator = QuantSignalCalculator()
   result = calculator.get_yield_curve_spread_trend_following()
   
   if result:
       print("✅ 정상 작동")
       print(f"현재 국면: {result['regime_kr']}")
   else:
       print("❌ 데이터 부족")
   ```

### 경제 뉴스 확인

1. **뉴스 개수 확인**
   ```sql
   SELECT COUNT(*) as total_count,
          COUNT(DISTINCT country) as country_count,
          COUNT(DISTINCT category) as category_count
   FROM economic_news;
   ```

2. **최근 24시간 뉴스 확인**
   ```sql
   SELECT COUNT(*) as count
   FROM economic_news
   WHERE published_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR);
   ```

3. **국가별 뉴스 분포 확인**
   ```sql
   SELECT country, COUNT(*) as count
   FROM economic_news
   WHERE published_at >= DATE_SUB(NOW(), INTERVAL 48 HOUR)
   GROUP BY country
   ORDER BY count DESC
   LIMIT 10;
   ```

4. **카테고리별 뉴스 분포 확인**
   ```sql
   SELECT category, COUNT(*) as count
   FROM economic_news
   WHERE published_at >= DATE_SUB(NOW(), INTERVAL 48 HOUR)
   GROUP BY category
   ORDER BY count DESC
   LIMIT 10;
   ```

5. **최신 뉴스 조회**
   ```sql
   SELECT title, country, category, published_at, link
   FROM economic_news
   ORDER BY published_at DESC
   LIMIT 10;
   ```

---

## 🔄 초기 적재 후

초기 적재가 완료되면:

1. **FRED 데이터**: 자동 스케줄러가 매일 09:00에 최신 데이터를 수집합니다.
2. **경제 뉴스**: 자동 스케줄러가 매 1시간마다 최신 뉴스를 수집합니다.
3. **중복 데이터는 자동으로 건너뛰므로** 초기 적재를 여러 번 실행해도 안전합니다.
4. **정량 시그널 계산이 정상적으로 작동**합니다.
5. **AI 전략가가 뉴스 데이터를 활용하여 정성 분석을 수행**할 수 있습니다.

---

## ⚠️ 주의사항

### FRED API Rate Limit
- **분당 120회 요청 제한**: 코드에 자동으로 반영되어 요청 간 약 0.5초 딜레이가 적용됩니다.
- **요청당 최대 100,000개 관측치 제한**: 매우 긴 기간의 데이터 수집 시 경고가 표시됩니다.
- **Rate limit 오류 처리**: Rate limit 초과 시 자동으로 60초 대기 후 재시도합니다.

### 뉴스 수집 주의사항
- **Selenium 필수**: TradingEconomics Stream 페이지는 JavaScript로 동적 렌더링되므로 Selenium이 필요합니다.
- **Chrome 브라우저 필요**: Chrome이 설치되어 있어야 하며, `webdriver-manager`가 자동으로 ChromeDriver를 관리합니다.
- **EC2 환경**: EC2에서 실행 시 Chrome 및 관련 라이브러리 설치가 필요할 수 있습니다 (참고: [EC2_SELENIUM_SETUP.md](./EC2_SELENIUM_SETUP.md)).
- **중복 방지**: 동일한 제목과 링크를 가진 뉴스는 자동으로 건너뜁니다 (`UNIQUE KEY unique_title_link`).
- **네트워크 지연**: 페이지 로딩 및 JavaScript 렌더링으로 인해 시간이 걸릴 수 있습니다.

### 기타 주의사항
- 초기 적재 시 많은 데이터를 수집하므로 시간이 걸릴 수 있습니다 (FRED: 약 20-30분, 뉴스: 약 3-7분).
- 네트워크 연결이 불안정한 경우 재시도가 필요할 수 있습니다.
- 데이터 수집 실패 시 로그를 확인하고 필요시 재실행하세요.
- 초기 적재 스크립트는 요청 간 0.6초 딜레이를 사용하여 rate limit을 안전하게 준수합니다.

---

## 🐛 문제 해결

### FRED 데이터 관련

**"FRED API 키가 설정되지 않았습니다" 오류**
- `.env` 파일에 `FRED_API_KEY`를 설정하세요.

**"데이터베이스 연결 실패" 오류**
- MySQL 서버가 실행 중인지 확인하세요.
- 데이터베이스 연결 정보를 확인하세요.

**"데이터가 부족합니다" 경고**
- 초기 적재를 더 긴 기간으로 실행하세요 (예: `--years 10`).
- 또는 수동으로 해당 지표만 추가 수집하세요.

### 뉴스 수집 관련

**"Selenium이 설치되지 않았습니다" 오류**
```bash
pip install selenium webdriver-manager
```

**"ChromeDriver를 찾을 수 없습니다" 오류**
- `webdriver-manager`가 자동으로 다운로드하지만, 실패 시:
  - Chrome 브라우저가 설치되어 있는지 확인
  - EC2 환경에서는 [EC2_SELENIUM_SETUP.md](./EC2_SELENIUM_SETUP.md) 참고

**"뉴스를 한 건도 가져오지 못했습니다"**
- TradingEconomics 페이지 구조가 변경되었을 수 있습니다.
- Selenium이 제대로 작동하는지 확인:
  ```bash
  python -m service.macro_trading.tests.test_news_collector_no_db
  ```
- 네트워크 연결 및 방화벽 설정 확인

**"Service chromedriver unexpectedly exited. Status code was: 127" (EC2)**
- Chrome 및 필수 라이브러리가 설치되지 않았을 수 있습니다.
- [EC2_SELENIUM_SETUP.md](./EC2_SELENIUM_SETUP.md)의 설치 가이드를 따르세요.

**뉴스 수집이 느립니다**
- Selenium을 사용한 JavaScript 렌더링으로 인해 시간이 걸립니다.
- 정상적인 현상이며, 뉴스 수집 시간 범위를 줄이면 더 빠릅니다 (예: `--news-hours 24`).

