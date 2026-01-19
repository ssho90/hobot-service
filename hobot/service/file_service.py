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

def save_file(file: UploadFile) -> Dict:
    """
    업로드된 파일을 서버의 uploads 디렉토리에 저장합니다.
    """
    try:
        # 파일 경로 생성
        file_location = os.path.join(UPLOAD_DIRECTORY, file.filename)
        
        # 파일 저장
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        file_size = os.path.getsize(file_location)
        
        logger.info(f"File saved successfully: {file.filename} ({file_size} bytes)")
        
        return {
            "filename": file.filename,
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
            file_path = os.path.join(UPLOAD_DIRECTORY, filename)
            if os.path.isfile(file_path):
                stats = os.stat(file_path)
                files_list.append({
                    "name": filename,
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
        file_path = os.path.join(UPLOAD_DIRECTORY, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"File deleted: {filename}")
            return {"status": "success", "message": f"File {filename} deleted successfully"}
        else:
            logger.warning(f"File not found for deletion: {filename}")
            return {"status": "error", "message": "File not found"}
    except Exception as e:
        logger.error(f"Failed to delete file: {filename}, error: {str(e)}")
        raise e
