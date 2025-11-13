# MySQL 데이터베이스 설정 가이드

## 📋 개요

이 프로젝트는 **MySQL** 데이터베이스를 사용하여 데이터를 관리합니다.

## 🔧 환경 변수 설정

`.env` 파일에 다음 환경 변수를 설정하세요:

```bash
# MySQL 연결 설정
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=hobot
DB_CHARSET=utf8mb4
```

## 🚀 빠른 시작

### 1. MySQL 설치 (EC2)

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install mysql-server

# MySQL 시작
sudo systemctl start mysql
sudo systemctl enable mysql

# 보안 설정
sudo mysql_secure_installation
```

### 2. 데이터베이스 생성

```bash
# MySQL 접속
mysql -u root -p

# 데이터베이스 생성
CREATE DATABASE hobot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 사용자 생성 및 권한 부여 (선택사항)
CREATE USER 'hobot'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON hobot.* TO 'hobot'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 3. Python 패키지 설치

```bash
pip install -r requirements.txt
```

### 4. 데이터베이스 초기화 및 마이그레이션

```bash
# 자동 마이그레이션 (서비스 시작 시 자동 실행)
python hobot/main.py

# 또는 수동 마이그레이션
python hobot/migrate_to_mysql.py
```

## 📁 데이터베이스 구조

### 테이블

1. **users**: 사용자 인증 정보
2. **memory_store**: LLM 메모리 저장소
3. **strategies**: 거래 전략 설정
4. **tokens**: API 토큰 저장
5. **migration_metadata**: 마이그레이션 메타데이터

### 테이블 스키마

#### users 테이블
```sql
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'user',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX idx_username (username),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### memory_store 테이블
```sql
CREATE TABLE memory_store (
    id INT AUTO_INCREMENT PRIMARY KEY,
    topic VARCHAR(255) NOT NULL,
    summary TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_topic (topic)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### strategies 테이블
```sql
CREATE TABLE strategies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    platform VARCHAR(50) UNIQUE NOT NULL,
    strategy VARCHAR(255) NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX idx_platform (platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

## 🔧 관리 명령어

### 데이터베이스 확인

```bash
# MySQL 접속
mysql -u root -p

# 데이터베이스 선택
USE hobot;

# 테이블 목록
SHOW TABLES;

# 데이터 조회
SELECT * FROM users;
SELECT COUNT(*) FROM memory_store;
```

### 백업

```bash
# Python 함수 사용
python -c "from service.database.db import backup_database; backup_database()"

# 백업 유틸리티 사용
python hobot/service/database/backup_utils.py backup

# 수동 백업 (mysqldump)
mysqldump -u root -p hobot > /var/backups/hobot/backup_$(date +%Y%m%d_%H%M%S).sql
```

### 복원

```bash
# Python 함수 사용
python -c "from service.database.db import restore_database; restore_database('/var/backups/hobot/backup.sql')"

# 백업 유틸리티 사용
python hobot/service/database/backup_utils.py restore --file /var/backups/hobot/backup.sql

# 수동 복원
mysql -u root -p hobot < /var/backups/hobot/backup.sql
```

## ⚠️ 주의사항

1. **연결 풀**: 현재는 연결 풀을 사용하지 않습니다. 필요시 추가할 수 있습니다.
2. **트랜잭션**: 모든 쓰기 작업은 트랜잭션으로 처리됩니다.
3. **인덱스**: 주요 컬럼에 인덱스가 자동으로 생성됩니다.
4. **백업**: 정기적으로 데이터베이스를 백업하세요.

## 🔐 보안 고려사항

1. **비밀번호**: `.env` 파일에 데이터베이스 비밀번호를 저장하고 Git에 커밋하지 마세요.
2. **사용자 권한**: 프로덕션 환경에서는 최소 권한 원칙을 따르세요.
3. **SSL 연결**: 가능하면 SSL 연결을 사용하세요.

## 📊 성능 최적화

1. **인덱스**: 자동으로 생성된 인덱스로 빠른 검색 지원
2. **InnoDB 엔진**: 트랜잭션 및 외래 키 지원
3. **utf8mb4**: 이모지 및 모든 유니코드 문자 지원

## 🆘 문제 해결

### 연결 오류

```bash
# MySQL 서버 상태 확인
sudo systemctl status mysql

# MySQL 재시작
sudo systemctl restart mysql

# 방화벽 확인 (원격 연결 시)
sudo ufw allow 3306/tcp
```

### 권한 오류

```bash
# MySQL 접속
mysql -u root -p

# 권한 확인
SHOW GRANTS FOR 'hobot'@'localhost';

# 권한 부여
GRANT ALL PRIVILEGES ON hobot.* TO 'hobot'@'localhost';
FLUSH PRIVILEGES;
```

### 데이터베이스가 생성되지 않는 경우

```python
from service.database.db import init_database
init_database()
```

## 📚 추가 리소스

- [MySQL 공식 문서](https://dev.mysql.com/doc/)
- [PyMySQL 문서](https://pymysql.readthedocs.io/)

