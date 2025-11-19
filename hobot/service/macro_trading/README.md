# Macro Trading Module

거시경제 기반 자동매매 Agent 모듈

## 📁 디렉토리 구조

```
macro_trading/
├── __init__.py              # 메인 모듈 초기화 (공통 인터페이스)
├── config/                  # 설정 관리
│   ├── __init__.py
│   └── config_loader.py    # 설정 파일 로더 및 검증
├── collectors/              # 데이터 수집 모듈
│   ├── __init__.py
│   └── fred_collector.py   # FRED API 데이터 수집
├── signals/                 # 정량 시그널 계산
│   ├── __init__.py
│   └── quant_signals.py    # 정량 시그널 계산 (장단기 금리차, 실질 금리, 테일러 준칙)
└── tests/                   # 테스트 스크립트
    ├── __init__.py
    ├── test_config.py      # 설정 파일 테스트
    └── test_fred.py        # FRED API 테스트
```

## 📦 모듈 설명

### 1. Config (`config/`)
설정 파일 관리 및 검증

**주요 기능:**
- `config/macro_trading_config.json` 파일 로드
- Pydantic V2 기반 스키마 검증
- 설정 캐싱 및 재로드

**사용 예시:**
```python
from service.macro_trading import get_config

config = get_config()
print(config.rebalancing.threshold)  # 5.0
```

### 2. Collectors (`collectors/`)
외부 데이터 소스에서 데이터 수집

**주요 기능:**
- FRED API를 통한 거시경제 지표 수집
- 데이터베이스 저장 (중복 방지)
- 최신 데이터 조회

**사용 예시:**
```python
from service.macro_trading import get_fred_collector

collector = get_fred_collector()
collector.test_connection()  # 연결 테스트
results = collector.collect_all_indicators()  # 모든 지표 수집
```

### 3. Signals (`signals/`)
정량 시그널 계산

**주요 기능:**
- 장단기 금리차 계산 (DGS10 - DGS2)
- 실질 금리 계산 (DGS10 - CPI 증가율)
- 테일러 준칙 신호 계산

**사용 예시:**
```python
from service.macro_trading import QuantSignalCalculator

calculator = QuantSignalCalculator()
signals = calculator.calculate_all_signals()
print(signals['yield_curve_spread'])  # 장단기 금리차
```

### 4. Tests (`tests/`)
테스트 스크립트

**실행 방법:**
```bash
# 설정 파일 테스트
python service/macro_trading/tests/test_config.py

# FRED API 테스트
python service/macro_trading/tests/test_fred.py
```

## 🔧 환경 설정

### 필수 환경 변수
`.env` 파일에 다음을 설정하세요:

```env
# FRED API
FRED_API_KEY=your_fred_api_key_here

# 데이터베이스 (기존 설정 사용)
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=hobot
```

### 필수 패키지
```bash
pip install fredapi pandas numpy pydantic
```

## 📝 사용 가이드

### 1. 설정 파일 확인
```python
from service.macro_trading import get_config

config = get_config()
print(f"리밸런싱 임계값: {config.rebalancing.threshold}%")
print(f"LLM 모델: {config.llm.model}")
```

### 2. FRED 데이터 수집
```python
from service.macro_trading import get_fred_collector
from datetime import date, timedelta

collector = get_fred_collector()

# 연결 테스트
if collector.test_connection():
    # 최근 30일 데이터 수집
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    results = collector.collect_all_indicators(start_date, end_date)
    print(f"수집 완료: {results}")
```

### 3. 정량 시그널 계산
```python
from service.macro_trading import QuantSignalCalculator

calculator = QuantSignalCalculator()

# 모든 시그널 계산
signals = calculator.calculate_all_signals(
    natural_rate=2.0,  # 자연 이자율
    target_inflation=2.0  # 목표 인플레이션율
)

print(f"장단기 금리차: {signals['yield_curve_spread']}%")
print(f"실질 금리: {signals['real_interest_rate']}%")
print(f"테일러 준칙 신호: {signals['taylor_rule_signal']}%")
```

## 🚀 다음 단계

- [ ] Phase 2.2: 정성 분석 모듈 (LLM 기반)
- [ ] Phase 2.3: 내부 데이터 모듈 (계좌 손익)
- [ ] Phase 3: AI 전략가 모듈
- [ ] Phase 4: 실행 봇 모듈

## 📚 관련 문서

- [구현 계획서](../../docs/macro-trading/implementation_plan.md)
- [데이터베이스 스키마](../../docs/macro-trading/database_schema.sql)

