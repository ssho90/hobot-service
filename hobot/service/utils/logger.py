"""
시스템 로깅 유틸리티 모듈
DB 로깅 및 파일 로깅을 통합 관리
"""
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, Any
from service.database.db import get_db_connection

# 로거 인스턴스
_logger = None

def get_logger():
    """로거 인스턴스 반환"""
    global _logger
    if _logger is None:
        _logger = logging.getLogger('hobot')
    return _logger

def log_to_db(
    module_name: str,
    log_level: str,
    log_message: str,
    error_type: Optional[str] = None,
    stack_trace: Optional[str] = None,
    execution_time_ms: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    시스템 로그를 DB에 저장
    
    Args:
        module_name: 모듈명 (module_1, module_2, module_3, module_4, module_5 등)
        log_level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL, FATAL)
        log_message: 로그 메시지
        error_type: 에러 타입 (에러 발생 시)
        stack_trace: 스택 트레이스 (에러 발생 시)
        execution_time_ms: 실행 시간 (밀리초)
        metadata: 추가 메타데이터 (JSON)
    """
    try:
        import json
        metadata_json = json.dumps(metadata) if metadata else None
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_logs (
                    module_name, log_level, log_message, error_type, 
                    stack_trace, execution_time_ms, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                module_name,
                log_level,
                log_message,
                error_type,
                stack_trace,
                execution_time_ms,
                metadata_json
            ))
            conn.commit()
    except Exception as e:
        # DB 로깅 실패 시 파일 로깅으로 폴백
        logger = get_logger()
        logger.error(f"Failed to log to DB: {e}", exc_info=True)

def log_info(module_name: str, message: str, metadata: Optional[Dict[str, Any]] = None):
    """INFO 레벨 로그"""
    logger = get_logger()
    logger.info(f"[{module_name}] {message}")
    log_to_db(module_name, "INFO", message, metadata=metadata)

def log_warning(module_name: str, message: str, metadata: Optional[Dict[str, Any]] = None):
    """WARNING 레벨 로그"""
    logger = get_logger()
    logger.warning(f"[{module_name}] {message}")
    log_to_db(module_name, "WARNING", message, metadata=metadata)

def log_error(
    module_name: str, 
    message: str, 
    error: Optional[Exception] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """ERROR 레벨 로그"""
    logger = get_logger()
    logger.error(f"[{module_name}] {message}", exc_info=error)
    
    error_type = type(error).__name__ if error else None
    stack_trace = traceback.format_exc() if error else None
    
    log_to_db(
        module_name, 
        "ERROR", 
        message, 
        error_type=error_type,
        stack_trace=stack_trace,
        metadata=metadata
    )

def log_critical(
    module_name: str, 
    message: str, 
    error: Optional[Exception] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """CRITICAL 레벨 로그"""
    logger = get_logger()
    logger.critical(f"[{module_name}] {message}", exc_info=error)
    
    error_type = type(error).__name__ if error else None
    stack_trace = traceback.format_exc() if error else None
    
    log_to_db(
        module_name, 
        "CRITICAL", 
        message, 
        error_type=error_type,
        stack_trace=stack_trace,
        metadata=metadata
    )

def log_debug(module_name: str, message: str, metadata: Optional[Dict[str, Any]] = None):
    """DEBUG 레벨 로그"""
    logger = get_logger()
    logger.debug(f"[{module_name}] {message}")
    log_to_db(module_name, "DEBUG", message, metadata=metadata)

