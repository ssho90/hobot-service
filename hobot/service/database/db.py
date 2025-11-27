"""
MySQL 데이터베이스 관리 모듈
"""
import os
import json
import threading
from typing import Optional, Dict, List, Any
from contextlib import contextmanager
from datetime import datetime
import pymysql
from pymysql.cursors import DictCursor
from pymysql.err import OperationalError, IntegrityError

# MySQL 연결 설정 (환경 변수에서 가져오기)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "hobot")
DB_CHARSET = os.getenv("DB_CHARSET", "utf8mb4")

# 백업 디렉토리 (시스템 경로)
BACKUP_DIR = "/var/backups/hobot"

# 파일 접근 동기화를 위한 Lock
_db_lock = threading.Lock()


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
def get_db_connection():
    """데이터베이스 연결 컨텍스트 매니저"""
    # 데이터베이스 초기화 확인 (재귀 호출 방지를 위해 init_database 내부에서는 호출하지 않음)
    # init_database 내부에서 get_db_connection을 호출하므로, 여기서는 초기화만 확인
    if not _initializing:  # 초기화 중이 아닐 때만 호출
        ensure_database_initialized()
    
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
            connect_timeout=5  # 5초 타임아웃
        )
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def init_database():
    """데이터베이스 및 테이블 초기화"""
    # 먼저 데이터베이스가 없으면 생성
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            charset=DB_CHARSET,
            connect_timeout=5  # 5초 타임아웃
        )
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET {DB_CHARSET} COLLATE {DB_CHARSET}_unicode_ci")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  데이터베이스 생성 실패: {e}")
        raise
    
    # 테이블 생성
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 사용자 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'user',
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                INDEX idx_username (username),
                INDEX idx_email (email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
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
        
        # 자산군 상세 설정 테이블 (사용자가 관리하는 자산군별 종목 및 비율)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS asset_class_details (
                id INT AUTO_INCREMENT PRIMARY KEY,
                asset_class VARCHAR(50) NOT NULL COMMENT '자산군 (stocks, bonds, alternatives, cash)',
                ticker VARCHAR(20) NOT NULL COMMENT 'ETF 티커',
                name VARCHAR(255) NOT NULL COMMENT 'ETF 이름',
                weight DECIMAL(5,4) NOT NULL COMMENT '자산군 내 비중 (0-1)',
                currency VARCHAR(10) COMMENT '통화 (현금 자산군의 경우: KRW, USD)',
                is_active BOOLEAN DEFAULT TRUE COMMENT '활성화 여부',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
                UNIQUE KEY unique_asset_class_ticker (asset_class, ticker) COMMENT '자산군별 티커 중복 방지',
                INDEX idx_asset_class (asset_class) COMMENT '자산군 인덱스',
                INDEX idx_is_active (is_active) COMMENT '활성화 여부 인덱스'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='자산군별 상세 종목 및 비율 설정'
        """)
        
        # currency 컬럼 추가 (마이그레이션)
        try:
            cursor.execute("ALTER TABLE asset_class_details ADD COLUMN currency VARCHAR(10) COMMENT '통화 (현금 자산군의 경우: KRW, USD)'")
        except Exception:
            pass  # 이미 존재하는 경우 무시
        
        # 종목명-티커 매핑 테이블 (KIS API에서 수집)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_tickers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ticker VARCHAR(20) NOT NULL COMMENT '종목 코드',
                stock_name VARCHAR(255) NOT NULL COMMENT '종목명',
                market_type VARCHAR(10) DEFAULT 'J' COMMENT '시장 구분 (J: 주식, ETF 등)',
                is_active BOOLEAN DEFAULT TRUE COMMENT '활성화 여부',
                last_updated DATE NOT NULL COMMENT '마지막 업데이트 날짜',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
                UNIQUE KEY unique_ticker (ticker) COMMENT '티커 중복 방지',
                INDEX idx_stock_name (stock_name) COMMENT '종목명 인덱스 (검색용)',
                INDEX idx_is_active (is_active) COMMENT '활성화 여부 인덱스',
                INDEX idx_last_updated (last_updated) COMMENT '업데이트 날짜 인덱스'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='종목명-티커 매핑 (KIS API 수집)'
        """)
        
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
                INDEX idx_model_name (model_name) COMMENT '모델명 인덱스',
                INDEX idx_provider (provider) COMMENT '제공자 인덱스',
                INDEX idx_created_at (created_at) COMMENT '생성 일시 인덱스 (일자별 조회용)',
                INDEX idx_service_name (service_name) COMMENT '서비스명 인덱스'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='LLM 사용 로그'
        """)
        
        conn.commit()


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
                        cursor.execute("""
                            INSERT IGNORE INTO users 
                            (id, username, email, password_hash, role, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            user.get('id'),
                            user.get('username'),
                            user.get('email'),
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
_initializing = False  # 재귀 호출 방지 플래그

def ensure_database_initialized():
    """데이터베이스가 초기화되었는지 확인하고, 필요시 초기화"""
    global _db_initialized, _initializing
    
    # 이미 초기화되었으면 바로 리턴
    if _db_initialized:
        return
    
    # 현재 초기화 중이면 리턴 (재귀 호출 방지)
    if _initializing:
        return
    
    # 초기화 시작
    _initializing = True
    try:
        init_database()
        _db_initialized = True
    except Exception as e:
        print(f"⚠️  데이터베이스 초기화 실패: {e}")
        print("MySQL 서버가 실행 중인지, 연결 정보가 올바른지 확인하세요.")
        # 초기화 실패해도 예외를 발생시키지 않음 (서비스 시작은 계속)
    finally:
        _initializing = False
