"""
사용자 인증 및 권한 관리 모듈 (JSON 파일 기반)
"""
import os
import json
import hashlib
import secrets
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import jwt
from fastapi import HTTPException, status

# JWT 시크릿 키 (환경 변수에서 가져오거나 기본값 사용)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# 데이터베이스 디렉토리 및 파일 경로
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_DIR = os.path.join(BASE_DIR, "service", "database")
USERS_FILE = os.path.join(DATABASE_DIR, "users.json")

# 파일 접근 동기화를 위한 Lock
_file_lock = threading.Lock()


def ensure_database_dir():
    """데이터베이스 디렉토리 생성"""
    os.makedirs(DATABASE_DIR, exist_ok=True)


def load_users() -> List[Dict]:
    """JSON 파일에서 사용자 목록 로드"""
    ensure_database_dir()
    
    if not os.path.exists(USERS_FILE):
        return []
    
    try:
        with _file_lock:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('users', [])
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_users(users: List[Dict]):
    """사용자 목록을 JSON 파일에 저장"""
    ensure_database_dir()
    
    with _file_lock:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'users': users}, f, indent=2, ensure_ascii=False)


def get_next_id(users: List[Dict]) -> int:
    """다음 사용자 ID 생성"""
    if not users:
        return 1
    return max(user.get('id', 0) for user in users) + 1


def init_db():
    """데이터베이스 초기화"""
    ensure_database_dir()
    
    users = load_users()
    
    # 기본 admin 사용자 확인 및 생성
    admin_exists = any(user.get('role') == 'admin' for user in users)
    
    if not admin_exists:
        admin_user = {
            'id': get_next_id(users),
            'username': 'admin',
            'email': 'admin@hobot.com',
            'password_hash': hash_password('admin'),
            'role': 'admin',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        users.append(admin_user)
        save_users(users)


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
    users = load_users()
    for user in users:
        if user.get('username') == username:
            return user
    return None


def get_user_by_email(email: str) -> Optional[Dict]:
    """이메일로 사용자 조회"""
    users = load_users()
    for user in users:
        if user.get('email') == email:
            return user
    return None


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """ID로 사용자 조회"""
    users = load_users()
    for user in users:
        if user.get('id') == user_id:
            return user
    return None


def create_user(username: str, email: str, password: str, role: str = "user") -> Dict:
    """새 사용자 생성"""
    users = load_users()
    
    # 중복 확인
    if get_user_by_username(username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    if get_user_by_email(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )
    
    password_hash = hash_password(password)
    now = datetime.now().isoformat()
    
    new_user = {
        'id': get_next_id(users),
        'username': username,
        'email': email,
        'password_hash': password_hash,
        'role': role,
        'created_at': now,
        'updated_at': now
    }
    
    users.append(new_user)
    save_users(users)
    
    # 비밀번호 해시 제외하고 반환
    return {
        'id': new_user['id'],
        'username': new_user['username'],
        'email': new_user['email'],
        'role': new_user['role'],
        'created_at': new_user['created_at'],
        'updated_at': new_user['updated_at']
    }


def get_all_users() -> List[Dict]:
    """모든 사용자 조회 (admin 전용)"""
    users = load_users()
    # 비밀번호 해시 제외하고 반환
    return [
        {
            'id': user.get('id'),
            'username': user.get('username'),
            'email': user.get('email'),
            'role': user.get('role'),
            'created_at': user.get('created_at'),
            'updated_at': user.get('updated_at')
        }
        for user in users
    ]


def update_user(user_id: int, username: Optional[str] = None, 
                email: Optional[str] = None, role: Optional[str] = None) -> Dict:
    """사용자 정보 업데이트"""
    users = load_users()
    
    user_index = None
    for i, user in enumerate(users):
        if user.get('id') == user_id:
            user_index = i
            break
    
    if user_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user = users[user_index]
    
    # 중복 확인 및 업데이트
    if username is not None:
        existing = get_user_by_username(username)
        if existing and existing.get('id') != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )
        user['username'] = username
    
    if email is not None:
        existing = get_user_by_email(email)
        if existing and existing.get('id') != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
        user['email'] = email
    
    if role is not None:
        user['role'] = role
    
    user['updated_at'] = datetime.now().isoformat()
    
    save_users(users)
    
    # 비밀번호 해시 제외하고 반환
    return {
        'id': user['id'],
        'username': user['username'],
        'email': user['email'],
        'role': user['role'],
        'created_at': user['created_at'],
        'updated_at': user['updated_at']
    }


def delete_user(user_id: int) -> bool:
    """사용자 삭제"""
    users = load_users()
    
    user_index = None
    for i, user in enumerate(users):
        if user.get('id') == user_id:
            user_index = i
            break
    
    if user_index is None:
        return False
    
    users.pop(user_index)
    save_users(users)
    
    return True


# 데이터베이스 초기화
init_db()
