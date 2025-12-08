# 거시경제 기반 자동매매 Agent 구현 계획서

> 이 문서는 실제 구현 작업을 추적하고 관리하기 위한 작업 계획서입니다.
> 각 작업 항목에 대해 의견을 주고받으며 진행합니다.

**최종 업데이트**: 2024-12-19  
**현재 Phase**: Phase 1 (기초 인프라)  
**상태**: 검토 의견 반영 완료, 구현 준비 완료

---

## 🌐 Hobot Web Site 컨텐츠 구조

### 1. Macro Dashboard
- **Overview**
  - FRED 지표와 Economic News를 조합하여 LLM으로 현재 거시경제 상황 분석
  - LLM 분석 결과를 Overview에 출력
  - 관련 API 엔드포인트: `/api/macro-trading/economic-news`, `/api/macro-trading/quantitative-signals`
- **FRED 지표**
  - Tradingview Lightweight Charts를 사용한 시각화 (이미 구현 완료)
  - 장단기 금리차, 실질 금리, 테일러 준칙, 순유동성, 하이일드 스프레드 등 지표 표시
  - 관련 API 엔드포인트: `/api/macro-trading/fred-data`, `/api/macro-trading/yield-curve-spread`
- **Economic News**
  - TradingEconomics 스트림 뉴스 표시
  - 최근 24시간 내 경제 뉴스 조회 및 표시
  - 국가별, 카테고리별 필터링 기능
  - 관련 API 엔드포인트: `/api/macro-trading/economic-news`, `/api/macro-trading/economic-news-data`

### 2. Trading Dashboard
- **Macro Quant Trading**
  - 한국투자증권 API 연동 상태 표시
  - 현재 계좌 잔액 및 보유 자산 표시 (`/api/kis/balance`)
  - Macro 지표에 따른 자동 리밸런싱 상태 모니터링
  - 리밸런싱 이력 표시 (`/api/macro-trading/rebalancing-history`)
  - 계좌 스냅샷 조회 (`/api/macro-trading/account-snapshots`)
- **Crypto Auto Trading**
  - Upbit API 연동 상태 표시 (`/api/health`)
  - 현재 포지션 및 전략 상태 표시 (`/api/current-strategy`)
  - 자동매매 실행 이력 표시

### 3. Admin 메뉴
- **사용자 관리**
  - 사용자 목록 조회 (`/api/admin/users`)
  - 사용자 추가/수정/삭제 (`/api/admin/users/{user_id}`)
  - 권한 관리 (admin/user)
- **로그 관리**
  - 백엔드 로그 조회 (`/api/admin/logs?log_type=backend`)
  - 프론트엔드 로그 조회 (`/api/admin/logs?log_type=frontend`)
  - nginx 로그 조회 (`/api/admin/logs?log_type=nginx`)
  - 로그 필터링 (시간, 레벨, 모듈별)

---

## 📊 전체 진행 상황

- [ ] Phase 1: 기초 인프라
  - [x] 1.1 데이터베이스 스키마 설계 및 생성
  - [x] 1.2 설정 파일 구조 설계
  - [ ] 1.3 로깅 및 모니터링 시스템 구축
  - [ ] 1.4 기본 에러 핸들링
- [ ] Phase 2: 데이터 수집 모듈
- [ ] Phase 3: AI 전략가
- [ ] Phase 4: 실행 봇
- [ ] Phase 5: 백테스팅
- [ ] Phase 6: 통합 및 테스트

---

## Phase 1: 기초 인프라 (1-2주)

### 1.1 데이터베이스 스키마 설계 및 생성

#### 작업 항목
- [x] **1.1.1** MySQL 데이터베이스 스키마 설계
  - [x] `ai_strategy_decisions` 테이블 생성
  - [x] `rebalancing_history` 테이블 생성
  - [x] `account_snapshots` 테이블 생성
  - [x] `economic_events` 테이블 생성
  - [x] `fred_data` 테이블 생성 (금리 데이터 저장용)
  - [x] `etf_price_history` 테이블 생성 (백테스팅용)
  - [x] `system_logs` 테이블 생성 (모듈별 실행 로그)

#### 테이블별 역할 설명

**1. `ai_strategy_decisions`**
- **역할**: AI 전략가(모듈 4)가 결정한 포트폴리오 목표 비중을 저장
- **주요 데이터**: 
  - 분석 요약 (analysis_summary)
  - 목표 비중 (target_allocation JSON)
  - 입력 데이터 (FRED 정량 시그널, 물가 지표, 경제 뉴스)
- **사용처**: 모듈 5에서 리밸런싱 시 최신 목표 비중을 참조

**2. `rebalancing_history`**
- **역할**: 실제 리밸런싱 실행 이력을 저장
- **주요 데이터**:
  - 실행 날짜/시간
  - 사용된 임계값
  - 실행 전/후 편차 (drift_before, drift_after)
  - 실제 거래 내역 (trades_executed JSON)
- **사용처**: 성과 분석, 백테스팅 검증, 거래 이력 추적

**3. `account_snapshots`**
- **역할**: 매일 계좌 상태를 스냅샷으로 저장
- **주요 데이터**:
  - 총 자산 가치
  - 실제 자산 배분 (allocation_actual JSON)
  - 자산군별 손익률 (pnl_by_asset JSON)
- **사용처**: 계좌 성과 추적 (AI 분석에는 사용하지 않음)

**4. `economic_events`**
- **역할**: 주요 경제 이벤트(CPI, FOMC, 실업률 등) 정보 저장
- **주요 데이터**:
  - 이벤트 날짜, 이름, 유형
  - 중요도 (HIGH, MEDIUM, LOW)
  - 예상값, 실제값
- **사용처**: 모듈 2에서 크롤링한 데이터 저장, 모듈 4에서 AI 분석 시 참조

**5. `fred_data`**
- **역할**: FRED API에서 수집한 금리 및 거시경제 지표 저장
- **주요 데이터**:
  - 지표 코드 (DGS10, DGS2, FEDFUNDS, CPI, PCE, WALCL, WTREGEN, RRPONTSYD, BAMLH0A0HYM2 등)
  - 날짜별 값
  - 데이터 출처 (FRED API)
- **사용처**: 모듈 1에서 정량 시그널 계산 시 사용, 중복 조회 방지
- **참고**: 유동성 평가 지표(WALCL, WTREGEN, RRPONTSYD, BAMLH0A0HYM2) 추가됨

**6. `etf_price_history`**
- **역할**: 백테스팅을 위한 과거 ETF 가격 데이터 저장
- **주요 데이터**:
  - ETF 티커
  - 날짜별 OHLCV 데이터
- **사용처**: 모듈 6 백테스팅 시 과거 가격 데이터 참조

**7. `system_logs`**
- **역할**: 각 모듈의 실행 로그 및 에러 로그 저장
- **주요 데이터**:
  - 모듈명
  - 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
  - 로그 메시지
  - 실행 시간
- **사용처**: 디버깅, 모니터링, 문제 추적

#### 의사결정 필요 사항
- [x] 각 테이블의 인덱스 전략 결정
  - `ai_strategy_decisions`: `decision_date` 인덱스 (최신 조회용)
  - `rebalancing_history`: `execution_date` 인덱스
  - `account_snapshots`: `snapshot_date` UNIQUE 인덱스 (중복 방지)
  - `economic_events`: `event_date`, `event_type` 복합 인덱스
  - `fred_data`: `indicator_code`, `date` 복합 인덱스
  - `etf_price_history`: `ticker`, `date` 복합 인덱스
  - `system_logs`: `module_name`, `log_level`, `created_at` 인덱스
- [x] JSON 컬럼 vs 별도 테이블 정규화 여부 결정
  - **결정**: JSON 컬럼 사용 (유연성 및 조회 편의성)
- [x] 데이터 보관 기간 정책 결정
  - **결정**: 무제한 보관

#### 질문/의견


---

### 1.2 설정 파일 구조 설계

#### 작업 항목
- [x] **1.2.1** 설정 파일 생성 (`config/macro_trading_config.json`)
  - [x] 리밸런싱 설정 (임계값, 실행 시간, 최소 거래 금액, 여유 자금 비율)
  - [x] ETF 매핑 설정 (자산군별 티커 및 비중)
  - [x] LLM 설정 (모델, temperature, max_tokens)
  - [x] FRED API 설정 (캐시 기간)
  - [x] 스케줄 설정 (계좌 조회, LLM 분석, 리밸런싱 실행 시간)
  - [x] **유동성 평가 설정** (순유동성 이동평균 기간, 하이일드 스프레드 임계값)
  - [x] 안전장치 설정 (최대 손실 한도, 수동 승인 모드, 드라이런 모드)
  - [x] 설정 파일 JSON 스키마 정의 및 검증 로직 구현
    - [x] Pydantic 모델로 스키마 정의 (`service/macro_trading/config_loader.py`)
    - [x] 설정 파일 로더 클래스 구현
    - [x] 검증 로직 구현 (시간 형식, 비중 합계 등)
    - [x] 테스트 스크립트 작성 및 검증 완료

#### 설정 파일 예시 구조
```json
{
  "rebalancing": {
    "threshold": 5.0,
    "execution_time": "15:00",
    "min_trade_amount": 100000,
    "cash_reserve_ratio": 0.03
  },
  "etf_mapping": {
    "stocks": {
      "tickers": ["360750", "133690", "069500"],
      "weights": [0.333, 0.333, 0.333],
      "names": ["TIGER 미국 S&P500", "TIGER 미국나스닥100", "KODEX 200"]
    },
    "alternatives": {
      "tickers": ["132030", "138230"],
      "weights": [0.7, 0.3],
      "names": ["KODEX 골드선물(H)", "KODEX 미국달러선물"]
    },
    "cash": {
      "tickers": ["130730", "114260"],
      "weights": [0.5, 0.5],
      "names": ["TIGER CD금리투자KIS", "KODEX KOFR금리액티브"]
    }
  },
  "llm": {
    "model": "gemini-2.5-pro",
    "temperature": 0.0,
    "max_tokens": 5000
  },
  "schedules": {
    "account_check": ["09:10", "14:40"],
    "llm_analysis": ["09:10", "14:40"],
    "rebalancing": ["15:00"]
  },
  "fred": {
    "cache_duration_hours": 24
  },
  "liquidity": {
    "net_liquidity_ma_weeks": 4,
    "high_yield_spread_thresholds": {
      "greed": 3.5,
      "fear": 5.0,
      "panic": 10.0
    }
  },
  "safety": {
    "max_daily_loss_percent": 5.0,
    "max_monthly_loss_percent": 15.0,
    "manual_approval_required": false,
    "dry_run_mode": false
  }
}
```

#### 의사결정 필요 사항
- [x] 설정 파일 위치: `config/` 디렉토리 (결정 완료)
- [x] 설정 변경 시 재시작 필요 여부: 배포 시 자동 반영 (결정 완료)

---

### 1.3 로깅 및 모니터링 시스템 구축

#### 작업 항목
- [x] **1.3.1** 로깅 시스템 구현
  - [x] Python `logging` 모듈 설정 (main.py에 구현 완료)
  - [x] 로그 레벨별 분리 (DEBUG, INFO, WARNING, ERROR)
  - [x] DB 로깅 함수 구현 (`system_logs` 테이블에 저장) - service/utils/logger.py 구현 완료
  - [x] 파일 로깅 (log.txt, logs/access.log, logs/error.log)

- [x] **1.3.2** 모니터링 시스템 구현
  - [x] 각 모듈별 헬스체크 함수 구현 (/api/health, /api/kis/health)
  - [x] API 연결 상태 확인 (FRED, KIS, Gemini)

- [x] **1.3.3** Hobot Web Site 컨텐츠 구현
  - [x] **1.3.3.1** Macro Dashboard
    - [x] Overview 페이지 (화면 구성 완료, API는 추후 구현)
      - [x] FRED 지표와 Economic News를 조합하여 LLM으로 현재 거시경제 상황 분석 (화면 구성)
      - [x] LLM 분석 결과를 Overview에 출력 (화면 구성)
      - [ ] 관련 API 엔드포인트 구현 (추후 구현)
    - [x] FRED 지표 페이지
      - [x] Tradingview Lightweight Charts를 사용한 시각화 (이미 구현 완료)
      - [x] 장단기 금리차, 실질 금리, 테일러 준칙, 순유동성, 하이일드 스프레드 등 지표 표시
    - [x] Economic News 페이지 (화면 구성 완료)
      - [x] TradingEconomics 스트림 뉴스 표시
      - [x] 최근 24시간 내 경제 뉴스 조회 및 표시
      - [x] 국가별, 카테고리별 필터링 기능
  - [x] **1.3.3.2** Trading Dashboard (화면 구성 완료)
    - [x] Macro Quant Trading 페이지
      - [x] 한국투자증권 API 연동 상태 표시
      - [x] 현재 계좌 잔액 및 보유 자산 표시
      - [x] Macro 지표에 따른 자동 리밸런싱 상태 모니터링 (모니터링 탭으로 안내)
      - [x] 리밸런싱 이력 표시 (모니터링 탭으로 안내)
    - [x] Crypto Auto Trading 페이지
      - [x] Upbit API 연동 상태 표시
      - [x] 현재 포지션 및 전략 상태 표시
      - [ ] 자동매매 실행 이력 표시 (추후 구현)
  - [ ] **1.3.3.3** Admin 메뉴
    - [ ] 사용자 관리 페이지
      - [ ] 사용자 목록 조회
      - [ ] 사용자 추가/수정/삭제
      - [ ] 권한 관리 (admin/user)
    - [ ] 로그 관리 페이지
      - [ ] 백엔드 로그 조회
      - [ ] 프론트엔드 로그 조회
      - [ ] nginx 로그 조회
      - [ ] 로그 필터링 (시간, 레벨, 모듈별)

#### 의사결정 필요 사항
- [x] 로그 보관 기간: 7일, 파일 (결정 완료)
- [x] Slack 알림 빈도: 에러, 매매 실행, 매일 아침 시장동향 레포트 (결정 완료)

#### 추가 작업 항목
- [ ] **1.3.4** 로그 로테이션 정책 구현
  - [ ] 파일 크기 제한 (100MB)
  - [ ] 일별 로그 파일 분리
  - [ ] 압축 보관 정책

- [ ] **1.3.5** Macro Dashboard 상세 요구사항 정의
  - [x] 표시할 매크로 지표 목록 결정
    - [x] FRED 지표: 장단기 금리차, 실질 금리, 테일러 준칙, 순유동성, 하이일드 스프레드
    - [x] Economic News: TradingEconomics 스트림 뉴스
  - [x] 차트 라이브러리 선택: Tradingview Lightweight Charts (FRED 지표 추이, 주가 차트, 장단기 금리차 그래프, 환율 등 시계열 메인 차트) - 이미 구현 완료
  - [x] 업데이트 주기: 주기적 (1시간)
  - [x] 사용자 권한: 시계열 메인 차트는 모든 사람, 스냅샷 데이터는 관리자만

---

### 1.4 기본 에러 핸들링

#### 작업 항목
- [ ] **1.4.1** 공통 에러 핸들링 클래스 구현
  - [ ] 커스텀 예외 클래스 정의 (FatalError, CriticalError, WarningError, InfoError)
  - [ ] 재시도 로직 (exponential backoff: 1분 → 3분 → 5분)
  - [ ] 에러 발생 시 Slack 알림
  - [ ] 에러 로깅 및 DB 저장

- [ ] **1.4.2** 각 모듈별 에러 핸들링 전략 수립
  - [ ] 모듈 1: FRED API 장애 시 처리 (CriticalError, 3회 재시도)
  - [ ] 모듈 2: 크롤링 실패 시 처리 (WarningError, 2회 재시도)
  - [ ] 모듈 3: KIS API 장애 시 처리 (CriticalError, 3회 재시도)
  - [ ] 모듈 4: LLM API 장애 시 처리 (CriticalError, 3회 재시도 후 폴백 전략)
  - [ ] 모듈 5: 매매 실패 시 처리 (CriticalError, 즉시 알림)

#### 에러 구분 기준
- **FATAL (치명적)**: 시스템 중단 필요
  - DB 연결 실패
  - KIS API 인증 실패
  - 시스템 리소스 부족
- **CRITICAL (심각)**: 기능 수행 불가, 재시도 필요
  - FRED API 장애 (3회 재시도 실패)
  - LLM API 장애 (3회 재시도 실패)
  - 매매 실행 실패
- **WARNING (경고)**: 일부 기능 실패, 시스템은 계속 동작
  - 데이터 부족 (일부 지표만 수집 실패)
  - 크롤링 실패 (재시도 후 성공)
- **INFO (정보)**: 정상적인 작업 완료 로그

#### 의사결정 필요 사항
- [x] 재시도 횟수 및 간격: 3회, exponential backoff (1분 → 3분 → 5분) (결정 완료)
- [x] 치명적 에러 vs 경고성 에러 구분 기준: 4단계 구분 (결정 완료)

---

## Phase 2: 데이터 수집 모듈 (2-3주)

### 2.1 모듈 1: 정량 시그널 수집 (FRED API)

#### 작업 항목
- [x] **2.1.1** FRED API 연동
  - [x] `fredapi` 패키지 설치 및 테스트
  - [x] 환경변수에서 FRED API 키 로드 (`.env` 파일)
  - [x] API 연결 테스트 (`test_connection()` 메서드 구현 완료)

- [ ] **2.1.2** 금리 데이터 수집 및 저장
  - [x] DGS10 (미국 10년 국채 금리) 수집 및 저장
    - [x] `collect_yield_curve_data()` 메서드 구현 완료
    - [x] DB에 자동 저장 (`fred_data` 테이블)
    - [x] 중복 데이터 방지 (당일 데이터 존재 여부 확인)
  - [x] DGS2 (미국 2년 국채 금리) 수집 및 저장
    - [x] `collect_yield_curve_data()` 메서드 구현 완료
    - [x] DB에 자동 저장 (`fred_data` 테이블)
    - [x] 중복 데이터 방지 (당일 데이터 존재 여부 확인)
  - [x] FEDFUNDS (연준 금리) 수집
    - [x] `collect_all_indicators()` 메서드로 수집 가능 (구현 완료)
    - [x] 자동 스케줄링 구현 완료 (매일 09:00 KST 자동 실행)
  - [x] CPI 데이터 수집 (월별 → 일별 보간)
    - [x] `collect_all_indicators()` 메서드로 수집 가능 (구현 완료)
    - [x] 자동 스케줄링 구현 완료 (매일 09:00 KST 자동 실행)
  - [x] PCE 데이터 수집 (테일러 준칙용)
    - [x] `collect_all_indicators()` 메서드로 수집 가능 (구현 완료)
    - [x] 자동 스케줄링 구현 완료 (매일 09:00 KST 자동 실행)
  - [x] GDP 데이터 수집
    - [x] `collect_all_indicators()` 메서드로 수집 가능 (구현 완료)
    - [x] 자동 스케줄링 구현 완료 (매일 09:00 KST 자동 실행)
  - [x] 유동성 지표 데이터 수집
    - [x] `collect_all_indicators()` 메서드로 수집 가능 (구현 완료)
    - [x] WALCL (연준 총자산 - Total Assets) 수집 가능
    - [x] WTREGEN (재무부 일반 계정 - TGA) 수집 가능
    - [x] RRPONTSYD (역레포 잔고 - RRP) 수집 가능
    - [x] BAMLH0A0HYM2 (하이일드 스프레드) 수집 가능
    - [x] 자동 스케줄링 구현 완료 (매일 09:00 KST 자동 실행)
  - [x] DB에 저장 (`fred_data` 테이블) - DGS10, DGS2 완료
  - [x] 당일 데이터 존재 여부 확인 후 중복 조회 방지 - DGS10, DGS2 완료

- [ ] **2.1.3** 정량 시그널 계산
  - [x] 공식 1: 장단기 금리차 장기 추세 추종 전략 (DGS10 - DGS2)
    - [x] 알고리즘 구현 완료: `get_yield_curve_spread_trend_following()`
    - [x] Spread 계산: DGS10 - DGS2
    - [x] Spread_Fast: Spread의 20일 이동평균
    - [x] Spread_Slow: Spread의 120일 이동평균
    - [x] Yield_Trend: DGS10의 200일 이동평균
    - [x] 4가지 국면 판단:
      - Bull Steepening (Spread 확대 + 금리 하락)
      - Bear Steepening (Spread 확대 + 금리 상승)
      - Bull Flattening (Spread 축소 + 금리 하락)
      - Bear Flattening (Spread 축소 + 금리 상승)
    - [x] MySQL에서 일별 데이터 조회 (최소 250일)
    - [x] AI가 최종 판단하도록 action 필드 제거
  - [x] 공식 2: 실질 금리 (DGS10 - CPI 증가율)
    - [x] `get_real_interest_rate()` 메서드 구현 완료
    - [x] CPI 데이터 조회 및 증가율 계산
    - [x] 실질 금리 = 명목 금리 - 인플레이션율
  - [x] 공식 3: 테일러 준칙 (Target_Rate - FEDFUNDS)
    - [x] `get_taylor_rule_signal()` 메서드 구현 완료
    - [x] 테일러 준칙 공식 구현 (r* + π + 0.5(π - π*) + 0.5(y - y*))
    - [x] PCE 인플레이션율 계산
    - [x] 목표 금리 - 현재 금리 신호 계산
  - [x] 공식 4: 연준 순유동성 (Fed Net Liquidity)
    - [x] `get_net_liquidity()` 메서드 구현 완료
    - [x] 개념: 연준이 돈을 찍어냈어도(자산), 정부가 통장에 묶어두거나(TGA), 은행이 다시 연준에 맡겨두면(RRP) 시장에는 돈이 없습니다. 이 묶인 돈을 뺀 것이 순유동성입니다.
    - [x] 공식: `Net Liquidity = WALCL - WTREGEN - RRPONTSYD`
    - [x] AI 판단 로직:
      - [x] Net Liquidity의 4주(또는 8주) 이동평균이 상승 중인가?
      - [x] 상승 중: 유동성 공급 확대 → 위험자산(주식/코인) 비중 확대 (경기가 나빠도 주가는 오를 수 있음)
      - [x] 하락 중: 유동성 흡수 → 현금/채권 비중 확대
    - [x] 상관관계: S&P 500 및 비트코인 가격과 매우 높은 양의 상관관계(Coupling)를 보입니다.
  - [x] 공식 5: 하이일드 스프레드 (High Yield Spread)
    - [x] `get_high_yield_spread_signal()` 메서드 구현 완료
    - [x] 개념: 유동성의 **'양(Quantity)'**이 아니라 **'질(Quality)'**을 평가합니다. 시장에 돈이 말라가면(유동성 위기), 위험한 기업부터 돈을 못 빌리게 됩니다.
    - [x] 공식: `(투기등급 기업의 회사채 금리) - (안전한 국채 금리)`
    - [x] FRED Ticker: BAMLH0A0HYM2 (ICE BofA US High Yield Index Option-Adjusted Spread)
    - [x] 평가 기준:
      - [x] 3.5% 미만: 유동성 매우 풍부 (Greed) → 주식 적극 매수
      - [x] 5.0% 이상: 유동성 경색 시작 (Fear) → 주식 비중 축소
      - [x] 10.0% 이상: 금융 위기 (Panic) → 전량 현금/달러/국채
    - [x] AI 판단 로직:
      - [x] 스프레드가 전주 대비 **급격히 확대(Spike)**되고 있는가? (위기 감지 신호)

  - [x] 물가 및 고용 지표 시계열 데이터 제공
    - [x] Core PCE (PCEPILFE): 지난 10개 데이터를 날짜와 함께 LLM에 전달
    - [x] CPI (CPIAUCSL): 지난 10개 데이터를 날짜와 함께 LLM에 전달
    - [x] 실업률 (UNRATE): 지난 10개 데이터를 날짜와 함께 LLM에 전달
    - [x] 비농업 고용 (PAYEMS): 지난 10개 데이터를 날짜와 함께 LLM에 전달
    - [x] AI 전략가 프롬프트에 물가/고용 지표 섹션 추가

- [x] **2.1.4** 에러 핸들링
  - [x] FRED API 장애 시 사이트 팝업/에러 문구 표시
  - [x] 데이터 부족 시 처리 로직

#### 의사결정 필요 사항
- [x] CPI 월별 데이터를 일별로 보간하는 방법: ffill (결정 완료)
- [x] 테일러 준칙 계산에 필요한 모든 변수 확인 (결정 완료)
- [x] 추가 지표 수집 우선순위 (결정 완료)
- [x] **자연 이자율 ($r^*$) 추정 방법: 초기에는 고정값 2% 사용, 이후 실질 GDP 성장률 기반으로 개선 (결정 완료)

#### 추가 작업 항목
- [x] **2.1.5** 데이터 수집 스케줄 정의
  - [x] FRED API 호출 빈도 (매일 1회, 09:00 KST) - 설정 파일에 추가 완료
  - [x] 데이터 수집 실패 시 재시도 정책 (3회 재시도, 60초 간격)
  - [x] 자동 스케줄러 구현 완료 (`scheduler.py`)
  - [x] 메인 애플리케이션 시작 시 스케줄러 자동 시작

- [x] **2.1.6** 데이터 검증 로직 구현
  - [x] 이상치(outlier) 감지
  - [x] 데이터 누락 시 처리 방법
  - [x] 데이터 품질 검증
---

### 2.2 모듈 2: 정성 분석 (LLM)

#### 작업 항목
- [x] **2.2.1** 데이터 소스 크롤링
  - [x] TradingEconomics 스트림 뉴스 크롤링
    - [x] 24시간 이내의 경제 뉴스 수집
    - [x] 뉴스 제목, 날짜, 내용, 링크 추출
    - [x] 국가 코드, 중요도, 이벤트 유형 자동 분류
    - [x] `NewsCollector` 클래스 구현 완료 (`service/macro_trading/collectors/news_collector.py`)
    - [x] 데이터를 `economic_news` 테이블에 저장

---

### 2.3 모듈 3: 내부 데이터 (계좌 손익) - AI 분석에 사용하지 않음

#### 작업 항목
- [x] **2.3.1** 계좌 상태 조회
  - [x] 기존 `KISAPI.get_balance()` 활용
  - [x] 자산군별 보유 현황 파싱
    - [x] Stocks (S&P500, 나스닥, KOSPI)
    - [x] Bonds (미국 장기채, 한국 단기채)
    - [x] Alternatives (금, 달러)
    - [x] Cash
  - [x] `parse_holdings_by_asset_class()` 함수 구현 완료
  - [x] 설정 파일(`macro_trading_config.json`)에서 ETF 매핑 로드

- [x] **2.3.2** 자산군별 손익 계산
  - [x] 각 자산군별 평가 손익률 계산
  - [x] 매입가 대비 현재가 비교
  - [x] JSON 형식으로 구조화
  - [x] `calculate_asset_class_pnl()` 함수 구현 완료
  - [x] API 응답에 `asset_class_info` 필드 추가
  - [x] UI에 자산군별 수익률 표시 (그룹별/종목별)

- [ ] **2.3.3** DB 저장
  - [ ] 매일 계좌 상태를 `account_snapshots` 테이블에 저장
  - [ ] 자산군별 손익을 `pnl_by_asset` JSON 컬럼에 저장
  - [ ] 중복 저장 방지 (당일 데이터 존재 시 업데이트)

#### 의사결정 필요 사항
- [x] 계좌 조회 빈도: 09:10, 14:40 (결정 완료)
- [x] 자산군 분류 기준: ETF 티커 기반 매핑 (결정 완료)

#### 추가 작업 항목
- [x] **2.3.4** ETF 티커 → 자산군 매핑 테이블 생성
  - [x] 설정 파일의 ETF 매핑 정보 활용 (DB 저장은 추후 구현)
  - [x] 자동 분류 로직 구현 완료 (`parse_holdings_by_asset_class()`)

- [ ] **2.3.5** 계좌 조회 실패 시 처리 로직
  - [ ] 재시도 정책 (3회, exponential backoff)
  - [ ] 이전 스냅샷 사용 여부 결정

- [ ] **2.3.6** 손익 계산 정확도 개선
  - [ ] 수수료 반영 여부
  - [ ] 환율 변동 반영 (해외 ETF)

---

## Phase 3: AI 전략가 (2-3주)

### 3.1 모듈 4: Gemini LLM 통합

#### 작업 항목
- [x] **3.1.1** LLM 통합
  - [x] 기존 `llm.py`의 `llm_gemini_pro()` 활용
  - [x] Temperature=0 설정 (일관성 보장)
  - [x] JSON 출력 강제 (Pydantic 스키마)
  - [x] LangGraph 기반 워크플로우 구현

- [x] **3.1.2** 프롬프트 엔지니어링
  - [x] System Prompt 설계
    - [x] 역할 정의 (거시경제 전문가)
    - [x] 입력 데이터 설명 (FRED 정량 시그널, 물가 지표, 경제 뉴스)
    - [x] 출력 형식 명시 (JSON 스키마)
  - [x] 규칙 명시
    - [x] 총 비중 100% 검증
    - [x] 각 자산군별 비중 범위 (0-100%)
    - [x] 손실 중인 자산에 대한 판단 명시

- [x] **3.1.3** 출력 검증
  - [x] Pydantic 모델 정의
    ```python
    class TargetAllocation(BaseModel):
        Stocks: float
        Bonds: float
        Alternatives: float
        Cash: float
    ```
  - [x] 총합 100% 자동 검증
  - [x] 각 비중 범위 검증 (0-100%)

- [x] **3.1.4** 결과 저장
  - [x] AI 의사결정을 `ai_strategy_decisions` 테이블에 저장
  - [x] 분석 요약, 목표 비중, 입력 데이터 모두 저장

- [x] **3.1.5** LangGraph 워크플로우 구현
  - [x] State 정의 (AIAnalysisState)
  - [x] 노드 구현:
    - [x] `collect_fred_node`: FRED 시그널 수집
    - [x] `collect_news_node`: 경제 뉴스 수집 (지난 20일, 특정 국가)
    - [x] `summarize_news_node`: 뉴스 LLM 요약 (gemini-3.0-pro)
    - [x] `analyze_node`: AI 분석 및 전략 결정 (gemini-3-pro-preview)
    - [x] `save_decision_node`: 결과 저장
  - [x] 워크플로우 그래프 구성 및 순차 실행 보장
  - [x] 에러 핸들링 및 상태 관리

- [x] **3.1.6** 뉴스 정제 및 요약
  - [x] 지난 20일간 특정 국가 뉴스 수집 (Crypto, Commodity, Euro Area, China, United States)
  - [x] gemini-3.0-pro를 사용한 뉴스 요약
  - [x] 주요 경제 지표 변화, 경제 흐름, 주요 이벤트 도출
  - [x] 정제된 요약을 AI 분석 프롬프트에 포함

#### AI 분석 워크플로우 (LangGraph)

**워크플로우 구조:**
```
START
  ↓
[노드 1] collect_fred_node
  - FRED 정량 시그널 수집
  - 금리차, 실질금리, 테일러준칙, 유동성, 하이일드 스프레드
  - 물가 지표 (Core PCE, CPI) - 지난 10개 데이터
  - 고용 지표 (실업률, 비농업 고용) - 지난 10개 데이터
  ↓
[노드 2] collect_news_node
  - 지난 20일간 경제 뉴스 수집
  - 필터링 국가: Crypto, Commodity, Euro Area, China, United States
  - LLM 요약 제외 (별도 노드에서 처리)
  ↓
[노드 3] summarize_news_node
  - gemini-3.0-pro로 뉴스 요약
  - 주요 경제 지표 변화 도출
  - 경제 흐름 및 트렌드 분석
  - 주요 이벤트 추출
  ↓
[노드 4] analyze_node
  - FRED 시그널 + 정제된 뉴스 요약 종합 분석
  - gemini-3-pro-preview로 포트폴리오 목표 비중 결정
  - 자산군별 추천 섹터/카테고리 제시
  ↓
[노드 5] save_decision_node
  - AI 의사결정을 DB에 저장
  - 분석 요약, 목표 비중, 입력 데이터 저장
  ↓
END
```

**워크플로우 장점:**
- 순차 실행 보장: 뉴스 요약 완료 후 분석 실행
- 중복 실행 방지: 각 단계가 명확히 분리되어 관리
- 에러 핸들링 개선: 각 노드별 독립적 에러 처리
- 코드 가독성 향상: 워크플로우가 시각적으로 명확
- 재사용성: 각 노드를 독립적으로 테스트 및 재사용 가능

#### 의사결정 필요 사항
- [x] 폴백 전략의 구체적인 룰 정의 (아래 참조)
- [x] LLM 호출 빈도: 주기적 (08:30) (결정 완료)
- [x] 뉴스 수집 기간: 지난 20일 (결정 완료)
- [x] 뉴스 요약 모델: gemini-3.0-pro (결정 완료)
- [x] 전략 결정 모델: gemini-3-pro-preview (결정 완료)
- [x] 워크플로우 관리: LangGraph 사용 (결정 완료)


#### 추가 작업 항목
- [ ] **3.1.6** Few-shot 예시 데이터 수집
  - [ ] 초기: 수동으로 2-3개 성공 사례 작성
  - [ ] 이후: DB에서 성과가 좋았던 의사결정 자동 추출

- [ ] **3.1.7** LLM 출력 검증 강화
  - [ ] 각 자산군별 최소/최대 비중 제한 (예: Stocks 20-60%)
  - [ ] 이전 결정과의 급격한 변화 감지 (예: ±20% 이상 변화 시 경고)

---

## Phase 4: 실행 봇 (2주)

### 4.1 모듈 5: 임계값 리밸런싱

#### 작업 항목
- [ ] **4.1.1** ETF 티커 매핑
  - [ ] 설정 파일에서 ETF 티커 로드
  - [ ] 자산군별 티커 및 비중 매핑 확인

- [ ] **4.1.2** 편차 계산
  - [ ] DB에서 최신 `target_allocation` 로드
  - [ ] KIS API로 현재 계좌의 실제 비중 조회
  - [ ] 자산군별 편차 계산: `|목표 비중 - 실제 비중|`
  - [ ] 임계값(기본 5%) 초과 여부 확인

- [ ] **4.1.3** 리밸런싱 실행 로직
  - [ ] 매도 우선: 초과 비중 자산 매도
    - [ ] Alternatives의 경우 7:3 비율로 금/달러 매도
    - [ ] 부분 매도: 현금 확보 후 매수 시작
  - [ ] 매수 실행: 부족 비중 자산 매수
    - [ ] Stocks의 경우 1:1:1 비율로 S&P/나스닥/KOSPI 매수
    - [ ] 여유 자금 남기기 (총 자산의 3% 유지)
    - [ ] 1주당 가격 고려하여 정확한 수량 계산
  - [ ] 부분 리밸런싱: 편차가 5% 이상인 자산부터 우선 처리
  - [ ] 동시 매매 방지: 매도 완료 후 매수 시작

- [ ] **4.1.4** 거래 비용 고려
  - [ ] 매매 수수료 계산 (수수료율: 0.015%)
  - [ ] 세금 계산 (양도소득세 등)
  - [ ] 거래 비용이 예상 수익보다 크면 리밸런싱 취소
  - [ ] 거래 비용이 임계값(5%)보다 크면 리밸런싱 취소

- [ ] **4.1.5** 유동성 확인 (제거됨)
  - ~~[ ] ETF 거래량 확인~~
  - ~~[ ] 거래량 부족 시 부분 매매 또는 다음 날로 연기~~
  - **의사결정**: 거래량 부족 기준 제거 (항상 매매 실행)

- [ ] **4.1.6** 스케줄링 및 실행 조건 확인
  - [ ] 매일 15:00 KST에 실행 (장 마감 직전)
  - [ ] `schedule` 라이브러리 또는 cron 활용
  - [ ] 장 운영 시간 확인 (09:00 ~ 15:30 KST)
  - [ ] 공휴일/휴장일 확인 (한국 증시 휴장일 체크)
  - [ ] 긴급 중지 플래그 확인 (설정 파일 또는 DB)

- [ ] **4.1.7** 실행 이력 저장
  - [ ] 리밸런싱 실행 시 `rebalancing_history` 테이블에 저장
  - [ ] 실행 전/후 편차, 거래 내역 저장

#### 의사결정 필요 사항
- [x] 여유 자금 비율: 3% (결정 완료)
- [x] 거래량 부족 기준: 제거 (결정 완료)
- [x] 부분 리밸런싱 시 편차 임계값: 5% (결정 완료)
- [x] 거래 비용 계산: 수수료율 0.015%, 세금 포함 (결정 완료)
- [x] 리밸런싱 실행 조건: 장 운영 시간, 공휴일 확인 포함 (결정 완료)

---

## Phase 5: 백테스팅 (2-3주)

### 5.1 모듈 6: 백테스팅 프레임워크

#### 작업 항목
- [ ] **5.1.1** 과거 데이터 수집
  - [ ] FRED API로 2010년~현재 금리 데이터 수집
  - [ ] ETF 가격 데이터 수집 (한국투자증권 API 또는 yfinance)
  - [ ] `etf_price_history` 테이블에 저장
  - [ ] 경제 이벤트 데이터 수집 (TradingEconomics 크롤링 또는 수동 입력)

- [ ] **5.1.2** 백테스팅 엔진 구현
  - [ ] 백테스팅 프레임워크 선택 (backtrader vs 자체 구현)
  - [ ] 시뮬레이션 로직 구현
    - [ ] 일별로 AI 의사결정 시뮬레이션
    - [ ] 임계값 기반 리밸런싱 시뮬레이션
    - [ ] 거래 비용 반영

- [ ] **5.1.3** 성과 지표 계산
  - [ ] 총 수익률 (Total Return)
  - [ ] 연환산 수익률 (Annualized Return)
  - [ ] MDD (Maximum Drawdown)
  - [ ] Sharpe Ratio
  - [ ] Sortino Ratio
  - [ ] 거래 횟수 및 거래 비용

- [ ] **5.1.4** 최적화
  - [ ] Grid Search: 임계값 3%, 5%, 8%, 10% 테스트
  - [ ] Walk-Forward Analysis: 과적합 방지
  - [ ] 여러 기간으로 테스트 (2010-2015, 2015-2020, 2020-현재)

#### 의사결정 필요 사항
- [ ] 백테스팅 프레임워크 선택 (backtrader vs 자체 구현)
- [ ] AI 의사결정 시뮬레이션 방법 (실제 LLM 호출 vs 룰 기반)
- [ ] 최적화 목표 (수익률 최대화 vs Sharpe Ratio 최대화)

#### 질문/의견
> 여기에 의견을 적어주세요

---

## Phase 6: 통합 및 테스트 (1-2주)

### 6.1 전체 시스템 통합

#### 작업 항목
- [ ] **6.1.1** 모듈 간 연동
  - [ ] 모듈 1 → 모듈 4: FRED 정량 시그널 및 물가 지표 전달
  - [ ] 모듈 2 → 모듈 4: 경제 뉴스 전달
  - [ ] 모듈 4 → 모듈 5: 목표 비중 전달
  - [ ] 전체 워크플로우 테스트

- [ ] **6.1.2** 이벤트 트리거 구현
  - [ ] 경제 이벤트 발생 시 모듈 1, 2, 4 자동 실행
  - [ ] 스케줄러 설정

### 6.2 테스트

#### 작업 항목
- [ ] **6.2.1** 드라이런 테스트
  - [ ] 실제 매매 없이 전체 워크플로우 실행
  - [ ] 로그 확인 및 검증

- [ ] **6.2.2** 모의투자 테스트
  - [ ] 한국투자증권 모의투자 계좌 활용
  - [ ] 1-2주간 모의투자 실행
  - [ ] 성과 분석

### 6.3 문서화

#### 작업 항목
- [ ] **6.3.1** API 문서 작성
- [ ] **6.3.2** 사용자 매뉴얼 작성
- [ ] **6.3.3** 배포 가이드 작성

---

## 🔧 공통 작업

### 패키지 설치

```bash
# requirements.txt에 추가할 패키지
fredapi>=0.5.0
pandas>=2.0.0
numpy>=1.24.0
beautifulsoup4>=4.12.0
requests>=2.31.0
pydantic>=2.0.0
backtrader>=1.9.78  # 백테스팅용 (선택적)
yfinance>=0.2.0  # 백테스팅용 (선택적)
```

---

## 📝 의사결정 이력

### 2024-12-19 (장단기 금리차 로직 개선)
- **공식 1 개선 완료**: 장단기 금리차 장기 추세 추종 전략 구현
  - ✅ `get_yield_curve_spread_trend_following()` 메서드 구현
  - ✅ 4가지 국면 판단 로직 구현 (Bull/Bear Steepening, Bull/Bear Flattening)
  - ✅ 이동평균 기반 추세 분석 (20일, 120일, 200일)
  - ✅ AI 최종 판단을 위해 action 필드 제거
  - ✅ 기존 `get_yield_curve_spread()` 메서드 삭제
- **DGS10, DGS2 자동 수집 및 저장 구현**
  - ✅ `collect_yield_curve_data()` 메서드 추가
  - ✅ MySQL DB에 자동 저장 로직 구현
  - ✅ 중복 데이터 방지 로직 구현

### 2024-12-19 (구현 진행)
- **Phase 1.1 완료**: 데이터베이스 스키마 설계 및 생성 완료
- **Phase 1.2 완료**: 설정 파일 구조 설계 및 검증 로직 구현 완료 (Pydantic V2 마이그레이션 완료)
- **검토 의견 반영 완료**:
  - ✅ 설정 파일 JSON 스키마 예시 추가
  - ✅ 에러 구분 기준 4단계 정의 (FATAL, CRITICAL, WARNING, INFO)
  - ✅ Exponential backoff 상세화 (1분 → 3분 → 5분)
  - ✅ 폴백 전략 룰 목록 구체화 (5개 룰 정의)
  - ✅ 매매 순서 최적화 로직 상세화
  - ✅ 거래 비용 계산 상세화 (수수료율 0.015%, 세금 포함)
  - ✅ 리밸런싱 실행 조건 추가 (장 운영 시간, 공휴일 확인)
  - ✅ 자연 이자율 추정 방법 제안 (초기 고정값 2%, 이후 개선)
  - ✅ 추가 작업 항목 다수 추가 (데이터 검증, 로그 로테이션, Dashboard 요구사항 등)
  - ✅ 경제 캘린더 데이터 소스 변경: Investing.com → TradingEconomics (Cloudflare 제한 회피)
  - ✅ 스케줄 시간 조정: 리밸런싱 15:00, 계좌 조회/LLM 분석 14:40

### 2024-12-19 (초기 의사결정)
- **의사결정 완료 사항**:
  - ✅ 데이터 보관 기간: 무제한
  - ✅ JSON 컬럼 사용 결정 (정규화 대신)
  - ✅ 인덱스 전략 결정
  - ✅ LLM 설정: Gemini 2.5 pro, temperature=0, max_tokens=5000
  - ✅ 설정 파일 위치: config/ 디렉토리
  - ✅ 로그 보관: 7일, 파일
  - ✅ Slack 알림 빈도 결정
  - ✅ Macro 분석 Dashboard 개발 추가
  - ✅ 재시도: 3회, exponential backoff
  - ✅ CPI 보간 방법: ffill
  - ✅ 테일러 준칙 변수 확인
  - ✅ 추가 지표 우선순위 결정
  - ✅ 연준 발표문 수집 방법 결정
  - ✅ LLM 센티멘트 분석 제외, 요약만 수행
  - ✅ 계좌 조회 빈도: 09:10, 14:40
  - ✅ 자산군 분류 기준 상세화
  - ✅ LLM 호출 빈도: 09:10, 14:40
  - ✅ 리밸런싱 실행 시간: 15:00
  - ✅ 여유 자금 비율: 3%
  - ✅ 거래량 부족 기준 제거
  - ✅ 편차 임계값: 5%

---

## 💬 질문 및 논의 사항

> 여기에 진행 중인 논의 사항이나 질문을 적어주세요

---

**다음 단계**: Phase 1.1 데이터베이스 스키마 설계부터 시작

