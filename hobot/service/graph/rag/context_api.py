"""
Phase D-1: Question -> subgraph context API.
"""

import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..neo4j_client import get_neo4j_client
from ..normalization.country_mapping import get_country_name, normalize_country
from .kr_region_scope import (
    extract_region_codes_from_question,
    format_lawd_codes_csv,
    parse_region_input_to_lawd_codes,
)

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

SUPPORTED_QA_COUNTRY_CODES: Set[str] = {"US", "KR", "US-KR"}
SUPPORTED_QA_DATA_COUNTRY_CODES: Set[str] = {"US", "KR"}
SUPPORTED_COMPARE_MODES: Set[str] = {"single", "country_compare", "region_compare"}

PROPERTY_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "apartment_sale": ["아파트", "매매", "매매가", "sale", "apartment"],
    "jeonse": ["전세", "jeonse"],
    "monthly_rent": ["월세", "monthly rent", "rent"],
}
US_SINGLE_STOCK_ROUTE_TYPE = "us_single_stock"
KR_SCOPE_DEFAULT_ROUTE_TYPES: Set[str] = {
    "real_estate_detail",
    "market_summary",
    "sector_recommendation",
    "timing_scenario",
}
KR_SCOPE_EXCLUDED_ROUTE_TYPES: Set[str] = {
    US_SINGLE_STOCK_ROUTE_TYPE,
    "compare_outlook",
    "fx_driver",
    "general_knowledge",
}
KR_SCOPE_HINT_KEYWORDS: Set[str] = {
    "한국",
    "국내",
    "korea",
    "south korea",
    "kr",
    "코스피",
    "코스닥",
    "서울",
    "수도권",
    "부동산",
    "아파트",
    "전세",
    "월세",
    "매매가",
    "실거래",
    "기준금리",
    "원화",
    "원달러",
    "usdkrw",
    "원/달러",
}
US_SINGLE_STOCK_SYMBOL_COMPANY_HINTS: Dict[str, List[str]] = {
    "PLTR": ["Palantir", "Palantir Technologies"],
    "SNOW": ["Snowflake"],
    "AAPL": ["Apple", "Apple Inc."],
    "MSFT": ["Microsoft", "Microsoft Corporation"],
    "NVDA": ["NVIDIA", "NVIDIA Corporation"],
    "AMZN": ["Amazon", "Amazon.com"],
    "GOOGL": ["Alphabet", "Google"],
    "META": ["Meta", "Meta Platforms"],
    "TSLA": ["Tesla", "Tesla Motors"],
}

DEFAULT_GRAPH_RAG_VECTOR_INDEX_NAME = "document_text_embedding_idx"
DEFAULT_GRAPH_RAG_QUERY_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_GRAPH_RAG_QUERY_EMBEDDING_DIMENSION = 768


class GraphRagContextRequest(BaseModel):
    question: str = Field(..., min_length=3)
    time_range: str = Field(default="30d")
    country: Optional[str] = None
    country_code: Optional[str] = None
    compare_mode: Optional[str] = None
    region_code: Optional[str] = None
    property_type: Optional[str] = None
    route_type: Optional[str] = None
    focus_symbols: List[str] = Field(default_factory=list)
    focus_companies: List[str] = Field(default_factory=list)
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


def _truthy_env(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


class GraphRagContextBuilder:
    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()
        self.vector_search_enabled = _truthy_env(
            os.getenv("GRAPH_RAG_VECTOR_SEARCH_ENABLED", "1"),
            default=True,
        )
        self.vector_index_name = (
            os.getenv("GRAPH_RAG_VECTOR_INDEX_NAME", DEFAULT_GRAPH_RAG_VECTOR_INDEX_NAME)
            or DEFAULT_GRAPH_RAG_VECTOR_INDEX_NAME
        ).strip()
        self.query_embedding_model = (
            os.getenv("GRAPH_RAG_QUERY_EMBEDDING_MODEL", DEFAULT_GRAPH_RAG_QUERY_EMBEDDING_MODEL)
            or DEFAULT_GRAPH_RAG_QUERY_EMBEDDING_MODEL
        ).strip()
        self.query_embedding_dimension = max(
            int(os.getenv("GRAPH_RAG_QUERY_EMBEDDING_DIMENSION", str(DEFAULT_GRAPH_RAG_QUERY_EMBEDDING_DIMENSION))),
            1,
        )
        self.vector_query_multiplier = max(
            int(os.getenv("GRAPH_RAG_VECTOR_QUERY_MULTIPLIER", "3")),
            1,
        )
        self.bm25_weight = max(_safe_float(os.getenv("GRAPH_RAG_BM25_WEIGHT", "0.55"), 0.55), 0.0)
        self.vector_weight = max(_safe_float(os.getenv("GRAPH_RAG_VECTOR_WEIGHT", "0.45"), 0.45), 0.0)
        self.fallback_weight = max(_safe_float(os.getenv("GRAPH_RAG_FALLBACK_WEIGHT", "0.15"), 0.15), 0.0)
        self.stock_focus_weight = max(_safe_float(os.getenv("GRAPH_RAG_STOCK_FOCUS_WEIGHT", "0.6"), 0.6), 0.0)
        self._embedding_client = None

    @staticmethod
    def _resolve_embedding_api_key() -> Optional[str]:
        for key_name in ("GEMINI_EMBEDDING_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
            value = _normalize_text(os.getenv(key_name))
            if value:
                return value
        return None

    def _get_embedding_client(self):
        if self._embedding_client is not None:
            return self._embedding_client
        api_key = self._resolve_embedding_api_key()
        if not api_key:
            return None
        try:
            from google import genai

            self._embedding_client = genai.Client(api_key=api_key)
            return self._embedding_client
        except Exception as exc:
            logger.warning("[GraphRAGContext] failed to initialize embedding client: %s", exc)
            return None

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
        if raw_country_code in {"USKR", "KRUS", "US/KR", "KR/US", "KR-US"}:
            raw_country_code = "US-KR"

        normalized_code = raw_country_code or normalize_country(raw_country or "")
        raw_country_lower = _normalize_text(raw_country).lower()
        if not normalized_code and raw_country_lower in {"us-kr", "kr-us", "us/kr", "kr/us", "미국한국", "한미", "미국-한국"}:
            normalized_code = "US-KR"
        normalized_name = get_country_name(normalized_code) if normalized_code else None
        if normalized_name and normalized_name == normalized_code:
            normalized_name = None

        return raw_country, normalized_name, normalized_code

    @staticmethod
    def _resolve_country_scope_params(
        country: Optional[str],
        country_name: Optional[str],
        country_code: Optional[str],
    ) -> Dict[str, Any]:
        if country_code == "US-KR":
            country_codes = sorted(SUPPORTED_QA_DATA_COUNTRY_CODES)
            country_names = [get_country_name(code) for code in country_codes]
            country_names = [name for name in country_names if name]
            return {
                "country": None,
                "country_name": None,
                "country_code": None,
                "country_codes": country_codes,
                "country_names": country_names,
            }
        return {
            "country": country,
            "country_name": country_name,
            "country_code": country_code,
            "country_codes": [country_code] if country_code in SUPPORTED_QA_DATA_COUNTRY_CODES else None,
            "country_names": [country_name] if country_name else None,
        }

    @staticmethod
    def _normalize_compare_mode(
        compare_mode: Optional[str],
        *,
        question: str,
        country_code: Optional[str],
        region_group_count: int,
    ) -> str:
        normalized = _normalize_text(compare_mode).lower().replace("-", "_")
        if normalized in SUPPORTED_COMPARE_MODES:
            return normalized

        lowered_question = _normalize_text(question).lower()
        has_compare_token = any(token in lowered_question for token in ["비교", "vs", "versus", "대비", "차이"])
        has_country_pair_token = any(
            token in lowered_question
            for token in ["미국", "한국", "한미", "us", "kr", "us-kr", "kr-us", "미-한"]
        )

        if country_code == "US-KR" or (has_compare_token and has_country_pair_token):
            return "country_compare"
        if has_compare_token and region_group_count >= 2:
            return "region_compare"
        return "single"

    @staticmethod
    def _normalize_region_code(
        region_code: Optional[str],
        *,
        question: str,
    ) -> Tuple[Optional[str], int]:
        raw = _normalize_text(region_code)
        if raw:
            codes, _, group_count = parse_region_input_to_lawd_codes(raw)
            normalized_csv = format_lawd_codes_csv(codes)
            if normalized_csv:
                return normalized_csv, max(group_count, 1)
            return raw, max(group_count, 1 if raw else 0)

        question_codes, group_count = extract_region_codes_from_question(question)
        normalized_csv = format_lawd_codes_csv(question_codes)
        if normalized_csv:
            return normalized_csv, max(group_count, 1)

        lowered_question = _normalize_text(question).lower()
        if "서울" in lowered_question:
            return format_lawd_codes_csv([code for code in question_codes if code.startswith("11")]) or "SEOUL", 1
        if any(token in lowered_question for token in ["경기", "gyeonggi"]):
            return format_lawd_codes_csv([code for code in question_codes if code.startswith("41")]) or "GYEONGGI", 1
        return None, 0

    @staticmethod
    def _normalize_property_type(property_type: Optional[str], *, question: str) -> Optional[str]:
        raw = _normalize_text(property_type).lower().replace("-", "_")
        if raw:
            return raw

        lowered_question = _normalize_text(question).lower()
        for normalized, keywords in PROPERTY_TYPE_KEYWORDS.items():
            if any(keyword in lowered_question for keyword in keywords):
                return normalized
        return None

    @staticmethod
    def _should_default_country_to_kr(
        *,
        question: str,
        route_type: str,
        region_code: Optional[str],
        property_type: Optional[str],
        has_focus_scope_hint: bool,
    ) -> bool:
        normalized_route = _normalize_text(route_type).lower()
        if normalized_route in KR_SCOPE_EXCLUDED_ROUTE_TYPES:
            return False
        if normalized_route in KR_SCOPE_DEFAULT_ROUTE_TYPES:
            return True
        if _normalize_text(region_code) or _normalize_text(property_type):
            return True
        if has_focus_scope_hint and not normalized_route:
            return False
        lowered_question = _normalize_text(question).lower()
        return any(keyword in lowered_question for keyword in KR_SCOPE_HINT_KEYWORDS)

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
        requested_country_codes: Optional[Set[str]],
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
                if resolved_code not in SUPPORTED_QA_DATA_COUNTRY_CODES:
                    counts["out_of_scope_country_code"] += 1
                    add_sample("out_of_scope_country_code", node_type, row, resolved_code)
                if requested_country_codes and resolved_code not in requested_country_codes:
                    counts["requested_country_mismatch"] += 1
                    add_sample("requested_country_mismatch", node_type, row, resolved_code)

        messages: List[str] = []
        if counts["missing_country_code"] > 0:
            messages.append(f"country_code 누락 데이터 {counts['missing_country_code']}건")
        if counts["out_of_scope_country_code"] > 0:
            messages.append(f"US/KR 범위 외 데이터 {counts['out_of_scope_country_code']}건")
        if requested_country_codes and counts["requested_country_mismatch"] > 0:
            messages.append(
                f"요청 국가({', '.join(sorted(requested_country_codes))})와 불일치한 데이터 {counts['requested_country_mismatch']}건"
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
        country_codes: Optional[List[str]],
        country_names: Optional[List[str]],
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
                ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL AND $country_codes IS NULL)
                OR ($country IS NOT NULL AND d.country = $country)
                OR ($country_name IS NOT NULL AND d.country = $country_name)
                OR ($country_code IS NOT NULL AND (d.country_code = $country_code OR d.country = $country_code))
                OR ($country_codes IS NOT NULL AND (d.country_code IN $country_codes OR d.country IN $country_codes OR d.country IN coalesce($country_names, [])))
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
                "country_codes": country_codes,
                "country_names": country_names,
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

    @staticmethod
    def _extract_theme_keyword_terms(theme_ids: List[str]) -> List[str]:
        terms: List[str] = []
        seen: Set[str] = set()
        for theme_id in theme_ids or []:
            for raw_keyword in THEME_KEYWORDS.get(theme_id, []):
                keyword = _normalize_text(raw_keyword).lower()
                if len(keyword) < 2:
                    continue
                if keyword in QUESTION_TERM_STOPWORDS:
                    continue
                if keyword in seen:
                    continue
                seen.add(keyword)
                terms.append(keyword)
        return terms[:24]

    @staticmethod
    def _normalize_focus_symbols(symbols: List[str]) -> List[str]:
        normalized: List[str] = []
        seen: Set[str] = set()
        for value in symbols or []:
            text = _normalize_text(str(value)).upper()
            if not text:
                continue
            compact = "".join(ch for ch in text if ch.isalnum() or ch in {".", "-"})
            if not compact:
                continue
            variants = [compact]
            compact_no_sep = compact.replace(".", "").replace("-", "")
            if compact_no_sep and compact_no_sep != compact:
                variants.append(compact_no_sep)
            for variant in variants:
                if variant in seen:
                    continue
                seen.add(variant)
                normalized.append(variant)
        return normalized[:16]

    @staticmethod
    def _normalize_focus_companies(companies: List[str]) -> List[str]:
        normalized: List[str] = []
        seen: Set[str] = set()
        for value in companies or []:
            text = _normalize_text(str(value))
            if len(text) < 2:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(text)
        return normalized[:16]

    @staticmethod
    def _expand_focus_companies_from_symbols(symbols: List[str]) -> List[str]:
        expanded: List[str] = []
        seen: Set[str] = set()
        for symbol in symbols or []:
            upper_symbol = _normalize_text(str(symbol)).upper()
            if not upper_symbol:
                continue
            for company in US_SINGLE_STOCK_SYMBOL_COMPANY_HINTS.get(upper_symbol, []):
                company_name = _normalize_text(company)
                if len(company_name) < 2:
                    continue
                key = company_name.lower()
                if key in seen:
                    continue
                seen.add(key)
                expanded.append(company_name)
        return expanded[:16]

    def _embed_query_vector(self, question: str) -> Optional[List[float]]:
        query_text = _normalize_text(question)
        if not query_text:
            return None

        client = self._get_embedding_client()
        if client is None:
            return None

        try:
            from google.genai import types

            response = client.models.embed_content(
                model=self.query_embedding_model,
                contents=[query_text],
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=self.query_embedding_dimension,
                ),
            )
            embeddings = list(response.embeddings or [])
            if not embeddings:
                return None
            vector = list(embeddings[0].values or [])
            if len(vector) != self.query_embedding_dimension:
                logger.warning(
                    "[GraphRAGContext] query embedding dimension mismatch(expected=%s, actual=%s)",
                    self.query_embedding_dimension,
                    len(vector),
                )
                return None
            return vector
        except Exception as exc:
            logger.warning("[GraphRAGContext] query embedding failed: %s", exc)
            return None

    def _fetch_documents_by_vector(
        self,
        *,
        start_iso: str,
        end_iso: str,
        country: Optional[str],
        country_name: Optional[str],
        country_code: Optional[str],
        country_codes: Optional[List[str]],
        country_names: Optional[List[str]],
        query_embedding: List[float],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not query_embedding or limit <= 0:
            return []
        vector_limit = max(int(limit), 1)
        vector_k = max(int(limit * self.vector_query_multiplier), vector_limit)
        try:
            rows = self.neo4j_client.run_read(
                """
                // phase_d_documents_by_vector
                CALL db.index.vector.queryNodes($index_name, $vector_k, $query_embedding)
                YIELD node AS d, score
                WHERE d.published_at IS NOT NULL
                  AND d.published_at >= datetime($start_iso)
                  AND d.published_at <= datetime($end_iso)
                  AND (
                    ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL AND $country_codes IS NULL)
                    OR ($country IS NOT NULL AND d.country = $country)
                    OR ($country_name IS NOT NULL AND d.country = $country_name)
                    OR ($country_code IS NOT NULL AND (d.country_code = $country_code OR d.country = $country_code))
                    OR ($country_codes IS NOT NULL AND (d.country_code IN $country_codes OR d.country IN $country_codes OR d.country IN coalesce($country_names, [])))
                  )
                WITH d, score
                ORDER BY score DESC, d.published_at DESC
                LIMIT $limit
                OPTIONAL MATCH (d)-[:MENTIONS]->(e:Event)
                OPTIONAL MATCH (d)-[:ABOUT_THEME]->(t:MacroTheme)
                RETURN d.doc_id AS doc_id,
                       d.title AS title,
                       coalesce(d['url'], d.link) AS url,
                       d.source AS source,
                       d.country AS country,
                       d.country_code AS country_code,
                       d.category AS category,
                       d.published_at AS published_at,
                       collect(DISTINCT e.event_id) AS event_ids,
                       collect(DISTINCT t.theme_id) AS theme_ids,
                       score AS vector_score
                """,
                {
                    "index_name": self.vector_index_name,
                    "vector_k": vector_k,
                    "query_embedding": query_embedding,
                    "start_iso": start_iso,
                    "end_iso": end_iso,
                    "country": country,
                    "country_name": country_name,
                    "country_code": country_code,
                    "country_codes": country_codes,
                    "country_names": country_names,
                    "limit": vector_limit,
                },
            )
        except Exception as exc:
            logger.warning("[GraphRAGContext] vector search fallback to keyword-only: %s", exc)
            return []

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

    @staticmethod
    def _normalize_rank_scores(raw_scores: Dict[str, float]) -> Dict[str, float]:
        if not raw_scores:
            return {}
        max_score = max((float(value) for value in raw_scores.values()), default=0.0)
        if max_score <= 0:
            return {doc_id: 0.0 for doc_id in raw_scores.keys()}
        return {
            doc_id: max(0.0, float(score) / max_score)
            for doc_id, score in raw_scores.items()
        }

    def _merge_hybrid_documents(
        self,
        *,
        base_documents: List[Dict[str, Any]],
        keyword_documents: List[Dict[str, Any]],
        fallback_documents: List[Dict[str, Any]],
        vector_documents: List[Dict[str, Any]],
        stock_documents: List[Dict[str, Any]],
        limit: int,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        doc_map: Dict[str, Dict[str, Any]] = {}
        source_map: Dict[str, Set[str]] = {}
        bm25_raw: Dict[str, float] = {}
        vector_raw: Dict[str, float] = {}
        fallback_raw: Dict[str, float] = {}
        stock_raw: Dict[str, float] = {}
        base_doc_ids: Set[str] = set()

        def _merge_row(row: Dict[str, Any], source_tag: str):
            doc_id = row.get("doc_id")
            if not doc_id:
                return
            event_ids = set(row.get("event_ids") or [])
            theme_ids = set(row.get("theme_ids") or [])

            existing = doc_map.get(doc_id)
            if existing is None:
                merged = dict(row)
                merged["event_ids"] = sorted(event_ids)
                merged["theme_ids"] = sorted(theme_ids)
                doc_map[doc_id] = merged
            else:
                merged_event_ids = set(existing.get("event_ids") or [])
                merged_event_ids.update(event_ids)
                merged_theme_ids = set(existing.get("theme_ids") or [])
                merged_theme_ids.update(theme_ids)
                existing["event_ids"] = sorted(merged_event_ids)
                existing["theme_ids"] = sorted(merged_theme_ids)
                for key in ("title", "url", "source", "country", "country_code", "category", "published_at"):
                    if not existing.get(key) and row.get(key):
                        existing[key] = row.get(key)

            source_map.setdefault(doc_id, set()).add(source_tag)

        for row in base_documents:
            doc_id = row.get("doc_id")
            if doc_id:
                base_doc_ids.add(doc_id)
            _merge_row(row, "base")
        for row in keyword_documents:
            _merge_row(row, "bm25")
            doc_id = row.get("doc_id")
            if doc_id:
                bm25_raw[doc_id] = max(
                    float(bm25_raw.get(doc_id, 0.0)),
                    float(row.get("fulltext_score") or 0.0),
                )
        for row in vector_documents:
            _merge_row(row, "vector")
            doc_id = row.get("doc_id")
            if doc_id:
                vector_raw[doc_id] = max(
                    float(vector_raw.get(doc_id, 0.0)),
                    float(row.get("vector_score") or 0.0),
                )
        for row in fallback_documents:
            _merge_row(row, "contains")
            doc_id = row.get("doc_id")
            if doc_id:
                fallback_raw[doc_id] = max(
                    float(fallback_raw.get(doc_id, 0.0)),
                    float(len(row.get("matched_terms") or [])),
                )
        for row in stock_documents:
            _merge_row(row, "stock_focus")
            doc_id = row.get("doc_id")
            if doc_id:
                stock_raw[doc_id] = max(
                    float(stock_raw.get(doc_id, 0.0)),
                    float(row.get("stock_focus_score") or len(row.get("matched_terms") or [])),
                )

        bm25_norm = self._normalize_rank_scores(bm25_raw)
        vector_norm = self._normalize_rank_scores(vector_raw)
        fallback_norm = self._normalize_rank_scores(fallback_raw)
        stock_norm = self._normalize_rank_scores(stock_raw)
        recent_priority_count = max(
            _safe_int(os.getenv("GRAPH_RAG_RECENT_DOC_PRIORITY_COUNT"), 8),
            0,
        )
        recent_base_doc_ids: Set[str] = set()
        if recent_priority_count > 0 and base_documents:
            base_recent_candidates = sorted(
                base_documents,
                key=lambda row: str(row.get("published_at") or ""),
                reverse=True,
            )
            for row in base_recent_candidates:
                doc_id = str(row.get("doc_id") or "").strip()
                if not doc_id:
                    continue
                recent_base_doc_ids.add(doc_id)
                if len(recent_base_doc_ids) >= recent_priority_count:
                    break
        recent_base_boost = 0.12 if recent_base_doc_ids else 0.0

        effective_stock_weight = self.stock_focus_weight if stock_documents else 0.0
        weight_sum = self.bm25_weight + self.vector_weight + self.fallback_weight + effective_stock_weight
        if weight_sum <= 0:
            bm25_weight = 0.55
            vector_weight = 0.45
            fallback_weight = 0.0
            stock_weight = 0.0
        else:
            bm25_weight = self.bm25_weight / weight_sum
            vector_weight = self.vector_weight / weight_sum
            fallback_weight = self.fallback_weight / weight_sum
            stock_weight = effective_stock_weight / weight_sum

        ranked_docs: List[Dict[str, Any]] = []
        for doc_id, row in doc_map.items():
            hybrid_score = (
                bm25_weight * float(bm25_norm.get(doc_id, 0.0))
                + vector_weight * float(vector_norm.get(doc_id, 0.0))
                + fallback_weight * float(fallback_norm.get(doc_id, 0.0))
                + stock_weight * float(stock_norm.get(doc_id, 0.0))
                + (0.03 if doc_id in base_doc_ids else 0.0)
                + (recent_base_boost if doc_id in recent_base_doc_ids else 0.0)
            )
            enriched = dict(row)
            enriched["hybrid_score"] = round(hybrid_score, 6)
            enriched["fulltext_score"] = bm25_raw.get(doc_id)
            enriched["vector_score"] = vector_raw.get(doc_id)
            enriched["matched_term_count"] = int(fallback_raw.get(doc_id, 0.0))
            enriched["stock_focus_score"] = stock_raw.get(doc_id)
            enriched["retrieval_sources"] = sorted(source_map.get(doc_id, set()))
            ranked_docs.append(enriched)

        ranked_docs.sort(
            key=lambda item: (
                float(item.get("hybrid_score") or 0.0),
                str(item.get("published_at") or ""),
            ),
            reverse=True,
        )
        selected_docs = ranked_docs[:limit]
        selected_doc_ids: Set[str] = {
            str(row.get("doc_id") or "").strip()
            for row in selected_docs
            if str(row.get("doc_id") or "").strip()
        }
        ranked_by_doc_id: Dict[str, Dict[str, Any]] = {
            str(row.get("doc_id") or "").strip(): row
            for row in ranked_docs
            if str(row.get("doc_id") or "").strip()
        }
        recent_base_injected_count = 0
        if recent_priority_count > 0 and selected_docs:
            recent_base_candidates = sorted(
                base_documents,
                key=lambda row: str(row.get("published_at") or ""),
                reverse=True,
            )
            protected_doc_ids: Set[str] = set()
            for row in selected_docs:
                doc_id = str(row.get("doc_id") or "").strip()
                if doc_id in recent_base_doc_ids:
                    protected_doc_ids.add(doc_id)

            for base_row in recent_base_candidates:
                base_doc_id = str(base_row.get("doc_id") or "").strip()
                if (
                    not base_doc_id
                    or base_doc_id in selected_doc_ids
                    or base_doc_id not in ranked_by_doc_id
                ):
                    continue

                replace_index: Optional[int] = None
                for idx in range(len(selected_docs) - 1, -1, -1):
                    current_doc_id = str(selected_docs[idx].get("doc_id") or "").strip()
                    if current_doc_id and current_doc_id not in protected_doc_ids:
                        replace_index = idx
                        break

                if replace_index is None:
                    break

                replaced_doc_id = str(selected_docs[replace_index].get("doc_id") or "").strip()
                if replaced_doc_id:
                    selected_doc_ids.discard(replaced_doc_id)
                    protected_doc_ids.discard(replaced_doc_id)

                selected_docs[replace_index] = ranked_by_doc_id[base_doc_id]
                selected_doc_ids.add(base_doc_id)
                protected_doc_ids.add(base_doc_id)
                recent_base_injected_count += 1
                if recent_base_injected_count >= recent_priority_count:
                    break

        retrieval_meta = {
            "bm25_docs": len(keyword_documents),
            "vector_docs": len(vector_documents),
            "contains_docs": len(fallback_documents),
            "stock_focus_docs": len(stock_documents),
            "base_docs": len(base_documents),
            "merged_docs": len(ranked_docs),
            "weights": {
                "bm25": bm25_weight,
                "vector": vector_weight,
                "contains": fallback_weight,
                "stock_focus": stock_weight,
            },
            "recent_base_priority_count": len(recent_base_doc_ids),
            "recent_base_boost": recent_base_boost,
            "recent_base_injected_count": recent_base_injected_count,
            "vector_enabled": bool(self.vector_search_enabled),
            "vector_index_name": self.vector_index_name,
        }
        return selected_docs[:limit], retrieval_meta

    @staticmethod
    def _prioritize_evidence_doc_ids(
        *,
        documents: List[Dict[str, Any]],
        route_type: Optional[str],
        prioritize_stock_focus: bool = False,
        recent_doc_priority_count: int = 0,
    ) -> List[str]:
        seen: Set[str] = set()
        focus_doc_ids: List[str] = []
        other_doc_ids: List[str] = []
        prioritize_focus = (
            prioritize_stock_focus
            or str(route_type or "").strip().lower() == US_SINGLE_STOCK_ROUTE_TYPE
        )
        normalized_recent_doc_priority_count = max(int(recent_doc_priority_count or 0), 0)

        recent_doc_ids: List[str] = []
        if normalized_recent_doc_priority_count > 0:
            recent_candidates = sorted(
                documents,
                key=lambda row: str(row.get("published_at") or ""),
                reverse=True,
            )
            recent_seen: Set[str] = set()
            for row in recent_candidates:
                doc_id = str(row.get("doc_id") or "").strip()
                if not doc_id or doc_id in recent_seen:
                    continue
                recent_seen.add(doc_id)
                recent_doc_ids.append(doc_id)
                if len(recent_doc_ids) >= normalized_recent_doc_priority_count:
                    break

        for row in documents:
            doc_id = str(row.get("doc_id") or "").strip()
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            retrieval_sources = row.get("retrieval_sources") or []
            is_stock_focus = isinstance(retrieval_sources, list) and "stock_focus" in retrieval_sources
            if prioritize_focus and is_stock_focus:
                focus_doc_ids.append(doc_id)
            else:
                other_doc_ids.append(doc_id)

        ordered_doc_ids = (
            focus_doc_ids + recent_doc_ids + other_doc_ids
            if prioritize_focus
            else recent_doc_ids + other_doc_ids
        )
        deduped_doc_ids: List[str] = []
        deduped_seen: Set[str] = set()
        for doc_id in ordered_doc_ids:
            if not doc_id or doc_id in deduped_seen:
                continue
            deduped_seen.add(doc_id)
            deduped_doc_ids.append(doc_id)
        return deduped_doc_ids

    def _fetch_events(
        self,
        start_iso: str,
        end_iso: str,
        country: Optional[str],
        country_name: Optional[str],
        country_code: Optional[str],
        country_codes: Optional[List[str]],
        country_names: Optional[List[str]],
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
                ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL AND $country_codes IS NULL)
                OR ($country IS NOT NULL AND e.country = $country)
                OR ($country_name IS NOT NULL AND e.country = $country_name)
                OR ($country_code IS NOT NULL AND (e.country_code = $country_code OR e.country = $country_code))
                OR ($country_codes IS NOT NULL AND (e.country_code IN $country_codes OR e.country IN $country_codes OR e.country IN coalesce($country_names, [])))
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
                "country_codes": country_codes,
                "country_names": country_names,
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
        country_codes: Optional[List[str]],
        country_names: Optional[List[str]],
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
                ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL AND $country_codes IS NULL)
                OR ($country IS NOT NULL AND d.country = $country)
                OR ($country_name IS NOT NULL AND d.country = $country_name)
                OR ($country_code IS NOT NULL AND (d.country_code = $country_code OR d.country = $country_code))
                OR ($country_codes IS NOT NULL AND (d.country_code IN $country_codes OR d.country IN $country_codes OR d.country IN coalesce($country_names, [])))
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
                   coalesce(d['url'], d.link) AS url,
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
                "country_codes": country_codes,
                "country_names": country_names,
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
        country_codes: Optional[List[str]],
        country_names: Optional[List[str]],
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
                    ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL AND $country_codes IS NULL)
                    OR ($country IS NOT NULL AND d.country = $country)
                    OR ($country_name IS NOT NULL AND d.country = $country_name)
                    OR ($country_code IS NOT NULL AND (d.country_code = $country_code OR d.country = $country_code))
                    OR ($country_codes IS NOT NULL AND (d.country_code IN $country_codes OR d.country IN $country_codes OR d.country IN coalesce($country_names, [])))
                  )
                WITH d, score
                ORDER BY score DESC, d.published_at DESC
                LIMIT $limit
                OPTIONAL MATCH (d)-[:MENTIONS]->(e:Event)
                OPTIONAL MATCH (d)-[:ABOUT_THEME]->(t:MacroTheme)
                RETURN d.doc_id AS doc_id,
                       d.title AS title,
                       coalesce(d['url'], d.link) AS url,
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
                    "country_codes": country_codes,
                    "country_names": country_names,
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
                country_codes,
                country_names,
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

    def _fetch_documents_for_us_single_stock(
        self,
        *,
        start_iso: str,
        end_iso: str,
        country: Optional[str],
        country_name: Optional[str],
        country_code: Optional[str],
        country_codes: Optional[List[str]],
        country_names: Optional[List[str]],
        focus_symbols: List[str],
        focus_companies: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []

        normalized_symbols = self._normalize_focus_symbols(focus_symbols)
        normalized_companies = self._normalize_focus_companies(focus_companies)
        if not normalized_symbols and not normalized_companies:
            return []

        symbol_terms = [term.lower() for term in normalized_symbols]
        company_terms = [term.lower() for term in normalized_companies]
        query_terms = list(dict.fromkeys(symbol_terms + company_terms))[:24]
        if not query_terms:
            return []

        rows = self.neo4j_client.run_read(
            """
            // phase_d_documents_for_us_single_stock
            MATCH (d:Document)
            WHERE d.published_at IS NOT NULL
              AND d.published_at >= datetime($start_iso)
              AND d.published_at <= datetime($end_iso)
              AND (
                ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL AND $country_codes IS NULL)
                OR ($country IS NOT NULL AND d.country = $country)
                OR ($country_name IS NOT NULL AND d.country = $country_name)
                OR ($country_code IS NOT NULL AND (d.country_code = $country_code OR d.country = $country_code))
                OR ($country_codes IS NOT NULL AND (d.country_code IN $country_codes OR d.country IN $country_codes OR d.country IN coalesce($country_names, [])))
              )
            OPTIONAL MATCH (d)-[:MENTIONS]->(ent:Entity)
            OPTIONAL MATCH (ent)-[:HAS_ALIAS]->(ea:EntityAlias)
            WITH d,
                 collect(DISTINCT toLower(coalesce(ent.name, ''))) AS entity_names,
                 collect(DISTINCT toLower(coalesce(ent.canonical_id, ''))) AS entity_ids,
                 collect(DISTINCT toLower(coalesce(ea.alias, ''))) AS entity_aliases
            WITH d,
                 [term IN $query_terms WHERE
                    toLower(coalesce(d.title, '')) CONTAINS term
                    OR toLower(coalesce(d.description, '')) CONTAINS term
                    OR toLower(coalesce(d.description_ko, '')) CONTAINS term
                    OR toLower(coalesce(d.text, '')) CONTAINS term
                 ] AS text_terms,
                 [term IN $query_terms WHERE
                    any(token IN entity_names WHERE token CONTAINS term)
                    OR any(token IN entity_ids WHERE token CONTAINS term)
                    OR any(token IN entity_aliases WHERE token CONTAINS term)
                 ] AS entity_terms
            WITH d,
                 text_terms,
                 entity_terms,
                 text_terms + entity_terms AS raw_terms
            UNWIND raw_terms AS matched_term
            WITH d,
                 size(text_terms) AS text_match_count,
                 size(entity_terms) AS entity_match_count,
                 collect(DISTINCT matched_term) AS matched_terms
            WHERE size(matched_terms) > 0
            OPTIONAL MATCH (d)-[:MENTIONS]->(e:Event)
            OPTIONAL MATCH (d)-[:ABOUT_THEME]->(t:MacroTheme)
            RETURN d.doc_id AS doc_id,
                   d.title AS title,
                   coalesce(d['url'], d.link) AS url,
                   d.source AS source,
                   d.country AS country,
                   d.country_code AS country_code,
                   d.category AS category,
                   d.published_at AS published_at,
                   collect(DISTINCT e.event_id) AS event_ids,
                   collect(DISTINCT t.theme_id) AS theme_ids,
                   matched_terms,
                   (text_match_count + (entity_match_count * 2)) AS stock_focus_score
            ORDER BY stock_focus_score DESC, d.published_at DESC
            LIMIT $limit
            """,
            {
                "start_iso": start_iso,
                "end_iso": end_iso,
                "country": country,
                "country_name": country_name,
                "country_code": country_code,
                "country_codes": country_codes,
                "country_names": country_names,
                "query_terms": query_terms,
                "limit": max(int(limit), 1),
            },
        )

        normalized_rows: List[Dict[str, Any]] = []
        for row in rows:
            normalized_rows.append(
                {
                    **row,
                    "event_ids": [item for item in (row.get("event_ids") or []) if item],
                    "theme_ids": [item for item in (row.get("theme_ids") or []) if item],
                    "matched_terms": [str(item) for item in (row.get("matched_terms") or []) if str(item)],
                }
            )
        return normalized_rows

    def _fetch_documents_by_question_terms_fallback(
        self,
        start_iso: str,
        end_iso: str,
        country: Optional[str],
        country_name: Optional[str],
        country_code: Optional[str],
        country_codes: Optional[List[str]],
        country_names: Optional[List[str]],
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
                ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL AND $country_codes IS NULL)
                OR ($country IS NOT NULL AND d.country = $country)
                OR ($country_name IS NOT NULL AND d.country = $country_name)
                OR ($country_code IS NOT NULL AND (d.country_code = $country_code OR d.country = $country_code))
                OR ($country_codes IS NOT NULL AND (d.country_code IN $country_codes OR d.country IN $country_codes OR d.country IN coalesce($country_names, [])))
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
                   coalesce(d['url'], d.link) AS url,
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
                "country_codes": country_codes,
                "country_names": country_names,
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

    def _fetch_documents_by_theme_keywords_fallback(
        self,
        *,
        start_iso: str,
        end_iso: str,
        country: Optional[str],
        country_name: Optional[str],
        country_code: Optional[str],
        country_codes: Optional[List[str]],
        country_names: Optional[List[str]],
        theme_ids: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        theme_terms = self._extract_theme_keyword_terms(theme_ids)
        if not theme_terms or limit <= 0:
            return []

        rows = self.neo4j_client.run_read(
            """
            // phase_d_documents_by_theme_keywords (fallback)
            MATCH (d:Document)
            WHERE d.published_at IS NOT NULL
              AND d.published_at >= datetime($start_iso)
              AND d.published_at <= datetime($end_iso)
              AND (
                ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL AND $country_codes IS NULL)
                OR ($country IS NOT NULL AND d.country = $country)
                OR ($country_name IS NOT NULL AND d.country = $country_name)
                OR ($country_code IS NOT NULL AND (d.country_code = $country_code OR d.country = $country_code))
                OR ($country_codes IS NOT NULL AND (d.country_code IN $country_codes OR d.country IN $country_codes OR d.country IN coalesce($country_names, [])))
              )
            WITH d,
                 [term IN $theme_terms WHERE
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
                   coalesce(d['url'], d.link) AS url,
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
                "country_codes": country_codes,
                "country_names": country_names,
                "theme_terms": theme_terms,
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

    def _fetch_evidences(
        self,
        doc_ids: List[str],
        limit: int,
        *,
        per_doc_limit: int = 3,
    ) -> List[Dict[str, Any]]:
        if not doc_ids:
            return []

        rows = self.neo4j_client.run_read(
            """
            // phase_d_evidences
            UNWIND range(0, size($doc_ids) - 1) AS doc_rank
            WITH doc_rank, $doc_ids[doc_rank] AS ordered_doc_id
            MATCH (d:Document {doc_id: ordered_doc_id})-[:HAS_EVIDENCE]->(ev:Evidence)
            WITH doc_rank, d, ev
            ORDER BY doc_rank ASC, d.published_at DESC, ev.evidence_id ASC
            WITH doc_rank, d, collect(ev)[0..$per_doc_limit] AS sampled_evidences
            UNWIND sampled_evidences AS ev
            OPTIONAL MATCH (ev)-[:SUPPORTS]->(target)
            RETURN ev.evidence_id AS evidence_id,
                   ev.text AS text,
                   d.doc_id AS doc_id,
                   coalesce(d['url'], d.link) AS doc_url,
                   d.title AS doc_title,
                   d.category AS doc_category,
                   d.published_at AS published_at,
                   collect(DISTINCT labels(target)) AS support_labels_nested,
                   collect(DISTINCT target.event_id) AS event_ids,
                   collect(DISTINCT target.claim_id) AS claim_ids,
                   doc_rank
            ORDER BY doc_rank ASC, d.published_at DESC
            LIMIT $limit
            """,
            {
                "doc_ids": doc_ids,
                "limit": limit,
                "per_doc_limit": max(int(per_doc_limit), 1),
            },
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
        normalized_route_type = _normalize_text(request.route_type).lower()
        country_input, country_name, country_code = self._resolve_country_filter(
            request.country,
            request.country_code,
        )
        has_focus_scope_hint = bool((request.focus_symbols or []) or (request.focus_companies or []))
        if (
            (normalized_route_type == US_SINGLE_STOCK_ROUTE_TYPE or has_focus_scope_hint)
            and not country_input
            and not country_name
            and not country_code
        ):
            country_code = "US"
            country_name = get_country_name(country_code)
        elif (
            not country_input
            and not country_name
            and not country_code
            and self._should_default_country_to_kr(
                question=request.question,
                route_type=normalized_route_type,
                region_code=request.region_code,
                property_type=request.property_type,
                has_focus_scope_hint=has_focus_scope_hint,
            )
        ):
            country_code = "KR"
            country_name = get_country_name(country_code)

        self._validate_scope_country(
            request_country=request.country,
            request_country_code=request.country_code,
            normalized_country_code=country_code,
        )
        scope_filters = self._resolve_country_scope_params(
            country=country_input,
            country_name=country_name,
            country_code=country_code,
        )
        normalized_region_code, normalized_region_group_count = self._normalize_region_code(
            request.region_code,
            question=request.question,
        )
        normalized_property_type = self._normalize_property_type(
            request.property_type,
            question=request.question,
        )
        normalized_compare_mode = self._normalize_compare_mode(
            request.compare_mode,
            question=request.question,
            country_code=country_code,
            region_group_count=normalized_region_group_count,
        )
        normalized_focus_symbols = self._normalize_focus_symbols(request.focus_symbols)
        normalized_focus_companies = self._normalize_focus_companies(request.focus_companies)
        expanded_companies = self._expand_focus_companies_from_symbols(normalized_focus_symbols)
        normalized_company_keys = {item.lower() for item in normalized_focus_companies}
        for company in expanded_companies:
            company_key = company.lower()
            if company_key not in normalized_company_keys:
                normalized_focus_companies.append(company)
                normalized_company_keys.add(company_key)
        normalized_focus_companies = normalized_focus_companies[:16]

        matched_theme_ids = self._resolve_theme_candidates(
            question=request.question,
            start_iso=start_iso,
            end_iso=end_iso,
            country=scope_filters.get("country"),
            country_name=scope_filters.get("country_name"),
            country_code=scope_filters.get("country_code"),
            country_codes=scope_filters.get("country_codes"),
            country_names=scope_filters.get("country_names"),
        )
        matched_indicator_codes = self._resolve_indicator_candidates(request.question)
        question_terms = self._extract_question_search_terms(request.question)

        events = self._fetch_events(
            start_iso=start_iso,
            end_iso=end_iso,
            country=scope_filters.get("country"),
            country_name=scope_filters.get("country_name"),
            country_code=scope_filters.get("country_code"),
            country_codes=scope_filters.get("country_codes"),
            country_names=scope_filters.get("country_names"),
            theme_filter=matched_theme_ids,
            indicator_filter=matched_indicator_codes,
            limit=request.top_k_events,
        )
        event_ids = [row["event_id"] for row in events if row.get("event_id")]

        base_documents = self._fetch_documents(
            start_iso=start_iso,
            end_iso=end_iso,
            country=scope_filters.get("country"),
            country_name=scope_filters.get("country_name"),
            country_code=scope_filters.get("country_code"),
            country_codes=scope_filters.get("country_codes"),
            country_names=scope_filters.get("country_names"),
            theme_filter=matched_theme_ids,
            event_filter=event_ids,
            limit=request.top_k_documents,
        )

        # Hybrid Search 1) BM25 full-text 후보
        keyword_documents = self._fetch_documents_by_fulltext(
            start_iso=start_iso,
            end_iso=end_iso,
            country=scope_filters.get("country"),
            country_name=scope_filters.get("country_name"),
            country_code=scope_filters.get("country_code"),
            country_codes=scope_filters.get("country_codes"),
            country_names=scope_filters.get("country_names"),
            question=request.question,
            limit=request.top_k_documents,
        )

        # Hybrid Search 2) Vector 후보 (질문 임베딩 기반)
        query_embedding = self._embed_query_vector(request.question) if self.vector_search_enabled else None
        vector_documents: List[Dict[str, Any]] = []
        if query_embedding:
            vector_documents = self._fetch_documents_by_vector(
                start_iso=start_iso,
                end_iso=end_iso,
                country=scope_filters.get("country"),
                country_name=scope_filters.get("country_name"),
                country_code=scope_filters.get("country_code"),
                country_codes=scope_filters.get("country_codes"),
                country_names=scope_filters.get("country_names"),
                query_embedding=query_embedding,
                limit=request.top_k_documents,
            )

        # Hybrid Search 3) CONTAINS fallback 후보
        fallback_documents: List[Dict[str, Any]] = []
        if question_terms and len(keyword_documents) < request.top_k_documents:
            # Full-text만으로 놓칠 수 있는 인물명/복합 키워드 문서를 보강한다.
            fallback_documents = self._fetch_documents_by_question_terms_fallback(
                start_iso=start_iso,
                end_iso=end_iso,
                country=scope_filters.get("country"),
                country_name=scope_filters.get("country_name"),
                country_code=scope_filters.get("country_code"),
                country_codes=scope_filters.get("country_codes"),
                country_names=scope_filters.get("country_names"),
                question=request.question,
                limit=request.top_k_documents,
            )

        theme_keyword_documents: List[Dict[str, Any]] = []
        if matched_theme_ids and (not question_terms or len(base_documents) < request.top_k_documents):
            # ABOUT_THEME 링크 누락 문서를 보강하기 위해 테마 키워드 텍스트 매칭을 병행한다.
            theme_keyword_documents = self._fetch_documents_by_theme_keywords_fallback(
                start_iso=start_iso,
                end_iso=end_iso,
                country=scope_filters.get("country"),
                country_name=scope_filters.get("country_name"),
                country_code=scope_filters.get("country_code"),
                country_codes=scope_filters.get("country_codes"),
                country_names=scope_filters.get("country_names"),
                theme_ids=matched_theme_ids,
                limit=request.top_k_documents,
            )
        merged_fallback_documents = fallback_documents + theme_keyword_documents

        stock_documents: List[Dict[str, Any]] = []
        has_stock_focus = bool(normalized_focus_symbols or normalized_focus_companies)
        if has_stock_focus:
            stock_documents = self._fetch_documents_for_us_single_stock(
                start_iso=start_iso,
                end_iso=end_iso,
                country=scope_filters.get("country"),
                country_name=scope_filters.get("country_name"),
                country_code=scope_filters.get("country_code"),
                country_codes=scope_filters.get("country_codes"),
                country_names=scope_filters.get("country_names"),
                focus_symbols=normalized_focus_symbols,
                focus_companies=normalized_focus_companies,
                limit=request.top_k_documents,
            )

        documents, retrieval_meta = self._merge_hybrid_documents(
            base_documents=base_documents,
            keyword_documents=keyword_documents,
            fallback_documents=merged_fallback_documents,
            vector_documents=vector_documents,
            stock_documents=stock_documents,
            limit=request.top_k_documents,
        )
        retrieval_meta["theme_keyword_docs"] = len(theme_keyword_documents)
        recent_doc_priority_count = max(
            _safe_int(os.getenv("GRAPH_RAG_RECENT_DOC_PRIORITY_COUNT"), 8),
            0,
        )
        retrieval_meta["recent_doc_priority_count"] = recent_doc_priority_count

        doc_ids = self._prioritize_evidence_doc_ids(
            documents=documents,
            route_type=normalized_route_type,
            prioritize_stock_focus=has_stock_focus,
            recent_doc_priority_count=recent_doc_priority_count,
        )
        scope_warnings = self._build_scope_warning_summary(
            events=events,
            documents=documents,
            requested_country_codes=set(scope_filters.get("country_codes") or []),
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
        evidences = self._fetch_evidences(
            doc_ids=doc_ids,
            limit=request.top_k_evidences,
            per_doc_limit=2 if (normalized_route_type == US_SINGLE_STOCK_ROUTE_TYPE or has_stock_focus) else 3,
        )

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

        node_ids = set(nodes.keys())
        filtered_links = [
            link
            for link in links
            if str(link.get("source") or "").strip() in node_ids
            and str(link.get("target") or "").strip() in node_ids
        ]
        dangling_link_count = len(links) - len(filtered_links)
        if dangling_link_count > 0:
            logger.warning(
                "[GraphRAGContext] removed dangling links(count=%s)",
                dangling_link_count,
            )
        links = filtered_links

        normalized_evidences: List[Dict[str, Any]] = []
        seen_evidence_keys: Set[Tuple[Optional[str], Optional[str], str]] = set()
        for row in evidences:
            raw_support_labels = row.get("support_labels")
            if not raw_support_labels:
                nested_labels = row.get("support_labels_nested") or []
                flattened_labels: List[str] = []
                for labels in nested_labels:
                    for label in labels or []:
                        label_text = str(label or "").strip()
                        if label_text:
                            flattened_labels.append(label_text)
                raw_support_labels = flattened_labels
            support_labels: List[str] = []
            seen_support_labels: Set[str] = set()
            for label in raw_support_labels or []:
                label_text = str(label or "").strip()
                if not label_text or label_text in seen_support_labels:
                    continue
                seen_support_labels.add(label_text)
                support_labels.append(label_text)

            event_id = row.get("event_id")
            if not event_id:
                event_candidates = [str(item) for item in (row.get("event_ids") or []) if str(item or "").strip()]
                event_id = event_candidates[0] if event_candidates else None

            claim_id = row.get("claim_id")
            if not claim_id:
                claim_candidates = [str(item) for item in (row.get("claim_ids") or []) if str(item or "").strip()]
                claim_id = claim_candidates[0] if claim_candidates else None

            evidence_key = (
                row.get("evidence_id"),
                row.get("doc_id"),
                str(row.get("text") or ""),
            )
            if evidence_key in seen_evidence_keys:
                continue
            seen_evidence_keys.add(evidence_key)
            normalized_evidences.append(
                {
                    "evidence_id": row.get("evidence_id"),
                    "text": row.get("text") or "",
                    "doc_id": row.get("doc_id"),
                    "doc_url": row.get("doc_url"),
                    "doc_title": row.get("doc_title"),
                    "doc_category": row.get("doc_category"),
                    "published_at": _to_json_value(row.get("published_at")),
                    "support_labels": support_labels,
                    "event_id": event_id,
                    "claim_id": claim_id,
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
            "compare_mode": request.compare_mode,
            "region_code": request.region_code,
            "property_type": request.property_type,
            "route_type": request.route_type,
            "focus_symbols": request.focus_symbols,
            "focus_companies": request.focus_companies,
            "resolved_country": country_input or country_name,
            "resolved_country_code": country_code,
            "resolved_country_codes": scope_filters.get("country_codes"),
            "resolved_country_names": scope_filters.get("country_names"),
            "parsed_scope": {
                "compare_mode": normalized_compare_mode,
                "region_code": normalized_region_code,
                "region_group_count": normalized_region_group_count,
                "property_type": normalized_property_type,
                "route_type": normalized_route_type or None,
                "focus_symbols": normalized_focus_symbols,
                "focus_companies": normalized_focus_companies,
            },
            "scope_allowed_country_codes": sorted(SUPPORTED_QA_COUNTRY_CODES),
            "scope_warnings": scope_warnings.get("messages", []),
            "scope_violation_counts": scope_warnings.get("counts", {}),
            "scope_violation_samples": scope_warnings.get("samples", []),
            "matched_theme_ids": matched_theme_ids,
            "matched_indicator_codes": matched_indicator_codes,
            "question_terms": question_terms[:10],
            "retrieval": {
                **retrieval_meta,
                "query_embedding_model": self.query_embedding_model,
                "query_embedding_dimension": self.query_embedding_dimension,
                "query_embedding_used": bool(query_embedding),
            },
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
