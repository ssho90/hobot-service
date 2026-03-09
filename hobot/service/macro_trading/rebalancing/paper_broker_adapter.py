import logging
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from service.macro_trading.kis.kis import get_balance_info_api
from service.macro_trading.kis.user_credentials import get_user_kis_credentials
from service.macro_trading.rebalancing.rebalancing_engine import execute_rebalancing


logger = logging.getLogger(__name__)


class PaperTradingBrokerAdapter:
    US_MARKET_TIMEZONE = ZoneInfo("America/New_York")
    MARKET_OPEN_HOUR = 9
    MARKET_OPEN_MINUTE = 30
    MARKET_CLOSE_HOUR = 16
    MARKET_CLOSE_MINUTE = 0

    def __init__(self, user_id: str):
        self.user_id = str(user_id or "").strip()
        self.credentials = get_user_kis_credentials(self.user_id)
        if not self.credentials:
            raise ValueError(f"No KIS credentials for user {self.user_id}")
        if not self.credentials.get("is_simulation", False):
            raise ValueError(f"User {self.user_id} is not configured for paper trading")

    def get_account_snapshot(self) -> Dict[str, Any]:
        snapshot = get_balance_info_api(self.user_id)
        if not snapshot or snapshot.get("status") != "success":
            raise ValueError(snapshot.get("message") if snapshot else "Failed to fetch paper account snapshot")
        return snapshot

    async def execute_rebalancing(self, max_phase: int = 5) -> Dict[str, Any]:
        logger.info("Executing paper rebalancing for user=%s max_phase=%s", self.user_id, max_phase)
        return await execute_rebalancing(self.user_id, max_phase=max_phase)

    @classmethod
    def is_us_market_open(cls, reference_time: Optional[datetime] = None) -> bool:
        if reference_time is None:
            reference_time = datetime.now().astimezone()
        elif reference_time.tzinfo is None:
            reference_time = reference_time.astimezone()

        eastern_now = reference_time.astimezone(cls.US_MARKET_TIMEZONE)
        if eastern_now.weekday() >= 5:
            return False

        market_open = eastern_now.replace(
            hour=cls.MARKET_OPEN_HOUR,
            minute=cls.MARKET_OPEN_MINUTE,
            second=0,
            microsecond=0,
        )
        market_close = eastern_now.replace(
            hour=cls.MARKET_CLOSE_HOUR,
            minute=cls.MARKET_CLOSE_MINUTE,
            second=0,
            microsecond=0,
        )
        return market_open <= eastern_now <= market_close
