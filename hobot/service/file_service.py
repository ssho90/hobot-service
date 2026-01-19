import os
import shutil
from fastapi import UploadFile
from typing import List, Dict
import logging
from datetime import datetime

# 파일 저장 경로 설정
UPLOAD_DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)

logger = logging.getLogger(__name__)

import unicodedata

# ... existing imports ...

def save_file(file: UploadFile) -> Dict:
    """
    업로드된 파일을 서버의 uploads 디렉토리에 저장합니다.
    파일명은 NFC(단일 문자) 형태로 정규화하여 저장합니다.
    """
    try:
        # 파일명 정규화 (NFD -> NFC)
        filename = unicodedata.normalize('NFC', file.filename)
        
        # 파일 경로 생성
        file_location = os.path.join(UPLOAD_DIRECTORY, filename)
        
        # 파일 저장
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        file_size = os.path.getsize(file_location)
        
        logger.info(f"File saved successfully: {filename} ({file_size} bytes)")
        
        return {
            "filename": filename,
            "size": file_size,
            "path": file_location,
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Failed to save file: {file.filename}, error: {str(e)}")
        raise e
    finally:
        file.file.close()

def list_files() -> List[Dict]:
    """
    uploads 디렉토리의 파일 목록을 반환합니다.
    """
    try:
        files_list = []
        if not os.path.exists(UPLOAD_DIRECTORY):
            return []
            
        for filename in os.listdir(UPLOAD_DIRECTORY):
            # 파일이 NFD로 저장되어 있을 경우를 대비해 목록 조회 시에도 NFC로 보여주는 것이 좋지만,
            # 다운로드/삭제 시 파일명을 그대로 사용하기 위해 원본 파일명을 사용하거나,
            # 별도의 매핑 로직이 필요함. 여기서는 있는 그대로 반환하되,
            # get_file_path에서 NFD/NFC 모두 찾도록 처리함.
            
            file_path = os.path.join(UPLOAD_DIRECTORY, filename)
            if os.path.isfile(file_path):
                stats = os.stat(file_path)
                
                # 표시용 이름은 NFC로 변환하여 보기 좋게 표시 (선택사항)
                display_name = unicodedata.normalize('NFC', filename)
                
                files_list.append({
                    "name": display_name,         # 프론트엔드에 보여줄 이름 (NFC)
                    "original_name": filename,    # 실제 파일시스템 이름 (삭제/다운로드 요청 시 사용) - *하지만 프론트엔드는 name만 씀*
                    # 프론트엔드는 name만 쓰므로, 백엔드 get_file_path에서 유연하게 찾아야 함.
                    "size": stats.st_size,
                    "last_modified": datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
        
        # 최신 수정일 순으로 정렬
        files_list.sort(key=lambda x: x["last_modified"], reverse=True)
        return files_list
    except Exception as e:
        logger.error(f"Failed to list files: {str(e)}")
        raise e

def delete_file(filename: str) -> Dict:
    """
    지정된 파일을 삭제합니다.
    """
    try:
        # 삭제 시에도 파일 찾기를 시도
        file_path = get_file_path(filename)
        
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"File deleted: {filename}")
            return {"status": "success", "message": f"File {filename} deleted successfully"}
        else:
            logger.warning(f"File not found for deletion: {filename}")
            return {"status": "error", "message": "File not found"}
    except Exception as e:
        logger.error(f"Failed to delete file: {filename}, error: {str(e)}")
        raise e

def get_file_path(filename: str) -> str:
    """
    파일의 절대 경로를 반환합니다. 파일이 없으면 None을 반환합니다.
    파일명 매칭 시 Unicode 정규화(NFC)를 거쳐 비교하여
    서버(NFD/NFC)와 클라이언트(NFC) 간의 인코딩 차이를 해결합니다.
    """
    # 1. 우선 정확한 경로로 존재 여부 확인 (빠른 경로)
    file_path = os.path.join(UPLOAD_DIRECTORY, filename)
    if os.path.exists(file_path):
        return file_path

    # 2. 존재하지 않는 경우, 디렉토리를 순회하며 NFC 정규화 후 비교
    try:
        if not os.path.exists(UPLOAD_DIRECTORY):
            return None
            
        target_nfc = unicodedata.normalize('NFC', filename)
        
        for disk_filename in os.listdir(UPLOAD_DIRECTORY):
            disk_nfc = unicodedata.normalize('NFC', disk_filename)
            
            if disk_nfc == target_nfc:
                return os.path.join(UPLOAD_DIRECTORY, disk_filename)
                
    except Exception as e:
        logger.error(f"Error while searching for file {filename}: {str(e)}")
        
    return None
