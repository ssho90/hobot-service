"""
암호화/복호화 유틸리티 모듈
KIS API 인증 정보를 암호화하여 저장하기 위한 모듈
"""
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import Optional


def get_master_key() -> bytes:
    """
    마스터키를 환경 변수에서 가져옴
    GitHub Action Secret에 등록된 KIS_ENCRYPTION_MASTER_KEY 사용
    
    환경 변수 값은 Fernet 키 형식(32바이트를 base64로 인코딩한 문자열)이어야 합니다.
    Fernet 키 생성 방법:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        print(key.decode())  # 이 값을 환경 변수에 설정
    """
    master_key = os.getenv("KIS_ENCRYPTION_MASTER_KEY")
    if not master_key:
        raise ValueError(
            "KIS_ENCRYPTION_MASTER_KEY 환경 변수가 설정되지 않았습니다. "
            "GitHub Action Secret에 등록해주세요."
        )
    
    # Fernet 키는 32바이트를 base64로 인코딩한 문자열이어야 함
    # 환경 변수에서 가져온 키를 Fernet 형식으로 변환
    try:
        # 이미 base64 인코딩된 Fernet 키인 경우
        # Fernet 키는 항상 44자 (32바이트를 base64로 인코딩)
        if len(master_key) == 44:
            return base64.urlsafe_b64decode(master_key.encode())
        else:
            # 길이가 맞지 않으면 PBKDF2로 키 생성
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'hobot_kis_encryption_salt',  # 고정된 salt
                iterations=100000,
            )
            derived_key = kdf.derive(master_key.encode())
            return derived_key
    except Exception as e:
        raise ValueError(f"마스터키 처리 실패: {str(e)}")


def get_fernet() -> Fernet:
    """Fernet 암호화 객체 생성"""
    master_key = get_master_key()
    # Fernet은 32바이트 키를 base64로 인코딩한 형식을 요구
    fernet_key = base64.urlsafe_b64encode(master_key)
    return Fernet(fernet_key)


def encrypt_data(data: str) -> str:
    """
    데이터 암호화
    
    Args:
        data: 암호화할 문자열
        
    Returns:
        암호화된 문자열 (base64 인코딩)
    """
    if not data:
        return ""
    
    fernet = get_fernet()
    encrypted = fernet.encrypt(data.encode('utf-8'))
    return base64.urlsafe_b64encode(encrypted).decode('utf-8')


def decrypt_data(encrypted_data: str) -> str:
    """
    데이터 복호화
    
    Args:
        encrypted_data: 암호화된 문자열 (base64 인코딩)
        
    Returns:
        복호화된 문자열
    """
    if not encrypted_data:
        return ""
    
    try:
        fernet = get_fernet()
        decoded = base64.urlsafe_b64decode(encrypted_data.encode('utf-8'))
        decrypted = fernet.decrypt(decoded)
        return decrypted.decode('utf-8')
    except Exception as e:
        raise ValueError(f"복호화 실패: {str(e)}")

