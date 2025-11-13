"""
사용자 인증 및 권한 관리 모듈 (SQLite 기반)
"""
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import jwt
from fastapi import HTTPException, status
from service.database.db import get_db_connection

# JWT 시크릿 키 (환경 변수에서 가져오거나 기본값 사용)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


def _row_to_dict(row) -> Dict:
    """MySQL Row를 딕셔너리로 변환"""
    return dict(row) if row else None


_db_initialized = False

def init_db():
    """데이터베이스 초기화 (지연 초기화)"""
    global _db_initialized
    if _db_initialized:
        return
    
    from service.database.db import init_database, migrate_from_json, ensure_database_initialized
    
    # 데이터베이스 초기화 (이미 ensure_database_initialized에서 처리됨)
    ensure_database_initialized()
    
    # JSON에서 마이그레이션 (최초 1회만)
    try:
        migrate_from_json()
    except Exception as e:
        print(f"⚠️  마이그레이션 실패 (무시하고 계속): {e}")
    
    # 기본 admin 사용자 확인 및 생성
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = %s", ('admin',))
            admin_user = cursor.fetchone()
            
            if not admin_user:
                now = datetime.now()
                cursor.execute("""
                    INSERT INTO users (username, email, password_hash, role, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    'admin',
                    'admin@hobot.com',
                    hash_password('admin'),
                    'admin',
                    now,
                    now
                ))
                conn.commit()
    except Exception as e:
        print(f"⚠️  Admin 사용자 생성 실패 (무시하고 계속): {e}")
    
    _db_initialized = True


def hash_password(password: str) -> str:
    """비밀번호 해싱"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """비밀번호 검증"""
    return hash_password(password) == password_hash


def create_access_token(data: Dict) -> str:
    """JWT 토큰 생성"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict]:
    """JWT 토큰 검증"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


def get_user_by_username(username: str) -> Optional[Dict]:
    """사용자명으로 사용자 조회"""
    init_db()  # 지연 초기화
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        return _row_to_dict(row)


def get_user_by_email(email: str) -> Optional[Dict]:
    """이메일로 사용자 조회"""
    init_db()  # 지연 초기화
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        row = cursor.fetchone()
        return _row_to_dict(row)


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """ID로 사용자 조회"""
    init_db()  # 지연 초기화
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        return _row_to_dict(row)


def create_user(username: str, email: str, password: str, role: str = "user") -> Dict:
    """새 사용자 생성"""
    init_db()  # 지연 초기화
    # 중복 확인
    if get_user_by_username(username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # 이메일이 있는 경우에만 중복 확인
    if email and get_user_by_email(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )
    
    password_hash = hash_password(password)
    now = datetime.now()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, role, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (username, email, password_hash, role, now, now))
        user_id = cursor.lastrowid
        conn.commit()
    
    # 비밀번호 해시 제외하고 반환
    return {
        'id': user_id,
        'username': username,
        'email': email,
        'role': role,
        'created_at': now,
        'updated_at': now
    }


def get_all_users() -> List[Dict]:
    """모든 사용자 조회 (admin 전용)"""
    init_db()  # 지연 초기화
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, role, created_at, updated_at FROM users")
        rows = cursor.fetchall()
        # 비밀번호 해시 제외하고 반환
        return [
            {
                'id': row['id'],
                'username': row['username'],
                'email': row['email'],
                'role': row['role'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at']
            }
            for row in rows
        ]


def update_user(user_id: int, username: Optional[str] = None, 
                email: Optional[str] = None, role: Optional[str] = None) -> Dict:
    """사용자 정보 업데이트"""
    init_db()  # 지연 초기화
    # 사용자 존재 확인
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # 중복 확인 및 업데이트
    update_fields = []
    update_values = []
    
    if username is not None:
        existing = get_user_by_username(username)
        if existing and existing.get('id') != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )
        update_fields.append("username = %s")
        update_values.append(username)
    
    if email is not None:
        existing = get_user_by_email(email)
        if existing and existing.get('id') != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
        update_fields.append("email = %s")
        update_values.append(email)
    
    if role is not None:
        update_fields.append("role = %s")
        update_values.append(role)
    
    if update_fields:
        update_fields.append("updated_at = %s")
        update_values.append(datetime.now())
        update_values.append(user_id)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # MySQL에서는 마지막 값이 WHERE 조건
            where_value = update_values.pop()
            update_values.append(where_value)
            cursor.execute(
                f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s",
                update_values
            )
            conn.commit()
    
    # 업데이트된 사용자 정보 반환
    updated_user = get_user_by_id(user_id)
    return {
        'id': updated_user['id'],
        'username': updated_user['username'],
        'email': updated_user['email'],
        'role': updated_user['role'],
        'created_at': updated_user['created_at'],
        'updated_at': updated_user['updated_at']
    }


def delete_user(user_id: int) -> bool:
    """사용자 삭제"""
    init_db()  # 지연 초기화
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        return cursor.rowcount > 0


def is_system_admin(username: str) -> bool:
    """시스템 어드민 여부 확인 (ssho, admin 사용자)"""
    SYSTEM_ADMINS = ['ssho', 'admin']
    return username in SYSTEM_ADMINS


# 데이터베이스 초기화는 지연 초기화로 변경
# 실제 사용 시점에 초기화됨 (get_db_connection 호출 시)
