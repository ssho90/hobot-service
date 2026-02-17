"""
Phase D-1: Question -> subgraph context API.
"""

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..neo4j_client import get_neo4j_client
from ..normalization.country_mapping import get_country_name, normalize_country

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph/rag", tags=["graph-rag"])

TIME_RANGE_TO_DAYS: Dict[str, int] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
}

THEME_KEYWORDS: Dict[str, List[str]] = {
    "inflation": ["inflation", "인플레이션", "물가", "cpi", "ppi"],
    "rates": ["rates", "rate", "금리", "yield", "fomc", "국채"],
    "growth": ["growth", "gdp", "경기", "성장", "recession", "침체"],
    "labor": ["labor", "employment", "jobs", "고용", "실업", "임금"],
    "liquidity": ["liquidity", "유동성", "netliq", "walcl", "wtregen", "qe", "qt"],
}

THEME_DISPLAY_NAMES: Dict[str, str] = {
    "inflation": "Inflation",
    "rates": "Rates",
    "growth": "Growth",
    "labor": "Labor",
    "liquidity": "Liquidity",
}

QUESTION_TERM_STOPWORDS: Set[str] = {
    "recent",
    "latest",
    "today",
    "what",
    "which",
    "who",
    "how",
    "when",
    "where",
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
}

SUPPORTED_QA_COUNTRY_CODES: Set[str] = {"US", "KR"}


class GraphRagContextRequest(BaseModel):
    question: str = Field(..., min_length=3)
    time_range: str = Field(default="30d")
    country: Optional[str] = None
    country_code: Optional[str] = None
    as_of_date: Optional[date] = None
    top_k_events: int = Field(default=25, ge=5, le=100)
    top_k_documents: int = Field(default=40, ge=5, le=200)
    top_k_stories: int = Field(default=20, ge=5, le=100)
    top_k_evidences: int = Field(default=40, ge=5, le=200)


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphLink(BaseModel):
    source: str
    target: str
    type: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphEvidence(BaseModel):
    evidence_id: Optional[str] = None
    text: str
    doc_id: Optional[str] = None
    doc_url: Optional[str] = None
    doc_title: Optional[str] = None
    doc_category: Optional[str] = None
    published_at: Optional[str] = None
    support_labels: List[str] = Field(default_factory=list)
    event_id: Optional[str] = None
    claim_id: Optional[str] = None


class GraphRagContextResponse(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]
    evidences: List[GraphEvidence]
    suggested_queries: List[str]
    meta: Dict[str, Any] = Field(default_factory=dict)


def parse_time_range_days(time_range: str) -> int:
    value = (time_range or "").strip().lower()
    if value not in TIME_RANGE_TO_DAYS:
        allowed = ", ".join(TIME_RANGE_TO_DAYS.keys())
        raise ValueError(f"time_range must be one of: {allowed}")
    return TIME_RANGE_TO_DAYS[value]


def _to_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_json_value(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_to_json_value(inner) for inner in value]
    if isinstance(value, tuple):
        return [_to_json_value(inner) for inner in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _normalize_text(value: Optional[str]) -> str:
    return (value or "").strip()


class GraphRagContextBuilder:
    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    @staticmethod
    def _resolve_country_filter(
        country: Optional[str],
        country_code: Optional[str],
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        country 입력을 (raw_country, normalized_country_name, normalized_country_code)로 정규화

        - raw_country: 요청 원문(legacy country 필드 호환)
        - normalized_country_name: ISO 코드 기반 표준 국가명
        - normalized_country_code: ISO 3166-1 alpha-2
        """
        raw_country = _normalize_text(country) or None
        raw_country_code = _normalize_text(country_code).upper() if country_code else None

        normalized_code = raw_country_code or normalize_country(raw_country or "")
        normalized_name = get_country_name(normalized_code) if normalized_code else None
        if normalized_name and normalized_name == normalized_code:
            normalized_name = None

        return raw_country, normalized_name, normalized_code

    @staticmethod
    def _validate_scope_country(
        request_country: Optional[str],
        request_country_code: Optional[str],
        normalized_country_code: Optional[str],
    ) -> None:
        has_scope_input = bool(_normalize_text(request_country) or _normalize_text(request_country_code))
        if not has_scope_input:
            return

        if not normalized_country_code:
            allowed = ", ".join(sorted(SUPPORTED_QA_COUNTRY_CODES))
            raise ValueError(f"country scope must resolve to one of: {allowed}")

        if normalized_country_code not in SUPPORTED_QA_COUNTRY_CODES:
            allowed = ", ".join(sorted(SUPPORTED_QA_COUNTRY_CODES))
            raise ValueError(f"country_code '{normalized_country_code}' is not supported in Phase 1 scope ({allowed})")

    @staticmethod
    def _resolve_row_country_code(row: Dict[str, Any]) -> Optional[str]:
        country_code = _normalize_text(str(row.get("country_code") or "")).upper()
        if country_code:
            return country_code

        raw_country = _normalize_text(str(row.get("country") or ""))
        if not raw_country:
            return None
        normalized = normalize_country(raw_country)
        return normalized.upper() if normalized else None

    def _build_scope_warning_summary(
        self,
        *,
        events: List[Dict[str, Any]],
        documents: List[Dict[str, Any]],
        requested_country_code: Optional[str],
    ) -> Dict[str, Any]:
        counts = {
            "missing_country_code": 0,
            "out_of_scope_country_code": 0,
            "requested_country_mismatch": 0,
        }
        samples: List[Dict[str, Any]] = []

        def add_sample(kind: str, node_type: str, row: Dict[str, Any], resolved_code: Optional[str]) -> None:
            if len(samples) >= 10:
                return
            samples.append(
                {
                    "warning_type": kind,
                    "node_type": node_type,
                    "id": row.get("event_id") or row.get("doc_id"),
                    "country": row.get("country"),
                    "country_code": row.get("country_code"),
                    "resolved_country_code": resolved_code,
                }
            )

        for node_type, rows in (("Event", events), ("Document", documents)):
            for row in rows:
                resolved_code = self._resolve_row_country_code(row)
                if not resolved_code:
                    counts["missing_country_code"] += 1
                    add_sample("missing_country_code", node_type, row, resolved_code)
                    continue
                if resolved_code not in SUPPORTED_QA_COUNTRY_CODES:
                    counts["out_of_scope_country_code"] += 1
                    add_sample("out_of_scope_country_code", node_type, row, resolved_code)
                if requested_country_code and resolved_code != requested_country_code:
                    counts["requested_country_mismatch"] += 1
                    add_sample("requested_country_mismatch", node_type, row, resolved_code)

        messages: List[str] = []
        if counts["missing_country_code"] > 0:
            messages.append(f"country_code 누락 데이터 {counts['missing_country_code']}건")
        if counts["out_of_scope_country_code"] > 0:
            messages.append(f"US/KR 범위 외 데이터 {counts['out_of_scope_country_code']}건")
        if requested_country_code and counts["requested_country_mismatch"] > 0:
            messages.append(
                f"요청 국가({requested_country_code})와 불일치한 데이터 {counts['requested_country_mismatch']}건"
            )

        has_violation = any(value > 0 for value in counts.values())
        return {
            "has_violation": has_violation,
            "counts": counts,
            "messages": messages,
            "samples": samples,
        }

    def _resolve_theme_candidates(
        self,
        question: str,
        start_iso: str,
        end_iso: str,
        country: Optional[str],
        country_name: Optional[str],
        country_code: Optional[str],
    ) -> List[str]:
        normalized_question = question.lower()
        matched: Set[str] = set()

        for theme_id, keywords in THEME_KEYWORDS.items():
            if any(keyword in normalized_question for keyword in keywords):
                matched.add(theme_id)

        if matched:
            return sorted(matched)

        rows = self.neo4j_client.run_read(
            """
            // phase_d_top_themes
            MATCH (d:Document)-[:ABOUT_THEME]->(t:MacroTheme)
            WHERE d.published_at IS NOT NULL
              AND d.published_at >= datetime($start_iso)
              AND d.published_at <= datetime($end_iso)
              AND (
                ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL)
                OR ($country IS NOT NULL AND d.country = $country)
                OR ($country_name IS NOT NULL AND d.country = $country_name)
                OR ($country_code IS NOT NULL AND (d.country_code = $country_code OR d.country = $country_code))
              )
            RETURN t.theme_id AS theme_id, count(*) AS doc_count
            ORDER BY doc_count DESC
            LIMIT 3
            """,
            {
                "start_iso": start_iso,
                "end_iso": end_iso,
                "country": country,
                "country_name": country_name,
                "country_code": country_code,
            },
        )
        return [row["theme_id"] for row in rows if row.get("theme_id")]

    def _resolve_indicator_candidates(self, question: str) -> List[str]:
        candidates: Set[str] = set()

        for token in re.findall(r"\b[A-Z][A-Z0-9]{2,10}\b", question):
            candidates.add(token)

        tokens = sorted(set(re.findall(r"[A-Za-z]{3,}", question.lower())))
        if tokens:
            rows = self.neo4j_client.run_read(
                """
                // phase_d_indicator_candidates
                MATCH (i:EconomicIndicator)
                WHERE any(token IN $tokens WHERE
                    toLower(i.indicator_code) CONTAINS token
                    OR toLower(coalesce(i.name, '')) CONTAINS token
                )
                RETURN i.indicator_code AS indicator_code
                ORDER BY i.indicator_code
                LIMIT 10
                """,
                {"tokens": tokens[:12]},
            )
            for row in rows:
                indicator_code = row.get("indicator_code")
                if indicator_code:
                    candidates.add(indicator_code)

        return sorted(candidates)

    @staticmethod
    def _extract_question_search_terms(question: str) -> List[str]:
        lowered = (question or "").lower()
        ascii_tokens = re.findall(r"[a-z][a-z0-9\-']{2,}", lowered)
        ascii_tokens = [token for token in ascii_tokens if token not in QUESTION_TERM_STOPWORDS]

        terms: Set[str] = set(ascii_tokens)
        for left, right in zip(ascii_tokens, ascii_tokens[1:]):
            terms.add(f"{left} {right}")

        if len(terms) > 20:
            return sorted(terms)[:20]
        return sorted(terms)

    def _fetch_events(
        self,
        start_iso: str,
        end_iso: str,
        country: Optional[str],
        country_name: Optional[str],
        country_code: Optional[str],
        theme_filter: List[str],
        indicator_filter: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        rows = self.neo4j_client.run_read(
            """
            // phase_d_events
            MATCH (e:Event)
            WHERE e.event_time IS NOT NULL
              AND e.event_time >= datetime($start_iso)
              AND e.event_time <= datetime($end_iso)
              AND (
                ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL)
                OR ($country IS NOT NULL AND e.country = $country)
                OR ($country_name IS NOT NULL AND e.country = $country_name)
                OR ($country_code IS NOT NULL AND (e.country_code = $country_code OR e.country = $country_code))
              )
            OPTIONAL MATCH (e)-[:ABOUT_THEME]->(t:MacroTheme)
            OPTIONAL MATCH (e)-[:AFFECTS]->(i:EconomicIndicator)
            WITH e,
                 collect(DISTINCT t.theme_id) AS theme_ids,
                 collect(DISTINCT i.indicator_code) AS indicator_codes
            WHERE (
                (size($theme_filter) = 0 AND size($indicator_filter) = 0)
                OR any(theme_id IN theme_ids WHERE theme_id IN $theme_filter)
                OR any(indicator_code IN indicator_codes WHERE indicator_code IN $indicator_filter)
            )
            RETURN e.event_id AS event_id,
                   e.type AS event_type,
                   e.summary AS summary,
                   e.event_time AS event_time,
                   e.country AS country,
                   e.country_code AS country_code,
                   theme_ids,
                   indicator_codes
            ORDER BY e.event_time DESC
            LIMIT $limit
            """,
            {
                "start_iso": start_iso,
                "end_iso": end_iso,
                "country": country,
                "country_name": country_name,
                "country_code": country_code,
                "theme_filter": theme_filter,
                "indicator_filter": indicator_filter,
                "limit": limit,
            },
        )

        normalized_rows: List[Dict[str, Any]] = []
        for row in rows:
            normalized_rows.append(
                {
                    **row,
                    "theme_ids": [item for item in (row.get("theme_ids") or []) if item],
                    "indicator_codes": [item for item in (row.get("indicator_codes") or []) if item],
                }
            )
        return normalized_rows

    def _fetch_documents(
        self,
        start_iso: str,
        end_iso: str,
        country: Optional[str],
        country_name: Optional[str],
        country_code: Optional[str],
        theme_filter: List[str],
        event_filter: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        rows = self.neo4j_client.run_read(
            """
            // phase_d_documents
            MATCH (d:Document)
            WHERE d.published_at IS NOT NULL
              AND d.published_at >= datetime($start_iso)
              AND d.published_at <= datetime($end_iso)
              AND (
                ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL)
                OR ($country IS NOT NULL AND d.country = $country)
                OR ($country_name IS NOT NULL AND d.country = $country_name)
                OR ($country_code IS NOT NULL AND (d.country_code = $country_code OR d.country = $country_code))
              )
            OPTIONAL MATCH (d)-[:MENTIONS]->(e:Event)
            OPTIONAL MATCH (d)-[:ABOUT_THEME]->(t:MacroTheme)
            WITH d,
                 collect(DISTINCT e.event_id) AS event_ids,
                 collect(DISTINCT t.theme_id) AS theme_ids
            WHERE (
                (size($theme_filter) = 0 AND size($event_filter) = 0)
                OR any(theme_id IN theme_ids WHERE theme_id IN $theme_filter)
                OR any(event_id IN event_ids WHERE event_id IN $event_filter)
            )
            RETURN d.doc_id AS doc_id,
                   d.title AS title,
                   coalesce(d.url, d.link) AS url,
                   d.source AS source,
                   d.country AS country,
                   d.country_code AS country_code,
                   d.category AS category,
                   d.published_at AS published_at,
                   event_ids,
                   theme_ids
            ORDER BY d.published_at DESC
            LIMIT $limit
            """,
            {
                "start_iso": start_iso,
                "end_iso": end_iso,
                "country": country,
                "country_name": country_name,
                "country_code": country_code,
                "theme_filter": theme_filter,
                "event_filter": event_filter,
                "limit": limit,
            },
        )

        normalized_rows: List[Dict[str, Any]] = []
        for row in rows:
            normalized_rows.append(
                {
                    **row,
                    "event_ids": [item for item in (row.get("event_ids") or []) if item],
                    "theme_ids": [item for item in (row.get("theme_ids") or []) if item],
                }
            )
        return normalized_rows

    def _fetch_documents_by_fulltext(
        self,
        start_iso: str,
        end_iso: str,
        country: Optional[str],
        country_name: Optional[str],
        country_code: Optional[str],
        question: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        Full-text Index 기반 문서 검색 (BM25 랭킹 적용)
        - 기존 CONTAINS 스캔 대비 속도/정확도 대폭 개선
        - 한글/영어 혼용 검색 지원 (cjk analyzer)
        """
        if not question or len(question.strip()) < 2:
            return []

        # Lucene 쿼리 문법으로 변환: 공백으로 구분된 단어들을 OR로 연결
        # 특수문자 이스케이프 (Lucene reserved: + - && || ! ( ) { } [ ] ^ " ~ * ? : \ /)
        escaped_question = re.sub(r'([+\-&|!(){}[\]^"~*?:\\/])', r'\\\1', question)
        search_query = " OR ".join(escaped_question.split())

        try:
            rows = self.neo4j_client.run_read(
                """
                // phase_d_documents_by_fulltext (BM25 랭킹)
                CALL db.index.fulltext.queryNodes('document_fulltext', $search_query)
                YIELD node AS d, score
                WHERE d.published_at IS NOT NULL
                  AND d.published_at >= datetime($start_iso)
                  AND d.published_at <= datetime($end_iso)
                  AND (
                    ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL)
                    OR ($country IS NOT NULL AND d.country = $country)
                    OR ($country_name IS NOT NULL AND d.country = $country_name)
                    OR ($country_code IS NOT NULL AND (d.country_code = $country_code OR d.country = $country_code))
                  )
                WITH d, score
                ORDER BY score DESC, d.published_at DESC
                LIMIT $limit
                OPTIONAL MATCH (d)-[:MENTIONS]->(e:Event)
                OPTIONAL MATCH (d)-[:ABOUT_THEME]->(t:MacroTheme)
                RETURN d.doc_id AS doc_id,
                       d.title AS title,
                       coalesce(d.url, d.link) AS url,
                       d.source AS source,
                       d.country AS country,
                       d.country_code AS country_code,
                       d.category AS category,
                       d.published_at AS published_at,
                       collect(DISTINCT e.event_id) AS event_ids,
                       collect(DISTINCT t.theme_id) AS theme_ids,
                       score AS fulltext_score
                """,
                {
                    "search_query": search_query,
                    "start_iso": start_iso,
                    "end_iso": end_iso,
                    "country": country,
                    "country_name": country_name,
                    "country_code": country_code,
                    "limit": limit * 2,  # 그래프 필터링 후 상위 N개 선택을 위해 여유분 확보
                },
            )
        except Exception as e:
            # Full-text index가 없거나 쿼리 실패 시 fallback
            logger.warning(f"Full-text search failed, falling back to CONTAINS: {e}")
            return self._fetch_documents_by_question_terms_fallback(
                start_iso,
                end_iso,
                country,
                country_name,
                country_code,
                question,
                limit,
            )

        normalized_rows: List[Dict[str, Any]] = []
        for row in rows:
            normalized_rows.append(
                {
                    **row,
                    "event_ids": [item for item in (row.get("event_ids") or []) if item],
                    "theme_ids": [item for item in (row.get("theme_ids") or []) if item],
                }
            )
        return normalized_rows[:limit]

    def _fetch_documents_by_question_terms_fallback(
        self,
        start_iso: str,
        end_iso: str,
        country: Optional[str],
        country_name: Optional[str],
        country_code: Optional[str],
        question: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Fallback: Full-text Index 미사용 시 기존 CONTAINS 방식"""
        question_terms = self._extract_question_search_terms(question)
        if not question_terms:
            return []

        rows = self.neo4j_client.run_read(
            """
            // phase_d_documents_by_question_terms (fallback)
            MATCH (d:Document)
            WHERE d.published_at IS NOT NULL
              AND d.published_at >= datetime($start_iso)
              AND d.published_at <= datetime($end_iso)
              AND (
                ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL)
                OR ($country IS NOT NULL AND d.country = $country)
                OR ($country_name IS NOT NULL AND d.country = $country_name)
                OR ($country_code IS NOT NULL AND (d.country_code = $country_code OR d.country = $country_code))
              )
            WITH d,
                 [term IN $question_terms WHERE
                    toLower(coalesce(d.title, '')) CONTAINS term
                    OR toLower(coalesce(d.description, '')) CONTAINS term
                    OR toLower(coalesce(d.description_ko, '')) CONTAINS term
                    OR toLower(coalesce(d.text, '')) CONTAINS term
                 ] AS matched_terms
            WHERE size(matched_terms) > 0
            OPTIONAL MATCH (d)-[:MENTIONS]->(e:Event)
            OPTIONAL MATCH (d)-[:ABOUT_THEME]->(t:MacroTheme)
            RETURN d.doc_id AS doc_id,
                   d.title AS title,
                   coalesce(d.url, d.link) AS url,
                   d.source AS source,
                   d.country AS country,
                   d.country_code AS country_code,
                   d.category AS category,
                   d.published_at AS published_at,
                   collect(DISTINCT e.event_id) AS event_ids,
                   collect(DISTINCT t.theme_id) AS theme_ids,
                   matched_terms
            ORDER BY size(matched_terms) DESC, d.published_at DESC
            LIMIT $limit
            """,
            {
                "start_iso": start_iso,
                "end_iso": end_iso,
                "country": country,
                "country_name": country_name,
                "country_code": country_code,
                "question_terms": question_terms,
                "limit": limit,
            },
        )

        normalized_rows: List[Dict[str, Any]] = []
        for row in rows:
            normalized_rows.append(
                {
                    **row,
                    "event_ids": [item for item in (row.get("event_ids") or []) if item],
                    "theme_ids": [item for item in (row.get("theme_ids") or []) if item],
                }
            )
        return normalized_rows

    def _fetch_stories(
        self,
        start_date: date,
        end_date: date,
        theme_filter: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        rows = self.neo4j_client.run_read(
            """
            // phase_d_stories
            MATCH (s:Story)-[:ABOUT_THEME]->(t:MacroTheme)
            WHERE s.story_date IS NOT NULL
              AND s.story_date >= date($start_date)
              AND s.story_date <= date($end_date)
              AND (size($theme_filter) = 0 OR t.theme_id IN $theme_filter)
            OPTIONAL MATCH (s)-[:CONTAINS]->(d:Document)
            RETURN s.story_id AS story_id,
                   s.title AS title,
                   s.story_date AS story_date,
                   t.theme_id AS theme_id,
                   collect(DISTINCT d.doc_id) AS doc_ids
            ORDER BY s.story_date DESC
            LIMIT $limit
            """,
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "theme_filter": theme_filter,
                "limit": limit,
            },
        )
        normalized_rows: List[Dict[str, Any]] = []
        for row in rows:
            normalized_rows.append(
                {
                    **row,
                    "doc_ids": [item for item in (row.get("doc_ids") or []) if item],
                }
            )
        return normalized_rows

    def _fetch_evidences(self, doc_ids: List[str], limit: int) -> List[Dict[str, Any]]:
        if not doc_ids:
            return []

        rows = self.neo4j_client.run_read(
            """
            // phase_d_evidences
            MATCH (d:Document)-[:HAS_EVIDENCE]->(ev:Evidence)
            WHERE d.doc_id IN $doc_ids
            OPTIONAL MATCH (ev)-[:SUPPORTS]->(target)
            RETURN ev.evidence_id AS evidence_id,
                   ev.text AS text,
                   d.doc_id AS doc_id,
                   coalesce(d.url, d.link) AS doc_url,
                   d.title AS doc_title,
                   d.category AS doc_category,
                   d.published_at AS published_at,
                   labels(target) AS support_labels,
                   target.event_id AS event_id,
                   target.claim_id AS claim_id
            ORDER BY d.published_at DESC
            LIMIT $limit
            """,
            {"doc_ids": doc_ids, "limit": limit},
        )
        return rows

    def _fetch_theme_metadata(self, theme_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not theme_ids:
            return {}
        rows = self.neo4j_client.run_read(
            """
            // phase_d_theme_meta
            MATCH (t:MacroTheme)
            WHERE t.theme_id IN $theme_ids
            RETURN t.theme_id AS theme_id,
                   t.name AS name,
                   t.description AS description
            """,
            {"theme_ids": theme_ids},
        )
        metadata: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            theme_id = row.get("theme_id")
            if not theme_id:
                continue
            metadata[theme_id] = {
                "name": row.get("name") or THEME_DISPLAY_NAMES.get(theme_id, theme_id),
                "description": row.get("description"),
            }
        return metadata

    def _fetch_indicator_metadata(self, indicator_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        if not indicator_codes:
            return {}
        rows = self.neo4j_client.run_read(
            """
            // phase_d_indicator_meta
            MATCH (i:EconomicIndicator)
            WHERE i.indicator_code IN $indicator_codes
            RETURN i.indicator_code AS indicator_code,
                   i.name AS name,
                   i.unit AS unit
            """,
            {"indicator_codes": indicator_codes},
        )
        metadata: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            indicator_code = row.get("indicator_code")
            if not indicator_code:
                continue
            metadata[indicator_code] = {
                "name": row.get("name") or indicator_code,
                "unit": row.get("unit"),
            }
        return metadata

    @staticmethod
    def _add_node(
        nodes: Dict[str, Dict[str, Any]],
        node_id: str,
        node_type: str,
        label: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not node_id:
            return
        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id,
                "type": node_type,
                "label": _normalize_text(label) or node_id,
                "properties": _to_json_value(properties or {}),
            }

    @staticmethod
    def _add_link(
        links: List[Dict[str, Any]],
        link_keys: Set[Tuple[str, str, str]],
        source: str,
        target: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not source or not target:
            return
        link_key = (source, target, rel_type)
        if link_key in link_keys:
            return
        links.append(
            {
                "source": source,
                "target": target,
                "type": rel_type,
                "properties": _to_json_value(properties or {}),
            }
        )
        link_keys.add(link_key)

    @staticmethod
    def _build_suggested_queries(theme_ids: List[str], question: str, window_days: int) -> List[str]:
        if theme_ids:
            primary_theme = theme_ids[0]
            theme_name = THEME_DISPLAY_NAMES.get(primary_theme, primary_theme)
            return [
                f"최근 {window_days}일 {theme_name} 관련 핵심 이벤트 Top 5는?",
                f"{theme_name} 테마와 함께 움직인 주요 지표는?",
                f"{theme_name} 관련 Story를 근거 문서와 함께 요약해줘.",
                f"{theme_name} 리스크가 자산배분에 주는 시사점은?",
            ]

        if "리스크" in question or "risk" in question.lower():
            return [
                f"최근 {window_days}일 리스크 상위 이벤트를 근거와 함께 보여줘.",
                "문서 근거가 많은 Story 순으로 정렬해줘.",
                "지표 변화폭이 큰 이벤트를 우선 설명해줘.",
            ]

        return [
            f"최근 {window_days}일 핵심 Macro Event Top 10은?",
            "현재 Macro Story를 테마별로 요약해줘.",
            "문서 근거가 많은 이벤트부터 설명해줘.",
        ]

    def build_context(self, request: GraphRagContextRequest) -> GraphRagContextResponse:
        window_days = parse_time_range_days(request.time_range)
        end_date = request.as_of_date or date.today()
        start_date = end_date - timedelta(days=window_days)
        start_iso = f"{start_date.isoformat()}T00:00:00"
        end_iso = f"{end_date.isoformat()}T23:59:59"
        country_input, country_name, country_code = self._resolve_country_filter(
            request.country,
            request.country_code,
        )
        self._validate_scope_country(
            request_country=request.country,
            request_country_code=request.country_code,
            normalized_country_code=country_code,
        )

        matched_theme_ids = self._resolve_theme_candidates(
            question=request.question,
            start_iso=start_iso,
            end_iso=end_iso,
            country=country_input,
            country_name=country_name,
            country_code=country_code,
        )
        matched_indicator_codes = self._resolve_indicator_candidates(request.question)
        question_terms = self._extract_question_search_terms(request.question)

        events = self._fetch_events(
            start_iso=start_iso,
            end_iso=end_iso,
            country=country_input,
            country_name=country_name,
            country_code=country_code,
            theme_filter=matched_theme_ids,
            indicator_filter=matched_indicator_codes,
            limit=request.top_k_events,
        )
        event_ids = [row["event_id"] for row in events if row.get("event_id")]

        documents = self._fetch_documents(
            start_iso=start_iso,
            end_iso=end_iso,
            country=country_input,
            country_name=country_name,
            country_code=country_code,
            theme_filter=matched_theme_ids,
            event_filter=event_ids,
            limit=request.top_k_documents,
        )

        # Hybrid Search: Full-text Index로 후보 문서 회수 (BM25 랭킹)
        keyword_documents = self._fetch_documents_by_fulltext(
            start_iso=start_iso,
            end_iso=end_iso,
            country=country_input,
            country_name=country_name,
            country_code=country_code,
            question=request.question,
            limit=request.top_k_documents,
        )
        fallback_documents: List[Dict[str, Any]] = []
        if question_terms and len(keyword_documents) < request.top_k_documents:
            # Full-text만으로 놓칠 수 있는 인물명/복합 키워드 문서를 보강한다.
            fallback_documents = self._fetch_documents_by_question_terms_fallback(
                start_iso=start_iso,
                end_iso=end_iso,
                country=country_input,
                country_name=country_name,
                country_code=country_code,
                question=request.question,
                limit=request.top_k_documents,
            )

        if keyword_documents or fallback_documents:
            merged_docs: Dict[str, Dict[str, Any]] = {}
            for row in fallback_documents:
                doc_id = row.get("doc_id")
                if doc_id:
                    merged_docs[doc_id] = row
            for row in keyword_documents:
                doc_id = row.get("doc_id")
                if doc_id:
                    merged_docs[doc_id] = row
            for row in documents:
                doc_id = row.get("doc_id")
                if doc_id and doc_id not in merged_docs:
                    merged_docs[doc_id] = row
            documents = list(merged_docs.values())[: request.top_k_documents]

        doc_ids = [row["doc_id"] for row in documents if row.get("doc_id")]
        scope_warnings = self._build_scope_warning_summary(
            events=events,
            documents=documents,
            requested_country_code=country_code,
        )
        if scope_warnings.get("has_violation"):
            logger.warning(
                "[GraphRAGContext] scope warning counts=%s requested_country_code=%s",
                scope_warnings.get("counts"),
                country_code,
            )

        discovered_theme_ids: Set[str] = set(matched_theme_ids)
        discovered_indicator_codes: Set[str] = set(matched_indicator_codes)
        for row in events:
            discovered_theme_ids.update(row.get("theme_ids") or [])
            discovered_indicator_codes.update(row.get("indicator_codes") or [])
        for row in documents:
            discovered_theme_ids.update(row.get("theme_ids") or [])

        stories = self._fetch_stories(
            start_date=start_date,
            end_date=end_date,
            theme_filter=sorted(discovered_theme_ids),
            limit=request.top_k_stories,
        )
        for row in stories:
            theme_id = row.get("theme_id")
            if theme_id:
                discovered_theme_ids.add(theme_id)

        theme_meta = self._fetch_theme_metadata(sorted(discovered_theme_ids))
        indicator_meta = self._fetch_indicator_metadata(sorted(discovered_indicator_codes))
        evidences = self._fetch_evidences(doc_ids=doc_ids, limit=request.top_k_evidences)

        nodes: Dict[str, Dict[str, Any]] = {}
        links: List[Dict[str, Any]] = []
        link_keys: Set[Tuple[str, str, str]] = set()

        for theme_id in sorted(discovered_theme_ids):
            theme_info = theme_meta.get(theme_id, {})
            self._add_node(
                nodes,
                node_id=f"theme:{theme_id}",
                node_type="MacroTheme",
                label=theme_info.get("name") or theme_id,
                properties={"theme_id": theme_id, **theme_info},
            )

        for indicator_code in sorted(discovered_indicator_codes):
            indicator_info = indicator_meta.get(indicator_code, {})
            self._add_node(
                nodes,
                node_id=f"indicator:{indicator_code}",
                node_type="EconomicIndicator",
                label=indicator_info.get("name") or indicator_code,
                properties={"indicator_code": indicator_code, **indicator_info},
            )

        for row in events:
            event_id = row.get("event_id")
            if not event_id:
                continue
            event_node_id = f"event:{event_id}"
            self._add_node(
                nodes,
                node_id=event_node_id,
                node_type="Event",
                label=row.get("summary") or row.get("event_type") or event_id,
                properties={
                    "event_id": event_id,
                    "event_type": row.get("event_type"),
                    "event_time": row.get("event_time"),
                    "country": row.get("country"),
                    "country_code": row.get("country_code"),
                },
            )
            for theme_id in row.get("theme_ids") or []:
                self._add_link(
                    links,
                    link_keys,
                    source=event_node_id,
                    target=f"theme:{theme_id}",
                    rel_type="ABOUT_THEME",
                )
            for indicator_code in row.get("indicator_codes") or []:
                self._add_link(
                    links,
                    link_keys,
                    source=event_node_id,
                    target=f"indicator:{indicator_code}",
                    rel_type="AFFECTS",
                )

        for row in documents:
            doc_id = row.get("doc_id")
            if not doc_id:
                continue
            document_node_id = f"document:{doc_id}"
            self._add_node(
                nodes,
                node_id=document_node_id,
                node_type="Document",
                label=row.get("title") or doc_id,
                properties={
                    "doc_id": doc_id,
                    "title": row.get("title"),
                    "url": row.get("url"),
                    "source": row.get("source"),
                    "country": row.get("country"),
                    "country_code": row.get("country_code"),
                    "category": row.get("category"),
                    "published_at": row.get("published_at"),
                },
            )
            for event_id in row.get("event_ids") or []:
                self._add_link(
                    links,
                    link_keys,
                    source=document_node_id,
                    target=f"event:{event_id}",
                    rel_type="MENTIONS",
                )
            for theme_id in row.get("theme_ids") or []:
                self._add_link(
                    links,
                    link_keys,
                    source=document_node_id,
                    target=f"theme:{theme_id}",
                    rel_type="ABOUT_THEME",
                )

        for row in stories:
            story_id = row.get("story_id")
            if not story_id:
                continue
            story_node_id = f"story:{story_id}"
            self._add_node(
                nodes,
                node_id=story_node_id,
                node_type="Story",
                label=row.get("title") or story_id,
                properties={
                    "story_id": story_id,
                    "story_date": row.get("story_date"),
                    "theme_id": row.get("theme_id"),
                    "doc_count": len(row.get("doc_ids") or []),
                },
            )
            theme_id = row.get("theme_id")
            if theme_id:
                self._add_link(
                    links,
                    link_keys,
                    source=story_node_id,
                    target=f"theme:{theme_id}",
                    rel_type="ABOUT_THEME",
                )
            for doc_id in row.get("doc_ids") or []:
                self._add_link(
                    links,
                    link_keys,
                    source=story_node_id,
                    target=f"document:{doc_id}",
                    rel_type="CONTAINS",
                )

        normalized_evidences: List[Dict[str, Any]] = []
        for row in evidences:
            normalized_evidences.append(
                {
                    "evidence_id": row.get("evidence_id"),
                    "text": row.get("text") or "",
                    "doc_id": row.get("doc_id"),
                    "doc_url": row.get("doc_url"),
                    "doc_title": row.get("doc_title"),
                    "doc_category": row.get("doc_category"),
                    "published_at": _to_json_value(row.get("published_at")),
                    "support_labels": [str(label) for label in row.get("support_labels") or []],
                    "event_id": row.get("event_id"),
                    "claim_id": row.get("claim_id"),
                }
            )

        suggested_queries = self._build_suggested_queries(
            theme_ids=matched_theme_ids or sorted(discovered_theme_ids),
            question=request.question,
            window_days=window_days,
        )

        meta = {
            "question": request.question,
            "time_range": request.time_range,
            "window_days": window_days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "country": request.country,
            "country_code": request.country_code,
            "resolved_country": country_input or country_name,
            "resolved_country_code": country_code,
            "scope_allowed_country_codes": sorted(SUPPORTED_QA_COUNTRY_CODES),
            "scope_warnings": scope_warnings.get("messages", []),
            "scope_violation_counts": scope_warnings.get("counts", {}),
            "scope_violation_samples": scope_warnings.get("samples", []),
            "matched_theme_ids": matched_theme_ids,
            "matched_indicator_codes": matched_indicator_codes,
            "question_terms": question_terms[:10],
            "counts": {
                "nodes": len(nodes),
                "links": len(links),
                "events": len(events),
                "documents": len(documents),
                "stories": len(stories),
                "evidences": len(normalized_evidences),
            },
        }

        return GraphRagContextResponse(
            nodes=list(nodes.values()),
            links=links,
            evidences=normalized_evidences,
            suggested_queries=suggested_queries,
            meta=meta,
        )


def build_graph_rag_context(
    request: GraphRagContextRequest,
    neo4j_client=None,
) -> GraphRagContextResponse:
    builder = GraphRagContextBuilder(neo4j_client=neo4j_client)
    return builder.build_context(request)


@router.post("/context", response_model=GraphRagContextResponse)
def graph_rag_context(request: GraphRagContextRequest):
    try:
        return build_graph_rag_context(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.error("[GraphRAGContext] failed: %s", error, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to build graph context") from error
