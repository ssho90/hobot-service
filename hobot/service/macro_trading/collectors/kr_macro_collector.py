"""
KR macro indicator collector.

Phase 2:
- KR macro/liquidity indicators (ECOS/KOSIS/FRED bridge)
- Frequency/unit normalization
- Canonical rows persisted into fred_data table for unified downstream pipeline
"""

from __future__ import annotations

import calendar
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from service.database.db import get_db_connection
from service.macro_trading.collectors.fred_collector import FREDCollector, get_fred_collector

logger = logging.getLogger(__name__)


KR_MACRO_INDICATORS: Dict[str, Dict[str, Any]] = {
    "KR_BASE_RATE": {
        "name": "Korea Base Rate",
        "country_code": "KR",
        "source": "ECOS",
        "frequency": "monthly",
        "unit": "%",
        "ecos": {
            # BOK base rate (example defaults, can be overridden via kwargs)
            "stat_code": "722Y001",
            "cycle": "M",
            "item_code_1": "0101000",
        },
    },
    "KR_CPI": {
        "name": "Korea CPI (Headline)",
        "country_code": "KR",
        "source": "KOSIS",
        "frequency": "monthly",
        "unit": "Index",
        "kosis": {
            # API parameter defaults are intentionally conservative and override-able.
            "orgId": "101",
            "tblId": "DT_1J22003",
            "itmId": "T01",
            "prdSe": "M",
        },
    },
    "KR_UNEMPLOYMENT": {
        "name": "Korea Unemployment Rate",
        "country_code": "KR",
        "source": "KOSIS",
        "frequency": "monthly",
        "unit": "%",
        "kosis": {
            "orgId": "101",
            "tblId": "DT_1DA7004S",
            "itmId": "T10",
            "prdSe": "M",
        },
    },
    "KR_USDKRW": {
        "name": "USD/KRW Exchange Rate",
        "country_code": "KR",
        "source": "FRED",
        "frequency": "daily",
        "unit": "KRW",
        "fred_code": "DEXKOUS",
    },
    "KR_HOUSE_PRICE_INDEX": {
        "name": "Korea Housing Sale Price Index",
        "country_code": "KR",
        "source": "KOSIS",
        "provider": "REB",
        "frequency": "monthly",
        "unit": "Index",
        "kosis": {
            "orgId": "408",
            "tblId": "DT_30404_A012",
            "itmId": "sales",
            "prdSe": "M",
            "objL1": "00",
            "objL2": "a0",
        },
        "kosis_env": {
            "orgId": "KOSIS_KR_HOUSE_PRICE_ORG_ID",
            "tblId": "KOSIS_KR_HOUSE_PRICE_TBL_ID",
            "itmId": "KOSIS_KR_HOUSE_PRICE_ITM_ID",
            "objL1": "KOSIS_KR_HOUSE_PRICE_OBJL1",
            "objL2": "KOSIS_KR_HOUSE_PRICE_OBJL2",
        },
        "kosis_required_params": ("orgId", "tblId", "itmId", "prdSe", "objL1", "objL2"),
    },
    "KR_JEONSE_PRICE_RATIO": {
        "name": "Korea Jeonse-to-Sale Price Ratio",
        "country_code": "KR",
        "source": "KOSIS",
        "provider": "REB",
        "frequency": "monthly",
        "unit": "%",
        "kosis": {
            "orgId": "408",
            "tblId": "DT_30404_N0006_R1",
            "itmId": "rate",
            "prdSe": "M",
            "objL1": "00",
            "objL2": "a0",
        },
        "kosis_env": {
            "orgId": "KOSIS_KR_JEONSE_RATIO_ORG_ID",
            "tblId": "KOSIS_KR_JEONSE_RATIO_TBL_ID",
            "itmId": "KOSIS_KR_JEONSE_RATIO_ITM_ID",
            "objL1": "KOSIS_KR_JEONSE_RATIO_OBJL1",
            "objL2": "KOSIS_KR_JEONSE_RATIO_OBJL2",
        },
        "kosis_required_params": ("orgId", "tblId", "itmId", "prdSe", "objL1", "objL2"),
    },
    "KR_UNSOLD_HOUSING": {
        "name": "Korea Unsold Housing Inventory",
        "country_code": "KR",
        "source": "KOSIS",
        "provider": "MOLIT/KOSIS",
        "frequency": "monthly",
        "unit": "count",
        "kosis": {
            "orgId": "116",
            "tblId": "DT_MLTM_2082",
            "itmId": "13103871087T1",
            "prdSe": "M",
            "objL1": "all",
            "objL2": "all",
        },
        "kosis_env": {
            "orgId": "KOSIS_KR_UNSOLD_HOUSING_ORG_ID",
            "tblId": "KOSIS_KR_UNSOLD_HOUSING_TBL_ID",
            "itmId": "KOSIS_KR_UNSOLD_HOUSING_ITM_ID",
            "objL1": "KOSIS_KR_UNSOLD_HOUSING_OBJL1",
            "objL2": "KOSIS_KR_UNSOLD_HOUSING_OBJL2",
        },
        "kosis_required_params": ("orgId", "tblId", "itmId", "prdSe", "objL1", "objL2"),
        # As of 2026-02-15, DT_MLTM_2082 returns non-empty rows from 202410 onward.
        "kosis_min_start_ym": "202410",
        # DT_MLTM_2082 returns city/province rows; filter subtotal row and aggregate to national monthly total.
        "kosis_row_filter": {"C2_NM": "계"},
        "kosis_aggregate": "sum",
    },
    "KR_HOUSING_SUPPLY_APPROVAL": {
        "name": "Korea Housing Supply (Permits/Approvals)",
        "country_code": "KR",
        "source": "KOSIS",
        "provider": "MOLIT/KOSIS",
        "frequency": "monthly",
        "unit": "count",
        "kosis": {
            "orgId": "116",
            "tblId": "DT_MLTM_1946",
            "itmId": "13103871089T1",
            "prdSe": "M",
            "objL1": "13102871089A.0001",
            "objL2": "13102871089B.0001",
            "objL3": "13102871089C.0001",
        },
        "kosis_env": {
            "orgId": "KOSIS_KR_HOUSING_SUPPLY_ORG_ID",
            "tblId": "KOSIS_KR_HOUSING_SUPPLY_TBL_ID",
            "itmId": "KOSIS_KR_HOUSING_SUPPLY_ITM_ID",
            "objL1": "KOSIS_KR_HOUSING_SUPPLY_OBJL1",
            "objL2": "KOSIS_KR_HOUSING_SUPPLY_OBJL2",
            "objL3": "KOSIS_KR_HOUSING_SUPPLY_OBJL3",
        },
        "kosis_required_params": ("orgId", "tblId", "itmId", "prdSe", "objL1", "objL2", "objL3"),
    },
}

# Phase 2 comparison lineup
US_KR_COMPARISON_INDICATORS: Tuple[str, ...] = ("KR_USDKRW", "DGS2", "DGS10")
KR_REAL_ESTATE_SUPPLEMENTAL_INDICATORS: Tuple[str, ...] = (
    "KR_HOUSE_PRICE_INDEX",
    "KR_JEONSE_PRICE_RATIO",
    "KR_UNSOLD_HOUSING",
    "KR_HOUSING_SUPPLY_APPROVAL",
)

FREQUENCY_ALIASES = {
    "d": "daily",
    "day": "daily",
    "daily": "daily",
    "w": "weekly",
    "week": "weekly",
    "weekly": "weekly",
    "m": "monthly",
    "month": "monthly",
    "monthly": "monthly",
    "q": "quarterly",
    "quarter": "quarterly",
    "quarterly": "quarterly",
    "y": "yearly",
    "year": "yearly",
    "yearly": "yearly",
}

SENSITIVE_QUERY_KEYS = {"apikey", "servicekey", "authkey", "key"}


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _coerce_date_from_timestamp(ts: Any) -> date:
    if isinstance(ts, datetime):
        return ts.date()
    if isinstance(ts, date):
        return ts
    if hasattr(ts, "to_pydatetime"):
        return ts.to_pydatetime().date()
    return date.fromisoformat(str(ts)[:10])


class KRMacroCollector:
    """KR macro collector with source adapters and canonical persistence."""

    def __init__(
        self,
        fred_collector: Optional[FREDCollector] = None,
        db_connection_factory=None,
    ):
        self.fred_collector = fred_collector or get_fred_collector()
        self._db_connection_factory = db_connection_factory or get_db_connection
        self._phase2_columns_ensured = False

    def _get_db_connection(self):
        return self._db_connection_factory()

    @staticmethod
    def normalize_frequency(raw: Optional[str]) -> str:
        return FREQUENCY_ALIASES.get(str(raw or "").strip().lower(), "daily")

    @staticmethod
    def normalize_unit(value: float, target_unit: str, source_unit: Optional[str] = None) -> float:
        """
        Normalize value scale by target unit.
        - For percent, convert ratios (0~1) to percent when source unit hints ratio.
        - For other units, preserve numeric value.
        """
        if target_unit == "%" and abs(value) <= 1:
            source_text = str(source_unit or "").lower()
            if source_text in {"ratio", "fraction", "decimal"}:
                return value * 100.0
        return value

    @staticmethod
    def _period_to_date(period: str, frequency: str) -> date:
        cleaned = "".join(ch for ch in str(period) if ch.isdigit())
        freq = KRMacroCollector.normalize_frequency(frequency)

        if len(cleaned) >= 8:
            return date(int(cleaned[:4]), int(cleaned[4:6]), int(cleaned[6:8]))

        if freq == "monthly" and len(cleaned) >= 6:
            year = int(cleaned[:4])
            month = int(cleaned[4:6])
            last_day = calendar.monthrange(year, month)[1]
            return date(year, month, last_day)

        if freq == "quarterly" and len(cleaned) >= 6:
            year = int(cleaned[:4])
            quarter = int(cleaned[4:6])
            month = max(1, min(quarter * 3, 12))
            last_day = calendar.monthrange(year, month)[1]
            return date(year, month, last_day)

        if freq == "yearly" and len(cleaned) >= 4:
            year = int(cleaned[:4])
            return date(year, 12, 31)

        # fallback: YYYYMMDD-ish
        year = int(cleaned[:4])
        month = int(cleaned[4:6]) if len(cleaned) >= 6 else 1
        day = int(cleaned[6:8]) if len(cleaned) >= 8 else 1
        return date(year, month, day)

    def _fetch_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        safe_params = {}
        raw_params = {k: v for k, v in (params or {}).items() if v is not None}
        for key, value in raw_params.items():
            if str(key).strip().lower() in SENSITIVE_QUERY_KEYS:
                safe_params[key] = "***REDACTED***"
            else:
                safe_params[key] = value
        safe_query = urlencode(safe_params, doseq=True)
        request_query = urlencode(raw_params, doseq=True)
        request_url = f"{url}?{request_query}" if request_query else url
        safe_url = f"{url}?{safe_query}" if safe_query else url
        logger.info("[KRMacroCollector] requesting %s", safe_url)

        req = Request(
            request_url,
            headers={"User-Agent": "hobot-kr-macro-collector/1.0"},
        )
        with urlopen(req, timeout=30) as response:  # nosec B310
            body = response.read().decode("utf-8")
        return json.loads(body)

    @staticmethod
    def _shift_ym(ym: str, delta_months: int) -> str:
        if len(ym) != 6 or not ym.isdigit():
            return ym
        year = int(ym[:4])
        month = int(ym[4:6])
        serial = year * 12 + (month - 1) + delta_months
        if serial < 0:
            return ym
        shifted_year = serial // 12
        shifted_month = serial % 12 + 1
        return f"{shifted_year:04d}{shifted_month:02d}"

    def fetch_ecos_series(
        self,
        *,
        stat_code: str,
        cycle: str,
        start_period: str,
        end_period: str,
        item_code_1: str = "",
        item_code_2: str = "",
        item_code_3: str = "",
        lang: str = "en",
    ) -> pd.Series:
        """
        Fetch ECOS statistics and return pandas series.
        """
        api_key = os.getenv("ECOS_API_KEY", "").strip()
        if not api_key:
            raise ValueError("ECOS_API_KEY is required for ECOS indicators")

        base = os.getenv("ECOS_API_BASE_URL", "https://ecos.bok.or.kr/api/StatisticSearch").rstrip("/")
        path = "/".join(
            [
                base,
                api_key,
                "json",
                lang,
                "1",
                "10000",
                stat_code,
                cycle,
                start_period,
                end_period,
                item_code_1 or "?",
                item_code_2 or "?",
                item_code_3 or "?",
            ]
        )
        payload = self._fetch_json(path)
        rows = (payload.get("StatisticSearch") or {}).get("row") or []

        values: Dict[date, float] = {}
        normalized_freq = self.normalize_frequency(cycle)
        for row in rows:
            period = row.get("TIME")
            value = _safe_float(row.get("DATA_VALUE"))
            if period is None or value is None:
                continue
            obs_date = self._period_to_date(str(period), normalized_freq)
            values[obs_date] = value

        if not values:
            return pd.Series(dtype=float)
        return pd.Series(values).sort_index()

    @staticmethod
    def _matches_kosis_row_filter(row: Dict[str, Any], row_filter: Dict[str, Any]) -> bool:
        for key, expected in (row_filter or {}).items():
            if str(row.get(str(key), "")).strip() != str(expected).strip():
                return False
        return True

    def fetch_kosis_series(
        self,
        params: Dict[str, Any],
        *,
        frequency: str,
        row_filter: Optional[Dict[str, Any]] = None,
        aggregate: Optional[str] = None,
    ) -> pd.Series:
        """
        Fetch KOSIS statistics and return pandas series.
        """
        api_key = os.getenv("KOSIS_API_KEY", "").strip()
        if not api_key:
            raise ValueError("KOSIS_API_KEY is required for KOSIS indicators")

        base = os.getenv(
            "KOSIS_API_BASE_URL",
            "https://kosis.kr/openapi/Param/statisticsParameterData.do",
        ).rstrip("/")
        query = {
            "method": "getList",
            "apiKey": api_key,
            "format": "json",
            "jsonVD": "Y",
            **params,
        }
        payload = self._fetch_json(base, query)
        rows: List[Dict[str, Any]] = payload if isinstance(payload, list) else []

        # Some KOSIS monthly tables return empty when endPrdDe points to unpublished/latest unsupported month.
        # Retry by stepping endPrdDe backward up to 24 months.
        if (
            not rows
            and str(params.get("prdSe", "")).upper() == "M"
            and str(params.get("startPrdDe", "")).isdigit()
            and len(str(params.get("startPrdDe", ""))) == 6
            and str(params.get("endPrdDe", "")).isdigit()
            and len(str(params.get("endPrdDe", ""))) == 6
        ):
            start_ym = str(params["startPrdDe"])
            retry_end_ym = str(params["endPrdDe"])
            for _ in range(24):
                retry_end_ym = self._shift_ym(retry_end_ym, -1)
                if retry_end_ym < start_ym:
                    break
                retry_query = dict(query)
                retry_query["endPrdDe"] = retry_end_ym
                retry_payload = self._fetch_json(base, retry_query)
                retry_rows = retry_payload if isinstance(retry_payload, list) else []
                if retry_rows:
                    logger.info(
                        "[KRMacroCollector] KOSIS fallback endPrdDe=%s -> %s yielded rows=%s",
                        params.get("endPrdDe"),
                        retry_end_ym,
                        len(retry_rows),
                    )
                    rows = retry_rows
                    break
        if row_filter:
            rows = [row for row in rows if self._matches_kosis_row_filter(row, row_filter)]

        values: Dict[date, float] = {}
        normalized_freq = self.normalize_frequency(frequency)
        aggregate_mode = str(aggregate or "").strip().lower()
        for row in rows:
            period = row.get("PRD_DE") or row.get("TIME")
            value = _safe_float(row.get("DT") or row.get("DATA_VALUE"))
            if period is None or value is None:
                continue
            obs_date = self._period_to_date(str(period), normalized_freq)
            if aggregate_mode == "sum":
                values[obs_date] = values.get(obs_date, 0.0) + value
            else:
                values[obs_date] = value

        if not values:
            return pd.Series(dtype=float)
        return pd.Series(values).sort_index()

    def _resolve_kosis_params(
        self,
        indicator_code: str,
        meta: Dict[str, Any],
        *,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = dict(meta.get("kosis") or {})
        env_mapping = dict(meta.get("kosis_env") or {})
        for param_name, env_name in env_mapping.items():
            env_value = os.getenv(str(env_name), "").strip()
            if env_value:
                params[str(param_name)] = env_value

        # Advanced override for provider-specific query fields.
        # Example:
        # KOSIS_KR_HOUSE_PRICE_INDEX_PARAMS_JSON='{"objL1":"ALL","objL2":"00"}'
        params_json_env = f"KOSIS_{indicator_code}_PARAMS_JSON"
        raw_json = os.getenv(params_json_env, "").strip()
        if raw_json:
            try:
                parsed = json.loads(raw_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{params_json_env} must be valid JSON object") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"{params_json_env} must be a JSON object")
            params.update(parsed)

        required_params = tuple(meta.get("kosis_required_params") or ())
        missing_params = [
            key for key in required_params if str(params.get(str(key), "")).strip() == ""
        ]
        if missing_params:
            raise ValueError(
                f"KOSIS params missing for {indicator_code}: {', '.join(missing_params)}"
            )

        if "startPrdDe" not in params:
            params["startPrdDe"] = start_date.strftime("%Y%m")
        if "endPrdDe" not in params:
            params["endPrdDe"] = end_date.strftime("%Y%m")

        min_start_ym = str(meta.get("kosis_min_start_ym") or "").strip()
        if (
            len(min_start_ym) == 6
            and min_start_ym.isdigit()
            and str(params.get("startPrdDe", "")).isdigit()
            and len(str(params.get("startPrdDe", ""))) == 6
            and str(params.get("startPrdDe")) < min_start_ym
        ):
            params["startPrdDe"] = min_start_ym

        return params

    def fetch_indicator(
        self,
        indicator_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.Series:
        if indicator_code not in KR_MACRO_INDICATORS:
            raise KeyError(f"Unsupported KR indicator code: {indicator_code}")

        meta = KR_MACRO_INDICATORS[indicator_code]
        source = str(meta.get("source", "")).upper()
        end = end_date or date.today()
        start = start_date or (end - timedelta(days=365))
        frequency = self.normalize_frequency(meta.get("frequency"))

        if source == "FRED":
            fred_code = meta.get("fred_code", indicator_code)
            return self.fred_collector.fetch_indicator(fred_code, start, end)

        if source == "ECOS":
            ecos = dict(meta.get("ecos") or {})
            cycle = str(ecos.get("cycle") or "M")
            # ECOS period format is driven by cycle.
            if cycle.upper().startswith("D"):
                start_period = start.strftime("%Y%m%d")
                end_period = end.strftime("%Y%m%d")
            elif cycle.upper().startswith("Q"):
                start_period = f"{start.year}{((start.month - 1) // 3) + 1:02d}"
                end_period = f"{end.year}{((end.month - 1) // 3) + 1:02d}"
            elif cycle.upper().startswith("Y"):
                start_period = f"{start.year}"
                end_period = f"{end.year}"
            else:
                start_period = start.strftime("%Y%m")
                end_period = end.strftime("%Y%m")
            return self.fetch_ecos_series(
                stat_code=str(ecos.get("stat_code")),
                cycle=cycle,
                start_period=start_period,
                end_period=end_period,
                item_code_1=str(ecos.get("item_code_1") or ""),
                item_code_2=str(ecos.get("item_code_2") or ""),
                item_code_3=str(ecos.get("item_code_3") or ""),
            )

        if source == "KOSIS":
            params = self._resolve_kosis_params(
                indicator_code,
                meta,
                start_date=start,
                end_date=end,
            )
            return self.fetch_kosis_series(
                params,
                frequency=frequency,
                row_filter=dict(meta.get("kosis_row_filter") or {}),
                aggregate=str(meta.get("kosis_aggregate") or ""),
            )

        raise ValueError(f"Unknown source for {indicator_code}: {source}")

    def build_observation_rows(
        self,
        indicator_code: str,
        series: pd.Series,
        *,
        as_of_date: Optional[date] = None,
        revision_flag: bool = False,
    ) -> List[Dict[str, Any]]:
        meta = KR_MACRO_INDICATORS[indicator_code]
        target_unit = str(meta.get("unit") or "")
        source_name = str(meta.get("source") or "KR")
        as_of = as_of_date or date.today()
        rows: List[Dict[str, Any]] = []

        for ts, raw_value in series.dropna().items():
            obs_date = _coerce_date_from_timestamp(ts)
            value = _safe_float(raw_value)
            if value is None:
                continue
            normalized_value = self.normalize_unit(value, target_unit=target_unit, source_unit=target_unit)
            rows.append(
                {
                    "indicator_code": indicator_code,
                    "indicator_name": str(meta.get("name") or indicator_code),
                    "date": obs_date,
                    "value": normalized_value,
                    "unit": target_unit,
                    "source": source_name,
                    "effective_date": obs_date,
                    "published_at": datetime.combine(obs_date, datetime.min.time()),
                    "as_of_date": as_of,
                    "revision_flag": bool(revision_flag),
                }
            )

        rows.sort(key=lambda item: item["date"])
        return rows

    def _get_fred_data_columns(self) -> List[str]:
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'fred_data'
                """
            )
            return [str(row["COLUMN_NAME"]) for row in cursor.fetchall()]

    def _ensure_phase2_columns(self):
        if self._phase2_columns_ensured:
            return
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            alter_statements = [
                "ALTER TABLE fred_data ADD COLUMN effective_date DATE NULL",
                "ALTER TABLE fred_data ADD COLUMN published_at DATETIME NULL",
                "ALTER TABLE fred_data ADD COLUMN as_of_date DATE NULL",
                "ALTER TABLE fred_data ADD COLUMN revision_flag TINYINT(1) DEFAULT 0",
            ]
            for stmt in alter_statements:
                try:
                    cursor.execute(stmt)
                except Exception:
                    # already exists or unsupported in this environment
                    pass

            # Ensure new indicator codes fit (e.g., KR_HOUSING_SUPPLY_APPROVAL > 20 chars).
            try:
                cursor.execute(
                    """
                    SELECT CHARACTER_MAXIMUM_LENGTH
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'fred_data'
                      AND COLUMN_NAME = 'indicator_code'
                    """
                )
                row = cursor.fetchone() or {}
                max_len = int(row.get("CHARACTER_MAXIMUM_LENGTH") or 0)
                if max_len and max_len < 64:
                    cursor.execute("ALTER TABLE fred_data MODIFY COLUMN indicator_code VARCHAR(64) NOT NULL")
            except Exception:
                pass
        self._phase2_columns_ensured = True

    def save_rows_to_db(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0

        self._ensure_phase2_columns()
        available_columns = set(self._get_fred_data_columns())

        insert_columns = [
            "indicator_code",
            "indicator_name",
            "date",
            "value",
            "unit",
            "source",
            "effective_date",
            "published_at",
            "as_of_date",
            "revision_flag",
        ]
        insert_columns = [col for col in insert_columns if col in available_columns]
        value_columns = ["`{}`".format(col) for col in insert_columns]
        placeholders = ", ".join(["%s"] * len(insert_columns))
        updates = [f"`{col}` = VALUES(`{col}`)" for col in insert_columns if col not in {"indicator_code", "date"}]

        query = f"""
            INSERT INTO fred_data ({", ".join(value_columns)})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {", ".join(updates)}
        """

        payload = [tuple(row.get(col) for col in insert_columns) for row in rows]
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            affected = int(cursor.rowcount or 0)

        logger.info("[KRMacroCollector] persisted rows=%s", len(rows))
        return affected

    def collect_indicators(
        self,
        indicator_codes: Optional[Iterable[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        codes = list(indicator_codes or KR_MACRO_INDICATORS.keys())
        result: Dict[str, Any] = {"success": {}, "failed": {}}

        for code in codes:
            try:
                series = self.fetch_indicator(code, start_date=start_date, end_date=end_date)
                rows = self.build_observation_rows(code, series, as_of_date=as_of_date)
                persisted = self.save_rows_to_db(rows)
                result["success"][code] = {
                    "points": int(series.dropna().shape[0]),
                    "rows": len(rows),
                    "db_affected": persisted,
                }
            except Exception as exc:
                logger.warning("[KRMacroCollector] %s failed: %s", code, exc)
                result["failed"][code] = str(exc)

        result["total_success"] = len(result["success"])
        result["total_failed"] = len(result["failed"])
        return result


_kr_macro_collector_singleton: Optional[KRMacroCollector] = None


def get_kr_macro_collector() -> KRMacroCollector:
    global _kr_macro_collector_singleton
    if _kr_macro_collector_singleton is None:
        _kr_macro_collector_singleton = KRMacroCollector()
    return _kr_macro_collector_singleton
