-- ============================================
-- 거시경제 기반 자동매매 Agent 데이터베이스 스키마
-- ============================================
-- 생성일: 2024-12-19
-- 데이터베이스: MySQL 5.7+
-- 문자셋: utf8mb4
-- ============================================

-- 1. AI 전략 결정 이력 테이블
-- 역할: AI 전략가(모듈 4)가 결정한 포트폴리오 목표 비중을 저장
CREATE TABLE ai_strategy_decisions (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '고유 ID',
    decision_date DATETIME NOT NULL COMMENT '의사결정 일시',
    analysis_summary TEXT COMMENT 'AI 분석 요약',
    target_allocation JSON NOT NULL COMMENT '목표 자산 배분 (Stocks, Bonds_US_Long, Bonds_KR_Short, Alternatives, Cash)',
    quant_signals JSON COMMENT '정량 시그널 데이터 (장단기 금리차, 실질 금리, 테일러 준칙 등)',
    qual_sentiment JSON COMMENT '정성 분석 데이터 (연준 발표문 요약, 경제 이벤트 등)',
    account_pnl JSON COMMENT '계좌 손익 데이터 (자산군별 손익률)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
    INDEX idx_decision_date (decision_date) COMMENT '의사결정 일시 인덱스 (최신 조회용)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 전략 결정 이력';

-- 2. 리밸런싱 실행 이력 테이블
-- 역할: 실제 리밸런싱 실행 이력을 저장
CREATE TABLE rebalancing_history (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '고유 ID',
    execution_date DATETIME NOT NULL COMMENT '실행 일시',
    threshold_used DECIMAL(5,2) NOT NULL COMMENT '사용된 임계값 (%)',
    drift_before JSON COMMENT '실행 전 편차 (자산군별 편차)',
    drift_after JSON COMMENT '실행 후 편차 (자산군별 편차)',
    trades_executed JSON COMMENT '실행된 거래 내역 (매수/매도 종목, 수량, 가격)',
    total_cost DECIMAL(15,2) COMMENT '총 거래 비용 (수수료 + 세금)',
    status ENUM('SUCCESS', 'PARTIAL', 'FAILED') DEFAULT 'SUCCESS' COMMENT '실행 상태',
    error_message TEXT COMMENT '에러 메시지 (실패 시)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
    INDEX idx_execution_date (execution_date) COMMENT '실행 일시 인덱스'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='리밸런싱 실행 이력';

-- 3. 계좌 상태 일별 스냅샷 테이블
-- 역할: 매일 계좌 상태를 스냅샷으로 저장
CREATE TABLE account_snapshots (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '고유 ID',
    snapshot_date DATE NOT NULL COMMENT '스냅샷 날짜',
    total_value DECIMAL(15,2) NOT NULL COMMENT '총 자산 가치 (원)',
    cash_balance DECIMAL(15,2) NOT NULL COMMENT '현금 잔액 (원)',
    allocation_actual JSON NOT NULL COMMENT '실제 자산 배분 (자산군별 비중)',
    pnl_by_asset JSON COMMENT '자산군별 손익률 (Stocks, Bonds, Alternatives, Cash)',
    pnl_total DECIMAL(10,2) COMMENT '총 손익률 (%)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
    UNIQUE KEY unique_date (snapshot_date) COMMENT '날짜별 중복 방지'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='계좌 상태 일별 스냅샷';

-- 4. 경제 이벤트 테이블
-- 역할: 주요 경제 이벤트(CPI, FOMC, 실업률 등) 정보 저장
CREATE TABLE economic_events (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '고유 ID',
    event_date DATE NOT NULL COMMENT '이벤트 날짜',
    event_name VARCHAR(255) NOT NULL COMMENT '이벤트 이름 (예: US CPI, FOMC Meeting)',
    event_type VARCHAR(50) NOT NULL COMMENT '이벤트 유형 (CPI, FOMC, UNEMPLOYMENT, GDP 등)',
    country VARCHAR(10) DEFAULT 'US' COMMENT '국가 코드 (US, KR 등)',
    importance ENUM('HIGH', 'MEDIUM', 'LOW') DEFAULT 'MEDIUM' COMMENT '중요도',
    forecast_value DECIMAL(10,2) COMMENT '예상값',
    actual_value DECIMAL(10,2) COMMENT '실제값',
    previous_value DECIMAL(10,2) COMMENT '이전값',
    unit VARCHAR(20) COMMENT '단위 (%, $, 등)',
    summary TEXT COMMENT 'LLM 요약 (연준 발표문 요약 등)',
    source VARCHAR(100) DEFAULT 'TradingEconomics' COMMENT '데이터 출처',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
    INDEX idx_event_date_type (event_date, event_type) COMMENT '날짜 및 유형 복합 인덱스',
    INDEX idx_event_type (event_type) COMMENT '이벤트 유형 인덱스'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='경제 이벤트';

-- 5. FRED 데이터 테이블
-- 역할: FRED API에서 수집한 금리 및 거시경제 지표 저장
CREATE TABLE fred_data (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '고유 ID',
    indicator_code VARCHAR(20) NOT NULL COMMENT '지표 코드 (DGS10, DGS2, FEDFUNDS, PCEPI 등)',
    indicator_name VARCHAR(255) COMMENT '지표 이름',
    date DATE NOT NULL COMMENT '날짜',
    value DECIMAL(15,4) NOT NULL COMMENT '지표 값',
    unit VARCHAR(20) COMMENT '단위 (%, $, 등)',
    source VARCHAR(50) DEFAULT 'FRED' COMMENT '데이터 출처',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
    UNIQUE KEY unique_indicator_date (indicator_code, date) COMMENT '지표 코드 및 날짜 중복 방지',
    INDEX idx_indicator_date (indicator_code, date) COMMENT '지표 코드 및 날짜 복합 인덱스',
    INDEX idx_date (date) COMMENT '날짜 인덱스'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='FRED 거시경제 지표 데이터';

-- 6. ETF 가격 이력 테이블 (백테스팅용)
-- 역할: 백테스팅을 위한 과거 ETF 가격 데이터 저장
CREATE TABLE etf_price_history (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '고유 ID',
    ticker VARCHAR(20) NOT NULL COMMENT 'ETF 티커',
    ticker_name VARCHAR(255) COMMENT 'ETF 이름',
    date DATE NOT NULL COMMENT '날짜',
    open_price DECIMAL(15,2) COMMENT '시가',
    high_price DECIMAL(15,2) COMMENT '고가',
    low_price DECIMAL(15,2) COMMENT '저가',
    close_price DECIMAL(15,2) NOT NULL COMMENT '종가',
    volume BIGINT COMMENT '거래량',
    adjusted_close DECIMAL(15,2) COMMENT '수정 종가 (배당 반영)',
    source VARCHAR(50) DEFAULT 'KIS' COMMENT '데이터 출처 (KIS, yfinance 등)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
    UNIQUE KEY unique_ticker_date (ticker, date) COMMENT '티커 및 날짜 중복 방지',
    INDEX idx_ticker_date (ticker, date) COMMENT '티커 및 날짜 복합 인덱스',
    INDEX idx_date (date) COMMENT '날짜 인덱스'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='ETF 가격 이력 (백테스팅용)';

-- 7. 시스템 로그 테이블
-- 역할: 각 모듈의 실행 로그 및 에러 로그 저장
CREATE TABLE system_logs (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '고유 ID',
    module_name VARCHAR(50) NOT NULL COMMENT '모듈명 (module_1, module_2, module_3, module_4, module_5)',
    log_level ENUM('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'FATAL') NOT NULL DEFAULT 'INFO' COMMENT '로그 레벨',
    log_message TEXT NOT NULL COMMENT '로그 메시지',
    error_type VARCHAR(100) COMMENT '에러 타입 (에러 발생 시)',
    stack_trace TEXT COMMENT '스택 트레이스 (에러 발생 시)',
    execution_time_ms INT COMMENT '실행 시간 (밀리초)',
    metadata JSON COMMENT '추가 메타데이터',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
    INDEX idx_module_level_created (module_name, log_level, created_at) COMMENT '모듈, 레벨, 생성일시 복합 인덱스',
    INDEX idx_created_at (created_at) COMMENT '생성 일시 인덱스',
    INDEX idx_log_level (log_level) COMMENT '로그 레벨 인덱스'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='시스템 로그';

-- 8. 경제 뉴스 테이블
-- 역할: TradingEconomics 스트림에서 수집한 경제 뉴스 저장
CREATE TABLE economic_news (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '고유 ID',
    title VARCHAR(500) NOT NULL COMMENT '뉴스 제목',
    link VARCHAR(500) COMMENT '뉴스 링크',
    country VARCHAR(100) COMMENT '국가 (예: United States, Peru)',
    category VARCHAR(100) COMMENT '카테고리 (예: Stock Market, GDP Annual Growth Rate)',
    description TEXT COMMENT '뉴스 본문/요약',
    published_at DATETIME COMMENT '뉴스 발행 시간',
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '수집 일시',
    source VARCHAR(100) DEFAULT 'TradingEconomics Stream' COMMENT '데이터 출처',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
    UNIQUE KEY unique_title_link (title(255), link(255)) COMMENT '제목과 링크로 중복 방지',
    INDEX idx_published_at (published_at) COMMENT '발행 시간 인덱스',
    INDEX idx_country (country) COMMENT '국가 인덱스',
    INDEX idx_category (category) COMMENT '카테고리 인덱스',
    INDEX idx_collected_at (collected_at) COMMENT '수집 일시 인덱스'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='경제 뉴스';

-- ============================================
-- 추가 인덱스 (성능 최적화)
-- ============================================

-- ai_strategy_decisions: 최신 의사결정 조회 최적화
ALTER TABLE ai_strategy_decisions ADD INDEX idx_created_at (created_at);

-- rebalancing_history: 최근 실행 이력 조회 최적화
ALTER TABLE rebalancing_history ADD INDEX idx_status (status);

-- account_snapshots: 기간별 조회 최적화
ALTER TABLE account_snapshots ADD INDEX idx_total_value (total_value);

-- ============================================
-- 테이블 생성 완료
-- ============================================

