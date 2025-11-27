"""
LLM 사용 모니터링 모듈
LLM 호출을 추적하고 데이터베이스에 로그를 저장합니다.
"""
import logging
import time
from typing import Optional, Dict, Any, Callable
from functools import wraps
from datetime import datetime

from service.database.db import get_db_connection

logger = logging.getLogger(__name__)


def log_llm_usage(
    model_name: str,
    provider: str,
    request_prompt: Optional[str] = None,
    response_prompt: Optional[str] = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    service_name: Optional[str] = None,
    duration_ms: Optional[int] = None
):
    """
    LLM 사용 로그를 데이터베이스에 저장
    
    Args:
        model_name: LLM 모델명 (예: gpt-4o-mini, gemini-2.5-pro)
        provider: LLM 제공자 (예: OpenAI, Google)
        request_prompt: 요청 프롬프트
        response_prompt: 응답 프롬프트
        prompt_tokens: 프롬프트 토큰 수
        completion_tokens: 완료 토큰 수
        total_tokens: 총 토큰 수
        service_name: 서비스명 (어떤 기능에서 호출했는지)
        duration_ms: 응답 시간 (밀리초)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO llm_usage_logs (
                    model_name, provider, request_prompt, response_prompt,
                    prompt_tokens, completion_tokens, total_tokens,
                    service_name, duration_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                model_name,
                provider,
                request_prompt[:10000] if request_prompt else None,  # 최대 10KB로 제한
                response_prompt[:10000] if response_prompt else None,  # 최대 10KB로 제한
                prompt_tokens,
                completion_tokens,
                total_tokens,
                service_name,
                duration_ms
            ))
            conn.commit()
    except Exception as e:
        logger.error(f"LLM 사용 로그 저장 실패: {e}", exc_info=True)


def track_llm_usage(service_name: Optional[str] = None):
    """
    LLM 호출을 추적하는 decorator
    
    사용 예:
        @track_llm_usage(service_name="ai_strategist")
        def analyze_and_decide():
            llm = llm_gemini_pro()
            response = llm.invoke(prompt)
            return response
    
    또는 함수 내에서 직접 사용:
        llm = llm_gemini_pro()
        with track_llm_call(service_name="news_agent"):
            response = llm.invoke(prompt)
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = None
            error = None
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = e
                raise
            finally:
                # LLM 호출 정보 추출 시도
                # result에서 LLM 응답 정보를 추출할 수 있는 경우 로깅
                if result is not None:
                    try:
                        # LangChain 응답 객체인 경우
                        if hasattr(result, 'content'):
                            response_text = result.content
                        elif hasattr(result, 'text'):
                            response_text = result.text
                        elif isinstance(result, str):
                            response_text = result
                        else:
                            response_text = str(result)
                        
                        # 기본값 설정 (실제로는 LLM 호출 시점에서 추적해야 함)
                        duration_ms = int((time.time() - start_time) * 1000)
                        
                        # 모델명과 제공자는 함수 내부에서 설정해야 함
                        # 여기서는 기본값만 설정
                        log_llm_usage(
                            model_name="unknown",
                            provider="unknown",
                            response_prompt=response_text[:1000] if response_text else None,
                            service_name=service_name or func.__name__,
                            duration_ms=duration_ms
                        )
                    except Exception as e:
                        logger.warning(f"LLM 사용 로그 추출 실패: {e}")
        
        return wrapper
    return decorator


class LLMCallTracker:
    """
    LLM 호출을 추적하는 컨텍스트 매니저
    
    사용 예:
        tracker = LLMCallTracker(
            model_name="gemini-2.5-pro",
            provider="Google",
            service_name="ai_strategist"
        )
        
        with tracker:
            llm = llm_gemini_pro()
            response = llm.invoke(prompt)
            tracker.set_request_prompt(prompt)
            tracker.set_response(response)
    """
    
    def __init__(
        self,
        model_name: str,
        provider: str,
        service_name: Optional[str] = None,
        request_prompt: Optional[str] = None
    ):
        self.model_name = model_name
        self.provider = provider
        self.service_name = service_name
        self.request_prompt = request_prompt
        self.response_prompt = None
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.start_time = None
        self.duration_ms = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            self.duration_ms = int((time.time() - self.start_time) * 1000)
        
        # 에러가 발생해도 로그는 저장
        log_llm_usage(
            model_name=self.model_name,
            provider=self.provider,
            request_prompt=self.request_prompt,
            response_prompt=self.response_prompt,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
            service_name=self.service_name,
            duration_ms=self.duration_ms
        )
        return False
    
    def set_request_prompt(self, prompt: str):
        """요청 프롬프트 설정"""
        self.request_prompt = prompt
    
    def set_response(self, response: Any):
        """
        LLM 응답 설정 및 토큰 정보 추출
        
        Args:
            response: LLM 응답 객체 (LangChain 응답 또는 문자열)
        """
        # 응답 텍스트 추출
        if hasattr(response, 'content'):
            self.response_prompt = response.content
        elif hasattr(response, 'text'):
            self.response_prompt = response.text
        elif isinstance(response, str):
            self.response_prompt = response
        else:
            self.response_prompt = str(response)
        
        # 토큰 정보 추출 (LangChain callback 사용)
        try:
            from langchain.callbacks import get_openai_callback
            # OpenAI의 경우 callback에서 토큰 정보를 가져올 수 있음
            # 하지만 이미 호출이 끝난 후이므로, 실제로는 호출 전에 callback을 설정해야 함
            pass
        except Exception:
            pass
    
    def set_token_usage(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0
    ):
        """토큰 사용량 직접 설정"""
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens or (prompt_tokens + completion_tokens)


def track_llm_call(
    model_name: str,
    provider: str,
    service_name: Optional[str] = None,
    request_prompt: Optional[str] = None
) -> LLMCallTracker:
    """
    LLM 호출 추적을 위한 컨텍스트 매니저 생성 헬퍼 함수
    
    사용 예:
        with track_llm_call("gemini-2.5-pro", "Google", "ai_strategist", prompt) as tracker:
            llm = llm_gemini_pro()
            response = llm.invoke(prompt)
            tracker.set_response(response)
    """
    return LLMCallTracker(model_name, provider, service_name, request_prompt)

