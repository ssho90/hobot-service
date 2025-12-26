"""
사용자 인증 및 권한 관리 모듈 (SQLite 기반)
"""
import os
import hashlib
import secrets
import json
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import jwt
import pyotp
import qrcode
from io import BytesIO
from fastapi import HTTPException, status
from service.database.db import get_db_connection
from service.utils.encryption import encrypt_data, decrypt_data

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
            cursor.execute("SELECT * FROM users WHERE id = %s", ('admin',))
            admin_user = cursor.fetchone()
            
            if not admin_user:
                now = datetime.now()
                cursor.execute("""
                    INSERT INTO users (id, password_hash, role, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    'admin',
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


def get_user_by_id(user_id: str) -> Optional[Dict]:
    """ID로 사용자 조회 (username이 id가 됨)"""
    init_db()  # 지연 초기화
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        return _row_to_dict(row)


def create_user(username: str, password: str, role: str = "user") -> Dict:
    """새 사용자 생성 (username이 id가 됨)"""
    init_db()  # 지연 초기화
    # 중복 확인
    if get_user_by_id(username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    password_hash = hash_password(password)
    now = datetime.now()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (id, password_hash, role, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (username, password_hash, role, now, now))
        conn.commit()
    
    # 비밀번호 해시 제외하고 반환
    return {

        'username': username,
        'id': username,
        'role': role,
        'created_at': now,
        'updated_at': now
    }


def get_all_users() -> List[Dict]:
    """모든 사용자 조회 (admin 전용)"""
    init_db()  # 지연 초기화
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, role, created_at, updated_at FROM users")
        rows = cursor.fetchall()
        # 비밀번호 해시 제외하고 반환
        return [
            {
                'id': row['id'],
                'role': row['role'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at']
            }
            for row in rows
        ]


def update_user(user_id: str, new_user_id: Optional[str] = None, 
                role: Optional[str] = None) -> Dict:
    """사용자 정보 업데이트 (id 변경 시 모든 관련 데이터도 함께 업데이트)"""
    init_db()  # 지연 초기화
    # 사용자 존재 확인
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # id 변경 시 중복 확인
    if new_user_id is not None and new_user_id != user_id:
        existing = get_user_by_id(new_user_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )
    
    # 업데이트 필드 구성
    update_fields = []
    update_values = []
    
    if new_user_id is not None and new_user_id != user_id:
        # id 변경은 복잡하므로 별도 처리 필요 (외래키 참조 업데이트)
        # 일단 role만 업데이트하고, id 변경은 별도 함수로 처리하는 것이 안전
        # 여기서는 role만 업데이트
        pass
    
    if role is not None:
        update_fields.append("role = %s")
        update_values.append(role)
    
    if update_fields:
        update_fields.append("updated_at = %s")
        update_values.append(datetime.now())
        update_values.append(user_id)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s",
                update_values
            )
            conn.commit()
    
    # id 변경 처리
    if new_user_id is not None and new_user_id != user_id:
        # 외래키 참조가 있는 경우 CASCADE로 처리되지만, 명시적으로 업데이트
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # user_kis_credentials 테이블의 user_id 업데이트
            cursor.execute("""
                UPDATE user_kis_credentials 
                SET user_id = %s 
                WHERE user_id = %s
            """, (new_user_id, user_id))
            # users 테이블의 id 업데이트
            cursor.execute("""
                UPDATE users 
                SET id = %s, updated_at = %s
                WHERE id = %s
            """, (new_user_id, datetime.now(), user_id))
            conn.commit()
        user_id = new_user_id
    
    # 업데이트된 사용자 정보 반환
    updated_user = get_user_by_id(user_id)
    return {
        'id': updated_user['id'],
        'role': updated_user['role'],
        'created_at': updated_user['created_at'],
        'updated_at': updated_user['updated_at']
    }


def delete_user(user_id: str) -> bool:
    """사용자 삭제"""
    init_db()  # 지연 초기화
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        return cursor.rowcount > 0


def is_system_admin(user_id: str) -> bool:
    """시스템 어드민 여부 확인 (admin role을 가진 사용자)"""
    user = get_user_by_id(user_id)
    if not user:
        return False
    return user.get("role") == "admin"


# ============================================
# MFA (Multi-Factor Authentication) 함수
# ============================================

def generate_mfa_secret() -> str:
    """MFA Secret Key 생성"""
    return pyotp.random_base32()


def generate_mfa_qr_code(secret: str, username: str, issuer: str = "Hobot") -> str:
    """
    MFA QR 코드 생성 (base64 인코딩된 이미지 반환)
    
    Args:
        secret: MFA Secret Key
        username: 사용자명
        issuer: 발행자 이름
        
    Returns:
        base64 인코딩된 QR 코드 이미지 문자열
    """
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name=issuer
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"


def verify_mfa_code(secret: str, code: str) -> bool:
    """
    MFA 코드 검증
    
    Args:
        secret: MFA Secret Key
        code: 사용자가 입력한 6자리 코드
        
    Returns:
        검증 성공 여부
    """
    try:
        totp = pyotp.TOTP(secret)
        # 현재 시간 기준 ±30초 허용
        return totp.verify(code, valid_window=1)
    except Exception:
        return False


def generate_backup_codes(count: int = 10) -> List[str]:
    """
    MFA 백업 코드 생성
    
    Args:
        count: 생성할 백업 코드 개수
        
    Returns:
        백업 코드 목록
    """
    codes = []
    for _ in range(count):
        # 8자리 숫자 코드 생성
        code = ''.join([str(secrets.randbelow(10)) for _ in range(8)])
        codes.append(code)
    return codes


def hash_backup_code(code: str) -> str:
    """백업 코드 해싱 (비교용)"""
    return hashlib.sha256(code.encode()).hexdigest()


def verify_backup_code(code: str, hashed_codes: List[str]) -> bool:
    """
    백업 코드 검증
    
    Args:
        code: 사용자가 입력한 백업 코드
        hashed_codes: 해시된 백업 코드 목록
        
    Returns:
        검증 성공 여부
    """
    code_hash = hash_backup_code(code)
    return code_hash in hashed_codes


def setup_mfa(user_id: str) -> Dict:
    """
    MFA 설정 시작 (Secret Key 및 QR 코드 생성)
    
    Args:
        user_id: 사용자 ID (username)
        
    Returns:
        {
            'secret': str,  # 임시 Secret (설정 완료 전까지만 사용)
            'qr_code': str  # QR 코드 이미지 (base64)
        }
    """
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.get("mfa_enabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled"
        )
    
    # Secret Key 생성
    secret = generate_mfa_secret()
    
    # QR 코드 생성 (user_id를 username으로 사용)
    qr_code = generate_mfa_qr_code(secret, user_id)
    
    return {
        "secret": secret,  # 임시로 평문 반환 (설정 완료 시 암호화하여 저장)
        "qr_code": qr_code
    }


def verify_mfa_setup(user_id: str, secret: str, code: str) -> Dict:
    """
    MFA 설정 완료 (코드 검증 후 DB에 저장)
    
    Args:
        user_id: 사용자 ID
        secret: 임시 Secret Key
        code: 사용자가 입력한 검증 코드
        
    Returns:
        백업 코드 목록
    """
    # 코드 검증
    if not verify_mfa_code(secret, code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code"
        )
    
    # 백업 코드 생성
    backup_codes = generate_backup_codes()
    hashed_backup_codes = [hash_backup_code(code) for code in backup_codes]
    
    # DB에 저장
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users
            SET mfa_enabled = TRUE,
                mfa_secret_encrypted = %s,
                mfa_backup_codes = %s,
                updated_at = %s
            WHERE id = %s
        """, (
            encrypt_data(secret),
            json.dumps(hashed_backup_codes),
            datetime.now(),
            user_id
        ))
        conn.commit()
    
    return {
        "backup_codes": backup_codes  # 평문으로 반환 (사용자가 저장해야 함)
    }


def disable_mfa(user_id: str, password: str) -> bool:
    """
    MFA 비활성화
    
    Args:
        user_id: 사용자 ID
        password: 사용자 비밀번호 (보안 확인용)
        
    Returns:
        성공 여부
    """
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # 비밀번호 확인
    if not verify_password(password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password"
        )
    
    # MFA 비활성화
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users
            SET mfa_enabled = FALSE,
                mfa_secret_encrypted = NULL,
                mfa_backup_codes = NULL,
                updated_at = %s
            WHERE id = %s
        """, (datetime.now(), user_id))
        conn.commit()
    
    return True


def verify_user_mfa(user_id: str, code: str) -> bool:
    """
    로그인 시 MFA 코드 검증
    
    Args:
        user_id: 사용자 ID
        code: 사용자가 입력한 MFA 코드
        
    Returns:
        검증 성공 여부
    """
    user = get_user_by_id(user_id)
    if not user or not user.get("mfa_enabled"):
        return False
    
    # Secret Key 복호화
    try:
        secret_encrypted = user.get("mfa_secret_encrypted")
        if not secret_encrypted:
            return False
        
        secret = decrypt_data(secret_encrypted)
    except Exception:
        return False
    
    # TOTP 코드 검증
    if verify_mfa_code(secret, code):
        return True
    
    # 백업 코드 검증
    backup_codes_json = user.get("mfa_backup_codes")
    if backup_codes_json:
        try:
            if isinstance(backup_codes_json, str):
                hashed_codes = json.loads(backup_codes_json)
            else:
                hashed_codes = backup_codes_json
            
            if verify_backup_code(code, hashed_codes):
                # 백업 코드 사용 시 해당 코드 제거
                hashed_codes.remove(hash_backup_code(code))
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE users
                        SET mfa_backup_codes = %s,
                            updated_at = %s
                        WHERE id = %s
                    """, (json.dumps(hashed_codes), datetime.now(), user_id))
                    conn.commit()
                return True
        except Exception:
            pass
    
    return False


def get_user_mfa_status(user_id: str) -> Dict:
    """
    사용자 MFA 상태 조회
    
    Args:
        user_id: 사용자 ID
        
    Returns:
        {
            'mfa_enabled': bool,
            'backup_codes_count': int  # 남은 백업 코드 개수
        }
    """
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    mfa_enabled = user.get("mfa_enabled", False)
    backup_codes_count = 0
    
    if mfa_enabled:
        backup_codes_json = user.get("mfa_backup_codes")
        if backup_codes_json:
            try:
                if isinstance(backup_codes_json, str):
                    backup_codes = json.loads(backup_codes_json)
                else:
                    backup_codes = backup_codes_json
                backup_codes_count = len(backup_codes) if isinstance(backup_codes, list) else 0
            except Exception:
                pass
    
    return {
        "mfa_enabled": mfa_enabled,
        "backup_codes_count": backup_codes_count
    }


def regenerate_backup_codes(user_id: str, password: str) -> List[str]:
    """
    백업 코드 재생성
    
    Args:
        user_id: 사용자 ID
        password: 사용자 비밀번호 (보안 확인용)
        
    Returns:
        새로운 백업 코드 목록
    """
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.get("mfa_enabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled"
        )
    
    # 비밀번호 확인
    if not verify_password(password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password"
        )
    
    # 새 백업 코드 생성
    backup_codes = generate_backup_codes()
    hashed_backup_codes = [hash_backup_code(code) for code in backup_codes]
    
    # DB에 저장
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users
            SET mfa_backup_codes = %s,
                updated_at = %s
            WHERE id = %s
        """, (json.dumps(hashed_backup_codes), datetime.now(), user_id))
        conn.commit()
    
    return backup_codes


# 데이터베이스 초기화는 지연 초기화로 변경
# 실제 사용 시점에 초기화됨 (get_db_connection 호출 시)
