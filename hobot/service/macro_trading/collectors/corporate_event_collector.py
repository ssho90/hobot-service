"""
US/KR Tier-1 기업 이벤트 표준 스키마 동기화 수집기.

표준 스키마 필수 필드:
- symbol
- event_type
- source_url
- effective_date
"""
from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests
from service.database.db import get_db_connection
from service.macro_trading.collectors.kr_corporate_collector import (
    DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
)
from service.macro_trading.collectors.us_corporate_collector import (
    DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
)

logger = logging.getLogger(__name__)
DEFAULT_KR_IR_FEED_TIMEOUT_SECONDS = 20
DEFAULT_SOURCE_RETRY_DELAYS_MINUTES = (1, 5, 15)


def _normalize_symbol(value: Any) -> Optional[str]:
    text = str(value or "").strip().upper()
    return text or None


def _normalize_corp_code(value: Any) -> Optional[str]:
    text = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(text) == 8:
        return text
    return None


def _normalize_cik(value: Any) -> Optional[str]:
    text = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not text:
        return None
    return text.zfill(10)


def _to_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return stripped
    return json.dumps(value, ensure_ascii=False, default=str)


def _load_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _normalize_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _normalize_epoch_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, (int, float)):
        return None
    try:
        ts = float(value)
    except Exception:
        return None
    # yfinance payloads may provide epoch seconds or milliseconds.
    if abs(ts) >= 10_000_000_000:
        ts = ts / 1000.0
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def _first_non_empty_str(*values: Any) -> Optional[str]:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _coerce_yahoo_url(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("/"):
        return urljoin("https://finance.yahoo.com", text)
    return text


def _normalize_similarity_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^0-9a-z가-힣 ]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_url_for_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text.endswith("/"):
        text = text[:-1]
    return text


def _contains_hangul(value: Any) -> bool:
    return bool(re.search(r"[가-힣]", str(value or "")))


def _extract_korean_keywords(*values: Any, max_keywords: int = 8) -> List[str]:
    seen = set()
    keywords: List[str] = []
    for value in values:
        text = str(value or "")
        for token in re.findall(r"[가-힣]{2,}", text):
            if token in seen:
                continue
            seen.add(token)
            keywords.append(token)
            if len(keywords) >= max_keywords:
                return keywords
    return keywords


def _build_multilingual_fields(
    *,
    title: Any,
    body: Any,
) -> Dict[str, Any]:
    title_text = str(title or "").strip()
    body_text = str(body or "").strip()

    title_has_ko = _contains_hangul(title_text)
    body_has_ko = _contains_hangul(body_text)

    title_en = title_text if title_text and not title_has_ko else None
    body_en = body_text if body_text and not body_has_ko else None

    summary_ko = None
    if body_text and body_has_ko:
        summary_ko = body_text
    elif title_text and title_has_ko:
        summary_ko = title_text

    keywords_ko = _extract_korean_keywords(title_text, body_text)

    return {
        "title_en": title_en,
        "body_en": body_en,
        "summary_ko": summary_ko,
        "keywords_ko": keywords_ko,
    }


def _build_news_source_ref(
    *,
    source_url: Any,
    title: Any,
    published_at: Optional[datetime],
    fallback_ref: Any = None,
) -> str:
    normalized_url = _normalize_url_for_key(source_url)
    normalized_title = _normalize_similarity_text(title)
    published_key = published_at.strftime("%Y-%m-%dT%H:%M:%S") if isinstance(published_at, datetime) else ""

    if normalized_url or normalized_title or published_key:
        seed = f"{normalized_url}|{normalized_title}|{published_key}"
    else:
        seed = str(fallback_ref or "").strip()

    if not seed:
        seed = "unknown"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


class CorporateEventCollector:
    def __init__(self, timeout_seconds: int = DEFAULT_KR_IR_FEED_TIMEOUT_SECONDS):
        self.timeout_seconds = max(int(timeout_seconds), 5)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
            }
        )
        self._last_run_dlq_count = 0
        self._last_run_retry_failure_count = 0

    @contextmanager
    def _get_db_connection(self):
        with get_db_connection() as conn:
            yield conn

    def ensure_tables(self) -> None:
        query = """
            CREATE TABLE IF NOT EXISTS corporate_event_feed (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                country_code VARCHAR(4) NOT NULL,
                symbol VARCHAR(32) NOT NULL,
                corp_code CHAR(8) NULL,
                cik CHAR(10) NULL,
                event_date DATE NOT NULL,
                effective_date DATETIME NOT NULL,
                event_type VARCHAR(64) NOT NULL,
                event_status VARCHAR(16) NULL,
                source VARCHAR(32) NOT NULL,
                source_url VARCHAR(255) NULL,
                source_ref VARCHAR(128) NOT NULL DEFAULT '',
                title VARCHAR(255) NULL,
                payload_json JSON NULL,
                as_of_date DATE NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_event_identity (
                    country_code, symbol, event_date, event_type, source, source_ref, event_status
                ),
                INDEX idx_country_effective_date (country_code, effective_date),
                INDEX idx_symbol_effective_date (symbol, effective_date),
                INDEX idx_event_type_date (event_type, event_date),
                INDEX idx_source_date (source, event_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        dlq_query = """
            CREATE TABLE IF NOT EXISTS corporate_event_ingest_dlq (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_key VARCHAR(64) NOT NULL,
                country_code VARCHAR(4) NULL,
                event_type VARCHAR(64) NULL,
                retry_count INT NOT NULL DEFAULT 0,
                error_code VARCHAR(64) NULL,
                error_message TEXT NULL,
                payload_json JSON NULL,
                next_retry_at DATETIME NULL,
                status VARCHAR(16) NOT NULL DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_dlq_source_time (source_key, occurred_at),
                INDEX idx_dlq_status_time (status, occurred_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            cursor.execute(dlq_query)

    @staticmethod
    def _resolve_source_retry_delays_seconds() -> List[int]:
        csv_value = str(
            os.getenv(
                "TIER1_EVENT_SOURCE_RETRY_DELAYS_MINUTES",
                ",".join(str(value) for value in DEFAULT_SOURCE_RETRY_DELAYS_MINUTES),
            )
            or ""
        ).strip()
        delays: List[int] = []
        for token in csv_value.split(","):
            text = token.strip()
            if not text:
                continue
            try:
                minute = int(float(text))
            except Exception:
                continue
            if minute < 0:
                continue
            delays.append(minute * 60)
        if not delays:
            return [int(value) * 60 for value in DEFAULT_SOURCE_RETRY_DELAYS_MINUTES]
        return delays

    def record_dlq(
        self,
        *,
        source_key: str,
        country_code: Optional[str],
        event_type: Optional[str],
        retry_count: int,
        error_code: str,
        error_message: str,
        payload: Optional[Dict[str, Any]] = None,
        next_retry_at: Optional[datetime] = None,
    ) -> None:
        query = """
            INSERT INTO corporate_event_ingest_dlq (
                source_key,
                country_code,
                event_type,
                retry_count,
                error_code,
                error_message,
                payload_json,
                next_retry_at,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'open')
        """
        payload_json = _to_json(payload) if payload is not None else None
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    query,
                    (
                        str(source_key or "").strip()[:64] or "unknown_source",
                        str(country_code or "").strip().upper()[:4] or None,
                        str(event_type or "").strip().lower()[:64] or None,
                        int(max(retry_count, 0)),
                        str(error_code or "").strip()[:64] or None,
                        str(error_message or "").strip()[:2000] or None,
                        payload_json,
                        next_retry_at,
                    ),
                )
            self._last_run_dlq_count += 1
        except Exception as exc:
            logger.warning("[CorporateEventCollector] failed to record DLQ(source=%s): %s", source_key, exc)

    def _run_with_source_retry(
        self,
        *,
        operation,
        source_key: str,
        country_code: Optional[str],
        event_type: Optional[str],
        payload: Optional[Dict[str, Any]] = None,
    ):
        delays = self._resolve_source_retry_delays_seconds()
        max_attempts = len(delays) + 1
        last_error: Optional[Exception] = None

        for attempt in range(max_attempts):
            try:
                return operation()
            except Exception as exc:
                last_error = exc
                if attempt < len(delays):
                    delay_seconds = max(int(delays[attempt]), 0)
                    logger.warning(
                        "[CorporateEventCollector] source retry %s/%s failed(source=%s): %s, retry in %ss",
                        attempt + 1,
                        max_attempts,
                        source_key,
                        exc,
                        delay_seconds,
                    )
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)
                    continue
                break

        self._last_run_retry_failure_count += 1
        next_retry_at = datetime.now() + timedelta(seconds=delays[0]) if delays else None
        self.record_dlq(
            source_key=source_key,
            country_code=country_code,
            event_type=event_type,
            retry_count=max_attempts,
            error_code=type(last_error).__name__ if last_error is not None else "UnknownError",
            error_message=str(last_error or "unknown error"),
            payload=payload,
            next_retry_at=next_retry_at,
        )
        return None

    @staticmethod
    def classify_event_category(
        *,
        country_code: str,
        event_type: str,
        source: str,
    ) -> str:
        et = str(event_type or "").strip().lower()
        src = str(source or "").strip().lower()
        cc = str(country_code or "").strip().upper()

        if cc == "US":
            if et == "yfinance_news":
                return "news"
            if et in {"yfinance_earnings_calendar", "sec_8k_earnings"}:
                return "earnings"
            if et in {"sec_10q", "sec_10k"}:
                return "periodic_report"
            if src == "sec":
                return "ir_event"
            return "corporate_event"

        if et in {"earnings_announcement"}:
            return "earnings"
        if et in {"periodic_report"}:
            return "periodic_report"
        if et in {"ir_event", "ir_news"}:
            return "ir_event"
        return "corporate_disclosure"

    @staticmethod
    def classify_event_domain(
        *,
        country_code: str,
        event_type: str,
        source: str,
    ) -> str:
        category = CorporateEventCollector.classify_event_category(
            country_code=country_code,
            event_type=event_type,
            source=source,
        )
        if category == "news":
            return "news"
        if category in {"earnings", "periodic_report", "ir_event"}:
            return "ir"
        return "disclosure"

    @staticmethod
    def build_kr_standard_event(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        corp_code = _normalize_corp_code(raw.get("corp_code"))
        symbol = _normalize_symbol(raw.get("stock_code")) or corp_code
        event_type = str(raw.get("event_type") or "").strip().lower()
        if not event_type or event_type == "corporate_disclosure":
            report_nm_for_classify = str(raw.get("report_nm") or "").strip()
            if report_nm_for_classify:
                report_name_lower = report_nm_for_classify.lower()
                if ("기업설명회" in report_nm_for_classify) or ("투자설명회" in report_nm_for_classify) or ("ir" in report_name_lower):
                    event_type = "ir_event"
                elif ("사업보고서" in report_nm_for_classify) or ("반기보고서" in report_nm_for_classify) or ("분기보고서" in report_nm_for_classify):
                    event_type = "periodic_report"
        source_url = str(raw.get("source_url") or "").strip()
        rcept_no = str(raw.get("rcept_no") or "").strip()
        event_date = raw.get("rcept_dt")

        if not symbol or not event_type or not isinstance(event_date, date):
            return None

        effective_date = datetime.combine(event_date, time.min)
        event_category = CorporateEventCollector.classify_event_category(
            country_code="KR",
            event_type=event_type,
            source="dart",
        )
        payload = {
            "corp_name": raw.get("corp_name"),
            "report_nm": raw.get("report_nm"),
            "period_year": raw.get("period_year"),
            "fiscal_quarter": raw.get("fiscal_quarter"),
            "is_earnings_event": int(raw.get("is_earnings_event") or 0),
            "event_category": event_category,
            "event_domain": CorporateEventCollector.classify_event_domain(
                country_code="KR",
                event_type=event_type,
                source="dart",
            ),
            "metadata_json": _load_json(raw.get("metadata_json")),
            **_build_multilingual_fields(
                title=raw.get("report_nm"),
                body=raw.get("report_nm"),
            ),
        }

        return {
            "country_code": "KR",
            "symbol": symbol,
            "corp_code": corp_code,
            "cik": None,
            "event_date": event_date,
            "effective_date": effective_date,
            "event_type": event_type,
            "event_status": "confirmed",
            "source": "dart",
            "source_url": source_url or None,
            "source_ref": rcept_no,
            "title": str(raw.get("report_nm") or "").strip() or None,
            "payload_json": _to_json(payload),
            "as_of_date": raw.get("as_of_date"),
        }

    @staticmethod
    def build_us_standard_event(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        symbol = _normalize_symbol(raw.get("symbol"))
        event_type = str(raw.get("event_type") or "").strip().lower()
        source = str(raw.get("source") or "").strip().lower() or "unknown"
        source_ref = str(raw.get("source_ref") or "").strip()
        event_status = str(raw.get("event_status") or "").strip().lower() or None
        event_date = raw.get("event_date")
        filed_at = raw.get("filed_at")
        metadata = _load_json(raw.get("metadata_json"))

        if not symbol or not event_type or not isinstance(event_date, date):
            return None

        if isinstance(filed_at, datetime):
            effective_date = filed_at
        else:
            effective_date = datetime.combine(event_date, time.min)

        source_url = _first_non_empty_str(
            metadata.get("source_url"),
            metadata.get("url"),
            metadata.get("link"),
        )
        event_category = CorporateEventCollector.classify_event_category(
            country_code="US",
            event_type=event_type,
            source=source,
        )
        title = f"{symbol} {event_type}".strip()
        payload = {
            "report_date": raw.get("report_date"),
            "event_category": event_category,
            "event_domain": CorporateEventCollector.classify_event_domain(
                country_code="US",
                event_type=event_type,
                source=source,
            ),
            "metadata_json": metadata,
            **_build_multilingual_fields(
                title=title,
                body=_first_non_empty_str(
                    metadata.get("summary"),
                    metadata.get("description"),
                    metadata.get("report_title"),
                ),
            ),
        }

        return {
            "country_code": "US",
            "symbol": symbol,
            "corp_code": None,
            "cik": _normalize_cik(raw.get("cik")),
            "event_date": event_date,
            "effective_date": effective_date,
            "event_type": event_type,
            "event_status": event_status,
            "source": source,
            "source_url": source_url,
            "source_ref": source_ref,
            "title": title,
            "payload_json": _to_json(payload),
            "as_of_date": raw.get("as_of_date"),
        }

    @staticmethod
    def _extract_yfinance_news_item(
        *,
        item: Dict[str, Any],
        symbol: str,
        start_date: date,
        end_date: date,
        as_of_date: date,
    ) -> Optional[Dict[str, Any]]:
        content = item.get("content")
        content_dict = content if isinstance(content, dict) else {}
        canonical_url = content_dict.get("canonicalUrl")
        canonical_url_dict = canonical_url if isinstance(canonical_url, dict) else {}
        provider = content_dict.get("provider")
        provider_dict = provider if isinstance(provider, dict) else {}

        title = _first_non_empty_str(
            item.get("title"),
            content_dict.get("title"),
        )
        link = _coerce_yahoo_url(
            _first_non_empty_str(
                item.get("link"),
                item.get("url"),
                content_dict.get("clickThroughUrl"),
                content_dict.get("url"),
                canonical_url_dict.get("url"),
            )
        )
        summary = _first_non_empty_str(
            item.get("summary"),
            content_dict.get("summary"),
            content_dict.get("description"),
        )

        published_dt = (
            _normalize_epoch_datetime(item.get("providerPublishTime"))
            or _normalize_datetime(item.get("pubDate"))
            or _normalize_datetime(item.get("published"))
            or _normalize_datetime(content_dict.get("pubDate"))
            or _normalize_datetime(content_dict.get("publishedAt"))
        )
        if published_dt is None:
            return None

        event_date = published_dt.date()
        if event_date < start_date or event_date > end_date:
            return None
        if not title and not link:
            return None

        raw_source_ref = _first_non_empty_str(
            item.get("id"),
            item.get("uuid"),
            content_dict.get("id"),
            content_dict.get("uuid"),
        )
        source_ref = _build_news_source_ref(
            source_url=link,
            title=title,
            published_at=published_dt,
            fallback_ref=raw_source_ref,
        )

        related_tickers = item.get("relatedTickers")
        if not isinstance(related_tickers, list):
            related_tickers = []
        finance_rows = content_dict.get("finance")
        if isinstance(finance_rows, list):
            for finance_row in finance_rows:
                if not isinstance(finance_row, dict):
                    continue
                related_symbol = _normalize_symbol(finance_row.get("symbol"))
                if related_symbol:
                    related_tickers.append(related_symbol)
        provider_name = _first_non_empty_str(
            item.get("publisher"),
            item.get("provider"),
            provider_dict.get("displayName"),
            provider_dict.get("name"),
        )

        payload = {
            "provider": provider_name,
            "relatedTickers": list(dict.fromkeys([str(value).strip().upper() for value in related_tickers if str(value or "").strip()])),
            "type": _first_non_empty_str(item.get("type"), content_dict.get("type")),
            "summary": summary,
            "normalized_title": _normalize_similarity_text(title),
            "published_at": published_dt.isoformat(),
            "event_category": "news",
            "event_domain": "news",
            **_build_multilingual_fields(
                title=title,
                body=summary,
            ),
        }
        return {
            "country_code": "US",
            "symbol": symbol,
            "corp_code": None,
            "cik": None,
            "event_date": event_date,
            "effective_date": published_dt,
            "event_type": "yfinance_news",
            "event_status": "published",
            "source": "yfinance",
            "source_url": link,
            "source_ref": source_ref,
            "title": title,
            "payload_json": _to_json(payload),
            "as_of_date": as_of_date,
        }

    @staticmethod
    def _normalize_match_text(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[^0-9a-z가-힣]", "", text)
        return text

    @staticmethod
    def _extract_feed_datetime(value: Any) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except Exception:
            return _normalize_datetime(text)

    @staticmethod
    def _extract_xml_text(parent: Optional[ET.Element], tag_names: Sequence[str]) -> Optional[str]:
        if parent is None:
            return None
        for tag_name in tag_names:
            node = parent.find(tag_name)
            if node is not None and node.text:
                value = node.text.strip()
                if value:
                    return value
        return None

    @staticmethod
    def _extract_atom_link(entry: ET.Element) -> Optional[str]:
        for link_node in entry.findall("{*}link"):
            href = str(link_node.attrib.get("href") or "").strip()
            rel = str(link_node.attrib.get("rel") or "alternate").strip().lower()
            if href and rel == "alternate":
                return href
            if href:
                return href
        return None

    def _fetch_feed_xml(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.text

    def _parse_feed_entries(self, xml_text: str) -> List[Dict[str, Any]]:
        if not xml_text:
            return []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ValueError(f"invalid feed xml: {exc}") from exc

        entries: List[Dict[str, Any]] = []

        # RSS
        for item in root.findall("./channel/item"):
            title = self._extract_xml_text(item, ["title"])
            link = self._extract_xml_text(item, ["link"])
            description = self._extract_xml_text(item, ["description"])
            source_ref = self._extract_xml_text(item, ["guid"])
            published_raw = self._extract_xml_text(item, ["pubDate", "dc:date"])
            published_at = self._extract_feed_datetime(published_raw)
            if not title and not link:
                continue
            entries.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "source_ref": source_ref,
                    "published_at": published_at,
                }
            )

        # Atom
        for entry in root.findall("./{*}entry"):
            title = self._extract_xml_text(entry, ["{*}title"])
            link = self._extract_atom_link(entry)
            description = self._extract_xml_text(entry, ["{*}summary", "{*}content"])
            source_ref = self._extract_xml_text(entry, ["{*}id"])
            published_raw = self._extract_xml_text(entry, ["{*}published", "{*}updated"])
            published_at = self._extract_feed_datetime(published_raw)
            if not title and not link:
                continue
            entries.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "source_ref": source_ref,
                    "published_at": published_at,
                }
            )

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for entry in entries:
            key = (
                str(entry.get("title") or "").strip().lower(),
                str(entry.get("link") or "").strip().lower(),
                str(entry.get("source_ref") or "").strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(entry)
        return deduped

    def load_kr_top_company_rows(
        self,
        *,
        market: str = "KOSPI",
        top_limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> List[Dict[str, Any]]:
        resolved_market = str(market or "KOSPI").strip().upper() or "KOSPI"
        resolved_top_limit = max(int(top_limit), 1)
        query = """
            SELECT
                s.stock_code,
                s.stock_name,
                s.corp_code,
                c.corp_name
            FROM kr_top50_universe_snapshot s
            LEFT JOIN kr_dart_corp_codes c
                ON c.corp_code = s.corp_code
            WHERE s.market = %s
              AND s.snapshot_date = (
                  SELECT MAX(snapshot_date)
                  FROM kr_top50_universe_snapshot
                  WHERE market = %s
              )
              AND s.rank_position <= %s
            ORDER BY s.rank_position ASC
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (resolved_market, resolved_market, resolved_top_limit))
            rows = cursor.fetchall() or []
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            symbol = _normalize_symbol(row.get("stock_code"))
            if not symbol:
                continue
            stock_name = str(row.get("stock_name") or "").strip()
            corp_name = str(row.get("corp_name") or "").strip()
            corp_code = _normalize_corp_code(row.get("corp_code"))
            normalized.append(
                {
                    "symbol": symbol,
                    "stock_name": stock_name or None,
                    "corp_name": corp_name or None,
                    "corp_code": corp_code,
                }
            )
        return normalized

    def _resolve_kr_symbol_from_text(
        self,
        *,
        title: str,
        description: str,
        companies: Sequence[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        haystack = self._normalize_match_text(f"{title} {description}")
        if not haystack:
            return None

        best_match: Optional[Dict[str, Any]] = None
        best_score = -1
        for company in companies:
            symbol = _normalize_symbol(company.get("symbol"))
            if not symbol:
                continue
            candidates = [
                str(company.get("stock_name") or "").strip(),
                str(company.get("corp_name") or "").strip(),
            ]
            for candidate in candidates:
                normalized_candidate = self._normalize_match_text(candidate)
                if len(normalized_candidate) < 2:
                    continue
                if normalized_candidate in haystack:
                    score = len(normalized_candidate)
                    if score > best_score:
                        best_score = score
                        best_match = {
                            "symbol": symbol,
                            "corp_code": _normalize_corp_code(company.get("corp_code")),
                            "matched_name": candidate,
                        }
        return best_match

    @staticmethod
    def _resolve_kr_ir_feed_urls(feed_urls: Optional[Sequence[str]] = None) -> List[str]:
        if feed_urls is not None:
            raw_values = [str(value or "").strip() for value in feed_urls]
        else:
            raw_csv = str(os.getenv("KR_TIER1_IR_FEED_URLS", "") or "").strip()
            raw_values = [value.strip() for value in raw_csv.split(",")]
        resolved = [value for value in raw_values if value]
        return list(dict.fromkeys(resolved))

    def fetch_kr_ir_news_rows(
        self,
        *,
        start_date: date,
        end_date: date,
        market: str = "KOSPI",
        top_limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
        as_of_date: Optional[date] = None,
        feed_urls: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        resolved_as_of = as_of_date or end_date
        resolved_feed_urls = self._resolve_kr_ir_feed_urls(feed_urls)
        if not resolved_feed_urls:
            return []

        companies = self.load_kr_top_company_rows(
            market=market,
            top_limit=top_limit,
        )
        if not companies:
            return []

        rows: List[Dict[str, Any]] = []
        seen_keys = set()
        for feed_url in resolved_feed_urls:
            xml_text = self._run_with_source_retry(
                operation=lambda: self._fetch_feed_xml(feed_url),
                source_key="kr_ir_feed_fetch",
                country_code="KR",
                event_type="ir_news",
                payload={"feed_url": feed_url},
            )
            if not isinstance(xml_text, str) or not xml_text.strip():
                continue
            try:
                entries = self._parse_feed_entries(xml_text)
            except Exception as exc:
                self._last_run_retry_failure_count += 1
                self.record_dlq(
                    source_key="kr_ir_feed_parse",
                    country_code="KR",
                    event_type="ir_news",
                    retry_count=1,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                    payload={"feed_url": feed_url},
                    next_retry_at=None,
                )
                logger.warning("[CorporateEventCollector] KR IR feed parse failed(url=%s): %s", feed_url, exc)
                continue

            for entry in entries:
                title = str(entry.get("title") or "").strip()
                link = str(entry.get("link") or "").strip()
                description = str(entry.get("description") or "").strip()
                published_at = entry.get("published_at")
                if not isinstance(published_at, datetime):
                    continue
                event_date = published_at.date()
                if event_date < start_date or event_date > end_date:
                    continue

                matched = self._resolve_kr_symbol_from_text(
                    title=title,
                    description=description,
                    companies=companies,
                )
                if not matched:
                    continue

                raw_source_ref = str(entry.get("source_ref") or "").strip()
                source_ref = _build_news_source_ref(
                    source_url=link or feed_url,
                    title=title,
                    published_at=published_at,
                    fallback_ref=raw_source_ref,
                )

                dedupe_key = (
                    matched.get("symbol"),
                    source_ref,
                    event_date,
                )
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)

                rows.append(
                    {
                        "country_code": "KR",
                        "symbol": matched.get("symbol"),
                        "corp_code": matched.get("corp_code"),
                        "cik": None,
                        "event_date": event_date,
                        "effective_date": published_at,
                        "event_type": "ir_news",
                        "event_status": "published",
                        "source": "kr_ir_feed",
                        "source_url": link or None,
                        "source_ref": source_ref,
                        "title": title or None,
                        "payload_json": _to_json(
                            {
                                "feed_url": feed_url,
                                "matched_name": matched.get("matched_name"),
                                "summary": description or None,
                                "normalized_title": _normalize_similarity_text(title),
                                "published_at": published_at.isoformat(),
                                "event_category": "ir_event",
                                "event_domain": "ir",
                                **_build_multilingual_fields(
                                    title=title,
                                    body=description,
                                ),
                            }
                        ),
                        "as_of_date": resolved_as_of,
                    }
                )
        return rows

    def load_kr_tier1_rows(
        self,
        *,
        start_date: date,
        end_date: date,
        market: str = "KOSPI",
        top_limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
    ) -> List[Dict[str, Any]]:
        resolved_market = str(market or "KOSPI").strip().upper() or "KOSPI"
        resolved_top_limit = max(int(top_limit), 1)

        query = """
            SELECT
                d.rcept_no,
                d.corp_code,
                COALESCE(d.stock_code, s.stock_code) AS stock_code,
                d.corp_name,
                d.report_nm,
                d.rcept_dt,
                d.event_type,
                d.is_earnings_event,
                d.period_year,
                d.fiscal_quarter,
                d.source_url,
                d.as_of_date,
                d.metadata_json
            FROM kr_corporate_disclosures d
            INNER JOIN (
                SELECT corp_code, stock_code
                FROM kr_top50_universe_snapshot
                WHERE market = %s
                  AND snapshot_date = (
                      SELECT MAX(snapshot_date)
                      FROM kr_top50_universe_snapshot
                      WHERE market = %s
                  )
                  AND rank_position <= %s
            ) s
                ON s.corp_code = d.corp_code
            WHERE d.rcept_dt BETWEEN %s AND %s
            ORDER BY d.rcept_dt DESC, d.rcept_no DESC
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                query,
                (resolved_market, resolved_market, resolved_top_limit, start_date, end_date),
            )
            rows = cursor.fetchall() or []

        normalized: List[Dict[str, Any]] = []
        for row in rows:
            event = self.build_kr_standard_event(row)
            if event is not None:
                normalized.append(event)
        return normalized

    def load_us_tier1_rows(
        self,
        *,
        start_date: date,
        end_date: date,
        market: str = "US",
        top_limit: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
        include_expected: bool = True,
    ) -> List[Dict[str, Any]]:
        resolved_market = str(market or "US").strip().upper() or "US"
        resolved_top_limit = max(int(top_limit), 1)
        expected_filter = "" if include_expected else "AND e.event_status <> 'expected'"
        query = f"""
            SELECT
                e.symbol,
                e.cik,
                e.event_date,
                e.event_status,
                e.event_type,
                e.source,
                e.source_ref,
                e.filed_at,
                e.report_date,
                e.as_of_date,
                e.metadata_json
            FROM us_corporate_earnings_events e
            INNER JOIN (
                SELECT symbol
                FROM us_top50_universe_snapshot
                WHERE market = %s
                  AND snapshot_date = (
                      SELECT MAX(snapshot_date)
                      FROM us_top50_universe_snapshot
                      WHERE market = %s
                  )
                  AND rank_position <= %s
            ) s
                ON s.symbol = e.symbol
            WHERE e.event_date BETWEEN %s AND %s
              {expected_filter}
            ORDER BY e.event_date DESC, e.symbol ASC
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                query,
                (resolved_market, resolved_market, resolved_top_limit, start_date, end_date),
            )
            rows = cursor.fetchall() or []

        normalized: List[Dict[str, Any]] = []
        for row in rows:
            event = self.build_us_standard_event(row)
            if event is not None:
                normalized.append(event)
        return normalized

    def load_us_top_symbols(
        self,
        *,
        market: str = "US",
        top_limit: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
    ) -> List[str]:
        resolved_market = str(market or "US").strip().upper() or "US"
        resolved_top_limit = max(int(top_limit), 1)
        query = """
            SELECT symbol
            FROM us_top50_universe_snapshot
            WHERE market = %s
              AND snapshot_date = (
                  SELECT MAX(snapshot_date)
                  FROM us_top50_universe_snapshot
                  WHERE market = %s
              )
              AND rank_position <= %s
            ORDER BY rank_position ASC
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (resolved_market, resolved_market, resolved_top_limit))
            rows = cursor.fetchall() or []
        symbols: List[str] = []
        for row in rows:
            symbol = _normalize_symbol(row.get("symbol"))
            if symbol:
                symbols.append(symbol)
        return list(dict.fromkeys(symbols))

    def fetch_us_yfinance_news_rows(
        self,
        *,
        symbols: Sequence[str],
        start_date: date,
        end_date: date,
        as_of_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        try:
            import yfinance as yf
        except Exception:
            return []

        resolved_as_of = as_of_date or end_date
        rows: List[Dict[str, Any]] = []
        seen_keys = set()
        for symbol in symbols:
            normalized_symbol = _normalize_symbol(symbol)
            if not normalized_symbol:
                continue
            news_items = self._run_with_source_retry(
                operation=lambda: list(getattr(yf.Ticker(normalized_symbol), "news", []) or []),
                source_key="us_yfinance_news_fetch",
                country_code="US",
                event_type="yfinance_news",
                payload={"symbol": normalized_symbol},
            )
            if news_items is None:
                continue
            for item in news_items:
                if not isinstance(item, dict):
                    continue
                row = self._extract_yfinance_news_item(
                    item=item,
                    symbol=normalized_symbol,
                    start_date=start_date,
                    end_date=end_date,
                    as_of_date=resolved_as_of,
                )
                if row is None:
                    continue
                dedupe_key = (row.get("symbol"), row.get("source_ref"), row.get("event_date"))
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                rows.append(row)
        return rows

    def dedupe_similar_news_rows(
        self,
        rows: Sequence[Dict[str, Any]],
        *,
        similarity_threshold: float = 0.95,
    ) -> tuple[List[Dict[str, Any]], int]:
        if not rows:
            return [], 0
        threshold = min(max(float(similarity_threshold), 0.0), 1.0)

        grouped: Dict[tuple, List[Dict[str, Any]]] = {}
        for row in rows:
            key = (
                row.get("country_code"),
                row.get("symbol"),
                row.get("event_date"),
                row.get("event_type"),
            )
            grouped.setdefault(key, []).append(row)

        kept_rows: List[Dict[str, Any]] = []
        dropped_count = 0
        for _group_key, group_rows in grouped.items():
            accepted_signatures: List[Dict[str, str]] = []
            for row in group_rows:
                payload = _load_json(row.get("payload_json"))
                title_text = _normalize_similarity_text(row.get("title"))
                summary_text = _normalize_similarity_text(payload.get("summary"))
                combined_text = " ".join(value for value in [title_text, summary_text] if value).strip()
                url_text = _normalize_similarity_text(row.get("source_url"))

                is_duplicate = False
                for signature in accepted_signatures:
                    prev_url = signature.get("url") or ""
                    prev_title = signature.get("title") or ""
                    prev_text = signature.get("text") or ""
                    if url_text and prev_url and url_text == prev_url:
                        is_duplicate = True
                        break
                    if title_text and prev_title and title_text == prev_title:
                        is_duplicate = True
                        break
                    if combined_text and prev_text:
                        ratio = SequenceMatcher(None, combined_text, prev_text).ratio()
                        if ratio >= threshold:
                            is_duplicate = True
                            break

                if is_duplicate:
                    dropped_count += 1
                    continue

                kept_rows.append(row)
                accepted_signatures.append(
                    {
                        "url": url_text,
                        "title": title_text,
                        "text": combined_text,
                    }
                )
        return kept_rows, dropped_count

    def upsert_standard_events(self, rows: Sequence[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.ensure_tables()
        query = """
            INSERT INTO corporate_event_feed (
                country_code,
                symbol,
                corp_code,
                cik,
                event_date,
                effective_date,
                event_type,
                event_status,
                source,
                source_url,
                source_ref,
                title,
                payload_json,
                as_of_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                corp_code = VALUES(corp_code),
                cik = VALUES(cik),
                effective_date = VALUES(effective_date),
                source_url = VALUES(source_url),
                title = VALUES(title),
                payload_json = VALUES(payload_json),
                as_of_date = VALUES(as_of_date),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [
            (
                row.get("country_code"),
                row.get("symbol"),
                row.get("corp_code"),
                row.get("cik"),
                row.get("event_date"),
                row.get("effective_date"),
                row.get("event_type"),
                row.get("event_status"),
                row.get("source"),
                row.get("source_url"),
                row.get("source_ref") or "",
                row.get("title"),
                row.get("payload_json"),
                row.get("as_of_date"),
            )
            for row in rows
            if row.get("symbol") and row.get("event_type")
        ]
        if not payload:
            return 0
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            return int(cursor.rowcount or 0)

    def sync_tier1_events(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        lookback_days: int = 30,
        kr_market: str = "KOSPI",
        kr_top_limit: int = DEFAULT_EXPECTATION_FEED_TOP_CORP_COUNT,
        us_market: str = "US",
        us_top_limit: int = DEFAULT_US_EARNINGS_MAX_SYMBOL_COUNT,
        include_us_expected: bool = True,
        include_us_news: bool = True,
        include_kr_ir_news: bool = True,
        kr_ir_feed_urls: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        self.ensure_tables()
        self._last_run_dlq_count = 0
        self._last_run_retry_failure_count = 0
        resolved_end_date = end_date or date.today()
        resolved_lookback_days = max(int(lookback_days), 1)
        resolved_start_date = start_date or (resolved_end_date - timedelta(days=resolved_lookback_days - 1))

        kr_rows = self.load_kr_tier1_rows(
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            market=kr_market,
            top_limit=kr_top_limit,
        )
        kr_ir_news_rows: List[Dict[str, Any]] = []
        kr_ir_news_deduped_count = 0
        if include_kr_ir_news:
            kr_ir_news_rows = self.fetch_kr_ir_news_rows(
                start_date=resolved_start_date,
                end_date=resolved_end_date,
                market=kr_market,
                top_limit=kr_top_limit,
                as_of_date=resolved_end_date,
                feed_urls=kr_ir_feed_urls,
            )
            kr_ir_news_rows, kr_ir_news_deduped_count = self.dedupe_similar_news_rows(
                kr_ir_news_rows,
                similarity_threshold=0.95,
            )
        us_rows = self.load_us_tier1_rows(
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            market=us_market,
            top_limit=us_top_limit,
            include_expected=include_us_expected,
        )
        us_news_rows: List[Dict[str, Any]] = []
        us_news_deduped_count = 0
        if include_us_news:
            us_symbols = self.load_us_top_symbols(market=us_market, top_limit=us_top_limit)
            us_news_rows = self.fetch_us_yfinance_news_rows(
                symbols=us_symbols,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
                as_of_date=resolved_end_date,
            )
            us_news_rows, us_news_deduped_count = self.dedupe_similar_news_rows(
                us_news_rows,
                similarity_threshold=0.95,
            )

        all_rows = list(kr_rows) + list(kr_ir_news_rows) + list(us_rows) + list(us_news_rows)
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for row in all_rows:
            key = (
                row.get("country_code"),
                row.get("symbol"),
                row.get("event_date"),
                row.get("event_type"),
                row.get("source"),
                row.get("source_ref") or "",
                row.get("event_status"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)

        affected = self.upsert_standard_events(deduped)
        category_counts: Dict[str, int] = {}
        for row in deduped:
            category = self.classify_event_category(
                country_code=str(row.get("country_code") or ""),
                event_type=str(row.get("event_type") or ""),
                source=str(row.get("source") or ""),
            )
            category_counts[category] = int(category_counts.get(category, 0)) + 1
        return {
            "start_date": resolved_start_date.isoformat(),
            "end_date": resolved_end_date.isoformat(),
            "lookback_days": resolved_lookback_days,
            "kr_event_count": len(kr_rows),
            "kr_ir_news_event_count": len(kr_ir_news_rows),
            "kr_ir_news_deduped_count": int(kr_ir_news_deduped_count),
            "us_event_count": len(us_rows),
            "us_news_event_count": len(us_news_rows),
            "us_news_deduped_count": int(us_news_deduped_count),
            "normalized_rows": len(deduped),
            "event_category_counts": category_counts,
            "db_affected": int(affected),
            "include_us_expected": bool(include_us_expected),
            "include_us_news": bool(include_us_news),
            "include_kr_ir_news": bool(include_kr_ir_news),
            "kr_ir_feed_url_count": len(self._resolve_kr_ir_feed_urls(kr_ir_feed_urls)),
            "retry_failure_count": int(self._last_run_retry_failure_count),
            "dlq_recorded_count": int(self._last_run_dlq_count),
            "status": "ok",
        }


_corporate_event_collector_singleton: Optional[CorporateEventCollector] = None


def get_corporate_event_collector() -> CorporateEventCollector:
    global _corporate_event_collector_singleton
    if _corporate_event_collector_singleton is None:
        _corporate_event_collector_singleton = CorporateEventCollector()
    return _corporate_event_collector_singleton
