"""
거시경제 기반 자동매매 Agent 설정 파일 로더 및 검증 모듈
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
import logging

logger = logging.getLogger(__name__)


# ============================================
# Pydantic 모델 정의 (설정 스키마 검증)
# ============================================

class RebalancingConfig(BaseModel):
    """리밸런싱 설정"""
    threshold: float = Field(..., ge=0, le=100, description="임계값 (%)")
    execution_time: str = Field(..., description="실행 시간 (HH:MM 형식)")
    min_trade_amount: int = Field(..., ge=0, description="최소 거래 금액 (원)")
    cash_reserve_ratio: float = Field(..., ge=0, le=1, description="여유 자금 비율 (0-1)")

    @field_validator('execution_time')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """시간 형식 검증 (HH:MM)"""
        try:
            hour, minute = v.split(':')
            if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                raise ValueError("시간 범위가 올바르지 않습니다")
            return v
        except (ValueError, AttributeError):
            raise ValueError("시간 형식이 올바르지 않습니다 (HH:MM 형식 필요)")


class ETFMappingConfig(BaseModel):
    """ETF 매핑 설정"""
    tickers: List[str] = Field(..., min_items=1, description="ETF 티커 리스트")
    weights: List[float] = Field(..., description="각 ETF의 비중 (0-1)")
    names: List[str] = Field(..., description="ETF 이름 리스트")

    @model_validator(mode='after')
    def validate_etf_mapping(self):
        """ETF 매핑 전체 검증 (비중 합계, 개수 일치 등)"""
        # 티커, 비중, 이름 개수 일치 확인
        if len(self.tickers) != len(self.weights) or len(self.tickers) != len(self.names):
            raise ValueError("티커, 비중, 이름의 개수가 일치하지 않습니다")
        
        # 비중 합계가 1인지 확인
        total = sum(self.weights)
        if abs(total - 1.0) > 0.01:  # 부동소수점 오차 허용
            raise ValueError(f"비중 합계가 1이 아닙니다: {total}")
        
        return self


class LLMConfig(BaseModel):
    """LLM 설정"""
    model: str = Field(..., description="모델명 (gemini-2.5-pro 등)")
    temperature: float = Field(..., ge=0, le=2, description="Temperature (0-2)")
    max_tokens: int = Field(..., ge=1, le=100000, description="최대 토큰 수")


class SchedulesConfig(BaseModel):
    """스케줄 설정"""
    account_check: List[str] = Field(..., description="계좌 조회 시간 리스트 (HH:MM)")
    llm_analysis: List[str] = Field(..., description="LLM 분석 시간 리스트 (HH:MM)")
    rebalancing: List[str] = Field(..., description="리밸런싱 실행 시간 리스트 (HH:MM)")
    fred_data_collection: List[str] = Field(..., description="FRED 데이터 수집 시간 리스트 (HH:MM)")

    @field_validator('account_check', 'llm_analysis', 'rebalancing', 'fred_data_collection')
    @classmethod
    def validate_time_format(cls, v: List[str]) -> List[str]:
        """시간 형식 검증 (리스트의 각 항목)"""
        def validate_single_time(time_str: str) -> str:
            """단일 시간 문자열 검증"""
            try:
                hour, minute = time_str.split(':')
                if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                    raise ValueError("시간 범위가 올바르지 않습니다")
                return time_str
            except (ValueError, AttributeError):
                raise ValueError("시간 형식이 올바르지 않습니다 (HH:MM 형식 필요)")
        
        # 리스트의 각 항목 검증
        return [validate_single_time(time_str) for time_str in v]


class LiquidityConfig(BaseModel):
    """유동성 평가 설정"""
    net_liquidity_ma_weeks: int = Field(default=4, ge=1, le=52, description="순유동성 이동평균 기간 (주)")
    high_yield_spread_thresholds: Dict[str, float] = Field(
        default={"greed": 3.5, "fear": 5.0, "panic": 10.0},
        description="하이일드 스프레드 임계값 (%)"
    )


class FREDConfig(BaseModel):
    """FRED API 설정"""
    cache_duration_hours: int = Field(..., ge=1, description="캐시 기간 (시간)")


class SafetyConfig(BaseModel):
    """안전장치 설정"""
    max_daily_loss_percent: float = Field(..., ge=0, le=100, description="일일 최대 손실 한도 (%)")
    max_monthly_loss_percent: float = Field(..., ge=0, le=100, description="월간 최대 손실 한도 (%)")
    manual_approval_required: bool = Field(..., description="수동 승인 필요 여부")
    dry_run_mode: bool = Field(..., description="드라이런 모드 (실제 매매 없이 시뮬레이션)")


class MacroTradingConfig(BaseModel):
    """전체 설정 모델"""
    rebalancing: RebalancingConfig
    etf_mapping: Dict[str, ETFMappingConfig] = Field(..., description="자산군별 ETF 매핑")
    llm: LLMConfig
    schedules: SchedulesConfig
    fred: FREDConfig
    liquidity: Optional[LiquidityConfig] = Field(default=None, description="유동성 평가 설정 (선택적)")
    safety: SafetyConfig

    @field_validator('etf_mapping')
    @classmethod
    def validate_etf_mapping_keys(cls, v: Dict[str, ETFMappingConfig]) -> Dict[str, ETFMappingConfig]:
        """ETF 매핑 키 검증 (stocks, alternatives, cash 등)"""
        valid_keys = {'stocks', 'alternatives', 'cash'}
        for key in v.keys():
            if key not in valid_keys:
                logger.warning(f"알 수 없는 ETF 매핑 키: {key}")
        return v


# ============================================
# 설정 파일 로더 클래스
# ============================================

class ConfigLoader:
    """설정 파일 로더 및 검증 클래스"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Args:
            config_path: 설정 파일 경로 (None이면 기본 경로 사용)
        """
        if config_path is None:
            # 기본 경로: hobot/service/macro_trading/config/macro_trading_config.json
            base_dir = Path(__file__).parent
            config_path = base_dir / "macro_trading_config.json"
        
        self.config_path = Path(config_path)
        self._config: Optional[MacroTradingConfig] = None
    
    def load(self) -> MacroTradingConfig:
        """
        설정 파일을 로드하고 검증합니다.
        
        Returns:
            MacroTradingConfig: 검증된 설정 객체
            
        Raises:
            FileNotFoundError: 설정 파일이 없을 때
            ValueError: 설정 파일 검증 실패 시
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)
            
            # Pydantic 모델로 검증
            self._config = MacroTradingConfig(**config_dict)
            logger.info(f"설정 파일 로드 완료: {self.config_path}")
            return self._config
            
        except json.JSONDecodeError as e:
            raise ValueError(f"설정 파일 JSON 파싱 오류: {e}")
        except Exception as e:
            raise ValueError(f"설정 파일 검증 오류: {e}")
    
    def get_config(self) -> MacroTradingConfig:
        """
        캐시된 설정을 반환합니다. 없으면 로드합니다.
        
        Returns:
            MacroTradingConfig: 설정 객체
        """
        if self._config is None:
            return self.load()
        return self._config
    
    def reload(self) -> MacroTradingConfig:
        """
        설정 파일을 다시 로드합니다.
        
        Returns:
            MacroTradingConfig: 새로 로드된 설정 객체
        """
        self._config = None
        return self.load()
    
    def validate(self) -> bool:
        """
        설정 파일의 유효성을 검증합니다.
        
        Returns:
            bool: 검증 성공 여부
        """
        try:
            self.load()
            return True
        except Exception as e:
            logger.error(f"설정 파일 검증 실패: {e}")
            return False


# ============================================
# 전역 설정 로더 인스턴스
# ============================================

_global_loader: Optional[ConfigLoader] = None


def get_config_loader() -> ConfigLoader:
    """전역 설정 로더 인스턴스를 반환합니다."""
    global _global_loader
    if _global_loader is None:
        _global_loader = ConfigLoader()
    return _global_loader


def get_config() -> MacroTradingConfig:
    """
    설정을 가져옵니다.
    
    Returns:
        MacroTradingConfig: 설정 객체
    """
    return get_config_loader().get_config()


def reload_config() -> MacroTradingConfig:
    """
    설정을 다시 로드합니다.
    
    Returns:
        MacroTradingConfig: 새로 로드된 설정 객체
    """
    return get_config_loader().reload()

