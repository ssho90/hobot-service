"""
LLM 사용 모니터링 모듈
LLM 호출을 추적하고 데이터베이스에 로그를 저장합니다.
"""
import logging
import time
from typing import Optional, Dict, Any, Callable
from functools import wraps
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except ImportError:
    try:
        # Python 3.8 이하를 위한 fallback
        from backports.zoneinfo import ZoneInfo
        KST = ZoneInfo("Asia/Seoul")
    except ImportError:
        # pytz를 사용하는 fallback
        try:
            import pytz
            KST = pytz.timezone("Asia/Seoul")
        except ImportError:
            # 최후의 수단: UTC+9를 수동으로 계산
            from datetime import timedelta, timezone
            KST = timezone(timedelta(hours=9))

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
        # 현재 UTC 시간을 가져온 후 UTC+9로 변환
        # 시스템 시간이 어떤 시간대든 상관없이 UTC+9로 저장
        from datetime import timezone
        utc_now = datetime.now(timezone.utc)
        
        # UTC를 UTC+9로 변환 (9시간 추가)
        if hasattr(KST, 'localize'):
            # pytz 사용: UTC 시간을 UTC+9로 변환
            now_kst = utc_now.astimezone(KST)
        else:
            # zoneinfo 사용: UTC 시간을 UTC+9로 변환
            now_kst = utc_now.astimezone(KST)
        
        # MySQL TIMESTAMP는 naive datetime을 저장하므로 시간대 정보 제거
        # UTC+9 시간을 naive datetime으로 변환 (시간대 정보 제거, 값은 UTC+9 시간 유지)
        now_kst_naive = now_kst.replace(tzinfo=None)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO llm_usage_logs (
                    model_name, provider, request_prompt, response_prompt,
                    prompt_tokens, completion_tokens, total_tokens,
                    service_name, duration_ms, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                model_name,
                provider,
                request_prompt[:10000] if request_prompt else None,  # 최대 10KB로 제한
                response_prompt[:10000] if response_prompt else None,  # 최대 10KB로 제한
                prompt_tokens,
                completion_tokens,
                total_tokens,
                service_name,
                duration_ms,
                now_kst_naive  # UTC+9 시간을 naive datetime으로 저장
            ))
            conn.commit()
            logger.info(f"LLM 사용 로그 DB 저장 성공: service_name={service_name}, model_name={model_name}, "
                       f"total_tokens={total_tokens}, created_at={now_kst_naive}")
    except Exception as e:
        logger.error(f"LLM 사용 로그 저장 실패 (service_name={service_name}, model_name={model_name}): {e}", exc_info=True)
        # 예외를 다시 발생시키지 않음 (로그 저장 실패가 전체 프로세스를 중단시키지 않도록)


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
        try:
            logger.info(f"LLM 사용 로그 저장 시도: service_name={self.service_name}, model_name={self.model_name}, "
                       f"tokens={self.total_tokens}, duration={self.duration_ms}ms")
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
            logger.info(f"LLM 사용 로그 저장 완료: service_name={self.service_name}, model_name={self.model_name}")
        except Exception as e:
            # 로그 저장 실패 시에도 에러를 기록하되, 원래 예외는 전파하지 않음
            logger.error(f"LLM 사용 로그 저장 실패 (service_name={self.service_name}, model_name={self.model_name}): {e}", exc_info=True)
        
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
            # content가 리스트인 경우 (예: [{'type': 'text', 'text': '...'}])
            if isinstance(response.content, list) and len(response.content) > 0:
                # 첫 번째 텍스트 항목 추출
                first_item = response.content[0]
                if isinstance(first_item, dict) and 'text' in first_item:
                    self.response_prompt = first_item['text']
                else:
                    self.response_prompt = str(first_item)
            elif isinstance(response.content, str):
                self.response_prompt = response.content
            else:
                self.response_prompt = str(response.content)
        elif hasattr(response, 'text'):
            self.response_prompt = response.text
        elif isinstance(response, str):
            self.response_prompt = response
        else:
            self.response_prompt = str(response)
        
        # 토큰 정보 추출 (LangChain 응답 객체의 usage_metadata에서)
        try:
            usage_found = False
            
            # 1. response_metadata에서 usage_metadata 추출 시도
            if hasattr(response, 'response_metadata'):
                metadata = response.response_metadata
                if isinstance(metadata, dict) and 'usage_metadata' in metadata:
                    usage = metadata['usage_metadata']
                    if isinstance(usage, dict):
                        # input_tokens, output_tokens, total_tokens 추출
                        self.prompt_tokens = usage.get('input_tokens', 0)
                        self.completion_tokens = usage.get('output_tokens', 0)
                        self.total_tokens = usage.get('total_tokens', 0)
                        usage_found = True
                        
                        # output_token_details에서 reasoning 토큰도 확인 가능
                        output_details = usage.get('output_token_details', {})
                        if isinstance(output_details, dict) and 'reasoning' in output_details:
                            reasoning_tokens = output_details.get('reasoning', 0)
                            logger.debug(f"Reasoning tokens: {reasoning_tokens}")
                        
                        logger.info(f"토큰 사용량 추출 (response_metadata): input={self.prompt_tokens}, output={self.completion_tokens}, total={self.total_tokens}")
            
            # 2. usage_metadata 속성이 직접 있는 경우 확인 (elif가 아닌 if로 변경)
            if not usage_found and hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                if isinstance(usage, dict):
                    self.prompt_tokens = usage.get('input_tokens', 0)
                    self.completion_tokens = usage.get('output_tokens', 0)
                    self.total_tokens = usage.get('total_tokens', 0)
                    usage_found = True
                    logger.info(f"토큰 사용량 추출 (직접 속성): input={self.prompt_tokens}, output={self.completion_tokens}, total={self.total_tokens}")
            
            # 3. response_metadata 자체에 토큰 정보가 있는 경우 (OpenAI 형식)
            if not usage_found and hasattr(response, 'response_metadata'):
                metadata = response.response_metadata
                if isinstance(metadata, dict):
                    # OpenAI 형식: token_usage
                    if 'token_usage' in metadata:
                        token_usage = metadata['token_usage']
                        if isinstance(token_usage, dict):
                            self.prompt_tokens = token_usage.get('prompt_tokens', 0)
                            self.completion_tokens = token_usage.get('completion_tokens', 0)
                            self.total_tokens = token_usage.get('total_tokens', 0)
                            usage_found = True
                            logger.info(f"토큰 사용량 추출 (token_usage): input={self.prompt_tokens}, output={self.completion_tokens}, total={self.total_tokens}")
            
            # 4. 디버깅: response 객체의 모든 속성 확인
            if not usage_found:
                logger.warning("토큰 정보를 찾을 수 없습니다. response 객체 속성 확인 중...")
                logger.debug(f"response 타입: {type(response)}")
                logger.debug(f"response 속성: {dir(response)}")
                if hasattr(response, 'response_metadata'):
                    logger.debug(f"response_metadata: {response.response_metadata}")
                if hasattr(response, 'usage_metadata'):
                    logger.debug(f"usage_metadata: {response.usage_metadata}")
                    
        except Exception as e:
            logger.error(f"토큰 정보 추출 실패: {e}", exc_info=True)
            # 토큰 정보 추출 실패해도 계속 진행
    
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

