import os
import shutil
import json
import uuid
import logging
import unicodedata
from datetime import datetime
from fastapi import UploadFile
from typing import List, Dict, Optional

# 파일 저장 경로 설정
UPLOAD_DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)
METADATA_FILE = os.path.join(UPLOAD_DIRECTORY, "files.json")

logger = logging.getLogger(__name__)

def _load_metadata() -> Dict:
    """메타데이터 파일 로드"""
    if not os.path.exists(METADATA_FILE):
        return {}
    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load metadata: {e}")
        return {}

def _save_metadata(data: Dict):
    """메타데이터 파일 저장"""
    try:
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save metadata: {e}")

def save_file(file: UploadFile) -> Dict:
    """
    업로드된 파일을 Hash ID로 저장하고 메타데이터를 기록합니다.
    """
    try:
        # Generate Hash ID (12 chars unique id)
        file_id = uuid.uuid4().hex[:12]
        ext = os.path.splitext(file.filename)[1]
        saved_filename = f"{file_id}{ext}"
        
        # 파일 경로
        file_location = os.path.join(UPLOAD_DIRECTORY, saved_filename)
        
        # 파일 저장
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        file_size = os.path.getsize(file_location)
        original_name = unicodedata.normalize('NFC', file.filename)
        
        # 메타데이터 저장
        metadata = _load_metadata()
        metadata[file_id] = {
            "id": file_id,
            "original_name": original_name,
            "saved_filename": saved_filename,
            "size": file_size,
            "upload_date": datetime.now().isoformat()
        }
        _save_metadata(metadata)
        
        logger.info(f"File saved: {original_name} -> {saved_filename} (ID: {file_id})")
        
        return {
            "id": file_id,
            "name": original_name,
            "size": file_size,
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Failed to save file: {file.filename}, error: {str(e)}")
        raise e
    finally:
        file.file.close()

def list_files() -> List[Dict]:
    """
    메타데이터를 기반으로 파일 목록을 반환합니다.
    """
    try:
        metadata = _load_metadata()
        files_list = []
        
        for fid, data in metadata.items():
            # 실제 파일 존재 여부 확인 (옵션)
            file_path = os.path.join(UPLOAD_DIRECTORY, data.get("saved_filename", ""))
            if os.path.exists(file_path):
                # 표시용 날짜 포맷
                try:
                    dt = datetime.fromisoformat(data["upload_date"])
                    date_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    date_str = data["upload_date"]
                    
                files_list.append({
                    "id": fid,
                    "name": data["original_name"],
                    "size": data["size"],
                    "last_modified": date_str
                })
        
        # 최신순 정렬
        files_list.sort(key=lambda x: x["last_modified"], reverse=True)
        return files_list
    except Exception as e:
        logger.error(f"Failed to list files: {str(e)}")
        raise e

def delete_file(file_id: str) -> Dict:
    """
    ID를 기반으로 파일을 삭제합니다.
    """
    try:
        metadata = _load_metadata()
        if file_id not in metadata:
             # 이전 버전 호환성 혹은 직접 파일명으로 삭제 요청이 왔을 경우를 대비할 수도 있으나,
             # 여기서는 ID 기반으로 완전히 전환함.
            return {"status": "error", "message": "File not found"}
            
        data = metadata[file_id]
        saved_filename = data["saved_filename"]
        file_path = os.path.join(UPLOAD_DIRECTORY, saved_filename)
        
        # 파일 삭제
        if os.path.exists(file_path):
            os.remove(file_path)
            
        # 메타데이터 삭제
        del metadata[file_id]
        _save_metadata(metadata)
        
        logger.info(f"File deleted: {file_id}")
        return {"status": "success", "message": "File deleted successfully"}
    except Exception as e:
        logger.error(f"Failed to delete file: {file_id}, error: {str(e)}")
        raise e

def get_file_info(file_id: str) -> Optional[Dict]:
    """
    ID를 기반으로 파일 정보(경로, 원본명)를 반환합니다.
    """
    metadata = _load_metadata()
    if file_id in metadata:
        data = metadata[file_id]
        file_path = os.path.join(UPLOAD_DIRECTORY, data["saved_filename"])
        if os.path.exists(file_path):
            return {
                "path": file_path,
                "original_name": data["original_name"]
            }
    return None
