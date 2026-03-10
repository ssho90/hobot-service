import logging
import time
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

from service.core.time_provider import TimeProvider
from service.macro_trading.kis.kis_api import KISAPI
from service.macro_trading.kis.user_credentials import get_user_kis_credentials
from service.macro_trading.rebalancing.asset_retriever import get_current_portfolio_state
from service.macro_trading.rebalancing.config_retriever import get_rebalancing_config
from service.macro_trading.rebalancing.drift_calculator import (
    calculate_detailed_drift,
    check_threshold_exceeded,
)
from service.macro_trading.rebalancing.portfolio_calculator import (
    apply_minimum_trade_filter,
    calculate_net_trades,
    calculate_target_quantities,
)
from service.macro_trading.rebalancing.run_repository import (
    DEFAULT_EXECUTION_DAYS,
    RebalancingRunRepository,
    build_daily_sliced_trades,
)
from service.macro_trading.rebalancing.signal_tracker import DEFAULT_STRATEGY_PROFILE_ID
from service.macro_trading.rebalancing.target_retriever import get_current_target_data


logger = logging.getLogger(__name__)


async def execute_rebalancing(
    user_id: str,
    max_phase: int = 5,
    strategy_profile_id: str = DEFAULT_STRATEGY_PROFILE_ID,
    business_date: Any = None,
) -> Dict[str, Any]:
    return await execute_rebalancing_for_user(
        user_id=user_id,
        max_phase=max_phase,
        strategy_profile_id=strategy_profile_id,
        business_date=business_date,
    )


async def execute_rebalancing_for_user(
    user_id: str,
    max_phase: int = 5,
    strategy_profile_id: str = DEFAULT_STRATEGY_PROFILE_ID,
    business_date: Any = None,
    planned_execution_days: int = DEFAULT_EXECUTION_DAYS,
) -> Dict[str, Any]:
    """
    전체 리밸런싱 프로세스 실행.

    - 현재 스냅샷 기준으로 전체 목표 잔량을 다시 계산한다.
    - 실제 주문은 `남은 수량 / 남은 실행일 수` 기준의 당일 slice만 실행한다.
    - run 상태는 사용자별로 관리한다.
    """
    normalized_business_date = _resolve_business_date(business_date)
    logger.info(
        "Starting rebalancing process for user=%s max_phase=%s strategy_profile_id=%s business_date=%s",
        user_id,
        max_phase,
        strategy_profile_id,
        normalized_business_date.isoformat(),
    )

    run_repo = RebalancingRunRepository()
    open_run = run_repo.get_open_run(user_id=user_id, strategy_profile_id=strategy_profile_id)

    current_state = get_current_portfolio_state(user_id)
    if not current_state:
        return {"status": "error", "message": "Failed to retrieve portfolio state"}

    target_data = get_current_target_data(strategy_profile_id=strategy_profile_id)
    if not target_data:
        return {"status": "error", "message": "Failed to retrieve target allocation"}

    target_mp = target_data["mp_target"]
    target_sub_mp = target_data["sub_mp_details"] or {}
    target_signature = str(target_data.get("target_signature") or "").strip()
    target_payload = target_data.get("target_payload") or {}

    config = get_rebalancing_config()
    thresholds = {"mp": float(config.get("mp", 3.0)), "sub_mp": float(config.get("sub_mp", 5.0))}
    needed, drift_info = check_rebalancing_needed(current_state, target_mp, target_sub_mp, thresholds)

    if max_phase <= 2:
        return {
            "status": "success",
            "message": "Phase 2 Completed",
            "rebalancing_needed": needed,
            "drift_info": drift_info,
            "run": open_run,
            "business_date": normalized_business_date.isoformat(),
            "target_signature": target_signature,
        }

    if not needed:
        completed_run = open_run
        if open_run and open_run.get("target_signature") == target_signature:
            completed_run = run_repo.complete_run(
                run_id=open_run["run_id"],
                business_date=normalized_business_date,
                completion_reason="DRIFT_WITHIN_TOLERANCE",
                details={"drift_info": drift_info},
            )
        return {
            "status": "success",
            "message": "Rebalancing not needed",
            "drift_info": drift_info,
            "run": completed_run,
            "business_date": normalized_business_date.isoformat(),
            "target_signature": target_signature,
        }

    current_run = open_run if open_run and open_run.get("target_signature") == target_signature else None
    preview_remaining_execution_days = _resolve_remaining_execution_days(
        current_run=current_run,
        planned_execution_days=planned_execution_days,
    )

    relevant_tickers = set()
    for _, sub_data in (target_sub_mp or {}).items():
        if isinstance(sub_data, dict) and "etf_details" in sub_data:
            for etf in sub_data["etf_details"]:
                ticker = str(etf.get("ticker") or "").strip()
                if ticker:
                    relevant_tickers.add(ticker)

    for holding in current_state.get("holdings", []):
        ticker = str(holding.get("stock_code") or "").strip()
        if ticker:
            relevant_tickers.add(ticker)

    user_cred = get_user_kis_credentials(user_id)
    if not user_cred:
        return {"status": "error", "message": "User credentials not found"}

    kis = KISAPI(
        user_cred["app_key"],
        user_cred["app_secret"],
        user_cred["account_no"],
        is_simulation=user_cred.get("is_simulation", True),
    )

    relevant_tickers.discard("CASH")
    current_prices: Dict[str, float] = {}
    for ticker in relevant_tickers:
        price = kis.get_current_price(ticker)
        if price:
            current_prices[ticker] = price
        else:
            logger.warning("Failed to fetch price for %s", ticker)
        time.sleep(0.5)

    missing_tickers = [ticker for ticker in relevant_tickers if ticker not in current_prices]
    if missing_tickers:
        error_msg = f"Failed to fetch current prices for: {missing_tickers}. Aborting rebalancing."
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}

    target_global_weights = {}
    for asset_class, mp_weight in target_mp.items():
        sub_info = target_sub_mp.get(asset_class, {}) if isinstance(target_sub_mp, dict) else {}
        etf_details = sub_info.get("etf_details", []) if isinstance(sub_info, dict) else []
        for etf in etf_details:
            ticker = str(etf.get("ticker") or "").strip()
            if not ticker:
                continue
            target_global_weights[ticker] = (mp_weight / 100.0) * float(etf.get("weight", 0))

    target_quantities = calculate_target_quantities(
        total_equity=current_state["total_eval_amount"],
        target_weights=target_global_weights,
        current_prices=current_prices,
    )
    current_holdings_map = {
        holding["stock_code"]: int(holding["quantity"])
        for holding in current_state.get("holdings", [])
    }
    full_net_trades = calculate_net_trades(current_holdings_map, target_quantities)
    filtered_trades = apply_minimum_trade_filter(full_net_trades, current_prices)
    sliced_trades = build_daily_sliced_trades(filtered_trades, preview_remaining_execution_days)

    logger.info(
        "Daily rebalancing slice planned user=%s remaining_execution_days=%s full_trade_count=%s sliced_trade_count=%s",
        user_id,
        preview_remaining_execution_days,
        len(filtered_trades),
        len(sliced_trades),
    )

    if len(sliced_trades) == 0:
        completed_run = open_run
        if max_phase >= 5:
            persisted_run = run_repo.ensure_run_for_target(
                user_id=user_id,
                strategy_profile_id=strategy_profile_id,
                business_date=normalized_business_date,
                target_signature=target_signature,
                target_payload=target_payload,
                planned_execution_days=planned_execution_days,
            )
            completed_run = run_repo.complete_run(
                run_id=persisted_run["run_id"],
                business_date=normalized_business_date,
                completion_reason="NO_SLICE_TRADES",
                details={"drift_info": drift_info},
            )
        return {
            "status": "success",
            "message": "No slice trades generated for today",
            "drift_info": drift_info,
            "full_net_trades": filtered_trades,
            "net_trades": sliced_trades,
            "run": completed_run,
            "business_date": normalized_business_date.isoformat(),
            "target_signature": target_signature,
        }

    from service.macro_trading.rebalancing.portfolio_calculator import verify_strategy_feasibility

    is_feasible, logic_errors = verify_strategy_feasibility(sliced_trades, current_holdings_map)
    if not is_feasible:
        return {"status": "error", "message": f"Strategy Logic Error: {logic_errors}"}

    from service.macro_trading.rebalancing.trading_strategy_builder import build_buy_orders, build_sell_orders

    sell_orders = build_sell_orders(sliced_trades, current_prices, tick_size=5)
    if max_phase <= 3:
        return {
            "status": "success",
            "message": "Phase 3 Completed (Planning)",
            "run": _build_preview_run(
                current_run=current_run,
                strategy_profile_id=strategy_profile_id,
                target_signature=target_signature,
                business_date=normalized_business_date,
                planned_execution_days=planned_execution_days,
                remaining_execution_days=preview_remaining_execution_days,
            ),
            "full_net_trades": filtered_trades,
            "net_trades": sliced_trades,
            "sell_orders": sell_orders,
            "drift_info": drift_info,
            "business_date": normalized_business_date.isoformat(),
        }

    current_cash = float(current_state.get("cash_balance", 0))
    est_sell_proceeds = sum(order["quantity"] * order["limit_price"] for order in sell_orders)
    simulated_cash_balance = current_cash + int(est_sell_proceeds * 0.998)

    buy_orders = build_buy_orders(sliced_trades, current_prices, tick_size=5)
    logger.info(
        "Daily slice orders built user=%s sell_orders=%s buy_orders=%s",
        user_id,
        len(sell_orders),
        len(buy_orders),
    )

    from service.macro_trading.rebalancing.strategy_validator import validate_buy_strategy

    is_valid, reasons, validation_summary = validate_buy_strategy(
        buy_orders=buy_orders,
        current_cash=simulated_cash_balance,
        current_state=current_state,
        target_mp=target_mp,
        target_sub_mp=target_sub_mp,
        current_prices=current_prices,
        thresholds=thresholds,
    )
    validation_result = {
        "is_valid": is_valid,
        "reasons": reasons,
        "summary": validation_summary,
    }
    if not is_valid:
        logger.error("Buy Strategy Validation Failed: %s", reasons)
        return {
            "status": "error",
            "message": "Buy Strategy Validation Failed",
            "validation_result": validation_result,
            "sell_orders": sell_orders,
            "buy_orders": buy_orders,
            "run": _build_preview_run(
                current_run=current_run,
                strategy_profile_id=strategy_profile_id,
                target_signature=target_signature,
                business_date=normalized_business_date,
                planned_execution_days=planned_execution_days,
                remaining_execution_days=preview_remaining_execution_days,
            ),
            "full_net_trades": filtered_trades,
            "net_trades": sliced_trades,
        }

    if max_phase <= 4:
        return {
            "status": "success",
            "message": "Phase 4 Completed (Validation)",
            "run": _build_preview_run(
                current_run=current_run,
                strategy_profile_id=strategy_profile_id,
                target_signature=target_signature,
                business_date=normalized_business_date,
                planned_execution_days=planned_execution_days,
                remaining_execution_days=preview_remaining_execution_days,
            ),
            "full_net_trades": filtered_trades,
            "net_trades": sliced_trades,
            "sell_orders": sell_orders,
            "buy_orders": buy_orders,
            "validation_result": validation_result,
            "business_date": normalized_business_date.isoformat(),
        }

    persisted_run = run_repo.ensure_run_for_target(
        user_id=user_id,
        strategy_profile_id=strategy_profile_id,
        business_date=normalized_business_date,
        target_signature=target_signature,
        target_payload=target_payload,
        planned_execution_days=planned_execution_days,
    )
    persisted_remaining_execution_days = _resolve_remaining_execution_days(
        current_run=persisted_run,
        planned_execution_days=planned_execution_days,
    )
    if persisted_remaining_execution_days != preview_remaining_execution_days:
        sliced_trades = build_daily_sliced_trades(filtered_trades, persisted_remaining_execution_days)
        sell_orders = build_sell_orders(sliced_trades, current_prices, tick_size=5)
        buy_orders = build_buy_orders(sliced_trades, current_prices, tick_size=5)
        is_valid, reasons, validation_summary = validate_buy_strategy(
            buy_orders=buy_orders,
            current_cash=simulated_cash_balance,
            current_state=current_state,
            target_mp=target_mp,
            target_sub_mp=target_sub_mp,
            current_prices=current_prices,
            thresholds=thresholds,
        )
        validation_result = {
            "is_valid": is_valid,
            "reasons": reasons,
            "summary": validation_summary,
        }
        if not is_valid:
            return {
                "status": "error",
                "message": "Buy Strategy Validation Failed",
                "validation_result": validation_result,
                "sell_orders": sell_orders,
                "buy_orders": buy_orders,
                "run": persisted_run,
                "full_net_trades": filtered_trades,
                "net_trades": sliced_trades,
            }

    run_repo.save_planning_snapshot(
        run_id=persisted_run["run_id"],
        business_date=normalized_business_date,
        current_state=current_state,
        full_trades=filtered_trades,
        sliced_trades=sliced_trades,
        metadata={
            "target_signature": target_signature,
            "current_prices": current_prices,
            "target_quantities": target_quantities,
            "drift_info": drift_info,
        },
    )

    from service.macro_trading.rebalancing.order_executor import OrderExecutor

    trading_plan = {
        "status": "success",
        "message": "Phase 4 Completed (Validation)",
        "sell_orders": sell_orders,
        "buy_orders": buy_orders,
        "validation_result": validation_result,
    }
    executor = OrderExecutor(user_id)
    execution_result = executor.execute_rebalancing_trades(trading_plan)
    persisted_run = run_repo.record_execution_result(
        run_id=persisted_run["run_id"],
        business_date=normalized_business_date,
        execution_result=execution_result,
        current_state=current_state,
        full_trades=filtered_trades,
        sliced_trades=sliced_trades,
        metadata={
            "target_signature": target_signature,
            "drift_info": drift_info,
            "validation_result": validation_result,
        },
    )

    return {
        **execution_result,
        "run": persisted_run,
        "full_net_trades": filtered_trades,
        "net_trades": sliced_trades,
        "business_date": normalized_business_date.isoformat(),
        "target_signature": target_signature,
    }


def check_rebalancing_needed(
    current_state: Dict[str, Any],
    target_mp: Dict[str, Any],
    target_sub_mp: Dict[str, Any],
    thresholds: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    drift_details = calculate_detailed_drift(current_state, target_mp, target_sub_mp)
    is_exceeded, reasons = check_threshold_exceeded(drift_details, thresholds)
    drift_details["reasons"] = reasons
    return is_exceeded, drift_details


def _resolve_remaining_execution_days(
    current_run: Optional[Dict[str, Any]],
    planned_execution_days: int,
) -> int:
    if current_run and current_run.get("remaining_execution_days") is not None:
        return max(int(current_run["remaining_execution_days"]), 1)
    return max(int(planned_execution_days or DEFAULT_EXECUTION_DAYS), 1)


def _build_preview_run(
    *,
    current_run: Optional[Dict[str, Any]],
    strategy_profile_id: str,
    target_signature: str,
    business_date: date,
    planned_execution_days: int,
    remaining_execution_days: int,
) -> Dict[str, Any]:
    if current_run:
        return current_run
    return {
        "run_id": None,
        "status": "PREVIEW",
        "strategy_profile_id": strategy_profile_id,
        "target_signature": target_signature,
        "planned_execution_days": max(int(planned_execution_days or DEFAULT_EXECUTION_DAYS), 1),
        "executed_days": 0,
        "remaining_execution_days": max(int(remaining_execution_days or 1), 1),
        "start_business_date": business_date.isoformat(),
    }


def _resolve_business_date(value: Any) -> date:
    if value is None:
        return TimeProvider.get_virtual_business_date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    raise ValueError(f"Unsupported business_date type: {type(value)}")
