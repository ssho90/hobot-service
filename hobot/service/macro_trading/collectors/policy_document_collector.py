"""
정책기관 공식 문서 수집기
- Fed/BOK RSS 기반 정책 문서를 수집해 economic_news 테이블에 저장한다.
- Phase 3 요구 시간 필드(published_at/release_date/effective_date/observed_at)를 강제 저장한다.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

import requests

from service.database.db import get_db_connection

logger = logging.getLogger(__name__)


class PolicyDocumentCollectorError(Exception):
    """정책 문서 수집기 오류"""


@dataclass(frozen=True)
class PolicyFeedSource:
    key: str
    name: str
    country: str
    country_ko: str
    category: str
    category_ko: str
    feed_url: str
    source: str = "Policy RSS"
    source_type: str = "policy_document"


FED_POLICY_RSS_URL = os.getenv(
    "FED_POLICY_RSS_URL",
    "https://www.federalreserve.gov/feeds/press_monetary.xml",
)
BOK_POLICY_RSS_URL = os.getenv(
    "BOK_POLICY_RSS_URL",
    "https://www.bok.or.kr/portal/bbs/B0000559/news.rss?menuNo=200690",
)
MOLIT_HOUSING_POLICY_RSS_URL = os.getenv("MOLIT_HOUSING_POLICY_RSS_URL", "").strip()
KREB_HOUSING_POLICY_RSS_URL = os.getenv("KREB_HOUSING_POLICY_RSS_URL", "").strip()
KHF_HOUSING_POLICY_RSS_URL = os.getenv("KHF_HOUSING_POLICY_RSS_URL", "").strip()

DEFAULT_POLICY_FEED_SOURCES: Tuple[PolicyFeedSource, ...] = (
    PolicyFeedSource(
        key="fed_policy",
        name="Federal Reserve Policy Releases",
        country="United States",
        country_ko="미국",
        category="Monetary Policy",
        category_ko="통화정책",
        feed_url=FED_POLICY_RSS_URL,
        source="Federal Reserve RSS",
    ),
    PolicyFeedSource(
        key="bok_policy",
        name="Bank of Korea Policy Releases",
        country="South Korea",
        country_ko="대한민국",
        category="Monetary Policy",
        category_ko="통화정책",
        feed_url=BOK_POLICY_RSS_URL,
        source="Bank of Korea RSS",
    ),
    PolicyFeedSource(
        key="molit_housing_policy",
        name="MOLIT Housing Policy Releases",
        country="South Korea",
        country_ko="대한민국",
        category="Housing Policy",
        category_ko="주택정책",
        feed_url=MOLIT_HOUSING_POLICY_RSS_URL,
        source="MOLIT RSS",
        source_type="housing_policy_document",
    ),
    PolicyFeedSource(
        key="kreb_housing_policy",
        name="KREB Housing Market Releases",
        country="South Korea",
        country_ko="대한민국",
        category="Housing Market Policy",
        category_ko="부동산시장정책",
        feed_url=KREB_HOUSING_POLICY_RSS_URL,
        source="KREB RSS",
        source_type="housing_policy_document",
    ),
    PolicyFeedSource(
        key="khf_housing_policy",
        name="KHF Housing Finance Releases",
        country="South Korea",
        country_ko="대한민국",
        category="Housing Finance Policy",
        category_ko="주택금융정책",
        feed_url=KHF_HOUSING_POLICY_RSS_URL,
        source="KHF RSS",
        source_type="housing_policy_document",
    ),
)


class PolicyDocumentCollector:
    def __init__(self, timeout_seconds: int = 20):
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

    def fetch_feed_xml(self, url: str) -> str:
        if not str(url or "").strip():
            raise PolicyDocumentCollectorError("feed url is empty")
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _extract_text(parent: Optional[ET.Element], tag_names: Sequence[str]) -> Optional[str]:
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
    def _extract_link_from_atom_entry(entry: ET.Element) -> Optional[str]:
        for link_node in entry.findall("{*}link"):
            href = str(link_node.attrib.get("href") or "").strip()
            rel = str(link_node.attrib.get("rel") or "alternate").strip().lower()
            if href and rel == "alternate":
                return href
            if href:
                return href
        return None

    @staticmethod
    def parse_datetime(value: Optional[str]) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except Exception:
            pass
        try:
            # ISO 문자열 대응 (예: 2026-02-18T08:30:00Z)
            normalized = text.replace("Z", "+00:00")
            parsed_iso = datetime.fromisoformat(normalized)
            if parsed_iso.tzinfo is not None:
                parsed_iso = parsed_iso.astimezone().replace(tzinfo=None)
            return parsed_iso
        except Exception:
            return None

    def parse_feed_entries(self, xml_text: str) -> List[Dict[str, Any]]:
        if not xml_text:
            return []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise PolicyDocumentCollectorError(f"invalid xml payload: {exc}") from exc

        entries: List[Dict[str, Any]] = []

        # RSS: /rss/channel/item
        rss_items = root.findall("./channel/item")
        for item in rss_items:
            title = self._extract_text(item, ["title"])
            link = self._extract_text(item, ["link"])
            description = self._extract_text(item, ["description"])
            published_raw = self._extract_text(item, ["pubDate", "dc:date"])
            entries.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "published_at": self.parse_datetime(published_raw),
                }
            )

        # Atom: /feed/entry
        atom_entries = root.findall("./{*}entry")
        for entry in atom_entries:
            title = self._extract_text(entry, ["{*}title"])
            link = self._extract_link_from_atom_entry(entry)
            description = self._extract_text(entry, ["{*}summary", "{*}content"])
            published_raw = self._extract_text(entry, ["{*}published", "{*}updated"])
            entries.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "published_at": self.parse_datetime(published_raw),
                }
            )

        normalized: List[Dict[str, Any]] = []
        seen: set[Tuple[str, str]] = set()
        for item in entries:
            title = str(item.get("title") or "").strip()
            link = str(item.get("link") or "").strip()
            if not title:
                continue
            dedupe_key = (title.lower(), link.lower())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized.append(item)
        return normalized

    @staticmethod
    def build_document_row(
        item: Dict[str, Any],
        source: PolicyFeedSource,
        *,
        observed_at: datetime,
    ) -> Dict[str, Any]:
        published_at = item.get("published_at")
        if not isinstance(published_at, datetime):
            published_at = observed_at

        return {
            "title": str(item.get("title") or "").strip(),
            "link": str(item.get("link") or "").strip() or None,
            "country": source.country,
            "country_ko": source.country_ko,
            "category": source.category,
            "category_ko": source.category_ko,
            "description": str(item.get("description") or "").strip() or None,
            "published_at": published_at,
            "release_date": published_at,
            "effective_date": published_at,
            "observed_at": observed_at,
            "source": source.source,
            "source_type": source.source_type,
        }

    def save_to_db(self, rows: Sequence[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        query = """
            INSERT INTO economic_news (
                title,
                link,
                country,
                category,
                description,
                published_at,
                source,
                country_ko,
                category_ko,
                release_date,
                effective_date,
                observed_at,
                source_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                country = VALUES(country),
                category = VALUES(category),
                description = COALESCE(VALUES(description), description),
                published_at = VALUES(published_at),
                source = VALUES(source),
                country_ko = VALUES(country_ko),
                category_ko = VALUES(category_ko),
                release_date = VALUES(release_date),
                effective_date = VALUES(effective_date),
                observed_at = VALUES(observed_at),
                source_type = VALUES(source_type),
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [
            (
                row.get("title"),
                row.get("link"),
                row.get("country"),
                row.get("category"),
                row.get("description"),
                row.get("published_at"),
                row.get("source"),
                row.get("country_ko"),
                row.get("category_ko"),
                row.get("release_date"),
                row.get("effective_date"),
                row.get("observed_at"),
                row.get("source_type"),
            )
            for row in rows
            if row.get("title")
        ]
        if not payload:
            return 0

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            return int(cursor.rowcount or 0)

    def collect_recent_documents(
        self,
        *,
        hours: int = 72,
        sources: Optional[Sequence[PolicyFeedSource]] = None,
    ) -> Dict[str, Any]:
        resolved_hours = max(int(hours), 1)
        observed_at = datetime.now()
        cutoff_at = observed_at - timedelta(hours=resolved_hours)
        resolved_sources = list(sources or DEFAULT_POLICY_FEED_SOURCES)

        source_results: List[Dict[str, Any]] = []
        normalized_rows: List[Dict[str, Any]] = []
        failed_sources = 0

        for source in resolved_sources:
            feed_url = str(source.feed_url or "").strip()
            if not feed_url:
                source_results.append(
                    {
                        "key": source.key,
                        "status": "skipped",
                        "reason": "empty_feed_url",
                        "fetched_rows": 0,
                        "normalized_rows": 0,
                    }
                )
                continue
            try:
                xml_text = self.fetch_feed_xml(feed_url)
                entries = self.parse_feed_entries(xml_text)
                rows = [
                    self.build_document_row(entry, source, observed_at=observed_at)
                    for entry in entries
                ]
                recent_rows = [
                    row
                    for row in rows
                    if isinstance(row.get("published_at"), datetime) and row["published_at"] >= cutoff_at
                ]
                normalized_rows.extend(recent_rows)
                source_results.append(
                    {
                        "key": source.key,
                        "status": "ok",
                        "fetched_rows": len(entries),
                        "normalized_rows": len(recent_rows),
                    }
                )
            except Exception as exc:
                failed_sources += 1
                logger.warning("[PolicyDocumentCollector] source=%s failed: %s", source.key, exc)
                source_results.append(
                    {
                        "key": source.key,
                        "status": "failed",
                        "error": str(exc),
                        "fetched_rows": 0,
                        "normalized_rows": 0,
                    }
                )

        # title+link 기준 중복 제거
        deduped: List[Dict[str, Any]] = []
        seen: set[Tuple[str, str]] = set()
        for row in normalized_rows:
            title = str(row.get("title") or "").strip().lower()
            link = str(row.get("link") or "").strip().lower()
            key = (title, link)
            if not title or key in seen:
                continue
            seen.add(key)
            deduped.append(row)

        affected = self.save_to_db(deduped)
        status = "ok" if failed_sources == 0 else ("partial" if deduped else "failed")
        return {
            "status": status,
            "hours": resolved_hours,
            "source_count": len(resolved_sources),
            "failed_source_count": failed_sources,
            "normalized_rows": len(deduped),
            "db_affected": affected,
            "source_results": source_results,
            "observed_at": observed_at.isoformat(),
        }


_policy_document_collector_singleton: Optional[PolicyDocumentCollector] = None


def get_policy_document_collector() -> PolicyDocumentCollector:
    global _policy_document_collector_singleton
    if _policy_document_collector_singleton is None:
        _policy_document_collector_singleton = PolicyDocumentCollector()
    return _policy_document_collector_singleton
