"""
MySQL 데이터베이스 관리 모듈
"""
import os
import json
import logging
import threading
import time
from typing import Optional, Dict, List, Any
from contextlib import contextmanager
from datetime import datetime
import pymysql
from pymysql.cursors import DictCursor
from pymysql.err import OperationalError, IntegrityError
import uuid

from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError as SAOperationalError

logger = logging.getLogger(__name__)

# MySQL 연결 설정 (환경 변수에서 가져오기)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "hobot")
DB_CHARSET = os.getenv("DB_CHARSET", "utf8mb4")

# 백업 디렉토리 (시스템 경로)
BACKUP_DIR = "/var/backups/hobot"

# 스레드 로컈: init_database 내부 실행 스레드에서만 True
# 전역 플래그가 아니라 스레드별 플래그라
# init 코드를 실행 중인 바로 그 스레드만 True가 됨
_tl = threading.local()

# ──────────────────────────────────────────────
# SQLAlchemy 커넥션 풀 (QueuePool)
# pool_size    : 풀에 상시 유지할 커넥션 수
# max_overflow : 급증 시 추가로 허용할 커넥션 수  → 최대 pool_size + max_overflow 개
# pool_timeout : 풀이 꽉 찼을 때 커넥션을 기다리는 최대 시간(초)
# pool_recycle : idle 커넥션을 교체할 주기(초) - SSH 터널 타임아웃 대비
# pool_pre_ping: 커넥션 사용 전 PING으로 죽은 커넥션 자동 교체
# ──────────────────────────────────────────────
_engine = None
_engine_lock = threading.Lock()


def _get_engine():
    """SQLAlchemy 엔진을 지연 생성하고 싱글턴으로 반환"""
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is not None:
            return _engine
        url = (
            f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
            f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
            f"?charset={DB_CHARSET}"
        )
        _engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=5,        # 상시 유지 커넥션
            max_overflow=3,     # 급증 시 최대 8개까지
            pool_timeout=10,    # 풀 대기 타임아웃 (초)
            pool_recycle=1800,  # 30분마다 커넥션 교체 (SSH 터널 대비)
            pool_pre_ping=True, # 사용 전 ping으로 끊긴 커넥션 자동 교체
            connect_args={
                # cursorclass는 SQLAlchemy 초기화 쿼리(SELECT @@version)와 충돌하여
                # 여기에 넣지 않고 get_db_connection()에서 수동으로 교체
                "connect_timeout": 5,
            },
        )
        logger.info(
            "✅ DB 커넥션 풀 생성 완료 "
            f"(pool_size=5, max_overflow=3, host={DB_HOST}:{DB_PORT})"
        )
        return _engine


def ensure_backup_dir():
    """백업 디렉토리 생성"""
    global BACKUP_DIR
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        # 백업 디렉토리에 쓰기 권한이 있는지 확인
        test_file = os.path.join(BACKUP_DIR, ".test_write")
        try:
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except (PermissionError, OSError):
            # /var/backups에 쓰기 권한이 없으면 프로젝트 내부에 백업
            BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            BACKUP_DIR = os.path.join(BASE_DIR, "service", "database", "backups")
            os.makedirs(BACKUP_DIR, exist_ok=True)
    except (PermissionError, OSError):
        # 시스템 경로에 접근할 수 없으면 프로젝트 내부에 백업
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        BACKUP_DIR = os.path.join(BASE_DIR, "service", "database", "backups")
        os.makedirs(BACKUP_DIR, exist_ok=True)


@contextmanager
def _direct_db_connection():
    """
    풀을 거치지 않는 pymysql 직접 커넥션.
    init_database() 내부 전용 - 절대 외부에서 호출하지 말 것.
    """
    conn = None
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset=DB_CHARSET,
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=5,
        )
        yield conn
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def _apply_dict_cursor(connection: Any) -> None:
    """프록시 여부와 관계없이 실제 DBAPI 커넥션에 DictCursor를 적용한다."""
    driver_connection = getattr(connection, "driver_connection", None)
    if driver_connection is None:
        driver_connection = getattr(connection, "dbapi_connection", None)
    if driver_connection is None:
        driver_connection = getattr(connection, "connection", None)
    if driver_connection is None:
        driver_connection = connection
    driver_connection.cursorclass = DictCursor


@contextmanager
def get_db_connection():
    """데이터베이스 연결 컨텍스트 매니저 (SQLAlchemy QueuePool 사용)

    - 동일한 `with get_db_connection() as conn:` 인터페이스 유지
    - 항상 커넥션 풀에서 꺼내 사용 후 반환 (TCP 신규 연결 최소화)
    - DictCursor는 풀에서 커넥션 획득 후 수동으로 설정
      (SQLAlchemy 초기화 쿼리가 숫자 인덱스로 접근하므로 connect_args에 넣으면 충돌)
    """
    ensure_database_initialized()

    conn = None
    try:
        engine = _get_engine()
        # raw_connection(): 풀에서 pymysql 커넥션을 직접 꺼내 사용
        # conn.close() 호출 시 TCP를 끔지 않고 풀에 반환
        conn = engine.raw_connection()
        # SQLAlchemy는 프록시 커넥션을 반환하므로 실제 드라이버 커넥션에 적용해야 한다.
        _apply_dict_cursor(conn)
        conn.autocommit(False)
        yield conn
        conn.commit()
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            conn.close()  # 풀로 반환 (TCP 연결은 유지)


def init_database():
    """데이터베이스 및 테이블 초기화"""
    # 1단계: 데이터베이스가 없으면 생성 (database 지정 없이 접속)
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            charset=DB_CHARSET,
            connect_timeout=5,
        )
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {DB_NAME} "
                f"CHARACTER SET {DB_CHARSET} COLLATE {DB_CHARSET}_unicode_ci"
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  데이터베이스 생성 실패: {e}")
        raise

    # 2단계: 테이블 생성 - 내부 전용 direct 커넥션 사용 (풀 비의존)
    with _direct_db_connection() as conn:
        cursor = conn.cursor()
        
        # 사용자 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(255) PRIMARY KEY,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'user',
                mfa_enabled BOOLEAN DEFAULT FALSE COMMENT 'MFA 활성화 여부',
                mfa_secret_encrypted TEXT COMMENT '암호화된 MFA Secret Key',
                mfa_backup_codes JSON COMMENT 'MFA 백업 코드 목록',
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                INDEX idx_id (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # MFA 관련 컬럼 추가 (마이그레이션)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN DEFAULT FALSE COMMENT 'MFA 활성화 여부'")
        except Exception:
            pass  # 이미 존재하는 경우 무시
        
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN mfa_secret_encrypted TEXT COMMENT '암호화된 MFA Secret Key'")
        except Exception:
            pass
        
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN mfa_backup_codes JSON COMMENT 'MFA 백업 코드 목록'")
        except Exception:
            pass
        
        # 사용자별 KIS API 인증 정보 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_kis_credentials (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                kis_id VARCHAR(255) NOT NULL COMMENT '한국투자증권 ID',
                account_no VARCHAR(50) NOT NULL COMMENT '계좌번호',
                app_key_encrypted TEXT NOT NULL COMMENT '암호화된 App Key',
                app_secret_encrypted TEXT NOT NULL COMMENT '암호화된 App Secret',
                is_simulation BOOLEAN DEFAULT FALSE COMMENT '모의투자 여부',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
                UNIQUE KEY unique_user_id (user_id) COMMENT '사용자별 중복 방지',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='사용자별 KIS API 인증 정보'
        """)
        
        # 모의투자 여부 컬럼 추가 (마이그레이션)
        try:
            cursor.execute("ALTER TABLE user_kis_credentials ADD COLUMN is_simulation BOOLEAN DEFAULT FALSE COMMENT '모의투자 여부'")
        except Exception:
            pass  # 이미 존재하는 경우 무시
        
        # 사용자별 Upbit API 인증 정보 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_upbit_credentials (
                id VARCHAR(64) PRIMARY KEY COMMENT '해시 기반 ID',
                user_id VARCHAR(50) NOT NULL COMMENT '사용자 ID',
                access_key TEXT NOT NULL COMMENT '암호화된 Access Key',
                secret_key TEXT NOT NULL COMMENT '암호화된 Secret Key',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
                UNIQUE KEY unique_user_id (user_id) COMMENT '사용자별 중복 방지',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='사용자별 Upbit API 인증 정보'
        """)

        # 리밸런싱 임계값 설정 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rebalancing_config (
                id VARCHAR(64) PRIMARY KEY COMMENT '해시 기반 ID',
                mp_threshold_percent DECIMAL(5,2) NOT NULL DEFAULT 3.00 COMMENT 'MP 임계값(%)',
                sub_mp_threshold_percent DECIMAL(5,2) NOT NULL DEFAULT 5.00 COMMENT 'Sub-MP 임계값(%)',
                is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT '활성화 여부',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_updated_at (updated_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='리밸런싱 임계값 설정'
        """)
        # 기존 INT 컬럼을 VARCHAR(64)로 마이그레이션 (기존 테이블이 있을 수 있음)
        try:
            cursor.execute("""
                ALTER TABLE rebalancing_config 
                MODIFY COLUMN id VARCHAR(64) NOT NULL COMMENT '해시 기반 ID'
            """)
        except Exception:
            pass
        
        # Crypto 설정 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crypto_config (
                id VARCHAR(64) PRIMARY KEY COMMENT '해시 기반 ID',
                market_status VARCHAR(20) NOT NULL DEFAULT 'BULL' COMMENT '시장 상태 (BULL/BEAR)',
                strategy VARCHAR(50) NOT NULL DEFAULT 'STRATEGY_NULL' COMMENT '현재 전략',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_updated_at (updated_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='가상화폐 매매 설정'
        """)
        
        # Crypto 설정 초기 데이터 확인 및 삽입
        try:
            cursor.execute("SELECT COUNT(*) as count FROM crypto_config")
            row = cursor.fetchone()
            if row['count'] == 0:
                # 초기 데이터 삽입
                initial_id = uuid.uuid4().hex
                cursor.execute("""
                    INSERT INTO crypto_config (id, market_status, strategy)
                    VALUES (%s, 'BULL', 'STRATEGY_NULL')
                """, (initial_id,))
                print("✅ crypto_config initialized with default values")
        except Exception as e:
            print(f"⚠️  crypto_config 초기화 실패: {e}")
        
        # 메모리 저장소 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_store (
                id INT AUTO_INCREMENT PRIMARY KEY,
                topic VARCHAR(255) NOT NULL,
                summary TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                INDEX idx_topic (topic)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # 전략 설정 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id INT AUTO_INCREMENT PRIMARY KEY,
                platform VARCHAR(50) UNIQUE NOT NULL,
                strategy VARCHAR(255) NOT NULL,
                updated_at DATETIME NOT NULL,
                INDEX idx_platform (platform)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # 토큰 저장 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                id INT AUTO_INCREMENT PRIMARY KEY,
                token_type VARCHAR(50) NOT NULL,
                token_data TEXT NOT NULL,
                expires_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                INDEX idx_token_type (token_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # 마이그레이션 메타데이터 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migration_metadata (
                `key` VARCHAR(255) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # 경제 뉴스 테이블 (TradingEconomics 스트림 뉴스)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS economic_news (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                link VARCHAR(500),
                country VARCHAR(100),
                category VARCHAR(100),
                description TEXT,
                published_at DATETIME,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source VARCHAR(100) DEFAULT 'TradingEconomics Stream',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY unique_title_link (title(255), link(255)),
                INDEX idx_published_at (published_at),
                INDEX idx_country (country),
                INDEX idx_category (category),
                INDEX idx_collected_at (collected_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # 한글 번역 컬럼 추가 (마이그레이션)
        try:
            cursor.execute("ALTER TABLE economic_news ADD COLUMN title_ko VARCHAR(500) COMMENT '제목 한글 번역'")
        except Exception:
            pass  # 이미 존재하는 경우 무시
        
        try:
            cursor.execute("ALTER TABLE economic_news ADD COLUMN description_ko TEXT COMMENT '설명 한글 번역'")
        except Exception:
            pass
        
        try:
            cursor.execute("ALTER TABLE economic_news ADD COLUMN country_ko VARCHAR(100) COMMENT '국가 한글 번역'")
        except Exception:
            pass
        
        try:
            cursor.execute("ALTER TABLE economic_news ADD COLUMN category_ko VARCHAR(100) COMMENT '카테고리 한글 번역'")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE economic_news ADD COLUMN release_date DATETIME NULL COMMENT '공식 발표 시각'")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE economic_news ADD COLUMN effective_date DATETIME NULL COMMENT '효력 발생 시각'")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE economic_news ADD COLUMN observed_at DATETIME NULL COMMENT '수집 관측 시각'")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE economic_news ADD COLUMN source_type VARCHAR(64) NULL COMMENT '소스 유형(예: policy_document)'")
        except Exception:
            pass
        
        # LLM 사용 로그 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_usage_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                model_name VARCHAR(100) NOT NULL COMMENT 'LLM 모델명 (예: gpt-4o-mini, gemini-2.5-pro)',
                provider VARCHAR(50) NOT NULL COMMENT 'LLM 제공자 (예: OpenAI, Google)',
                request_prompt TEXT COMMENT '요청 프롬프트',
                response_prompt TEXT COMMENT '응답 프롬프트',
                prompt_tokens INT DEFAULT 0 COMMENT '프롬프트 토큰 수',
                completion_tokens INT DEFAULT 0 COMMENT '완료 토큰 수',
                total_tokens INT DEFAULT 0 COMMENT '총 토큰 수',
                service_name VARCHAR(100) COMMENT '서비스명 (어떤 기능에서 호출했는지)',
                duration_ms INT COMMENT '응답 시간 (밀리초)',
                user_id VARCHAR(100) COMMENT '사용자 ID (인증된 사용자의 경우)',
                flow_type VARCHAR(64) NULL COMMENT '멀티에이전트 플로우 타입 (예: chatbot, dashboard_ai_analysis)',
                flow_run_id VARCHAR(80) NULL COMMENT '동일 요청(run) 추적 ID',
                agent_name VARCHAR(100) NULL COMMENT '호출 주체 에이전트/유틸리티 이름',
                trace_order INT NULL COMMENT 'run 내 호출 순서',
                metadata_json JSON NULL COMMENT '추가 메타데이터(JSON)',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
                INDEX idx_model_name (model_name) COMMENT '모델명 인덱스',
                INDEX idx_provider (provider) COMMENT '제공자 인덱스',
                INDEX idx_created_at (created_at) COMMENT '생성 일시 인덱스 (일자별 조회용)',
                INDEX idx_service_name (service_name) COMMENT '서비스명 인덱스',
                INDEX idx_user_id (user_id) COMMENT '사용자 ID 인덱스',
                INDEX idx_flow_type (flow_type) COMMENT '플로우 타입 인덱스',
                INDEX idx_flow_run_id (flow_run_id) COMMENT '플로우 run 인덱스',
                INDEX idx_agent_name (agent_name) COMMENT '에이전트명 인덱스'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='LLM 사용 로그'
        """)
        
        # llm_usage_logs 테이블에 user_id 컬럼 추가 (마이그레이션)
        try:
            cursor.execute("ALTER TABLE llm_usage_logs ADD COLUMN user_id VARCHAR(100) COMMENT '사용자 ID (인증된 사용자의 경우)'")
            cursor.execute("ALTER TABLE llm_usage_logs ADD INDEX idx_user_id (user_id)")
        except Exception:
            pass  # 이미 존재하는 경우 무시

        try:
            cursor.execute("ALTER TABLE llm_usage_logs ADD COLUMN flow_type VARCHAR(64) NULL COMMENT '멀티에이전트 플로우 타입 (예: chatbot, dashboard_ai_analysis)'")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE llm_usage_logs ADD COLUMN flow_run_id VARCHAR(80) NULL COMMENT '동일 요청(run) 추적 ID'")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE llm_usage_logs ADD COLUMN agent_name VARCHAR(100) NULL COMMENT '호출 주체 에이전트/유틸리티 이름'")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE llm_usage_logs ADD COLUMN trace_order INT NULL COMMENT 'run 내 호출 순서'")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE llm_usage_logs ADD COLUMN metadata_json JSON NULL COMMENT '추가 메타데이터(JSON)'")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE llm_usage_logs ADD INDEX idx_flow_type (flow_type)")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE llm_usage_logs ADD INDEX idx_flow_run_id (flow_run_id)")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE llm_usage_logs ADD INDEX idx_agent_name (agent_name)")
        except Exception:
            pass
        
        # 시장 뉴스 요약 테이블 (원본 분석 및 브리핑용 요약)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_news_summaries (
                id INT AUTO_INCREMENT PRIMARY KEY,
                summary_text TEXT NOT NULL COMMENT 'LLM이 생성한 원본 뉴스 분석 결과',
                briefing_text TEXT COMMENT 'Market Briefing용 2차 요약 (App Main 화면용)',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='시장 뉴스 요약 및 브리핑'
        """)
        
        # 추출 결과 캐시 테이블 (LLM 비용 절감용)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extraction_cache (
                cache_key VARCHAR(64) PRIMARY KEY COMMENT '해시 키 (doc_id + version + model)',
                doc_id VARCHAR(255) NOT NULL COMMENT '문서 ID',
                data JSON NOT NULL COMMENT '추출 결과 데이터',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
                INDEX idx_doc_id (doc_id),
                INDEX idx_updated_at (updated_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='뉴스 추출 결과 캐시'
        """)

        # AI 전략 결정 이력 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_strategy_decisions (
                id INT PRIMARY KEY AUTO_INCREMENT COMMENT '고유 ID',
                decision_date DATETIME NOT NULL COMMENT '의사결정 일시',
                analysis_summary TEXT COMMENT 'AI 분석 요약',
                target_allocation JSON NOT NULL COMMENT '목표 자산 배분 (Stocks, Bonds, Alternatives, Cash)',
                recommended_stocks JSON COMMENT '자산군별 추천 종목',
                quant_signals JSON COMMENT '정량 시그널 데이터 (장단기 금리차, 실질 금리, 테일러 준칙 등)',
                account_pnl JSON COMMENT '계좌 손익 데이터 (자산군별 손익률)',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
                INDEX idx_decision_date (decision_date) COMMENT '의사결정 일시 인덱스 (최신 조회용)',
                INDEX idx_created_at (created_at) COMMENT '생성 일시 인덱스'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 전략 결정 이력'
        """)
        
        # recommended_stocks 컬럼 추가 (마이그레이션)
        try:
            cursor.execute("ALTER TABLE ai_strategy_decisions ADD COLUMN recommended_stocks JSON COMMENT '자산군별 추천 종목'")
        except Exception:
            pass  # 이미 존재하는 경우 무시
        
        # 모델 포트폴리오 (MP) 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_portfolios (
                id VARCHAR(20) PRIMARY KEY COMMENT 'MP ID (MP-1 ~ MP-5)',
                name VARCHAR(255) NOT NULL COMMENT 'MP 이름',
                description TEXT NOT NULL COMMENT 'MP 설명',
                strategy VARCHAR(255) NOT NULL COMMENT '핵심 전략',
                allocation_stocks DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '주식 비중 (%)',
                allocation_bonds DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '채권 비중 (%)',
                allocation_alternatives DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '대체투자 비중 (%)',
                allocation_cash DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '현금 비중 (%)',
                display_order INT DEFAULT 0 COMMENT '표시 순서',
                is_active BOOLEAN DEFAULT TRUE COMMENT '활성화 여부',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
                INDEX idx_display_order (display_order),
                INDEX idx_is_active (is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='모델 포트폴리오 (MP) 설정'
        """)
        
        # 기존 테이블에 컬럼 추가 (마이그레이션)
        try:
            cursor.execute("ALTER TABLE model_portfolios ADD COLUMN allocation_stocks DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '주식 비중 (%)'")
        except Exception:
            pass  # 이미 존재하는 경우 무시
        
        try:
            cursor.execute("ALTER TABLE model_portfolios ADD COLUMN allocation_bonds DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '채권 비중 (%)'")
        except Exception:
            pass
        
        try:
            cursor.execute("ALTER TABLE model_portfolios ADD COLUMN allocation_alternatives DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '대체투자 비중 (%)'")
        except Exception:
            pass
        
        try:
            cursor.execute("ALTER TABLE model_portfolios ADD COLUMN allocation_cash DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '현금 비중 (%)'")
        except Exception:
            pass
        
        try:
            cursor.execute("ALTER TABLE model_portfolios ADD COLUMN display_order INT DEFAULT 0 COMMENT '표시 순서'")
        except Exception:
            pass
        
        try:
            cursor.execute("ALTER TABLE model_portfolios ADD COLUMN is_active BOOLEAN DEFAULT TRUE COMMENT '활성화 여부'")
        except Exception:
            pass
        
        # Sub-MP (자산군별 세부 모델) 테이블
        # 주의: sub_model_portfolios / sub_mp_etf_details는 사용하지 않음
        # 실제 사용하는 테이블: sub_portfolio_models / sub_portfolio_compositions
        # 아래 테이블은 레거시이며, 새로 생성하지 않음
        # cursor.execute("""
        #     CREATE TABLE IF NOT EXISTS sub_model_portfolios (
        #         id VARCHAR(20) PRIMARY KEY COMMENT 'Sub-MP ID (Eq-A, Eq-N, Eq-D, Bnd-L, Bnd-N, Bnd-S, Alt-I, Alt-C)',
        #         name VARCHAR(255) NOT NULL COMMENT 'Sub-MP 이름',
        #         description TEXT NOT NULL COMMENT 'Sub-MP 설명',
        #         asset_class VARCHAR(50) NOT NULL COMMENT '자산군 (Stocks, Bonds, Alternatives)',
        #         display_order INT DEFAULT 0 COMMENT '표시 순서',
        #         is_active BOOLEAN DEFAULT TRUE COMMENT '활성화 여부',
        #         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
        #         updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
        #         INDEX idx_asset_class (asset_class),
        #         INDEX idx_display_order (display_order),
        #         INDEX idx_is_active (is_active)
        #     ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Sub-MP (자산군별 세부 모델) 설정'
        # """)
        
        # 기존 테이블에 컬럼 추가 (마이그레이션) - 레거시 테이블이므로 주석 처리
        # try:
        #     cursor.execute("ALTER TABLE sub_model_portfolios ADD COLUMN display_order INT DEFAULT 0 COMMENT '표시 순서'")
        # except Exception:
        #     pass
        # 
        # try:
        #     cursor.execute("ALTER TABLE sub_model_portfolios ADD COLUMN is_active BOOLEAN DEFAULT TRUE COMMENT '활성화 여부'")
        # except Exception:
        #     pass
        
        # Sub-MP ETF 상세 테이블 - 레거시 테이블이므로 주석 처리
        # cursor.execute("""
        #     CREATE TABLE IF NOT EXISTS sub_mp_etf_details (
        #         id INT AUTO_INCREMENT PRIMARY KEY COMMENT '고유 ID',
        #         sub_mp_id VARCHAR(20) NOT NULL COMMENT 'Sub-MP ID',
        #         category VARCHAR(100) NOT NULL COMMENT '카테고리 (예: 나스닥, S&P500, 배당주, 미국 장기채 등)',
        #         ticker VARCHAR(20) NOT NULL COMMENT 'ETF 티커',
        #         name VARCHAR(255) NOT NULL COMMENT 'ETF 이름',
        #         weight DECIMAL(5,4) NOT NULL COMMENT '자산군 내 비중 (0-1)',
        #         display_order INT DEFAULT 0 COMMENT '표시 순서',
        #         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
        #         updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
        #         FOREIGN KEY (sub_mp_id) REFERENCES sub_model_portfolios(id) ON DELETE CASCADE,
        #         INDEX idx_sub_mp_id (sub_mp_id),
        #         INDEX idx_display_order (display_order)
        #     ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Sub-MP별 ETF 상세 정보'
        # """)

        # 가상 시간 (Time Travel) 상태 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                `key` VARCHAR(50) PRIMARY KEY,
                `value` JSON,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='시스템 가상 시간 및 설정'
        """)

        # 리밸런싱 진행 상태 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rebalancing_state (
                id INT AUTO_INCREMENT PRIMARY KEY,
                target_date DATE NOT NULL COMMENT '대상 리밸런싱 날짜',
                status VARCHAR(50) NOT NULL DEFAULT 'PENDING' COMMENT '진행 상태 (PENDING, IN_PROGRESS, COMPLETED, FAILED)',
                current_phase VARCHAR(50) COMMENT '현재 단계 (ANALYSIS, SIGNAL, EXECUTION)',
                details JSON COMMENT '실행 상세 로그',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_target_date (target_date),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='리밸런싱 진행 상태'
        """)
        
        conn.commit()
        
        # 포트폴리오 마이그레이션 (코드에서 DB로) - 데이터가 없을 때만
        try:
            cursor.execute("SELECT COUNT(*) as count FROM model_portfolios")
            mp_count = cursor.fetchone().get('count', 0)
            if mp_count == 0:
                migrate_portfolios_from_code()
        except Exception as e:
            print(f"⚠️  포트폴리오 마이그레이션 실패 (무시하고 계속): {e}")


def is_migration_completed():
    """마이그레이션이 완료되었는지 확인"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM migration_metadata WHERE `key` = %s", ('json_migration_completed',))
            row = cursor.fetchone()
            return row is not None and row['value'] == 'true'
    except Exception:
        return False


def mark_migration_completed():
    """마이그레이션 완료 표시"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now()
            cursor.execute("""
                INSERT INTO migration_metadata (`key`, value, updated_at)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE value = %s, updated_at = %s
            """, ('json_migration_completed', 'true', now, 'true', now))
            conn.commit()
    except Exception as e:
        print(f"⚠️  마이그레이션 완료 표시 실패: {e}")


def migrate_from_json():
    """JSON 파일에서 MySQL로 데이터 마이그레이션 (최초 1회만 실행)"""
    # 이미 마이그레이션이 완료되었으면 스킵
    if is_migration_completed():
        return
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATABASE_DIR = os.path.join(BASE_DIR, "service", "database")
    
    # 사용자 데이터 마이그레이션
    users_file = os.path.join(DATABASE_DIR, "users.json")
    if os.path.exists(users_file):
        try:
            with open(users_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                users = data.get('users', [])
                
            with get_db_connection() as conn:
                cursor = conn.cursor()
                for user in users:
                    try:
                        # username 값을 id로 사용 (기존 id는 무시)
                        user_id = user.get('username') or user.get('id')
                        cursor.execute("""
                            INSERT IGNORE INTO users 
                            (id, password_hash, role, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            user_id,
                            user.get('password_hash'),
                            user.get('role', 'user'),
                            user.get('created_at', datetime.now().isoformat()),
                            user.get('updated_at', datetime.now().isoformat())
                        ))
                    except IntegrityError:
                        # 이미 존재하는 사용자는 스킵
                        pass
                conn.commit()
            print("✅ Users migrated from JSON to MySQL")
        except Exception as e:
            print(f"⚠️  Error migrating users: {e}")
    
    # 메모리 저장소 마이그레이션
    memory_file = os.path.join(BASE_DIR, "memory_store.json")
    if os.path.exists(memory_file):
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                memories = json.load(f)
                
            with get_db_connection() as conn:
                cursor = conn.cursor()
                for mem in memories:
                    cursor.execute("""
                        INSERT IGNORE INTO memory_store (topic, summary, created_at)
                        VALUES (%s, %s, %s)
                    """, (
                        mem.get('topic', ''),
                        mem.get('summary', ''),
                        mem.get('created_at', datetime.now().isoformat())
                    ))
                conn.commit()
            print("✅ Memory store migrated from JSON to MySQL")
        except Exception as e:
            print(f"⚠️  Error migrating memory store: {e}")
    
    # 전략 설정 마이그레이션
    strategy_file = os.path.join(BASE_DIR, "service", "CurrentStrategy.json")
    if os.path.exists(strategy_file):
        try:
            with open(strategy_file, 'r', encoding='utf-8') as f:
                strategies = json.load(f)
                
            with get_db_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now()
                for platform, strategy in strategies.items():
                    cursor.execute("""
                        INSERT INTO strategies (platform, strategy, updated_at)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE strategy = %s, updated_at = %s
                    """, (platform, strategy, now, strategy, now))
                conn.commit()
            print("✅ Strategies migrated from JSON to MySQL")
        except Exception as e:
            print(f"⚠️  Error migrating strategies: {e}")
    
    # 마이그레이션 완료 표시
    mark_migration_completed()
    print("✅ JSON to MySQL migration completed")


def migrate_portfolios_from_code():
    """코드에 하드코딩된 포트폴리오 데이터를 DB로 마이그레이션
    
    주의: 초기 데이터는 이미 적재되어 있으므로 이 함수는 더 이상 사용하지 않습니다.
    DEFAULT 포트폴리오 정의도 삭제되었습니다.
    """
    # 초기 데이터는 이미 적재되어 있으므로 마이그레이션 불필요
    print("⚠️  migrate_portfolios_from_code()는 더 이상 사용하지 않습니다. 초기 데이터는 이미 적재되어 있습니다.")
    pass


def backup_database():
    """데이터베이스 백업 (mysqldump 사용)"""
    ensure_backup_dir()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"hobot_backup_{timestamp}.sql"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    try:
        import subprocess
        cmd = [
            'mysqldump',
            f'--host={DB_HOST}',
            f'--port={DB_PORT}',
            f'--user={DB_USER}',
            f'--password={DB_PASSWORD}',
            '--single-transaction',
            '--routines',
            '--triggers',
            DB_NAME
        ]
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
            
        if result.returncode == 0:
            print(f"✅ 데이터베이스 백업 완료: {backup_path}")
            cleanup_old_backups(days=30)
            return backup_path
        else:
            print(f"❌ 백업 실패: {result.stderr}")
            return None
    except FileNotFoundError:
        print("⚠️  mysqldump를 찾을 수 없습니다. MySQL 클라이언트가 설치되어 있는지 확인하세요.")
        return None
    except Exception as e:
        print(f"❌ 백업 실패: {e}")
        return None


def cleanup_old_backups(days=30):
    """오래된 백업 파일 정리"""
    try:
        import time
        current_time = time.time()
        cutoff_time = current_time - (days * 24 * 60 * 60)
        
        if not os.path.exists(BACKUP_DIR):
            return
        
        for filename in os.listdir(BACKUP_DIR):
            if filename.startswith("hobot_backup_") and filename.endswith(".sql"):
                file_path = os.path.join(BACKUP_DIR, filename)
                try:
                    file_time = os.path.getmtime(file_path)
                    if file_time < cutoff_time:
                        os.remove(file_path)
                        print(f"🗑️  오래된 백업 파일 삭제: {filename}")
                except Exception as e:
                    print(f"⚠️  백업 파일 삭제 실패 ({filename}): {e}")
    except Exception as e:
        print(f"⚠️  백업 정리 실패: {e}")


def cleanup_old_extraction_cache(days: int = 90) -> int:
    """오래된 뉴스 추출 캐시(extraction_cache) 정리.

    Args:
        days: 보존 일수 (기본 90일)

    Returns:
        int: 삭제된 레코드 수
    """
    if days <= 0:
        raise ValueError("days must be a positive integer")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM extraction_cache
            WHERE updated_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s DAY)
            """,
            (days,),
        )
        deleted_rows = cursor.rowcount or 0
        conn.commit()
        return deleted_rows


def restore_database(backup_path: str):
    """데이터베이스 복원"""
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"백업 파일을 찾을 수 없습니다: {backup_path}")
    
    try:
        import subprocess
        
        # 현재 데이터베이스 백업
        current_backup = backup_database()
        if current_backup:
            print(f"✅ 현재 데이터베이스 백업 완료: {current_backup}")
        
        # 백업 파일로 복원
        cmd = [
            'mysql',
            f'--host={DB_HOST}',
            f'--port={DB_PORT}',
            f'--user={DB_USER}',
            f'--password={DB_PASSWORD}',
            DB_NAME
        ]
        
        with open(backup_path, 'r', encoding='utf-8') as f:
            result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, text=True)
        
        if result.returncode == 0:
            print(f"✅ 데이터베이스 복원 완료: {backup_path}")
            return True
        else:
            raise Exception(f"복원 실패: {result.stderr}")
    except FileNotFoundError:
        raise Exception("mysql 클라이언트를 찾을 수 없습니다. MySQL 클라이언트가 설치되어 있는지 확인하세요.")
    except Exception as e:
        print(f"❌ 복원 실패: {e}")
        raise


def list_backups():
    """백업 파일 목록 조회"""
    ensure_backup_dir()
    
    if not os.path.exists(BACKUP_DIR):
        return []
    
    backups = []
    for filename in os.listdir(BACKUP_DIR):
        if filename.startswith("hobot_backup_") and filename.endswith(".sql"):
            file_path = os.path.join(BACKUP_DIR, filename)
            try:
                import time
                file_time = os.path.getmtime(file_path)
                file_size = os.path.getsize(file_path)
                backups.append({
                    'filename': filename,
                    'path': file_path,
                    'size': file_size,
                    'created_at': datetime.fromtimestamp(file_time).isoformat()
                })
            except Exception:
                pass
    
    # 생성 시간 기준으로 정렬 (최신순)
    backups.sort(key=lambda x: x['created_at'], reverse=True)
    return backups


# 데이터베이스 초기화는 지연 초기화로 변경
# 모듈 import 시점에는 실행하지 않고, 실제 사용 시점에 초기화
_db_initialized = False
_init_lock = threading.Lock()   # 멀티스레드 동시 초기화 방지 Lock
_init_failed_at: float = 0.0    # 마지막 초기화 실패 시각 (monotonic)
_INIT_RETRY_INTERVAL = 60.0     # 초기화 실패 후 재시도 대기 시간 (초)


def ensure_database_initialized():
    """데이터베이스가 초기화되었는지 확인하고, 필요시 초기화.

    - threading.Lock 으로 멀티스레드 동시 초기화 경쟁 방지 (Double-checked locking)
    - 초기화 실패 시 _INIT_RETRY_INTERVAL(60초) Cool-down 후 재시도
      → 매 요청마다 DB 커넥션을 낭비하는 (1040 Too many connections) 문제 해결
    - init_database()는 내부에서 _direct_db_connection()을 사용하므로
      재귀 감지(_initializing)가 더 이상 필요 없음
    """
    global _db_initialized, _init_failed_at

    # 빠른 경로: 이미 초기화 완료
    if _db_initialized:
        return

    # 빠른 경로: Cool-down 중이면 스킵 (매 요청마다 재시도 방지)
    if _init_failed_at and (time.monotonic() - _init_failed_at) < _INIT_RETRY_INTERVAL:
        return

    with _init_lock:
        # Lock 획득 후 다시 확인 (다른 스레드가 먼저 초기화했을 수 있음)
        if _db_initialized:
            return
        if _init_failed_at and (time.monotonic() - _init_failed_at) < _INIT_RETRY_INTERVAL:
            return

        try:
            init_database()
            _db_initialized = True
            _init_failed_at = 0.0  # 성공 시 실패 기록 초기화
        except Exception as e:
            _init_failed_at = time.monotonic()  # 실패 시각 기록 → Cool-down 시작
            print(f"⚠️  데이터베이스 초기화 실패: {e}")
            print(f"MySQL 서버가 실행 중인지, 연결 정보가 올바른지 확인하세요.")
            print(f"   → {_INIT_RETRY_INTERVAL:.0f}초 후 재시도합니다.")
            # 초기화 실패해도 예외를 발생시키지 않음 (서비스 시작은 계속)
