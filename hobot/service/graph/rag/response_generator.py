"""
Phase D-2: GraphRAG response generator.
"""

import json
import logging
import os
import re
import time
import uuid
import hashlib
import html
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote_plus
from typing import Any, Dict, List, Optional, Set
import xml.etree.ElementTree as ET

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import requests

from service import auth
from service.llm_monitoring import reset_llm_flow_context, set_llm_flow_context, track_llm_call

from service.llm import llm_gemini_flash, llm_gemini_pro
from service.database.db import get_db_connection
from service.graph.monitoring import GraphRagApiCallLogger
from service.graph.neo4j_client import get_neo4j_client
from service.graph.normalization.country_mapping import get_country_name, normalize_country
from service.graph.state import AnalysisRunWriter, MacroStateGenerator

from .context_api import (
    GraphEvidence,
    GraphRagContextRequest,
    GraphRagContextResponse,
    SUPPORTED_QA_COUNTRY_CODES,
    build_graph_rag_context,
)
from .agents import execute_agent_stub
from .kr_region_scope import LAWD_NAME_BY_CODE
from .security_id import infer_country_for_symbol, normalize_native_code, parse_security_id, to_security_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph/rag", tags=["graph-rag"])

ALLOWED_GRAPH_RAG_MODELS = {"gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-pro-preview"}
DEFAULT_GRAPH_RAG_MODEL = "gemini-3-pro-preview"
SUPERVISOR_AGENT_MODEL = "gemini-3-pro-preview"
ONTOLOGY_MASTER_AGENT_MODEL = "gemini-3-pro-preview"
DOMAIN_AGENT_MODEL = "gemini-3-flash-preview"
ROUTER_INTENT_MODEL = "gemini-2.5-flash"
LIGHTWEIGHT_UTILITY_MODEL = "gemini-2.5-flash"
DEFAULT_AGENT_MODEL_POLICY = {
    "supervisor_agent": SUPERVISOR_AGENT_MODEL,
    "ontology_master_agent": ONTOLOGY_MASTER_AGENT_MODEL,
    "macro_economy_agent": DOMAIN_AGENT_MODEL,
    "equity_analyst_agent": DOMAIN_AGENT_MODEL,
    "real_estate_agent": DOMAIN_AGENT_MODEL,
    "general_knowledge_agent": DOMAIN_AGENT_MODEL,
    "router_intent_classifier": ROUTER_INTENT_MODEL,
    "query_rewrite_utility": LIGHTWEIGHT_UTILITY_MODEL,
    "query_normalization_utility": LIGHTWEIGHT_UTILITY_MODEL,
    "citation_postprocess_utility": LIGHTWEIGHT_UTILITY_MODEL,
}
KR_TOP50_SCOPE_MESSAGE = "현재 수집 범위(Top50) 밖으로 데이터를 보유하고 있지 않습니다."
KR_TOP50_SCOPE_FOLLOWUP = "온디맨드 수집은 추후 지원 예정입니다."
KR_CORPORATE_QUESTION_KEYWORDS = {
    "기업",
    "회사",
    "종목",
    "주식",
    "실적",
    "매출",
    "영업이익",
    "당기순이익",
    "eps",
    "per",
    "시총",
    "주가",
}
KR_CORPORATE_TOKEN_STOPWORDS = {
    "한국",
    "국내",
    "코스피",
    "코스닥",
    "기업",
    "회사",
    "종목",
    "주식",
    "실적",
    "매출",
    "영업이익",
    "당기순이익",
    "비교",
    "전망",
    "분석",
    "요약",
    "최근",
    "현재",
}
US_STOCK_QUESTION_KEYWORDS = {
    "주가",
    "종목",
    "티커",
    "기업",
    "회사",
    "실적",
    "매출",
    "이익",
    "eps",
    "per",
    "stock",
    "stocks",
    "ticker",
    "company",
    "companies",
    "equity",
    "earnings",
    "guidance",
    "valuation",
}
US_TICKER_TOKEN_STOPWORDS = {
    "A",
    "AN",
    "THE",
    "AND",
    "OR",
    "TO",
    "FOR",
    "OF",
    "IN",
    "ON",
    "AT",
    "IS",
    "ARE",
    "US",
    "KR",
    "USD",
    "KRW",
    "CPI",
    "PCE",
    "GDP",
    "PMI",
    "ISM",
    "FOMC",
    "FED",
    "VIX",
    "DXY",
    "RRP",
    "TGA",
    "PPI",
    "NFP",
    "YOY",
    "MOM",
    "QOQ",
    "AI",
}
US_COMPANY_TOKEN_STOPWORDS = {
    "미국",
    "국내",
    "해외",
    "시장",
    "매크로",
    "지표",
    "환율",
    "금리",
    "물가",
    "주가",
    "종목",
    "회사",
    "기업",
    "티커",
    "비교",
    "전망",
    "분석",
    "요약",
    "최근",
    "현재",
    "오늘",
    "어때",
    "어때요",
    "어떤",
    "무엇",
    "what",
    "how",
    "about",
    "stock",
    "stocks",
    "ticker",
    "company",
    "companies",
    "equity",
    "macro",
    "market",
}
US_SINGLE_STOCK_ALIAS_HINTS = {
    "palantir": "PLTR",
    "palantirtechnologies": "PLTR",
    "팔란티어": "PLTR",
    "snowflake": "SNOW",
    "스노우플레이크": "SNOW",
    "apple": "AAPL",
    "애플": "AAPL",
    "microsoft": "MSFT",
    "마이크로소프트": "MSFT",
    "nvidia": "NVDA",
    "엔비디아": "NVDA",
    "amazon": "AMZN",
    "아마존": "AMZN",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "알파벳": "GOOGL",
    "구글": "GOOGL",
    "meta": "META",
    "메타": "META",
    "tesla": "TSLA",
    "테슬라": "TSLA",
}
US_SINGLE_STOCK_SYMBOL_COMPANY_HINTS = {
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
US_SINGLE_STOCK_ROUTE_TYPE = "us_single_stock"
GENERAL_KNOWLEDGE_ROUTE_TYPE = "general_knowledge"
US_SINGLE_STOCK_TEMPLATE_SPECS = [
    (
        "가격/변동률",
        {
            "price",
            "stock",
            "shares",
            "rose",
            "fell",
            "higher",
            "lower",
            "surged",
            "plunged",
            "상승",
            "하락",
            "급등",
            "급락",
            "주가",
            "등락",
            "%",
        },
        "제공 근거에서 해당 종목의 가격/등락률 직접 수치를 확인하지 못했습니다(근거 불충분).",
    ),
    (
        "실적",
        {
            "earnings",
            "eps",
            "revenue",
            "guidance",
            "profit",
            "margin",
            "실적",
            "매출",
            "이익",
            "영업이익",
            "가이던스",
        },
        "제공 근거에서 최근 실적/가이던스 직접 근거를 확인하지 못했습니다(근거 불충분).",
    ),
    (
        "밸류",
        {
            "valuation",
            "multiple",
            "p/e",
            "per",
            "p/s",
            "ev/ebitda",
            "premium",
            "discount",
            "밸류",
            "밸류에이션",
            "고평가",
            "저평가",
        },
        "제공 근거에서 밸류에이션(멀티플/프리미엄) 직접 근거를 확인하지 못했습니다(근거 불충분).",
    ),
    (
        "리스크",
        {
            "risk",
            "volatility",
            "uncertainty",
            "skepticism",
            "selloff",
            "drawdown",
            "pressure",
            "capex",
            "리스크",
            "변동성",
            "불확실",
            "매도",
            "하방",
        },
        "제공 근거에서 핵심 하방 리스크를 직접 확인하기 어렵습니다(근거 불충분).",
    ),
]
US_SINGLE_STOCK_STRICT_SECTION_LABELS = {"가격/변동률", "실적", "밸류"}
US_STOCK_PERCENT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s?%")
US_STOCK_PRICE_PATTERN = re.compile(r"(?:\$|usd\s*)\d+(?:,\d{3})*(?:\.\d+)?", flags=re.IGNORECASE)
US_STOCK_PRICE_ACTION_KEYWORDS = {
    "rose",
    "fell",
    "higher",
    "lower",
    "surged",
    "plunged",
    "jumped",
    "slid",
    "상승",
    "하락",
    "급등",
    "급락",
    "등락",
}
US_STOCK_BULLISH_KEYWORDS = {
    "rose",
    "higher",
    "surged",
    "jumped",
    "gained",
    "rebounded",
    "rallied",
    "상승",
    "급등",
    "강세",
    "반등",
    "오름",
}
US_STOCK_BEARISH_KEYWORDS = {
    "fell",
    "lower",
    "plunged",
    "slid",
    "dropped",
    "sank",
    "selloff",
    "weighed",
    "하락",
    "급락",
    "약세",
    "매도",
    "하방",
}
US_STOCK_BULLISH_CONCLUSION_KEYWORDS = {
    "긍정",
    "강세",
    "상승",
    "우상향",
    "추가 상승",
    "급등",
    "반등",
    "positive",
    "bullish",
    "uptrend",
}
SUPPORTED_QUESTION_IDS = {"Q1", "Q2", "Q3", "Q4", "Q5", "Q6"}
QUESTION_ID_SPECS = {
    "Q1": {"answer_type": "explain_drop", "country_code": "US"},
    "Q2": {"answer_type": "compare_outlook", "country_code": "US"},
    "Q3": {"answer_type": "market_summary", "country_code": "KR"},
    "Q4": {"answer_type": "sector_recommendation", "country_code": "KR"},
    "Q5": {"answer_type": "fx_driver", "country_code": "US-KR"},
    "Q6": {"answer_type": "timing_scenario", "country_code": "KR"},
}
ANSWER_TYPE_TO_QUESTION_ID = {
    "explain_drop": "Q1",
    "compare_outlook": "Q2",
    "market_summary": "Q3",
    "sector_recommendation": "Q4",
    "fx_driver": "Q5",
    "timing_scenario": "Q6",
}
QUERY_TYPE_TO_PROMPT_GUIDANCE = {
    "explain_drop": "Focus on downside drivers and causal chain. Avoid unsupported blame.",
    "compare_outlook": "Compare with the same metric frame and highlight relative strengths/risks.",
    "market_summary": "Summarize regime, trend, and risks in a balanced way.",
    "sector_recommendation": "Use conditional scenarios, not direct recommendation commands.",
    "fx_driver": "Explain FX move with cross-market drivers (rates, risk sentiment, flows).",
    "timing_scenario": "Provide threshold-based timing scenarios only, no direct buy/sell order.",
    "us_single_stock": "Treat this as a US single-stock query. Prioritize company-specific evidence and clearly state insufficiency if missing.",
    "real_estate_detail": "Include region/property-type context and price-volume interpretation.",
    "indicator_lookup": "Prioritize latest indicator values and data freshness caveat.",
    "general_macro": "Use concise macro narrative grounded in provided evidence.",
    "general_knowledge": "Answer directly with model knowledge only. Do not use internal graph/sql context.",
}
ROUTER_QUERY_TYPES = set(QUERY_TYPE_TO_PROMPT_GUIDANCE.keys())
CONDITIONAL_SCENARIO_ROUTE_TYPES = {"sector_recommendation", "timing_scenario"}
CONDITIONAL_SCENARIO_QUESTION_IDS = {"Q4", "Q6"}
DIRECT_BUY_SELL_PATTERN = re.compile(
    r"(무조건|지금|당장|즉시).{0,12}(매수|매도|사라|사세요|팔라|파세요)|"
    r"(매수|매도).{0,6}(하세요|하라)|"
    r"\b(buy|sell)\s+now\b",
    flags=re.IGNORECASE,
)
STATEMENT_KEEP_KEYWORDS = {
    "근거 불충분",
    "불확실",
    "한계",
    "재확인",
}
SUPPORT_TOKEN_STOPWORDS = {
    "그리고",
    "하지만",
    "또한",
    "the",
    "and",
    "with",
    "that",
    "this",
    "from",
    "market",
    "data",
}
STRUCTURED_CITATION_SUPPORT_ALIASES: Dict[str, Set[str]] = {
    "KR_REAL_ESTATE_MONTHLY_SUMMARY": {
        "부동산",
        "실거래",
        "가격",
        "거래량",
        "월간",
        "평균가",
        "전월",
    },
    "KR_REAL_ESTATE_TRANSACTIONS": {
        "부동산",
        "실거래",
        "거래",
        "계약",
        "가격",
        "면적",
    },
}
BUY_SELL_TEXT_PATTERN = re.compile(
    r"(매수|매도|사라|사세요|팔라|파세요|\bbuy\b|\bsell\b)",
    flags=re.IGNORECASE,
)
PROPERTY_TYPE_LABELS = {
    "apartment": "아파트",
    "apartment_sale": "아파트 매매",
    "officetel": "오피스텔",
    "multi_family": "연립/다세대",
    "single_family": "단독/다가구",
    "jeonse": "전세",
    "monthly_rent": "월세",
    "rent": "임대(통합)",
}
SQL_NEED_HINT_KEYWORDS = {
    "ohlcv",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "시가",
    "고가",
    "저가",
    "종가",
    "거래량",
    "수익률",
    "변동률",
    "실적",
    "매출",
    "영업이익",
    "가이던스",
    "eps",
    "per",
    "pbr",
    "시총",
    "실거래",
    "매매가",
    "전세",
    "월세",
    "지표값",
    "수치",
    "숫자",
    "최근값",
    "최신값",
    "cpi",
    "pce",
    "gdp",
    "실업률",
    "금리",
    "환율",
}
GRAPH_NEED_HINT_KEYWORDS = {
    "왜",
    "원인",
    "영향",
    "경로",
    "관계",
    "전망",
    "리스크",
    "시나리오",
    "테마",
    "이벤트",
    "뉴스",
    "설명",
    "explain",
    "impact",
    "theme",
    "event",
    "story",
}
EQUITY_HINT_KEYWORDS = {
    "주가",
    "종목",
    "티커",
    "기업",
    "회사",
    "주식",
    "ohlcv",
    "실적",
    "가이던스",
    "eps",
    "per",
    "pbr",
    "밸류",
}
REAL_ESTATE_HINT_KEYWORDS = {
    "부동산",
    "아파트",
    "전세",
    "월세",
    "실거래",
    "매매가",
    "거래가",
}
ONTOLOGY_HINT_KEYWORDS = {
    "관계",
    "경로",
    "연결",
    "그래프",
    "지식그래프",
    "impact",
    "path",
}
GENERAL_KNOWLEDGE_HINT_KEYWORDS = {
    "날씨",
    "weather",
    "기온",
    "습도",
    "체감",
    "비와",
    "비 올",
    "우산",
    "미세먼지",
    "황사",
}
GENERAL_KNOWLEDGE_EXCLUDE_KEYWORDS = (
    SQL_NEED_HINT_KEYWORDS
    | GRAPH_NEED_HINT_KEYWORDS
    | EQUITY_HINT_KEYWORDS
    | REAL_ESTATE_HINT_KEYWORDS
    | ONTOLOGY_HINT_KEYWORDS
    | {"주식", "금융", "증시", "환율", "금리", "부동산", "매크로", "지표"}
)
US_DAILY_MACRO_REFERENCE_EXCLUDED_ROUTE_TYPES = {
    GENERAL_KNOWLEDGE_ROUTE_TYPE,
    US_SINGLE_STOCK_ROUTE_TYPE,
    "compare_outlook",
    "fx_driver",
}
US_DAILY_MACRO_REFERENCE_PRIMARY_ROUTE_TYPES = {
    "real_estate_detail",
    "market_summary",
    "sector_recommendation",
    "timing_scenario",
}
KR_SCOPE_HINT_KEYWORDS = {
    "한국",
    "국내",
    "korea",
    "south korea",
    "kr",
    "코스피",
    "코스닥",
    "부동산",
    "아파트",
    "전세",
    "월세",
}
US_DAILY_MACRO_REFERENCE_MAX_CHARS = 900
INTERNAL_REFERENCE_TOKEN_PATTERN = re.compile(r"\b(?:EVT|EV|EVID|CLM)_[A-Za-z0-9]+\b")
REAL_ESTATE_TIMESERIES_LIMIT_PATTERN = re.compile(
    r"시계열[^.。\n]{0,40}(한계|불가|어렵|제약|부재)|스냅샷",
    re.IGNORECASE,
)


class GraphRagAnswerRequest(BaseModel):
    question: str = Field(..., min_length=3)
    question_id: Optional[str] = None
    time_range: str = Field(default="30d")
    country: Optional[str] = None
    country_code: Optional[str] = None
    compare_mode: Optional[str] = None
    region_code: Optional[str] = None
    property_type: Optional[str] = None
    as_of_date: Optional[date] = None
    top_k_events: int = Field(default=25, ge=5, le=100)
    top_k_documents: int = Field(default=40, ge=5, le=200)
    top_k_stories: int = Field(default=20, ge=5, le=100)
    top_k_evidences: int = Field(default=40, ge=5, le=200)
    model: str = Field(default=DEFAULT_GRAPH_RAG_MODEL)
    timeout_sec: int = Field(default=60, ge=10, le=180)
    max_prompt_evidences: int = Field(default=12, ge=3, le=50)
    include_context: bool = Field(default=False)
    reuse_cached_run: bool = Field(default=True)
    persist_macro_state: bool = Field(default=True)
    persist_analysis_run: bool = Field(default=True)
    state_theme_window_days: int = Field(default=14, ge=3, le=90)
    state_top_themes: int = Field(default=3, ge=1, le=10)
    state_top_signals: int = Field(default=8, ge=1, le=30)

    @staticmethod
    def _normalize_focus_list(values: Any) -> List[str]:
        if not isinstance(values, list):
            return []

        normalized: List[str] = []
        seen: Set[str] = set()
        for value in values:
            token = str(value or "").strip()
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(token)
        return normalized

    @staticmethod
    def _extract_symbols_from_security_ids(values: Any) -> List[str]:
        if not isinstance(values, list):
            return []
        symbols: List[str] = []
        seen: Set[str] = set()
        for value in values:
            country, native = parse_security_id(value)
            symbol = native if country and native else str(value or "").strip()
            if not symbol:
                continue
            key = symbol.lower()
            if key in seen:
                continue
            seen.add(key)
            symbols.append(symbol)
        return symbols

    @classmethod
    def _extract_route_focus(cls, route_meta: Dict[str, Any]) -> tuple[List[str], List[str]]:
        matched_symbols = cls._normalize_focus_list(route_meta.get("matched_symbols"))
        if not matched_symbols:
            matched_symbols = cls._extract_symbols_from_security_ids(route_meta.get("matched_security_ids"))
        matched_companies = cls._normalize_focus_list(route_meta.get("matched_companies"))
        if matched_symbols or matched_companies:
            return matched_symbols, matched_companies

        agents = route_meta.get("agents")
        if not isinstance(agents, list):
            return matched_symbols, matched_companies

        normalized_agents = [agent for agent in agents if isinstance(agent, dict)]
        prioritized_agents = [
            agent
            for agent in normalized_agents
            if str(agent.get("agent") or "").strip() == "us_single_stock_agent"
        ]
        if not prioritized_agents:
            selected_type = str(route_meta.get("selected_type") or "").strip()
            if selected_type:
                prioritized_agents = [
                    agent
                    for agent in normalized_agents
                    if str(agent.get("selected_type") or "").strip() == selected_type
                ]
        if not prioritized_agents:
            prioritized_agents = normalized_agents

        for agent in prioritized_agents:
            if not matched_symbols:
                matched_symbols = cls._normalize_focus_list(agent.get("matched_symbols"))
                if not matched_symbols:
                    matched_symbols = cls._extract_symbols_from_security_ids(agent.get("matched_security_ids"))
            if not matched_companies:
                matched_companies = cls._normalize_focus_list(agent.get("matched_companies"))
            if matched_symbols or matched_companies:
                break

        return matched_symbols, matched_companies

    def to_context_request(self, route: Optional[Dict[str, Any]] = None) -> GraphRagContextRequest:
        route_meta = route or {}
        selected_type = str(route_meta.get("selected_type") or "").strip()
        graph_need = bool(route_meta.get("graph_need")) if "graph_need" in route_meta else True
        matched_symbols, matched_companies = self._extract_route_focus(route_meta)
        top_k_events = self.top_k_events
        top_k_documents = self.top_k_documents
        top_k_stories = self.top_k_stories
        top_k_evidences = self.top_k_evidences

        # Graph branch가 비활성일 때는 컨텍스트 조회량을 보수적으로 줄여
        # supervisor 입력 토큰 폭증을 방지한다.
        if not graph_need:
            top_k_events = min(top_k_events, 8)
            top_k_documents = min(top_k_documents, 12)
            top_k_stories = min(top_k_stories, 6)
            top_k_evidences = min(top_k_evidences, 10)
            if selected_type == "real_estate_detail":
                top_k_events = min(top_k_events, 5)
                top_k_documents = min(top_k_documents, 8)
                top_k_stories = min(top_k_stories, 4)
                top_k_evidences = min(top_k_evidences, 8)

        return GraphRagContextRequest(
            question=self.question,
            time_range=self.time_range,
            country=self.country,
            country_code=self.country_code,
            compare_mode=self.compare_mode,
            region_code=self.region_code,
            property_type=self.property_type,
            route_type=selected_type or None,
            focus_symbols=matched_symbols,
            focus_companies=matched_companies,
            as_of_date=self.as_of_date,
            top_k_events=top_k_events,
            top_k_documents=top_k_documents,
            top_k_stories=top_k_stories,
            top_k_evidences=top_k_evidences,
        )


class GraphRagPathway(BaseModel):
    event_id: Optional[str] = None
    theme_id: Optional[str] = None
    indicator_code: Optional[str] = None
    explanation: str


class GraphRagCitation(BaseModel):
    evidence_id: Optional[str] = None
    doc_id: Optional[str] = None
    doc_url: Optional[str] = None
    doc_title: Optional[str] = None
    published_at: Optional[str] = None
    text: str
    support_labels: List[str] = Field(default_factory=list)
    node_ids: List[str] = Field(default_factory=list)


class GraphRagStructuredCitation(BaseModel):
    dataset_code: str
    table: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    date_range: Optional[str] = None
    as_of_date: Optional[str] = None
    query_fingerprint: Optional[str] = None
    row_count: Optional[int] = None
    source: Optional[str] = "sql"
    agent: Optional[str] = None
    branch: Optional[str] = None
    status: Optional[str] = None
    template_id: Optional[str] = None


class GraphRagAnswerPayload(BaseModel):
    conclusion: str
    uncertainty: str
    key_points: List[str] = Field(default_factory=list)
    impact_pathways: List[GraphRagPathway] = Field(default_factory=list)
    confidence_level: Optional[str] = None
    confidence_score: Optional[float] = None
    evidence_policy: str = "Evidence-grounded only"


class GraphRagAnswerResponse(BaseModel):
    question: str
    model: str
    as_of_date: str
    answer: GraphRagAnswerPayload
    citations: List[GraphRagCitation] = Field(default_factory=list)
    structured_citations: List[GraphRagStructuredCitation] = Field(default_factory=list)
    suggested_queries: List[str] = Field(default_factory=list)
    context_meta: Dict[str, Any] = Field(default_factory=dict)
    analysis_run_id: Optional[str] = None
    persistence: Dict[str, Any] = Field(default_factory=dict)
    data_freshness: Dict[str, Any] = Field(default_factory=dict)
    collection_eta_minutes: Optional[int] = None
    used_evidence_count: int = 0
    raw_model_output: Optional[Dict[str, Any]] = None
    context: Optional[GraphRagContextResponse] = None


def resolve_graph_rag_model(requested_model: Optional[str]) -> str:
    model_name = (requested_model or "").strip()
    if model_name in ALLOWED_GRAPH_RAG_MODELS:
        return model_name
    logger.warning(
        "Unsupported GraphRAG model '%s'. Fallback to '%s'.",
        requested_model,
        DEFAULT_GRAPH_RAG_MODEL,
    )
    return DEFAULT_GRAPH_RAG_MODEL


def _resolve_graph_rag_user_id(http_request: Optional[Request]) -> str:
    """요청 헤더의 Bearer 토큰에서 사용자 식별자를 추출한다."""
    if http_request is None:
        return "system"

    auth_header = str(http_request.headers.get("Authorization") or "").strip()
    if not auth_header:
        return "anonymous"

    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return "anonymous"

    token = parts[1].strip()
    if not token:
        return "anonymous"

    try:
        payload = auth.verify_token(token)
    except Exception:
        return "anonymous"

    if not isinstance(payload, dict):
        return "anonymous"

    for key in ("id", "user_id", "username", "sub"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return "anonymous"


def _resolve_country_filter(
    country: Optional[str],
    country_code: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    raw_country = (country or "").strip() or None
    raw_country_code = (country_code or "").strip().upper() or None
    if raw_country_code in {"USKR", "KRUS", "US/KR", "KR/US", "KR-US"}:
        raw_country_code = "US-KR"

    normalized_code = raw_country_code or normalize_country(raw_country or "")
    raw_country_lower = str(raw_country or "").strip().lower()
    if not normalized_code and raw_country_lower in {"us-kr", "kr-us", "us/kr", "kr/us", "미국한국", "한미", "미국-한국"}:
        normalized_code = "US-KR"
    normalized_name = get_country_name(normalized_code) if normalized_code else None
    if normalized_name and normalized_name == normalized_code:
        normalized_name = None

    return raw_country, normalized_name, normalized_code


def _validate_scope_country(
    request_country: Optional[str],
    request_country_code: Optional[str],
    normalized_country_code: Optional[str],
) -> None:
    has_scope_input = bool((request_country or "").strip() or (request_country_code or "").strip())
    if not has_scope_input:
        return

    if not normalized_country_code:
        allowed = ", ".join(sorted(SUPPORTED_QA_COUNTRY_CODES))
        raise ValueError(f"country scope must resolve to one of: {allowed}")

    if normalized_country_code not in SUPPORTED_QA_COUNTRY_CODES:
        allowed = ", ".join(sorted(SUPPORTED_QA_COUNTRY_CODES))
        raise ValueError(f"country_code '{normalized_country_code}' is not supported in Phase 1 scope ({allowed})")


def _extract_stock_codes(question: str) -> List[str]:
    if not question:
        return []
    found = re.findall(r"\b(\d{6})\b", question)
    return list(dict.fromkeys(found))


def _extract_corporate_tokens(question: str) -> List[str]:
    if not question:
        return []
    tokens = re.findall(r"[가-힣A-Za-z][가-힣A-Za-z0-9&\.\-]{1,20}", question)
    normalized = []
    for token in tokens:
        text = str(token or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in KR_CORPORATE_TOKEN_STOPWORDS:
            continue
        if len(text) < 2:
            continue
        normalized.append(text)
    return list(dict.fromkeys(normalized))[:12]


def _is_likely_kr_corporate_question(question: str, normalized_country_code: Optional[str]) -> bool:
    lowered = (question or "").lower()
    has_keyword = any(keyword in lowered for keyword in KR_CORPORATE_QUESTION_KEYWORDS)
    has_stock_code = bool(_extract_stock_codes(question))
    has_tokens = bool(_extract_corporate_tokens(question))

    if normalized_country_code in {"KR", "US-KR"}:
        return has_keyword or has_stock_code or has_tokens
    if normalized_country_code and normalized_country_code not in {"KR", "US-KR"}:
        return False
    if has_keyword and (has_tokens or has_stock_code):
        return True
    return False


def _load_latest_kr_top50_universe() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT snapshot_date
            FROM kr_top50_universe_snapshot
            WHERE market = 'KOSPI'
            ORDER BY snapshot_date DESC, captured_at DESC, id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone() or {}
        snapshot_date = row.get("snapshot_date")
        if not snapshot_date:
            return []
        cursor.execute(
            """
            SELECT rank_position, stock_code, stock_name, corp_code, snapshot_date
            FROM kr_top50_universe_snapshot
            WHERE market = 'KOSPI'
              AND snapshot_date = %s
            ORDER BY rank_position ASC
            """,
            (snapshot_date,),
        )
        rows = cursor.fetchall() or []
    return list(rows)


def _load_mentioned_kr_corporates(question: str) -> List[Dict[str, Any]]:
    stock_codes = _extract_stock_codes(question)
    corp_tokens = _extract_corporate_tokens(question)
    if not stock_codes and not corp_tokens:
        return []

    conditions: List[str] = []
    params: List[Any] = []
    if stock_codes:
        placeholders = ", ".join(["%s"] * len(stock_codes))
        conditions.append(f"stock_code IN ({placeholders})")
        params.extend(stock_codes)
    for token in corp_tokens:
        conditions.append("corp_name LIKE %s")
        params.append(f"%{token}%")
    if not conditions:
        return []

    query = f"""
        SELECT corp_code, stock_code, corp_name
        FROM kr_dart_corp_codes
        WHERE stock_code IS NOT NULL
          AND stock_code <> ''
          AND ({' OR '.join(conditions)})
        LIMIT 100
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall() or []

    question_text = question or ""
    matched: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        corp_name = str(row.get("corp_name") or "").strip()
        stock_code = str(row.get("stock_code") or "").strip()
        if not corp_name and not stock_code:
            continue
        is_match = False
        if stock_code and stock_code in stock_codes:
            is_match = True
        if corp_name and corp_name in question_text:
            is_match = True
        if not is_match:
            continue
        key = (str(row.get("corp_code") or ""), stock_code, corp_name)
        if key in seen:
            continue
        seen.add(key)
        matched.append(
            {
                "corp_code": str(row.get("corp_code") or "").strip() or None,
                "stock_code": stock_code or None,
                "corp_name": corp_name or None,
            }
        )
    return matched


def _evaluate_kr_top50_scope(question: str, normalized_country_code: Optional[str]) -> Dict[str, Any]:
    if not _is_likely_kr_corporate_question(question, normalized_country_code):
        return {
            "enforced": False,
            "reason": "not_corporate_question",
        }

    try:
        top50_rows = _load_latest_kr_top50_universe()
        if not top50_rows:
            return {
                "enforced": False,
                "reason": "top50_snapshot_not_ready",
            }

        top50_stock_codes = {str(row.get("stock_code") or "").strip() for row in top50_rows if row.get("stock_code")}
        top50_corp_codes = {str(row.get("corp_code") or "").strip() for row in top50_rows if row.get("corp_code")}
        mentioned = _load_mentioned_kr_corporates(question)
        if not mentioned:
            return {
                "enforced": False,
                "reason": "no_company_mention_detected",
                "top50_snapshot_date": str(top50_rows[0].get("snapshot_date")) if top50_rows else None,
            }

        out_of_scope: List[Dict[str, Any]] = []
        in_scope: List[Dict[str, Any]] = []
        for item in mentioned:
            corp_code = str(item.get("corp_code") or "").strip()
            stock_code = str(item.get("stock_code") or "").strip()
            is_top50 = (corp_code and corp_code in top50_corp_codes) or (stock_code and stock_code in top50_stock_codes)
            if is_top50:
                in_scope.append(item)
            else:
                out_of_scope.append(item)

        if out_of_scope:
            return {
                "enforced": True,
                "allowed": False,
                "top50_snapshot_date": str(top50_rows[0].get("snapshot_date")) if top50_rows else None,
                "mentioned_companies": mentioned,
                "out_of_scope_companies": out_of_scope,
                "in_scope_companies": in_scope,
            }
        return {
            "enforced": True,
            "allowed": True,
            "top50_snapshot_date": str(top50_rows[0].get("snapshot_date")) if top50_rows else None,
            "mentioned_companies": mentioned,
            "in_scope_companies": in_scope,
        }
    except Exception as exc:
        logger.warning("[GraphRAGAnswer] top50 scope check failed: %s", exc)
        return {
            "enforced": False,
            "reason": "scope_check_error",
        }


def _normalize_alias_token(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower().strip()
    if not text:
        return ""
    compact = re.sub(r"\s+", "", text)
    compact = re.sub(r"[^0-9a-z가-힣]", "", compact)
    return compact


def _extract_us_ticker_candidates(question: str) -> List[str]:
    if not question:
        return []
    matched = re.findall(r"\b([A-Za-z]{1,5}(?:[.\-][A-Za-z])?)\b", question)
    candidates: List[str] = []
    seen = set()
    for token in matched:
        upper_token = str(token or "").strip().upper()
        if not upper_token:
            continue
        compact = upper_token.replace(".", "").replace("-", "")
        if not compact or compact in US_TICKER_TOKEN_STOPWORDS:
            continue
        normalized = upper_token.replace(".", "-")
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(normalized)
    return candidates[:12]


def _extract_us_alias_lookup_tokens(question: str) -> List[str]:
    if not question:
        return []
    raw_tokens = re.findall(r"[가-힣A-Za-z][가-힣A-Za-z0-9&\.\-]{1,30}", question)
    tokens: List[str] = []
    seen = set()
    for token in raw_tokens:
        lowered = str(token or "").strip().lower()
        if not lowered or lowered in US_COMPANY_TOKEN_STOPWORDS:
            continue
        normalized = _normalize_alias_token(token)
        if len(normalized) < 3 or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(normalized)
    return tokens[:8]


def _lookup_us_company_mentions(
    *,
    ticker_candidates: List[str],
    alias_tokens: List[str],
) -> List[Dict[str, Any]]:
    if not ticker_candidates and not alias_tokens:
        return []

    conditions: List[str] = []
    params: List[Any] = []

    compact_tickers = list(
        dict.fromkeys(
            ticker.replace(".", "").replace("-", "")
            for ticker in ticker_candidates
            if ticker
        )
    )
    if compact_tickers:
        placeholders = ", ".join(["%s"] * len(compact_tickers))
        conditions.append(f"REPLACE(REPLACE(r.symbol, '.', ''), '-', '') IN ({placeholders})")
        params.extend(compact_tickers)

    for token in alias_tokens:
        if len(token) < 3:
            continue
        conditions.append("a.alias_normalized LIKE %s")
        params.append(f"%{token}%")

    if not conditions:
        return []

    query = f"""
        SELECT DISTINCT
            r.symbol,
            r.company_name,
            a.alias,
            a.alias_type
        FROM corporate_entity_registry r
        LEFT JOIN corporate_entity_aliases a
          ON a.country_code = r.country_code
         AND a.symbol = r.symbol
         AND a.is_active = 1
        WHERE r.country_code = 'US'
          AND r.is_active = 1
          AND ({' OR '.join(conditions)})
        ORDER BY r.symbol ASC
        LIMIT 30
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall() or []
        return list(rows)
    except Exception as exc:
        logger.warning("[GraphRAGRouter] US company mention lookup failed: %s", exc)
        return []


def _build_us_single_stock_forced_route(
    *,
    question: str,
    country_code: Optional[str],
    country: Optional[str],
) -> Optional[Dict[str, Any]]:
    _, _, normalized_country_code = _resolve_country_filter(country, country_code)
    if normalized_country_code == "KR":
        return None

    question_text = str(question or "")
    normalized_question = _normalize_alias_token(question_text)
    lowered = question_text.lower()
    has_stock_intent = any(keyword in lowered for keyword in US_STOCK_QUESTION_KEYWORDS)

    hint_symbols: List[str] = []
    for alias, symbol in US_SINGLE_STOCK_ALIAS_HINTS.items():
        if alias and alias in normalized_question:
            hint_symbols.append(symbol)
    hint_symbols = list(dict.fromkeys(hint_symbols))

    ticker_candidates = _extract_us_ticker_candidates(question_text)
    if not has_stock_intent and not hint_symbols and not ticker_candidates:
        return None

    alias_tokens = _extract_us_alias_lookup_tokens(question_text)
    db_rows = _lookup_us_company_mentions(
        ticker_candidates=ticker_candidates,
        alias_tokens=alias_tokens,
    ) if (ticker_candidates or alias_tokens) else []

    db_symbols = [
        str(row.get("symbol") or "").strip().upper()
        for row in db_rows
        if str(row.get("symbol") or "").strip()
    ]
    db_companies = [
        str(row.get("company_name") or "").strip()
        for row in db_rows
        if str(row.get("company_name") or "").strip()
    ]
    matched_symbols = list(dict.fromkeys(hint_symbols + db_symbols))
    if not matched_symbols and ticker_candidates and has_stock_intent:
        matched_symbols = list(dict.fromkeys(ticker_candidates))

    # 단일 종목만 강제 라우팅한다. 복수 종목은 기존 compare_outlook 경로를 유지.
    if len(matched_symbols) != 1:
        return None

    matched_companies = list(dict.fromkeys(db_companies))
    for symbol in matched_symbols:
        for company_hint in US_SINGLE_STOCK_SYMBOL_COMPANY_HINTS.get(symbol, []):
            company_name = str(company_hint or "").strip()
            if company_name and company_name not in matched_companies:
                matched_companies.append(company_name)

    confidence = 0.97 if (hint_symbols or db_symbols) else 0.9
    reason_parts: List[str] = []
    if hint_symbols:
        reason_parts.append("company_hint")
    if db_symbols:
        reason_parts.append("db_match")
    if ticker_candidates:
        reason_parts.append("ticker_pattern")
    reason = "us_single_stock_detected:" + ("+".join(reason_parts) if reason_parts else "signal")

    return {
        "agent": "us_single_stock_agent",
        "selected_type": US_SINGLE_STOCK_ROUTE_TYPE,
        "confidence": round(confidence, 3),
        "reason": reason,
        "scores": {US_SINGLE_STOCK_ROUTE_TYPE: round(confidence, 3)},
        "matched_symbols": matched_symbols,
        "matched_security_ids": [f"US:{symbol}" for symbol in matched_symbols if str(symbol).strip()],
        "matched_companies": matched_companies[:5],
    }


def _normalize_llm_text(raw: Any) -> str:
    if raw is None:
        return ""

    if isinstance(raw, str):
        return raw

    if isinstance(raw, list):
        chunks: List[str] = []
        for item in raw:
            text = _normalize_llm_text(item).strip()
            if text:
                chunks.append(text)
        return "\n".join(chunks)

    if isinstance(raw, dict):
        primary = raw.get("text")
        if isinstance(primary, str) and primary.strip():
            return primary
        content = raw.get("content")
        if content is not None:
            content_text = _normalize_llm_text(content).strip()
            if content_text:
                return content_text
        output_text = raw.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        return json.dumps(raw, ensure_ascii=False)

    return str(raw)


def _extract_json_block(text: Any) -> Dict[str, Any]:
    cleaned = _normalize_llm_text(text).strip()
    if not cleaned:
        return {}

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _load_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = _normalize_llm_text(value).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _load_cached_answer(
    *,
    request: GraphRagAnswerRequest,
    model_name: str,
    as_of_date: date,
) -> Optional[GraphRagAnswerResponse]:
    if request.include_context or not request.reuse_cached_run:
        return None

    country_input, country_name, country_code = _resolve_country_filter(
        request.country,
        request.country_code,
    )
    _validate_scope_country(
        request_country=request.country,
        request_country_code=request.country_code,
        normalized_country_code=country_code,
    )
    country_for_lookup = country_name or country_input or country_code

    neo4j_client = get_neo4j_client()
    cached_rows = neo4j_client.run_read(
        """
        // phase_d_cached_answer_lookup
        MATCH (c:GraphRagApiCall)
        WHERE c.status = 'success'
          AND c.question = $question
          AND c.model = $model
          AND c.time_range = $time_range
          AND (
            ($country IS NULL AND $country_name IS NULL AND $country_code IS NULL AND coalesce(c.country, '') = '')
            OR ($country IS NOT NULL AND c.country = $country)
            OR ($country_name IS NOT NULL AND c.country = $country_name)
            OR ($country_code IS NOT NULL AND (c.country = $country_code OR c.country_code = $country_code))
          )
          AND c.as_of_date = date($as_of_date)
          AND c.analysis_run_id IS NOT NULL
        RETURN c.analysis_run_id AS run_id
        ORDER BY c.created_at DESC
        LIMIT 1
        """,
        {
            "question": request.question,
            "model": model_name,
            "time_range": request.time_range,
            "country": country_for_lookup,
            "country_name": country_name,
            "country_code": country_code,
            "as_of_date": as_of_date.isoformat(),
        },
    )

    if not cached_rows:
        return None

    run_id = cached_rows[0].get("run_id")
    if not run_id:
        return None

    run_rows = neo4j_client.run_read(
        """
        // phase_d_cached_answer_run
        MATCH (ar:AnalysisRun {run_id: $run_id})
        RETURN ar.response AS response_text,
               ar.metadata_json AS metadata_json
        LIMIT 1
        """,
        {"run_id": run_id},
    )
    if not run_rows:
        return None

    run_row = run_rows[0]
    metadata = _load_json_dict(run_row.get("metadata_json"))
    raw_output = metadata.get("raw_model_output")
    if not isinstance(raw_output, dict):
        raw_output = {}
    structured_citations = _parse_structured_citations(
        metadata.get("structured_citations")
        if isinstance(metadata.get("structured_citations"), list)
        else raw_output.get("structured_citations"),
        default_as_of_date=as_of_date.isoformat(),
        default_date_range=request.time_range,
    )

    base_payload = _normalize_answer_payload(raw_output)
    response_text = str(run_row.get("response_text") or "").strip()
    uncertainty = str(metadata.get("uncertainty") or base_payload.uncertainty).strip()
    key_points = metadata.get("key_points")
    if not isinstance(key_points, list):
        key_points = base_payload.key_points
    key_points = [str(item).strip() for item in key_points if str(item).strip()][:7]

    payload = GraphRagAnswerPayload(
        conclusion=response_text or base_payload.conclusion,
        uncertainty=uncertainty or "근거 불충분",
        key_points=key_points,
        impact_pathways=base_payload.impact_pathways,
    )

    citation_rows = neo4j_client.run_read(
        """
        // phase_d_cached_answer_citations
        MATCH (ar:AnalysisRun {run_id: $run_id})-[:USED_EVIDENCE]->(e:Evidence)<-[:HAS_EVIDENCE]-(d:Document)
        OPTIONAL MATCH (e)-[:SUPPORTS]->(target)
        RETURN e.evidence_id AS evidence_id,
               e.text AS text,
               d.doc_id AS doc_id,
               coalesce(d.url, d.link) AS doc_url,
               d.title AS doc_title,
               d.published_at AS published_at,
               collect(DISTINCT labels(target)) AS support_labels_nested
        ORDER BY d.published_at DESC
        LIMIT 40
        """,
        {"run_id": run_id},
    )

    citations: List[GraphRagCitation] = []
    for row in citation_rows:
        nested_labels = row.get("support_labels_nested") or []
        flattened_labels: List[str] = []
        seen_labels = set()
        for labels in nested_labels:
            for label in labels or []:
                label_text = str(label).strip()
                if not label_text or label_text in seen_labels:
                    continue
                seen_labels.add(label_text)
                flattened_labels.append(label_text)

        doc_id = row.get("doc_id")
        node_ids = [f"document:{doc_id}"] if doc_id else []
        citations.append(
            GraphRagCitation(
                evidence_id=row.get("evidence_id"),
                doc_id=doc_id,
                doc_url=row.get("doc_url"),
                doc_title=row.get("doc_title"),
                published_at=str(row.get("published_at")) if row.get("published_at") else None,
                text=str(row.get("text") or ""),
                support_labels=flattened_labels,
                node_ids=node_ids,
            )
        )

    if not citations and not structured_citations:
        return None

    logger.info("[GraphRAGAnswer] cache hit run_id=%s", run_id)
    return GraphRagAnswerResponse(
        question=request.question,
        model=model_name,
        as_of_date=as_of_date.isoformat(),
        answer=payload,
        citations=citations,
        structured_citations=structured_citations,
        suggested_queries=[],
        context_meta={
            "cache_hit": True,
            "cache_source": "AnalysisRun",
            "cached_run_id": run_id,
            "structured_citation_count": len(structured_citations),
        },
        analysis_run_id=str(run_id),
        persistence={
            "analysis_run": {
                "run_id": str(run_id),
                "reused": True,
            }
        },
        raw_model_output=raw_output,
        context=None,
    )


def _normalize_stock_match_text(value: str) -> tuple[str, str]:
    lowered = str(value or "").lower()
    compact = re.sub(r"\s+", "", lowered)
    compact = re.sub(r"[^0-9a-z가-힣]", "", compact)
    return lowered, compact


def _contains_focus_term(text: str, focus_terms: set[str]) -> bool:
    if not text or not focus_terms:
        return False
    lowered, compact = _normalize_stock_match_text(text)
    for term in focus_terms:
        if not term:
            continue
        if term in lowered or term in compact:
            return True
    return False


def _parse_iso_datetime(value: Optional[str]) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime.min
    try:
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except Exception:
        return datetime.min


def _score_stock_focus_evidence(evidence: GraphEvidence, focus_terms: set[str]) -> int:
    score = 0
    body = str(evidence.text or "")
    title = str(evidence.doc_title or "")
    has_body_focus = _contains_focus_term(body, focus_terms)
    has_title_focus = _contains_focus_term(title, focus_terms)

    if not has_body_focus and not has_title_focus:
        return 0

    if has_body_focus:
        score += 10
    elif has_title_focus:
        score += 2

    if has_body_focus and "Fact" in (evidence.support_labels or []):
        score += 2
    if has_body_focus and US_STOCK_PERCENT_PATTERN.search(body):
        score += 2
    if has_body_focus and US_STOCK_PRICE_PATTERN.search(body):
        score += 1
    return score


def _score_stock_focus_citation(citation: GraphRagCitation, focus_terms: set[str]) -> int:
    score = 0
    body = str(citation.text or "")
    title = str(citation.doc_title or "")
    has_body_focus = _contains_focus_term(body, focus_terms)
    has_title_focus = _contains_focus_term(title, focus_terms)

    if not has_body_focus and not has_title_focus:
        return 0

    if has_body_focus:
        score += 10
    elif has_title_focus:
        score += 2

    if has_body_focus and "Fact" in (citation.support_labels or []):
        score += 2
    if has_body_focus and US_STOCK_PERCENT_PATTERN.search(body):
        score += 2
    if has_body_focus and US_STOCK_PRICE_PATTERN.search(body):
        score += 1
    return score


def _to_utc_sortable_datetime(value: Any) -> datetime:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _classify_stock_direction(text: str) -> str:
    lowered = str(text or "").lower()
    bullish_hits = sum(1 for token in US_STOCK_BULLISH_KEYWORDS if token in lowered)
    bearish_hits = sum(1 for token in US_STOCK_BEARISH_KEYWORDS if token in lowered)
    if bullish_hits > bearish_hits:
        return "up"
    if bearish_hits > bullish_hits:
        return "down"
    return "mixed"


def _find_focus_injection_replacement_index(
    *,
    selected: List[GraphRagCitation],
    focus_terms: set[str],
    preserve_bearish_focus: bool,
) -> int:
    candidates: List[tuple[int, int, datetime, int]] = []
    for index, citation in enumerate(selected):
        has_focus = _has_focus_in_citation_text(citation, focus_terms)
        if has_focus and preserve_bearish_focus and _classify_stock_direction(str(citation.text or "")) == "down":
            continue
        group = 0 if not has_focus else 1
        citation_score = _score_stock_focus_citation(citation, focus_terms)
        candidates.append(
            (
                group,
                citation_score,
                _to_utc_sortable_datetime(citation.published_at),
                index,
            )
        )
    if not candidates:
        return -1
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return candidates[0][3]


def _inject_focus_evidence_citation(
    *,
    selected: List[GraphRagCitation],
    evidence: GraphEvidence,
    max_citations: int,
    focus_terms: set[str],
    preserve_bearish_focus: bool = False,
) -> List[GraphRagCitation]:
    key = (evidence.evidence_id, evidence.doc_id, evidence.text)
    selected_keys = {(item.evidence_id, item.doc_id, item.text) for item in selected}
    if key in selected_keys:
        return selected

    new_citation = _citation_from_evidence(evidence)
    if len(selected) < max_citations:
        selected.append(new_citation)
        return selected

    replacement_index = _find_focus_injection_replacement_index(
        selected=selected,
        focus_terms=focus_terms,
        preserve_bearish_focus=preserve_bearish_focus,
    )
    if replacement_index < 0:
        return selected
    selected[replacement_index] = new_citation
    return selected


def _normalize_scope_country_code_for_reference(
    request: GraphRagAnswerRequest,
    context: GraphRagContextResponse,
) -> str:
    request_country_code = str(request.country_code or "").strip().upper()
    if request_country_code in {"USKR", "KRUS", "US/KR", "KR/US", "KR-US"}:
        request_country_code = "US-KR"
    if request_country_code:
        return request_country_code

    meta = context.meta if isinstance(context.meta, dict) else {}
    resolved = str(meta.get("resolved_country_code") or "").strip().upper()
    if resolved in {"USKR", "KRUS", "US/KR", "KR/US", "KR-US"}:
        return "US-KR"
    return resolved


def _should_attach_us_daily_macro_reference(
    *,
    request: GraphRagAnswerRequest,
    route_decision: Optional[Dict[str, Any]],
    context: GraphRagContextResponse,
) -> bool:
    selected_type = str((route_decision or {}).get("selected_type") or "").strip().lower()
    if selected_type in US_DAILY_MACRO_REFERENCE_EXCLUDED_ROUTE_TYPES:
        return False

    scope_country_code = _normalize_scope_country_code_for_reference(request, context)
    if scope_country_code not in {"KR", "US-KR"}:
        return False

    if selected_type in US_DAILY_MACRO_REFERENCE_PRIMARY_ROUTE_TYPES:
        return True

    lowered_question = str(request.question or "").lower()
    return any(keyword in lowered_question for keyword in KR_SCOPE_HINT_KEYWORDS)


def _trim_us_daily_macro_reference_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "판단 근거" in text:
        text = text.split("판단 근거", 1)[0].strip()
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= US_DAILY_MACRO_REFERENCE_MAX_CHARS:
        return text
    return text[: US_DAILY_MACRO_REFERENCE_MAX_CHARS - 1].rstrip() + "…"


def _load_us_daily_macro_reference(*, as_of_date: date) -> Optional[Dict[str, Any]]:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT decision_date, analysis_summary
                FROM ai_strategy_decisions
                WHERE decision_date <= %s
                ORDER BY decision_date DESC, created_at DESC
                LIMIT 1
                """,
                (f"{as_of_date.isoformat()} 23:59:59",),
            )
            row = cursor.fetchone() or {}
    except Exception as exc:
        logger.warning("[GraphRAGAnswer] failed to load daily US macro reference: %s", exc)
        return None

    summary = _trim_us_daily_macro_reference_text(row.get("analysis_summary"))
    if not summary:
        return None

    decision_date_raw = row.get("decision_date")
    decision_date_text = str(decision_date_raw).strip() if decision_date_raw else None
    return {
        "source": "ai_strategy_decisions",
        "schedule": "daily 08:30 KST",
        "decision_date": decision_date_text,
        "summary": summary,
    }


def _build_us_daily_macro_structured_citation(
    *,
    us_macro_reference: Dict[str, Any],
    as_of_date: date,
) -> GraphRagStructuredCitation:
    decision_date = str(us_macro_reference.get("decision_date") or "").strip() or None
    return GraphRagStructuredCitation(
        dataset_code="AI_STRATEGY_DECISIONS",
        table="ai_strategy_decisions",
        filters={
            "decision_date_lte": as_of_date.isoformat(),
            "decision_date": decision_date,
            "source": "daily_0830_us_macro_analysis",
        },
        date_range="latest<=as_of_date",
        as_of_date=as_of_date.isoformat(),
        query_fingerprint=_compute_query_fingerprint(
            "ai_strategy_decisions",
            as_of_date.isoformat(),
            decision_date,
            "daily_0830_us_macro_analysis",
        ),
        row_count=1,
        source="sql",
        agent="macro_economy_agent",
        branch="sql",
        status="ok",
        template_id="macro.sql.daily_us_macro_briefing.v1",
    )


def _resolve_prompt_context_limits(
    *,
    request: GraphRagAnswerRequest,
    route: Optional[Dict[str, Any]],
    context: GraphRagContextResponse,
    insight_first: bool = False,
) -> Dict[str, int]:
    selected_type = str((route or {}).get("selected_type") or "").strip().lower()
    scope_country_code = _normalize_scope_country_code_for_reference(request, context)
    if insight_first:
        if scope_country_code == "KR" and selected_type in {"real_estate_detail", "general_macro", "market_summary"}:
            return {
                "events": 4,
                "indicators": 6,
                "themes": 4,
                "stories": 3,
                "links": 0,
            }
        return {
            "events": 6,
            "indicators": 8,
            "themes": 5,
            "stories": 4,
            "links": 0,
        }
    if scope_country_code == "KR" and selected_type in {"real_estate_detail", "general_macro", "market_summary"}:
        return {
            "events": 6,
            "indicators": 8,
            "themes": 6,
            "stories": 5,
            "links": 40,
        }
    return {
        "events": 12,
        "indicators": 12,
        "themes": 8,
        "stories": 8,
        "links": 60,
    }


def _select_prompt_evidences(
    *,
    evidences: List[GraphEvidence],
    max_prompt_evidences: int,
    route: Optional[Dict[str, Any]],
) -> List[GraphEvidence]:
    if max_prompt_evidences <= 0:
        return []

    route_meta = route or {}
    if str(route_meta.get("selected_type") or "").strip() != US_SINGLE_STOCK_ROUTE_TYPE:
        return evidences[:max_prompt_evidences]

    focus_terms = _extract_us_single_stock_focus_terms(route_meta)
    if not focus_terms:
        return evidences[:max_prompt_evidences]

    scored: List[tuple[int, datetime, int, GraphEvidence]] = []
    for index, evidence in enumerate(evidences):
        score = _score_stock_focus_evidence(evidence, focus_terms)
        scored.append((score, _parse_iso_datetime(evidence.published_at), -index, evidence))
    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)

    selected: List[GraphEvidence] = []
    selected_keys: Set[tuple[Optional[str], Optional[str], str]] = set()
    doc_counts: Dict[str, int] = {}
    per_doc_cap = 2

    for score, _, _, evidence in scored:
        key = (evidence.evidence_id, evidence.doc_id, evidence.text)
        if key in selected_keys:
            continue
        doc_id = str(evidence.doc_id or "")
        if doc_id and doc_counts.get(doc_id, 0) >= per_doc_cap:
            continue
        if score <= 0 and len(selected) >= max_prompt_evidences:
            break
        selected.append(evidence)
        selected_keys.add(key)
        if doc_id:
            doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
        if len(selected) >= max_prompt_evidences:
            break

    if len(selected) < max_prompt_evidences:
        for evidence in evidences:
            key = (evidence.evidence_id, evidence.doc_id, evidence.text)
            if key in selected_keys:
                continue
            selected.append(evidence)
            selected_keys.add(key)
            if len(selected) >= max_prompt_evidences:
                break

    return selected[:max_prompt_evidences]


def _truncate_prompt_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return "…"
    return text[: max_chars - 1].rstrip() + "…"


def _estimate_prompt_tokens(text: str) -> int:
    # Gemini 토큰의 대략치(한글 포함)를 간단히 추정
    return max(int(len(str(text or "")) / 3.8), 1)


def _compact_route_for_prompt(route: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(route, dict):
        return {}

    compact: Dict[str, Any] = {
        "selected_type": str(route.get("selected_type") or "").strip() or None,
        "confidence": route.get("confidence"),
        "confidence_level": str(route.get("confidence_level") or "").strip() or None,
        "selected_question_id": str(route.get("selected_question_id") or "").strip() or None,
        "sql_need": bool(route.get("sql_need")),
        "graph_need": bool(route.get("graph_need")),
        "tool_mode": str(route.get("tool_mode") or "").strip() or None,
    }

    target_agents = route.get("target_agents") if isinstance(route.get("target_agents"), list) else []
    compact["target_agents"] = [str(agent).strip() for agent in target_agents if str(agent).strip()][:4]

    for key in ("matched_symbols", "matched_security_ids", "matched_companies"):
        values = route.get(key) if isinstance(route.get(key), list) else []
        compact[key] = [str(item).strip() for item in values if str(item).strip()][:4]

    aggregated_scores = route.get("aggregated_scores") if isinstance(route.get("aggregated_scores"), dict) else {}
    if aggregated_scores:
        def _score_value(value: Any) -> float:
            try:
                return float(value)
            except Exception:
                return 0.0

        sorted_scores = sorted(
            aggregated_scores.items(),
            key=lambda item: _score_value(item[1]),
            reverse=True,
        )
        compact["aggregated_scores_top"] = {
            str(route_type): round(_score_value(score), 3)
            for route_type, score in sorted_scores[:4]
        }

    agents = route.get("agents") if isinstance(route.get("agents"), list) else []
    agent_votes: List[Dict[str, Any]] = []
    for agent in agents[:4]:
        if not isinstance(agent, dict):
            continue
        agent_votes.append(
            {
                "agent": str(agent.get("agent") or "").strip(),
                "selected_type": str(agent.get("selected_type") or "").strip(),
                "confidence": agent.get("confidence"),
                "reason": _truncate_prompt_text(agent.get("reason"), 90),
            }
        )
    if agent_votes:
        compact["agent_votes"] = agent_votes

    model_policy = route.get("agent_model_policy")
    if isinstance(model_policy, dict):
        policy_subset_keys = {"supervisor_agent"} | set(compact.get("target_agents") or [])
        compact["agent_model_policy"] = {
            str(key): str(model_policy.get(key) or "").strip()
            for key in policy_subset_keys
            if str(model_policy.get(key) or "").strip()
        }

    return compact


def _compact_structured_data_for_prompt(structured_data_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(structured_data_context, dict):
        return {}

    max_agent_insights = max(_safe_int(os.getenv("GRAPH_RAG_PROMPT_AGENT_INSIGHTS_MAX"), 4), 1)
    max_datasets = max(_safe_int(os.getenv("GRAPH_RAG_PROMPT_DATASETS_MAX"), 2), 1)

    compact: Dict[str, Any] = {
        "dataset_count": _safe_int(structured_data_context.get("dataset_count"), 0),
        "agent_insight_count": _safe_int(structured_data_context.get("agent_insight_count"), 0),
    }

    agent_insights_raw = structured_data_context.get("agent_insights")
    if isinstance(agent_insights_raw, list):
        insights: List[Dict[str, Any]] = []
        for insight in agent_insights_raw[:max_agent_insights]:
            if not isinstance(insight, dict):
                continue
            key_points_raw = insight.get("key_points") if isinstance(insight.get("key_points"), list) else []
            risks_raw = insight.get("risks") if isinstance(insight.get("risks"), list) else []
            insights.append(
                {
                    "agent": str(insight.get("agent") or "").strip(),
                    "summary": _truncate_prompt_text(insight.get("summary"), 220),
                    "key_points": [_truncate_prompt_text(point, 100) for point in key_points_raw[:2]],
                    "risks": [_truncate_prompt_text(risk, 100) for risk in risks_raw[:2]],
                    "confidence": str(insight.get("confidence") or "").strip() or "Low",
                }
            )
        if insights:
            compact["agent_insights"] = insights

    datasets_raw = structured_data_context.get("datasets")
    if isinstance(datasets_raw, list):
        datasets: List[Dict[str, Any]] = []
        for dataset in datasets_raw[:max_datasets]:
            if not isinstance(dataset, dict):
                continue
            trend_analysis = dataset.get("trend_analysis") if isinstance(dataset.get("trend_analysis"), dict) else {}
            trend_summary = {
                "months_available": int(trend_analysis.get("months_available") or 0),
                "scope_label": str(trend_analysis.get("scope_label") or "").strip() or None,
                "earliest_month": str(trend_analysis.get("earliest_month") or "").strip() or None,
                "latest_month": str(trend_analysis.get("latest_month") or "").strip() or None,
                "price_change_pct_vs_start": trend_analysis.get("price_change_pct_vs_start"),
                "tx_change_pct_vs_start": trend_analysis.get("tx_change_pct_vs_start"),
                "latest_weighted_avg_price": trend_analysis.get("latest_weighted_avg_price"),
                "latest_tx_count": trend_analysis.get("latest_tx_count"),
            }
            equity_analysis = dataset.get("equity_analysis") if isinstance(dataset.get("equity_analysis"), dict) else {}
            moving_averages = equity_analysis.get("moving_averages") if isinstance(equity_analysis.get("moving_averages"), dict) else {}
            trend = equity_analysis.get("trend") if isinstance(equity_analysis.get("trend"), dict) else {}
            returns = equity_analysis.get("returns") if isinstance(equity_analysis.get("returns"), dict) else {}
            earnings_reaction = (
                equity_analysis.get("earnings_reaction")
                if isinstance(equity_analysis.get("earnings_reaction"), dict)
                else {}
            )
            equity_summary = {
                "status": str(equity_analysis.get("status") or "").strip() or None,
                "reason": str(equity_analysis.get("reason") or "").strip() or None,
                "bars_available": _safe_int(equity_analysis.get("bars_available"), 0),
                "latest_trade_date": str(equity_analysis.get("latest_trade_date") or "").strip() or None,
                "latest_close": equity_analysis.get("latest_close"),
                "moving_averages": {
                    "ma20": moving_averages.get("ma20"),
                    "ma60": moving_averages.get("ma60"),
                    "ma120": moving_averages.get("ma120"),
                },
                "trend": {
                    "short_term": str(trend.get("short_term") or "").strip() or None,
                    "long_term": str(trend.get("long_term") or "").strip() or None,
                    "cross_signal": str(trend.get("cross_signal") or "").strip() or None,
                },
                "returns": {
                    "return_1d_pct": returns.get("return_1d_pct"),
                    "return_5d_pct": returns.get("return_5d_pct"),
                    "return_20d_pct": returns.get("return_20d_pct"),
                    "return_60d_pct": returns.get("return_60d_pct"),
                    "return_120d_pct": returns.get("return_120d_pct"),
                },
                "earnings_reaction": {
                    "status": str(earnings_reaction.get("status") or "").strip() or None,
                    "event_count": _safe_int(earnings_reaction.get("event_count"), 0),
                    "latest_event_date": str(earnings_reaction.get("latest_event_date") or "").strip() or None,
                    "latest_event_day_pct_from_pre_close": earnings_reaction.get("latest_event_day_pct_from_pre_close"),
                    "latest_post_1d_pct_from_event_close": earnings_reaction.get("latest_post_1d_pct_from_event_close"),
                    "latest_post_5d_pct_from_event_close": earnings_reaction.get("latest_post_5d_pct_from_event_close"),
                },
            }
            filters = dataset.get("filters") if isinstance(dataset.get("filters"), dict) else {}
            filters_compact = {
                str(key): _truncate_prompt_text(value, 80)
                for key, value in filters.items()
                if value is not None and str(value).strip()
            }
            datasets.append(
                {
                    "agent": str(dataset.get("agent") or "").strip(),
                    "table": str(dataset.get("table") or "").strip(),
                    "template_id": str(dataset.get("template_id") or "").strip(),
                    "status": str(dataset.get("status") or "").strip(),
                    "reason": _truncate_prompt_text(dataset.get("reason"), 80),
                    "row_count": _safe_int(dataset.get("row_count"), 0),
                    "filters": filters_compact,
                    "trend_analysis": trend_summary if trend_summary.get("months_available", 0) > 0 else None,
                    "equity_analysis": equity_summary if equity_summary.get("bars_available", 0) > 0 else None,
                }
            )
        if datasets:
            compact["datasets"] = datasets

    return compact


def _build_compact_graph_context_for_prompt(
    *,
    context: GraphRagContextResponse,
    context_limits: Dict[str, int],
    evidences: List[GraphEvidence],
    evidence_text_max_chars: int,
    include_links: bool,
) -> Dict[str, Any]:
    event_nodes = [node for node in context.nodes if node.type == "Event"][: context_limits["events"]]
    indicator_nodes = [node for node in context.nodes if node.type == "EconomicIndicator"][: context_limits["indicators"]]
    theme_nodes = [node for node in context.nodes if node.type == "MacroTheme"][: context_limits["themes"]]
    story_nodes = [node for node in context.nodes if node.type == "Story"][: context_limits["stories"]]

    meta = context.meta if isinstance(context.meta, dict) else {}
    counts = meta.get("counts") if isinstance(meta.get("counts"), dict) else {}
    parsed_scope = meta.get("parsed_scope") if isinstance(meta.get("parsed_scope"), dict) else {}

    compact_context = {
        "summary": {
            "resolved_country_code": str(meta.get("resolved_country_code") or "").strip() or None,
            "route_type": str(meta.get("route_type") or "").strip() or None,
            "region_code": str(parsed_scope.get("region_code") or "").strip() or None,
            "property_type": str(parsed_scope.get("property_type") or "").strip() or None,
            "counts": {
                "events": _safe_int(counts.get("events"), 0),
                "documents": _safe_int(counts.get("documents"), 0),
                "stories": _safe_int(counts.get("stories"), 0),
                "evidences": _safe_int(counts.get("evidences"), 0),
            },
        },
        "events": [
            {
                "event_id": node.properties.get("event_id"),
                "summary": node.label,
                "event_time": node.properties.get("event_time"),
                "country": node.properties.get("country"),
            }
            for node in event_nodes
        ],
        "indicators": [
            {
                "indicator_code": node.properties.get("indicator_code"),
                "name": node.label,
                "unit": node.properties.get("unit"),
            }
            for node in indicator_nodes
        ],
        "themes": [
            {
                "theme_id": node.properties.get("theme_id"),
                "name": node.label,
            }
            for node in theme_nodes
        ],
        "stories": [
            {
                "story_id": node.properties.get("story_id"),
                "title": node.label,
                "story_date": node.properties.get("story_date"),
            }
            for node in story_nodes
        ],
        "links": (
            [
                {
                    "source": link.source,
                    "target": link.target,
                    "type": link.type,
                }
                for link in context.links[: context_limits["links"]]
            ]
            if include_links and context_limits["links"] > 0
            else []
        ),
        "evidences": [
            {
                "evidence_id": evidence.evidence_id,
                "doc_id": evidence.doc_id,
                "doc_title": evidence.doc_title,
                "text": _truncate_prompt_text(evidence.text, evidence_text_max_chars),
                "support_labels": evidence.support_labels,
            }
            for evidence in evidences
        ],
    }
    return compact_context


def _citation_from_evidence(evidence: GraphEvidence) -> GraphRagCitation:
    node_ids = []
    if evidence.event_id:
        node_ids.append(f"event:{evidence.event_id}")
    if evidence.doc_id:
        node_ids.append(f"document:{evidence.doc_id}")
    return GraphRagCitation(
        evidence_id=evidence.evidence_id,
        doc_id=evidence.doc_id,
        doc_url=evidence.doc_url,
        doc_title=evidence.doc_title,
        published_at=evidence.published_at,
        text=evidence.text,
        support_labels=evidence.support_labels,
        node_ids=node_ids,
    )


def _model_to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, BaseModel):
        dump_fn = getattr(value, "model_dump", None)
        if callable(dump_fn):
            return dump_fn()
        dict_fn = getattr(value, "dict", None)
        if callable(dict_fn):
            return dict_fn()
    return {}


def _normalize_dataset_code(raw_value: Any) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return "SQL_QUERY"
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_").upper()
    return normalized or "SQL_QUERY"


def _compute_query_fingerprint(*parts: Any) -> str:
    blob = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _coerce_structured_citation(
    value: Any,
    *,
    default_as_of_date: Optional[str] = None,
    default_date_range: Optional[str] = None,
) -> Optional[GraphRagStructuredCitation]:
    payload = _model_to_dict(value)
    if not payload:
        return None

    dataset_code = _normalize_dataset_code(
        payload.get("dataset_code")
        or payload.get("table")
        or payload.get("template_id")
        or payload.get("agent")
        or payload.get("source")
    )
    table_name = str(payload.get("table") or "").strip() or None
    filters = payload.get("filters")
    if not isinstance(filters, dict):
        filters = {}
    date_range = str(payload.get("date_range") or default_date_range or "").strip() or None
    as_of_date = str(payload.get("as_of_date") or default_as_of_date or "").strip() or None
    query_fingerprint = str(payload.get("query_fingerprint") or "").strip() or None
    if not query_fingerprint:
        query_fingerprint = _compute_query_fingerprint(
            dataset_code,
            table_name,
            filters,
            payload.get("template_id"),
            payload.get("agent"),
            payload.get("branch"),
            payload.get("status"),
            payload.get("row_count"),
        )
    try:
        row_count = int(payload.get("row_count")) if payload.get("row_count") is not None else None
    except Exception:
        row_count = None

    return GraphRagStructuredCitation(
        dataset_code=dataset_code,
        table=table_name,
        filters=filters,
        date_range=date_range,
        as_of_date=as_of_date,
        query_fingerprint=query_fingerprint,
        row_count=row_count,
        source=str(payload.get("source") or "sql").strip() or "sql",
        agent=str(payload.get("agent") or "").strip() or None,
        branch=str(payload.get("branch") or "").strip() or None,
        status=str(payload.get("status") or "").strip() or None,
        template_id=str(payload.get("template_id") or "").strip() or None,
    )


def _parse_structured_citations(
    values: Any,
    *,
    default_as_of_date: Optional[str] = None,
    default_date_range: Optional[str] = None,
) -> List[GraphRagStructuredCitation]:
    if not isinstance(values, list):
        return []
    parsed: List[GraphRagStructuredCitation] = []
    seen: Set[tuple[str, str, str]] = set()
    for value in values:
        citation = _coerce_structured_citation(
            value,
            default_as_of_date=default_as_of_date,
            default_date_range=default_date_range,
        )
        if citation is None:
            continue
        identity = (
            str(citation.dataset_code or "").strip(),
            str(citation.table or "").strip(),
            str(citation.query_fingerprint or "").strip(),
        )
        if identity in seen:
            continue
        seen.add(identity)
        parsed.append(citation)
    return parsed


def _derive_dataset_from_sql_probe(
    *,
    agent_name: str,
    tool_probe: Dict[str, Any],
    table_name: Optional[str],
) -> str:
    return _normalize_dataset_code(
        table_name
        or tool_probe.get("dataset_code")
        or tool_probe.get("template_id")
        or f"{agent_name}_sql",
    )


def _build_structured_citations_from_execution(
    *,
    supervisor_execution: Optional[Dict[str, Any]],
    as_of_date: date,
    time_range: str,
) -> List[GraphRagStructuredCitation]:
    if not isinstance(supervisor_execution, dict):
        return []
    execution_result = supervisor_execution.get("execution_result")
    if not isinstance(execution_result, dict):
        return []
    branch_results = execution_result.get("branch_results")
    if not isinstance(branch_results, list):
        return []

    as_of_text = as_of_date.isoformat()
    results: List[GraphRagStructuredCitation] = []

    for branch_result in branch_results:
        if not isinstance(branch_result, dict):
            continue
        branch_name = str(branch_result.get("branch") or "").strip().lower()
        if branch_name != "sql":
            continue
        agent_runs = branch_result.get("agent_runs")
        if not isinstance(agent_runs, list):
            continue

        for agent_run in agent_runs:
            if not isinstance(agent_run, dict):
                continue
            tool_probe = agent_run.get("tool_probe")
            if not isinstance(tool_probe, dict):
                continue
            if str(tool_probe.get("tool") or "").strip().lower() != "sql":
                continue

            agent_name = str(agent_run.get("agent") or "").strip() or "unknown_agent"
            status = str(tool_probe.get("status") or agent_run.get("status") or "").strip() or None
            template_id = str(tool_probe.get("template_id") or "").strip() or None
            query = str(tool_probe.get("query") or "").strip()
            params = tool_probe.get("params")
            if not isinstance(params, list):
                params = []
            base_filters = tool_probe.get("filters")
            if not isinstance(base_filters, dict):
                base_filters = {}

            table_name = str(tool_probe.get("table") or "").strip() or None
            checks = tool_probe.get("checks")
            if isinstance(checks, list) and checks:
                for check in checks:
                    if not isinstance(check, dict):
                        continue
                    check_table = str(check.get("table") or table_name or "").strip() or None
                    dataset_code = _derive_dataset_from_sql_probe(
                        agent_name=agent_name,
                        tool_probe=tool_probe,
                        table_name=check_table,
                    )
                    check_filters = dict(base_filters)
                    if check.get("latest_date") is not None:
                        check_filters["latest_date"] = str(check.get("latest_date"))
                    row_count = check.get("row_count")
                    try:
                        row_count_int = int(row_count) if row_count is not None else None
                    except Exception:
                        row_count_int = None
                    fingerprint = _compute_query_fingerprint(
                        dataset_code,
                        check_table,
                        query,
                        params,
                        check_filters,
                        template_id,
                        status,
                        row_count_int,
                    )
                    results.append(
                        GraphRagStructuredCitation(
                            dataset_code=dataset_code,
                            table=check_table,
                            filters=check_filters,
                            date_range=time_range,
                            as_of_date=as_of_text,
                            query_fingerprint=fingerprint,
                            row_count=row_count_int,
                            source="sql",
                            agent=agent_name,
                            branch="sql",
                            status=status,
                            template_id=template_id,
                        )
                    )
                continue

            dataset_code = _derive_dataset_from_sql_probe(
                agent_name=agent_name,
                tool_probe=tool_probe,
                table_name=table_name,
            )
            row_count = tool_probe.get("row_count")
            try:
                row_count_int = int(row_count) if row_count is not None else None
            except Exception:
                row_count_int = None

            fingerprint = _compute_query_fingerprint(
                dataset_code,
                table_name,
                query,
                params,
                base_filters,
                template_id,
                status,
                row_count_int,
            )
            results.append(
                GraphRagStructuredCitation(
                    dataset_code=dataset_code,
                    table=table_name,
                    filters=base_filters,
                    date_range=time_range,
                    as_of_date=as_of_text,
                    query_fingerprint=fingerprint,
                    row_count=row_count_int,
                    source="sql",
                    agent=agent_name,
                    branch="sql",
                    status=status,
                    template_id=template_id,
                )
            )

    return _parse_structured_citations(
        [_model_to_dict(item) for item in results],
        default_as_of_date=as_of_text,
        default_date_range=time_range,
    )


def _serialize_structured_citations(values: List[GraphRagStructuredCitation]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for value in values:
        payload = _model_to_dict(value)
        if payload:
            serialized.append(payload)
    return serialized


def _normalize_prompt_cell(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _resolve_lawd_label(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) >= 5:
        return LAWD_NAME_BY_CODE.get(digits[:5])
    return LAWD_NAME_BY_CODE.get(text)


def _humanize_region_cell(key: str, value: Any) -> Any:
    lowered_key = str(key or "").strip().lower()
    if lowered_key not in {"lawd_cd", "region_code"}:
        return value
    label = _resolve_lawd_label(value)
    return label or value


def _sanitize_prompt_row(
    *,
    row: Dict[str, Any],
    selected_columns: List[str],
    max_columns: int,
) -> Dict[str, Any]:
    ordered_keys: List[str] = []
    for column in selected_columns:
        if column in row and column not in ordered_keys:
            ordered_keys.append(column)
    for key in row.keys():
        key_text = str(key or "").strip()
        if not key_text or key_text in ordered_keys:
            continue
        ordered_keys.append(key_text)

    sanitized: Dict[str, Any] = {}
    for key in ordered_keys[: max(max_columns, 1)]:
        normalized_value = _normalize_prompt_cell(row.get(key))
        sanitized[key] = _humanize_region_cell(key, normalized_value)
    return sanitized


def _build_structured_data_context(
    *,
    supervisor_execution: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(supervisor_execution, dict):
        return {}
    execution_result = supervisor_execution.get("execution_result")
    if not isinstance(execution_result, dict):
        return {}
    branch_results = execution_result.get("branch_results")
    if not isinstance(branch_results, list):
        return {}

    max_datasets = max(_safe_int(os.getenv("GRAPH_RAG_SQL_CONTEXT_MAX_DATASETS"), 4), 1)
    max_rows = max(_safe_int(os.getenv("GRAPH_RAG_SQL_CONTEXT_MAX_ROWS_PER_DATASET"), 3), 1)
    max_columns = max(_safe_int(os.getenv("GRAPH_RAG_SQL_CONTEXT_MAX_COLUMNS_PER_ROW"), 8), 1)

    datasets: List[Dict[str, Any]] = []
    agent_insights: List[Dict[str, Any]] = []
    for branch_result in branch_results:
        if not isinstance(branch_result, dict):
            continue
        agent_runs = branch_result.get("agent_runs")
        if not isinstance(agent_runs, list):
            continue

        for agent_run in agent_runs:
            if not isinstance(agent_run, dict):
                continue
            agent_name = str(agent_run.get("agent") or "").strip()
            agent_llm = agent_run.get("agent_llm")
            if not isinstance(agent_llm, dict):
                continue
            if str(agent_llm.get("status") or "").strip() != "ok":
                continue
            payload = agent_llm.get("payload")
            if not isinstance(payload, dict):
                continue
            summary = str(payload.get("summary") or "").strip()
            key_points_raw = payload.get("key_points") if isinstance(payload.get("key_points"), list) else []
            risks_raw = payload.get("risks") if isinstance(payload.get("risks"), list) else []
            key_points = [str(item).strip() for item in key_points_raw if str(item).strip()][:4]
            risks = [str(item).strip() for item in risks_raw if str(item).strip()][:3]
            if not summary and not key_points and not risks:
                continue
            agent_insights.append(
                {
                    "agent": agent_name,
                    "branch": str(agent_run.get("branch") or "").strip(),
                    "model": str(agent_llm.get("model") or "").strip(),
                    "summary": summary,
                    "key_points": key_points,
                    "risks": risks,
                    "confidence": str(payload.get("confidence") or "").strip() or "Low",
                }
            )

        if str(branch_result.get("branch") or "").strip().lower() != "sql":
            continue

        for agent_run in agent_runs:
            if len(datasets) >= max_datasets:
                break
            if not isinstance(agent_run, dict):
                continue
            tool_probe = agent_run.get("tool_probe")
            if not isinstance(tool_probe, dict):
                continue
            if str(tool_probe.get("tool") or "").strip().lower() != "sql":
                continue

            rows = tool_probe.get("rows") if isinstance(tool_probe.get("rows"), list) else []
            selected_columns = [
                str(item).strip()
                for item in (tool_probe.get("selected_columns") or [])
                if str(item).strip()
            ]
            sample_rows: List[Dict[str, Any]] = []
            for row in rows[:max_rows]:
                if not isinstance(row, dict):
                    continue
                sample_rows.append(
                    _sanitize_prompt_row(
                        row=row,
                        selected_columns=selected_columns,
                        max_columns=max_columns,
                    )
                )

            row_count_value = tool_probe.get("row_count")
            try:
                row_count = int(row_count_value) if row_count_value is not None else len(rows)
            except Exception:
                row_count = len(rows)

            filters = tool_probe.get("filters")
            if not isinstance(filters, dict):
                filters = {}
            trend_analysis = tool_probe.get("trend_analysis")
            if isinstance(trend_analysis, dict):
                try:
                    months_available = int(trend_analysis.get("months_available") or 0)
                except Exception:
                    months_available = 0
                trend_rows_raw = trend_analysis.get("rows") if isinstance(trend_analysis.get("rows"), list) else []
                trend_rows: List[Dict[str, Any]] = []
                for trend_row in trend_rows_raw[:12]:
                    if not isinstance(trend_row, dict):
                        continue
                    trend_rows.append(
                        _sanitize_prompt_row(
                            row=trend_row,
                            selected_columns=["stat_ym", "weighted_avg_price", "tx_count"],
                            max_columns=max_columns,
                        )
                    )
                trend_analysis_payload = {
                    "status": str(trend_analysis.get("status") or "").strip(),
                    "reason": str(trend_analysis.get("reason") or "").strip(),
                    "scope_label": str(trend_analysis.get("scope_label") or "").strip(),
                    "months_available": months_available,
                    "earliest_month": str(trend_analysis.get("earliest_month") or "").strip(),
                    "latest_month": str(trend_analysis.get("latest_month") or "").strip(),
                    "price_change_pct_vs_start": trend_analysis.get("price_change_pct_vs_start"),
                    "tx_change_pct_vs_start": trend_analysis.get("tx_change_pct_vs_start"),
                    "latest_weighted_avg_price": trend_analysis.get("latest_weighted_avg_price"),
                    "latest_tx_count": trend_analysis.get("latest_tx_count"),
                    "rows": trend_rows,
                }
            else:
                trend_analysis_payload = None
            equity_analysis = tool_probe.get("equity_analysis")
            if isinstance(equity_analysis, dict):
                moving_averages = (
                    equity_analysis.get("moving_averages")
                    if isinstance(equity_analysis.get("moving_averages"), dict)
                    else {}
                )
                trend = equity_analysis.get("trend") if isinstance(equity_analysis.get("trend"), dict) else {}
                returns = equity_analysis.get("returns") if isinstance(equity_analysis.get("returns"), dict) else {}
                earnings_reaction = (
                    equity_analysis.get("earnings_reaction")
                    if isinstance(equity_analysis.get("earnings_reaction"), dict)
                    else {}
                )
                equity_events_raw = earnings_reaction.get("events") if isinstance(earnings_reaction.get("events"), list) else []
                equity_events: List[Dict[str, Any]] = []
                for event_row in equity_events_raw[:3]:
                    if not isinstance(event_row, dict):
                        continue
                    equity_events.append(
                        {
                            "event_date": str(event_row.get("event_date") or "").strip() or None,
                            "event_trade_date": str(event_row.get("event_trade_date") or "").strip() or None,
                            "event_day_pct_from_pre_close": event_row.get("event_day_pct_from_pre_close"),
                            "post_1d_pct_from_event_close": event_row.get("post_1d_pct_from_event_close"),
                            "post_5d_pct_from_event_close": event_row.get("post_5d_pct_from_event_close"),
                        }
                    )
                equity_analysis_payload = {
                    "status": str(equity_analysis.get("status") or "").strip(),
                    "reason": str(equity_analysis.get("reason") or "").strip(),
                    "country_code": str(equity_analysis.get("country_code") or "").strip() or None,
                    "bars_available": _safe_int(equity_analysis.get("bars_available"), 0),
                    "latest_trade_date": str(equity_analysis.get("latest_trade_date") or "").strip() or None,
                    "latest_close": equity_analysis.get("latest_close"),
                    "latest_volume": equity_analysis.get("latest_volume"),
                    "moving_averages": {
                        "ma20": moving_averages.get("ma20"),
                        "ma60": moving_averages.get("ma60"),
                        "ma120": moving_averages.get("ma120"),
                    },
                    "trend": {
                        "short_term": str(trend.get("short_term") or "").strip() or None,
                        "long_term": str(trend.get("long_term") or "").strip() or None,
                        "cross_signal": str(trend.get("cross_signal") or "").strip() or None,
                    },
                    "returns": {
                        "return_1d_pct": returns.get("return_1d_pct"),
                        "return_5d_pct": returns.get("return_5d_pct"),
                        "return_20d_pct": returns.get("return_20d_pct"),
                        "return_60d_pct": returns.get("return_60d_pct"),
                        "return_120d_pct": returns.get("return_120d_pct"),
                    },
                    "earnings_reaction": {
                        "status": str(earnings_reaction.get("status") or "").strip() or None,
                        "event_count": _safe_int(earnings_reaction.get("event_count"), 0),
                        "latest_event_date": str(earnings_reaction.get("latest_event_date") or "").strip() or None,
                        "latest_event_trade_date": str(earnings_reaction.get("latest_event_trade_date") or "").strip() or None,
                        "latest_event_day_pct_from_pre_close": earnings_reaction.get(
                            "latest_event_day_pct_from_pre_close"
                        ),
                        "latest_post_1d_pct_from_event_close": earnings_reaction.get(
                            "latest_post_1d_pct_from_event_close"
                        ),
                        "latest_post_5d_pct_from_event_close": earnings_reaction.get(
                            "latest_post_5d_pct_from_event_close"
                        ),
                        "events": equity_events,
                    },
                }
            else:
                equity_analysis_payload = None

            datasets.append(
                {
                    "agent": str(agent_run.get("agent") or "").strip(),
                    "table": str(tool_probe.get("table") or "").strip(),
                    "template_id": str(tool_probe.get("template_id") or "").strip(),
                    "status": str(tool_probe.get("status") or "").strip(),
                    "reason": str(tool_probe.get("reason") or "").strip(),
                    "row_count": row_count,
                    "selected_columns": selected_columns[:max_columns],
                    "filters": {
                        str(key): _humanize_region_cell(str(key), _normalize_prompt_cell(value))
                        for key, value in filters.items()
                    },
                    "sample_rows": sample_rows,
                    "trend_analysis": trend_analysis_payload,
                    "equity_analysis": equity_analysis_payload,
                }
            )
        if len(datasets) >= max_datasets:
            break

    if not datasets:
        if not agent_insights:
            return {}
        return {
            "dataset_count": 0,
            "datasets": [],
            "agent_insight_count": len(agent_insights),
            "agent_insights": agent_insights[:8],
        }

    context_payload = {
        "dataset_count": len(datasets),
        "datasets": datasets,
    }
    if agent_insights:
        context_payload["agent_insight_count"] = len(agent_insights)
        context_payload["agent_insights"] = agent_insights[:8]
    return context_payload


def _has_focus_in_evidence_text(evidence: GraphEvidence, focus_terms: set[str]) -> bool:
    return _contains_focus_term(str(evidence.text or ""), focus_terms)


def _has_focus_in_citation_text(citation: GraphRagCitation, focus_terms: set[str]) -> bool:
    return _contains_focus_term(str(citation.text or ""), focus_terms)


def _ensure_us_single_stock_focus_citations(
    *,
    citations: List[GraphRagCitation],
    context: GraphRagContextResponse,
    route_decision: Dict[str, Any],
    max_citations: int,
) -> List[GraphRagCitation]:
    if str(route_decision.get("selected_type") or "").strip() != US_SINGLE_STOCK_ROUTE_TYPE:
        return citations

    focus_terms = _extract_us_single_stock_focus_terms(route_decision)
    if not focus_terms:
        return citations

    selected: List[GraphRagCitation] = []
    seen_keys: Set[tuple[Optional[str], Optional[str], str]] = set()
    for citation in citations:
        key = (citation.evidence_id, citation.doc_id, citation.text)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        selected.append(citation)

    focus_count = sum(1 for citation in selected if _has_focus_in_citation_text(citation, focus_terms))
    target_focus_count = 3

    candidate_evidences = sorted(
        context.evidences,
        key=lambda evidence: (
            int(_has_focus_in_evidence_text(evidence, focus_terms)),
            _score_stock_focus_evidence(evidence, focus_terms),
            _to_utc_sortable_datetime(evidence.published_at),
        ),
        reverse=True,
    )

    if focus_count < target_focus_count:
        for evidence in candidate_evidences:
            if focus_count >= target_focus_count:
                break
            if not _has_focus_in_evidence_text(evidence, focus_terms):
                break
            score = _score_stock_focus_evidence(evidence, focus_terms)
            if score <= 0:
                break

            selected = _inject_focus_evidence_citation(
                selected=selected,
                evidence=evidence,
                max_citations=max_citations,
                focus_terms=focus_terms,
            )
            focus_count = sum(1 for citation in selected if _has_focus_in_citation_text(citation, focus_terms))

    focus_evidences = [
        evidence
        for evidence in context.evidences
        if _has_focus_in_evidence_text(evidence, focus_terms)
        and _score_stock_focus_evidence(evidence, focus_terms) > 0
    ]
    focus_evidences.sort(key=lambda evidence: _to_utc_sortable_datetime(evidence.published_at), reverse=True)

    if focus_evidences:
        latest_focus = focus_evidences[0]
        selected = _inject_focus_evidence_citation(
            selected=selected,
            evidence=latest_focus,
            max_citations=max_citations,
            focus_terms=focus_terms,
        )

    has_bearish_focus_citation = any(
        _has_focus_in_citation_text(citation, focus_terms)
        and _classify_stock_direction(str(citation.text or "")) == "down"
        for citation in selected
    )
    if not has_bearish_focus_citation:
        bearish_focus_evidence = next(
            (
                evidence
                for evidence in focus_evidences
                if _classify_stock_direction(str(evidence.text or "")) == "down"
            ),
            None,
        )
        if bearish_focus_evidence is not None:
            selected = _inject_focus_evidence_citation(
                selected=selected,
                evidence=bearish_focus_evidence,
                max_citations=max_citations,
                focus_terms=focus_terms,
                preserve_bearish_focus=True,
            )

    selected.sort(
        key=lambda citation: (
            int(_has_focus_in_citation_text(citation, focus_terms)),
            _score_stock_focus_citation(citation, focus_terms),
            _to_utc_sortable_datetime(citation.published_at),
        ),
        reverse=True,
    )
    return selected[:max_citations]


def _make_prompt(
    request: GraphRagAnswerRequest,
    context: GraphRagContextResponse,
    max_prompt_evidences: int,
    route: Optional[Dict[str, Any]] = None,
    us_macro_reference: Optional[Dict[str, Any]] = None,
    structured_data_context: Optional[Dict[str, Any]] = None,
) -> str:
    question = request.question
    route_meta = route or {}
    structured_prompt_context = _compact_structured_data_for_prompt(structured_data_context)
    has_agent_insights = bool(
        isinstance(structured_prompt_context.get("agent_insights"), list)
        and structured_prompt_context.get("agent_insights")
    )

    context_limits = _resolve_prompt_context_limits(
        request=request,
        route=route,
        context=context,
        insight_first=has_agent_insights,
    )

    prompt_evidence_limit = max_prompt_evidences
    if has_agent_insights:
        prompt_evidence_limit = min(
            prompt_evidence_limit,
            max(_safe_int(os.getenv("GRAPH_RAG_PROMPT_EVIDENCE_COUNT_WITH_INSIGHTS"), 6), 3),
        )

    evidences = _select_prompt_evidences(
        evidences=context.evidences,
        max_prompt_evidences=prompt_evidence_limit,
        route=route,
    )
    evidence_text_max_chars = max(_safe_int(os.getenv("GRAPH_RAG_PROMPT_EVIDENCE_TEXT_MAX_CHARS"), 220), 80)
    if has_agent_insights:
        evidence_text_max_chars = min(evidence_text_max_chars, 140)

    include_links = _is_env_flag_enabled("GRAPH_RAG_PROMPT_INCLUDE_LINKS", default=False) and not has_agent_insights
    compact_context = _build_compact_graph_context_for_prompt(
        context=context,
        context_limits=context_limits,
        evidences=evidences,
        evidence_text_max_chars=evidence_text_max_chars,
        include_links=include_links,
    )

    route_prompt_meta = _compact_route_for_prompt(route_meta)
    route_guidance = _build_route_prompt_guidance(
        route_meta,
        request=request,
        context_meta=context.meta if isinstance(context.meta, dict) else None,
    )
    macro_reference_block = (
        json.dumps(us_macro_reference, ensure_ascii=False, indent=2)
        if isinstance(us_macro_reference, dict)
        else "{}"
    )

    def _render_prompt() -> str:
        structured_data_block = (
            json.dumps(structured_prompt_context, ensure_ascii=False, indent=2)
            if isinstance(structured_prompt_context, dict)
            else "{}"
        )
        return f"""
[Role]
You are a macro analysis assistant grounded strictly in provided graph context.

[Question]
{question}

[RoutingDecisionCompact]
{json.dumps(route_prompt_meta, ensure_ascii=False, indent=2)}

[GraphContextCompact]
{json.dumps(compact_context, ensure_ascii=False, indent=2)}

[StructuredDataContextCompact]
{structured_data_block}

[USMacroReference0830]
{macro_reference_block}

[Rules]
1. Only use facts present in GraphContextCompact and StructuredDataContextCompact.
2. If evidence is weak or missing, say "근거 불충분" explicitly.
3. Explain at least one impact chain in Event -> Theme -> Indicator form when possible.
4. Every key claim must be traceable to evidence_id/doc_id in GraphContextCompact or table/template_id in StructuredDataContextCompact.
5. Do not invent entities, events, indicators, dates, or numbers.
6. Output JSON only (no markdown).
7. Follow routing guidance: {route_guidance}
8. For KR-focused questions, when US context is needed, prioritize USMacroReference0830 over unrelated global events.
9. Never expose internal IDs/tokens (e.g., EVT_xxx, EV_xxx, EVID_xxx, CLM_xxx, LAWD code only). Use plain Korean labels (지역명/사건 설명).
10. If StructuredDataContextCompact has real-estate monthly trend (months_available >= 6), include explicit time-series trend interpretation.
11. If StructuredDataContextCompact.agent_insights exists, treat it as primary domain analysis and synthesize across agents before adding extra context.
12. Keep answer concise: do not restate raw context dumps.
13. If StructuredDataContextCompact.datasets has equity_analysis, include short/long trend (MA20/60/120 기반) and earnings pre/post reaction explicitly.

[Output JSON Schema]
{{
  "conclusion": "핵심 결론",
  "uncertainty": "불확실성/한계",
  "key_points": ["핵심 포인트 1", "핵심 포인트 2"],
  "impact_pathways": [
    {{
      "event_id": "EVT_xxx",
      "theme_id": "inflation",
      "indicator_code": "CPIAUCSL",
      "explanation": "영향 경로 설명"
    }}
  ],
  "cited_evidence_ids": ["EVID_xxx"],
  "cited_doc_ids": ["te:1234"]
}}
""".strip()

    prompt = _render_prompt()
    max_prompt_tokens = max(_safe_int(os.getenv("GRAPH_RAG_SUPERVISOR_PROMPT_MAX_TOKENS"), 6500), 1800)
    if _estimate_prompt_tokens(prompt) > max_prompt_tokens:
        compact_context["links"] = []
        prompt = _render_prompt()
    if _estimate_prompt_tokens(prompt) > max_prompt_tokens:
        evidence_rows = compact_context.get("evidences") if isinstance(compact_context.get("evidences"), list) else []
        if evidence_rows:
            keep_count = max(min(len(evidence_rows), 4), 2)
            compact_context["evidences"] = evidence_rows[:keep_count]
            for row in compact_context["evidences"]:
                if isinstance(row, dict):
                    row["text"] = _truncate_prompt_text(row.get("text"), 96)
        prompt = _render_prompt()
    if _estimate_prompt_tokens(prompt) > max_prompt_tokens:
        for key in ("events", "indicators", "themes", "stories"):
            values = compact_context.get(key) if isinstance(compact_context.get(key), list) else []
            if len(values) > 3:
                compact_context[key] = values[:3]

        datasets = structured_prompt_context.get("datasets") if isinstance(structured_prompt_context, dict) else None
        if isinstance(datasets, list) and len(datasets) > 1:
            structured_prompt_context["datasets"] = datasets[:1]
            structured_prompt_context["dataset_count"] = len(structured_prompt_context["datasets"])

        insights = (
            structured_prompt_context.get("agent_insights")
            if isinstance(structured_prompt_context, dict)
            else None
        )
        if isinstance(insights, list) and len(insights) > 3:
            structured_prompt_context["agent_insights"] = insights[:3]
            structured_prompt_context["agent_insight_count"] = len(structured_prompt_context["agent_insights"])

        prompt = _render_prompt()
    return prompt


def _normalize_impact_pathways(raw_pathways: Any) -> List[GraphRagPathway]:
    if not isinstance(raw_pathways, list):
        return []

    normalized: List[GraphRagPathway] = []
    for row in raw_pathways[:10]:
        if not isinstance(row, dict):
            continue
        explanation = str(row.get("explanation") or "").strip()
        if not explanation:
            continue
        normalized.append(
            GraphRagPathway(
                event_id=(row.get("event_id") or None),
                theme_id=(row.get("theme_id") or None),
                indicator_code=(row.get("indicator_code") or None),
                explanation=explanation,
            )
        )
    return normalized


def _build_citations(
    context: GraphRagContextResponse,
    cited_evidence_ids: List[str],
    cited_doc_ids: List[str],
) -> List[GraphRagCitation]:
    evidences = context.evidences
    by_evidence_id = {
        evidence.evidence_id: evidence
        for evidence in evidences
        if evidence.evidence_id
    }

    citations: List[GraphRagCitation] = []
    seen_keys = set()

    def append_evidence(evidence: GraphEvidence) -> None:
        key = (evidence.evidence_id, evidence.doc_id, evidence.text)
        if key in seen_keys:
            return
        seen_keys.add(key)
        citations.append(_citation_from_evidence(evidence))

    for evidence_id in cited_evidence_ids:
        evidence = by_evidence_id.get(evidence_id)
        if evidence:
            append_evidence(evidence)

    if not citations and cited_doc_ids:
        for doc_id in cited_doc_ids:
            matched = next((e for e in evidences if e.doc_id == doc_id), None)
            if matched:
                append_evidence(matched)

    if not citations:
        for evidence in evidences[:3]:
            append_evidence(evidence)

    return citations


def _normalize_answer_payload(raw: Dict[str, Any]) -> GraphRagAnswerPayload:
    conclusion = str(raw.get("conclusion") or raw.get("summary") or "").strip()
    uncertainty = str(raw.get("uncertainty") or "").strip()
    key_points = raw.get("key_points")
    if not isinstance(key_points, list):
        key_points = []
    key_points = [str(item).strip() for item in key_points if str(item).strip()][:7]

    pathways = _normalize_impact_pathways(raw.get("impact_pathways"))

    if not conclusion:
        conclusion = "근거 기반 결론을 생성하지 못했습니다."
    if not uncertainty:
        uncertainty = "근거 불충분"

    return GraphRagAnswerPayload(
        conclusion=conclusion,
        uncertainty=uncertainty,
        key_points=key_points,
        impact_pathways=pathways,
    )


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _resolve_citation_bounds() -> tuple[int, int]:
    min_citations = max(_safe_int(os.getenv("GRAPH_RAG_MIN_CITATIONS"), 3), 1)
    max_citations = max(_safe_int(os.getenv("GRAPH_RAG_MAX_CITATIONS"), 10), min_citations)
    max_citations = min(max_citations, 40)
    return min_citations, max_citations


def _enforce_citation_bounds(
    *,
    context: GraphRagContextResponse,
    citations: List[GraphRagCitation],
    min_citations: int,
    max_citations: int,
) -> List[GraphRagCitation]:
    deduped: List[GraphRagCitation] = []
    seen = set()
    for citation in citations:
        key = (citation.evidence_id, citation.doc_id, citation.text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
        if len(deduped) >= max_citations:
            return deduped

    if len(deduped) >= min_citations:
        return deduped[:max_citations]

    for evidence in context.evidences:
        key = (evidence.evidence_id, evidence.doc_id, evidence.text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(_citation_from_evidence(evidence))
        if len(deduped) >= max_citations:
            break

    return deduped[:max_citations]


def _ensure_recent_citations(
    *,
    context: GraphRagContextResponse,
    citations: List[GraphRagCitation],
    route_decision: Dict[str, Any],
    as_of_date: date,
    max_citations: int,
) -> List[GraphRagCitation]:
    enforce_recent = str(os.getenv("GRAPH_RAG_REQUIRE_RECENT_CITATIONS", "1")).strip().lower() in {
        "1",
        "true",
        "t",
        "yes",
        "y",
        "on",
    }
    if not enforce_recent:
        return citations

    target_count = max(_safe_int(os.getenv("GRAPH_RAG_RECENT_CITATION_TARGET_COUNT"), 1), 1)
    max_age_hours = max(
        _safe_int(
            os.getenv("GRAPH_RAG_RECENT_CITATION_MAX_AGE_HOURS")
            or os.getenv("GRAPH_RAG_DATA_FRESHNESS_FAIL_HOURS"),
            168,
        ),
        1,
    )

    reference_dt = datetime.combine(as_of_date, datetime.min.time(), tzinfo=timezone.utc)
    freshness_cutoff = reference_dt - timedelta(hours=max_age_hours)

    selected: List[GraphRagCitation] = []
    seen: Set[tuple[Optional[str], Optional[str], str]] = set()
    for citation in citations:
        key = (citation.evidence_id, citation.doc_id, citation.text)
        if key in seen:
            continue
        seen.add(key)
        selected.append(citation)
        if len(selected) >= max_citations:
            break

    def is_recent(citation: GraphRagCitation) -> bool:
        published_at = _to_utc_sortable_datetime(citation.published_at)
        return published_at >= freshness_cutoff

    recent_count = sum(1 for citation in selected if is_recent(citation))
    if recent_count >= target_count:
        return selected[:max_citations]

    selected_type = str(route_decision.get("selected_type") or "").strip()
    focus_terms = _extract_us_single_stock_focus_terms(route_decision)
    require_focus_match = selected_type == US_SINGLE_STOCK_ROUTE_TYPE and bool(focus_terms)

    candidate_evidences = sorted(
        context.evidences,
        key=lambda evidence: _to_utc_sortable_datetime(evidence.published_at),
        reverse=True,
    )
    for evidence in candidate_evidences:
        if recent_count >= target_count:
            break
        evidence_dt = _to_utc_sortable_datetime(evidence.published_at)
        if evidence_dt < freshness_cutoff:
            break
        if require_focus_match and not _has_focus_in_evidence_text(evidence, focus_terms):
            continue

        evidence_key = (evidence.evidence_id, evidence.doc_id, evidence.text)
        if evidence_key in seen:
            continue

        if require_focus_match:
            selected = _inject_focus_evidence_citation(
                selected=selected,
                evidence=evidence,
                max_citations=max_citations,
                focus_terms=focus_terms,
            )
            seen = {(item.evidence_id, item.doc_id, item.text) for item in selected}
        elif len(selected) < max_citations:
            selected.append(_citation_from_evidence(evidence))
            seen.add(evidence_key)
        else:
            oldest_index = min(
                range(len(selected)),
                key=lambda index: _to_utc_sortable_datetime(selected[index].published_at),
            )
            selected[oldest_index] = _citation_from_evidence(evidence)
            seen = {(item.evidence_id, item.doc_id, item.text) for item in selected}

        recent_count = sum(1 for citation in selected if is_recent(citation))

    return selected[:max_citations]


def _citation_identity(citation: GraphRagCitation) -> tuple[str, str, str]:
    return (
        str(citation.evidence_id or "").strip(),
        str(citation.doc_id or "").strip(),
        str(citation.text or "").strip(),
    )


def _resolve_recent_citation_guard_config(
    *,
    route_decision: Dict[str, Any],
    as_of_date: date,
) -> Dict[str, Any]:
    enforce_recent = str(os.getenv("GRAPH_RAG_REQUIRE_RECENT_CITATIONS", "1")).strip().lower() in {
        "1",
        "true",
        "t",
        "yes",
        "y",
        "on",
    }
    target_count = max(_safe_int(os.getenv("GRAPH_RAG_RECENT_CITATION_TARGET_COUNT"), 1), 1)
    max_age_hours = max(
        _safe_int(
            os.getenv("GRAPH_RAG_RECENT_CITATION_MAX_AGE_HOURS")
            or os.getenv("GRAPH_RAG_DATA_FRESHNESS_FAIL_HOURS"),
            168,
        ),
        1,
    )
    reference_dt = datetime.combine(as_of_date, datetime.min.time(), tzinfo=timezone.utc)
    freshness_cutoff = reference_dt - timedelta(hours=max_age_hours)
    selected_type = str(route_decision.get("selected_type") or "").strip()
    focus_terms = _extract_us_single_stock_focus_terms(route_decision)
    require_focus_match = selected_type == US_SINGLE_STOCK_ROUTE_TYPE and bool(focus_terms)
    return {
        "enabled": enforce_recent,
        "target_count": target_count,
        "max_age_hours": max_age_hours,
        "freshness_cutoff": freshness_cutoff,
        "selected_type": selected_type,
        "focus_terms": focus_terms,
        "require_focus_match": require_focus_match,
    }


def _build_recent_citation_guard_debug(
    *,
    context: GraphRagContextResponse,
    route_decision: Dict[str, Any],
    as_of_date: date,
    citations_before_recent: List[GraphRagCitation],
    citations_after_recent_first: List[GraphRagCitation],
    citations_before_recent_second: List[GraphRagCitation],
    citations_final: List[GraphRagCitation],
) -> Dict[str, Any]:
    config = _resolve_recent_citation_guard_config(route_decision=route_decision, as_of_date=as_of_date)
    freshness_cutoff = config["freshness_cutoff"]
    require_focus_match = bool(config["require_focus_match"])
    focus_terms: set[str] = config["focus_terms"] if isinstance(config.get("focus_terms"), set) else set()

    candidate_recent_evidence_count = 0
    for evidence in context.evidences:
        evidence_dt = _to_utc_sortable_datetime(evidence.published_at)
        if evidence_dt < freshness_cutoff:
            continue
        if require_focus_match and not _has_focus_in_evidence_text(evidence, focus_terms):
            continue
        candidate_recent_evidence_count += 1

    def _recent_count(citations: List[GraphRagCitation]) -> int:
        return sum(
            1
            for citation in citations
            if _to_utc_sortable_datetime(citation.published_at) >= freshness_cutoff
        )

    before_first_keys = {_citation_identity(citation) for citation in citations_before_recent}
    after_first_keys = {_citation_identity(citation) for citation in citations_after_recent_first}
    before_second_keys = {_citation_identity(citation) for citation in citations_before_recent_second}
    final_keys = {_citation_identity(citation) for citation in citations_final}
    first_pass_added_keys = after_first_keys - before_first_keys
    second_pass_added_keys = final_keys - before_second_keys
    total_added_keys = first_pass_added_keys | second_pass_added_keys

    selected_recent_count = _recent_count(citations_final)
    return {
        "enabled": bool(config["enabled"]),
        "target_count": int(config["target_count"]),
        "max_age_hours": int(config["max_age_hours"]),
        "freshness_cutoff": freshness_cutoff.isoformat(),
        "require_focus_match": require_focus_match,
        "candidate_recent_evidence_count": candidate_recent_evidence_count,
        "selected_recent_citation_count": selected_recent_count,
        "added_recent_citation_count": len(total_added_keys),
        "added_recent_citation_count_first_pass": len(first_pass_added_keys),
        "added_recent_citation_count_second_pass": len(second_pass_added_keys),
        "target_satisfied": selected_recent_count >= int(config["target_count"]),
    }


def _tokenize_support_text(text: str) -> set[str]:
    tokens = re.findall(r"[가-힣]{2,}|[A-Za-z]{2,}|[0-9]{2,}", str(text or ""))
    normalized = {
        token.lower()
        for token in tokens
        if token and token.lower() not in SUPPORT_TOKEN_STOPWORDS
    }
    return normalized


def _collect_structured_support_tokens(
    structured_citations: Optional[List[GraphRagStructuredCitation]],
) -> set[str]:
    tokens: set[str] = set()
    if not isinstance(structured_citations, list):
        return tokens

    for citation in structured_citations:
        dataset_code = str(citation.dataset_code or "").strip().upper()
        table_name = str(citation.table or "").strip().upper()
        template_id = str(citation.template_id or "").strip()
        tokens.update(_tokenize_support_text(dataset_code))
        tokens.update(_tokenize_support_text(table_name))
        tokens.update(_tokenize_support_text(template_id))

        alias_tokens = STRUCTURED_CITATION_SUPPORT_ALIASES.get(dataset_code, set())
        if not alias_tokens and table_name:
            alias_tokens = STRUCTURED_CITATION_SUPPORT_ALIASES.get(table_name, set())
        tokens.update(alias_tokens)

        if citation.row_count is not None:
            tokens.update(_tokenize_support_text(str(citation.row_count)))

        filters = citation.filters if isinstance(citation.filters, dict) else {}
        for key, value in filters.items():
            tokens.update(_tokenize_support_text(str(key)))
            tokens.update(_tokenize_support_text(str(value)))

    return tokens


def _count_structured_support_evidences(
    structured_citations: Optional[List[GraphRagStructuredCitation]],
) -> int:
    if not isinstance(structured_citations, list):
        return 0
    count = 0
    for citation in structured_citations:
        try:
            row_count = int(citation.row_count) if citation.row_count is not None else 0
        except Exception:
            row_count = 0
        if row_count > 0:
            count += 1
    return count


def _split_sentences(text: str) -> List[str]:
    normalized = str(text or "").strip()
    if not normalized:
        return []
    parts = re.split(r"(?:\n+|(?<=[\.\?\!])\s+|(?<=다\.)\s+)", normalized)
    sentences = [part.strip() for part in parts if str(part).strip()]
    return sentences or [normalized]


def _is_supported_sentence(sentence: str, support_tokens: set[str]) -> bool:
    if not sentence:
        return False
    if any(keyword in sentence for keyword in STATEMENT_KEEP_KEYWORDS):
        return True
    if not support_tokens:
        return False
    sentence_tokens = _tokenize_support_text(sentence)
    if not sentence_tokens:
        return True
    return len(sentence_tokens.intersection(support_tokens)) >= 1


def _filter_unsupported_statements(
    *,
    payload: GraphRagAnswerPayload,
    citations: List[GraphRagCitation],
    structured_citations: Optional[List[GraphRagStructuredCitation]] = None,
) -> tuple[GraphRagAnswerPayload, Dict[str, int]]:
    support_tokens: set[str] = set()
    for citation in citations:
        support_tokens.update(_tokenize_support_text(citation.text))
        support_tokens.update(_tokenize_support_text(citation.doc_title or ""))
        for label in citation.support_labels:
            support_tokens.update(_tokenize_support_text(label))
    support_tokens.update(_collect_structured_support_tokens(structured_citations))

    filtered_key_points: List[str] = []
    statement_total = 0
    statement_supported = 0
    removed_count = 0

    for point in payload.key_points:
        statement_total += 1
        if _is_supported_sentence(point, support_tokens):
            filtered_key_points.append(point)
            statement_supported += 1
        else:
            removed_count += 1

    conclusion = str(payload.conclusion or "").strip()
    if conclusion:
        statement_total += 1
        if _is_supported_sentence(conclusion, support_tokens):
            statement_supported += 1

    if not filtered_key_points and payload.key_points:
        filtered_key_points = ["근거와 직접 연결된 핵심 포인트를 추가 수집 중입니다."]

    return (
        GraphRagAnswerPayload(
            conclusion=conclusion,
            uncertainty=payload.uncertainty,
            key_points=filtered_key_points,
            impact_pathways=payload.impact_pathways,
            confidence_level=payload.confidence_level,
            confidence_score=payload.confidence_score,
        ),
        {
            "statement_total": statement_total,
            "statement_supported": statement_supported,
            "statement_removed": removed_count,
        },
    )


def _derive_confidence(
    *,
    citations: List[GraphRagCitation],
    statement_stats: Dict[str, int],
    data_freshness: Dict[str, Any],
    min_citations: int,
    has_pathway: bool,
) -> Dict[str, Any]:
    freshness_status = str(data_freshness.get("status") or "").lower()
    freshness_score_map = {
        "fresh": 1.0,
        "warning": 0.8,
        "stale": 0.55,
        "unknown": 0.45,
        "missing": 0.25,
    }
    freshness_score = freshness_score_map.get(freshness_status, 0.4)
    citation_score = min(len(citations) / max(float(min_citations), 1.0), 1.0)
    statement_total = max(_safe_int(statement_stats.get("statement_total"), 1), 1)
    statement_supported = max(_safe_int(statement_stats.get("statement_supported"), 0), 0)
    support_ratio = min(statement_supported / float(statement_total), 1.0)
    pathway_bonus = 0.08 if has_pathway else 0.0

    score = (citation_score * 0.45) + (freshness_score * 0.35) + (support_ratio * 0.20) + pathway_bonus
    score = round(min(max(score, 0.0), 1.0), 3)
    if score >= 0.75:
        level = "High"
    elif score >= 0.45:
        level = "Medium"
    else:
        level = "Low"
    return {"level": level, "score": score}


def _normalize_question_id(question_id: Optional[str]) -> Optional[str]:
    normalized = str(question_id or "").strip().upper()
    if normalized in SUPPORTED_QUESTION_IDS:
        return normalized
    return None


def _infer_required_question_id(question: str, explicit_question_id: Optional[str]) -> Optional[str]:
    normalized = _normalize_question_id(explicit_question_id)
    if normalized:
        return normalized

    text = str(question or "").strip().lower()
    if not text:
        return None

    has_any = lambda *tokens: any(token in text for token in tokens)

    if has_any("부동산") and has_any("매수", "매도", "타이밍", "시점"):
        return "Q6"
    if has_any("스노우플레이크", "snowflake") and has_any("팔란티어", "palantir"):
        return "Q2"
    if has_any("원달러", "usdkrw", "환율") and has_any("급등", "급상승", "급변", "상승"):
        return "Q5"
    if has_any("유망", "추천") and has_any("섹터", "업종") and has_any("한국", "국내"):
        return "Q4"
    if has_any("부동산") and has_any("시장", "요약"):
        return "Q3"
    if has_any("팔란티어", "palantir") and has_any("급락", "하락", "drop"):
        return "Q1"
    return None


def _score_keyword_route(question: str) -> Dict[str, Any]:
    text = str(question or "").strip().lower()
    if not text:
        return {
            "agent": "keyword_agent",
            "selected_type": "general_macro",
            "confidence": 0.25,
            "reason": "empty_question",
            "scores": {"general_macro": 0.25},
        }

    if _is_general_knowledge_question(text):
        return {
            "agent": "keyword_agent",
            "selected_type": GENERAL_KNOWLEDGE_ROUTE_TYPE,
            "confidence": 0.98,
            "reason": "general_knowledge_rules",
            "scores": {GENERAL_KNOWLEDGE_ROUTE_TYPE: 0.98},
        }

    scores: Dict[str, float] = {"general_macro": 0.35}
    has_any = lambda *tokens: any(token in text for token in tokens)

    if has_any("팔란티어", "palantir") and has_any("급락", "하락", "drop"):
        scores["explain_drop"] = scores.get("explain_drop", 0.0) + 0.92
    if (has_any("스노우플레이크", "snowflake") and has_any("팔란티어", "palantir")) or (
        has_any("비교", "vs", "versus", "어떤 게") and has_any("기업", "종목", "회사")
    ):
        scores["compare_outlook"] = scores.get("compare_outlook", 0.0) + 0.9
    if has_any("원달러", "환율", "usdkrw") and has_any("급등", "상승", "급변", "원인"):
        scores["fx_driver"] = scores.get("fx_driver", 0.0) + 0.9
    if has_any("부동산") and has_any("시장", "요약", "상황"):
        scores["market_summary"] = scores.get("market_summary", 0.0) + 0.86
    if has_any("유망", "추천", "좋은") and has_any("섹터", "업종"):
        scores["sector_recommendation"] = scores.get("sector_recommendation", 0.0) + 0.84
    if has_any("부동산") and has_any("매수", "매도", "타이밍", "시점"):
        scores["timing_scenario"] = scores.get("timing_scenario", 0.0) + 0.95
    if has_any("아파트", "전세", "월세", "거래가", "매매가", "실거래"):
        scores["real_estate_detail"] = scores.get("real_estate_detail", 0.0) + 0.85
    if has_any("지표", "indicator", "cpi", "pce", "실업률", "금리", "gdp"):
        scores["indicator_lookup"] = scores.get("indicator_lookup", 0.0) + 0.78

    selected_type, selected_score = max(scores.items(), key=lambda item: item[1])
    return {
        "agent": "keyword_agent",
        "selected_type": selected_type,
        "confidence": round(float(selected_score), 3),
        "reason": "keyword_rules",
        "scores": scores,
    }


def _score_scope_route(
    *,
    question: str,
    country_code: Optional[str],
    country: Optional[str],
) -> Dict[str, Any]:
    text = str(question or "").strip().lower()
    normalized_country = str(country_code or country or "").strip().upper()
    scores: Dict[str, float] = {"general_macro": 0.4}

    if normalized_country == "KR":
        scores["market_summary"] = scores.get("market_summary", 0.0) + 0.55
        if any(token in text for token in ["부동산", "아파트", "전세", "월세"]):
            scores["real_estate_detail"] = scores.get("real_estate_detail", 0.0) + 0.72
    if normalized_country == "US":
        scores["explain_drop"] = scores.get("explain_drop", 0.0) + 0.5
        scores["compare_outlook"] = scores.get("compare_outlook", 0.0) + 0.5
        scores["indicator_lookup"] = scores.get("indicator_lookup", 0.0) + 0.45
    if normalized_country in {"US-KR", "USKR"}:
        scores["fx_driver"] = scores.get("fx_driver", 0.0) + 0.85
        scores["compare_outlook"] = scores.get("compare_outlook", 0.0) + 0.52

    if any(token in text for token in ["비교", "vs", "versus"]):
        scores["compare_outlook"] = scores.get("compare_outlook", 0.0) + 0.35
    if any(token in text for token in ["매수", "매도", "타이밍", "시점"]):
        scores["timing_scenario"] = scores.get("timing_scenario", 0.0) + 0.4

    selected_type, selected_score = max(scores.items(), key=lambda item: item[1])
    return {
        "agent": "scope_agent",
        "selected_type": selected_type,
        "confidence": round(float(selected_score), 3),
        "reason": "country_scope_rules",
        "scores": scores,
    }


def _build_router_llm_prompt(request: GraphRagAnswerRequest) -> str:
    explicit_question_id = _normalize_question_id(request.question_id) or ""
    return f"""
[Role]
You are a query routing classifier for a macro chatbot.

[Task]
Classify the user query into exactly one query_type.

[Allowed query_type]
{sorted(ROUTER_QUERY_TYPES)}

[Input]
question: {request.question}
country: {request.country or ""}
country_code: {request.country_code or ""}
compare_mode: {request.compare_mode or ""}
region_code: {request.region_code or ""}
property_type: {request.property_type or ""}
question_id: {explicit_question_id}

[Output JSON only]
{{
  "query_type": "one of allowed query_type",
  "confidence": 0.0,
  "reasoning": "short reason",
  "question_id": "Q1|Q2|Q3|Q4|Q5|Q6|null"
}}
""".strip()


def _build_general_knowledge_prompt(request: GraphRagAnswerRequest) -> str:
    return f"""
[Role]
You are a general assistant for non-financial casual questions.

[Policy]
- Use model knowledge only.
- Do not claim you used internal SQL/Neo4j data.
- If real-time information is required (e.g., today's weather), state that it may be outdated.
- Keep the answer concise and practical.

[Input]
question: {request.question}

[Output JSON only]
{{
  "conclusion": "short direct answer",
  "uncertainty": "data freshness caveat if needed",
  "key_points": ["point1", "point2"]
}}
""".strip()


def _clamp_confidence(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return round(min(max(parsed, 0.0), 0.99), 3)


def _invoke_router_llm_agent(
    request: GraphRagAnswerRequest,
    router_llm=None,
    user_id: Optional[str] = None,
    flow_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    use_llm = str(os.getenv("GRAPH_RAG_ROUTER_LLM_ENABLED", "1")).strip().lower() not in {"0", "false", "off", "no"}
    if not use_llm and router_llm is None:
        return {
            "agent": "llm_router_agent",
            "model": ROUTER_INTENT_MODEL,
            "selected_type": "general_macro",
            "confidence": 0.0,
            "reason": "llm_router_disabled",
            "scores": {},
        }

    llm_instance = router_llm
    if llm_instance is None:
        google_api_key = (
            str(os.getenv("GOOGLE_API_KEY") or "").strip()
            or str(os.getenv("GEMINI_API_KEY") or "").strip()
        )
        if not google_api_key:
            return {
                "agent": "llm_router_agent",
                "model": ROUTER_INTENT_MODEL,
                "selected_type": "general_macro",
                "confidence": 0.0,
                "reason": "llm_router_missing_api_key",
                "scores": {},
            }
        router_timeout = max(_safe_int(os.getenv("GRAPH_RAG_ROUTER_LLM_TIMEOUT_SEC"), 10), 10)
        llm_instance = llm_gemini_flash(model=ROUTER_INTENT_MODEL, timeout=router_timeout)

    try:
        prompt = _build_router_llm_prompt(request)
        with track_llm_call(
            model_name=ROUTER_INTENT_MODEL,
            provider="Google",
            service_name="graph_rag_router_intent",
            request_prompt=prompt,
            user_id=user_id,
            flow_type="chatbot",
            flow_run_id=flow_run_id,
            agent_name="router_intent_classifier",
        ) as tracker:
            response = llm_instance.invoke(prompt)
            tracker.set_response(response)
        raw_text = _normalize_llm_text(getattr(response, "content", None)).strip()
        if not raw_text:
            raw_text = _normalize_llm_text(response).strip()
        parsed = _extract_json_block(raw_text)

        query_type = str(parsed.get("query_type") or "").strip()
        if query_type not in ROUTER_QUERY_TYPES:
            query_type = "general_macro"
        confidence = _clamp_confidence(parsed.get("confidence"), default=0.55 if query_type != "general_macro" else 0.4)
        question_id = _normalize_question_id(parsed.get("question_id"))
        reasoning = str(parsed.get("reasoning") or "").strip() or "llm_routing"
        return {
            "agent": "llm_router_agent",
            "model": ROUTER_INTENT_MODEL,
            "selected_type": query_type,
            "confidence": confidence,
            "reason": reasoning,
            "question_id": question_id,
            "scores": {query_type: confidence},
        }
    except Exception as error:
        logger.warning("[GraphRAGRouter] llm route fallback: %s", error)
        return {
            "agent": "llm_router_agent",
            "model": ROUTER_INTENT_MODEL,
            "selected_type": "general_macro",
            "confidence": 0.0,
            "reason": f"llm_router_error:{type(error).__name__}",
            "scores": {},
        }


def _contains_any_keyword(text: str, keywords: Set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _build_agent_model_policy() -> Dict[str, str]:
    return dict(DEFAULT_AGENT_MODEL_POLICY)


def _is_general_knowledge_question(question: str) -> bool:
    lowered = str(question or "").strip().lower()
    if not lowered:
        return False
    if not _contains_any_keyword(lowered, GENERAL_KNOWLEDGE_HINT_KEYWORDS):
        return False
    if _contains_any_keyword(lowered, GENERAL_KNOWLEDGE_EXCLUDE_KEYWORDS):
        return False
    return True


def _resolve_target_agents(
    *,
    question: str,
    selected_type: str,
    selected_question_id: Optional[str],
    sql_need: bool,
    graph_need: bool,
) -> List[str]:
    lowered = str(question or "").lower()
    if selected_type == GENERAL_KNOWLEDGE_ROUTE_TYPE:
        return ["general_knowledge_agent"]

    is_equity_intent = selected_type in {
        US_SINGLE_STOCK_ROUTE_TYPE,
        "sector_recommendation",
    } or _contains_any_keyword(lowered, EQUITY_HINT_KEYWORDS)
    is_real_estate_intent = selected_type in {
        "real_estate_detail",
        "timing_scenario",
    } or _contains_any_keyword(lowered, REAL_ESTATE_HINT_KEYWORDS)
    is_ontology_intent = _contains_any_keyword(lowered, ONTOLOGY_HINT_KEYWORDS)
    is_macro_intent = selected_type in {
        "general_macro",
        "market_summary",
        "indicator_lookup",
        "fx_driver",
        "compare_outlook",
        "explain_drop",
    } or selected_question_id in {"Q3", "Q5"}

    targets: List[str] = []
    if is_real_estate_intent:
        targets.append("real_estate_agent")
    if is_equity_intent:
        targets.append("equity_analyst_agent")
    if is_macro_intent or not targets:
        targets.append("macro_economy_agent")
    if graph_need and is_ontology_intent:
        targets.append("ontology_master_agent")

    deduped: List[str] = []
    seen = set()
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        deduped.append(target)

    if not sql_need and not graph_need:
        if selected_type == GENERAL_KNOWLEDGE_ROUTE_TYPE:
            return ["general_knowledge_agent"]
        return ["macro_economy_agent"]
    return deduped


def _derive_conditional_parallel_strategy(
    *,
    request: GraphRagAnswerRequest,
    selected_type: str,
    selected_question_id: Optional[str],
) -> Dict[str, Any]:
    lowered = str(request.question or "").lower()
    route_defaults = {
        GENERAL_KNOWLEDGE_ROUTE_TYPE: {"sql_need": False, "graph_need": False},
        "general_macro": {"sql_need": False, "graph_need": True},
        "market_summary": {"sql_need": False, "graph_need": True},
        "explain_drop": {"sql_need": False, "graph_need": True},
        "compare_outlook": {"sql_need": False, "graph_need": True},
        "indicator_lookup": {"sql_need": True, "graph_need": True},
        "fx_driver": {"sql_need": True, "graph_need": True},
        "sector_recommendation": {"sql_need": True, "graph_need": True},
        "timing_scenario": {"sql_need": True, "graph_need": True},
        # 한국 부동산 상세 질의는 정량(SQL) 우선, 그래프는 필요 시 확장
        "real_estate_detail": {"sql_need": True, "graph_need": False},
        US_SINGLE_STOCK_ROUTE_TYPE: {"sql_need": True, "graph_need": True},
    }
    default_flags = route_defaults.get(selected_type, {"sql_need": False, "graph_need": True})
    sql_need = bool(default_flags.get("sql_need"))
    graph_need = bool(default_flags.get("graph_need"))

    if selected_type == GENERAL_KNOWLEDGE_ROUTE_TYPE:
        sql_need = False
        graph_need = False
    else:
        if _contains_any_keyword(lowered, SQL_NEED_HINT_KEYWORDS):
            sql_need = True
        if _contains_any_keyword(lowered, GRAPH_NEED_HINT_KEYWORDS):
            graph_need = True

        if selected_type == "compare_outlook" and _contains_any_keyword(lowered, EQUITY_HINT_KEYWORDS):
            sql_need = True
        if selected_question_id in {"Q3", "Q4", "Q5", "Q6"}:
            graph_need = True
        if not sql_need and not graph_need:
            graph_need = True

    target_agents = _resolve_target_agents(
        question=request.question,
        selected_type=selected_type,
        selected_question_id=selected_question_id,
        sql_need=sql_need,
        graph_need=graph_need,
    )
    tool_mode = "parallel" if sql_need and graph_need else "single"
    return {
        "sql_need": sql_need,
        "graph_need": graph_need,
        "tool_mode": tool_mode,
        "target_agents": target_agents,
    }


def _derive_matched_security_ids(
    *,
    matched_symbols: List[str],
    selected_type: str,
    requested_country_code: Optional[str],
    target_agents: List[str],
) -> List[str]:
    if not matched_symbols:
        return []
    requires_equity_context = selected_type == US_SINGLE_STOCK_ROUTE_TYPE or "equity_analyst_agent" in target_agents
    if not requires_equity_context:
        return []

    deduped: List[str] = []
    seen = set()
    for raw_symbol in matched_symbols:
        symbol = str(raw_symbol or "").strip()
        if not symbol:
            continue
        parsed_country, parsed_native = parse_security_id(symbol)
        if parsed_country and parsed_native:
            security_id = f"{parsed_country}:{parsed_native}"
        else:
            country = infer_country_for_symbol(
                symbol,
                requested_country_code=requested_country_code,
                selected_type=selected_type,
            )
            native = normalize_native_code(country or "", symbol)
            security_id = to_security_id(country, native) if country and native else None
        if not security_id or security_id in seen:
            continue
        seen.add(security_id)
        deduped.append(security_id)
    return deduped[:5]


def _build_supervisor_execution_trace(route_decision: Dict[str, Any]) -> Dict[str, Any]:
    sql_need = bool(route_decision.get("sql_need"))
    graph_need = bool(route_decision.get("graph_need"))
    selected_type = str(route_decision.get("selected_type") or "").strip()
    llm_direct_need = selected_type == GENERAL_KNOWLEDGE_ROUTE_TYPE or (not sql_need and not graph_need)
    tool_mode = str(route_decision.get("tool_mode") or "single").strip().lower()
    if tool_mode not in {"single", "parallel"}:
        tool_mode = "single"
    if tool_mode == "parallel" and not (sql_need and graph_need):
        tool_mode = "single"

    raw_targets = route_decision.get("target_agents")
    if isinstance(raw_targets, list):
        target_agents = [str(agent).strip() for agent in raw_targets if str(agent).strip()]
    else:
        target_agents = []
    if not target_agents:
        target_agents = ["general_knowledge_agent"] if llm_direct_need else ["macro_economy_agent"]

    dispatch_mode = "parallel" if tool_mode == "parallel" else "single"
    branch_plan = [
        {
            "branch": "sql",
            "enabled": sql_need,
            "dispatch_mode": dispatch_mode if sql_need else "skip",
            "agents": target_agents if sql_need else [],
        },
        {
            "branch": "graph",
            "enabled": graph_need,
            "dispatch_mode": dispatch_mode if graph_need else "skip",
            "agents": target_agents if graph_need else [],
        },
        {
            "branch": "llm_direct",
            "enabled": llm_direct_need,
            "dispatch_mode": "single" if llm_direct_need else "skip",
            "agents": target_agents if llm_direct_need else [],
        },
    ]

    agent_model_policy = route_decision.get("agent_model_policy")
    if not isinstance(agent_model_policy, dict):
        agent_model_policy = _build_agent_model_policy()

    return {
        "execution_policy": "conditional_parallel",
        "tool_mode": tool_mode,
        "sql_need": sql_need,
        "graph_need": graph_need,
        "llm_direct_need": llm_direct_need,
        "target_agents": target_agents,
        "agent_model_policy": agent_model_policy,
        "selected_agent_count": len(target_agents),
        "branch_plan": branch_plan,
    }


def _resolve_agent_llm(
    *,
    model_name: str,
    timeout_sec: int,
):
    resolved_model = str(model_name or "").strip() or DOMAIN_AGENT_MODEL
    if "pro" in resolved_model.lower():
        return llm_gemini_pro(model=resolved_model, timeout=timeout_sec)
    return llm_gemini_flash(model=resolved_model, timeout=timeout_sec)


def _is_env_flag_enabled(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _clone_answer_request_with_overrides(
    request: GraphRagAnswerRequest,
    **overrides: Any,
) -> GraphRagAnswerRequest:
    if hasattr(request, "model_dump"):
        payload = request.model_dump()
    else:
        payload = request.dict()  # type: ignore[attr-defined]
    payload.update({key: value for key, value in overrides.items() if value is not None})
    return GraphRagAnswerRequest(**payload)


def _invoke_query_rewrite_utility(
    *,
    request: GraphRagAnswerRequest,
    route_decision: Dict[str, Any],
    enabled: bool,
    user_id: Optional[str],
    flow_run_id: Optional[str],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "enabled": enabled,
        "status": "skipped",
        "reason": "utility_disabled",
        "applied": False,
        "original_question": request.question,
        "rewritten_question": request.question,
    }
    if not enabled:
        return result

    agent_model_policy = route_decision.get("agent_model_policy")
    if not isinstance(agent_model_policy, dict):
        agent_model_policy = _build_agent_model_policy()
    utility_model = str(agent_model_policy.get("query_rewrite_utility") or LIGHTWEIGHT_UTILITY_MODEL).strip()

    google_api_key = (
        str(os.getenv("GOOGLE_API_KEY") or "").strip()
        or str(os.getenv("GEMINI_API_KEY") or "").strip()
    )
    if not google_api_key:
        result["reason"] = "missing_api_key"
        return result

    prompt = f"""
[Role]
당신은 질의 재작성 유틸리티입니다.

[Question]
{request.question}

[Route]
{json.dumps({
    "selected_type": route_decision.get("selected_type"),
    "selected_question_id": route_decision.get("selected_question_id"),
    "target_agents": route_decision.get("target_agents"),
}, ensure_ascii=False, indent=2)}

[Rules]
1. 의미를 바꾸지 않고 질의를 명확하게 정리한다.
2. 과도한 확장/추론 금지. 원문 의도 유지.
3. 출력은 JSON만.

[Output JSON]
{{
  "rewritten_question": "정리된 질의",
  "applied": true,
  "reason": "적용 사유"
}}
""".strip()

    try:
        utility_llm = _resolve_agent_llm(
            model_name=utility_model,
            timeout_sec=max(min(request.timeout_sec, 30), 10),
        )
        metadata_json = {
            "log_type": "query_rewrite",
            "selected_type": str(route_decision.get("selected_type") or ""),
        }
        with track_llm_call(
            model_name=utility_model,
            provider="Google",
            service_name="graph_rag_query_rewrite",
            request_prompt=prompt,
            user_id=user_id,
            flow_type="chatbot",
            flow_run_id=flow_run_id,
            agent_name="query_rewrite_utility",
            metadata_json=metadata_json,
        ) as tracker:
            response = utility_llm.invoke(prompt)
            tracker.set_response(response)

        raw_text = _normalize_llm_text(getattr(response, "content", None)).strip()
        if not raw_text:
            raw_text = _normalize_llm_text(response).strip()
        raw_json = _extract_json_block(raw_text)

        rewritten_question = str(raw_json.get("rewritten_question") or "").strip()
        if not rewritten_question:
            rewritten_question = request.question
        applied = bool(raw_json.get("applied")) and rewritten_question != request.question
        if len(rewritten_question) < 3:
            rewritten_question = request.question
            applied = False

        result.update(
            {
                "status": "ok",
                "reason": str(raw_json.get("reason") or "query_rewrite_executed").strip() or "query_rewrite_executed",
                "applied": applied,
                "rewritten_question": rewritten_question,
                "model": utility_model,
                "raw_model_output": raw_json or {"raw_text": raw_text},
            }
        )
        return result
    except Exception as error:
        result.update(
            {
                "status": "degraded",
                "reason": "query_rewrite_failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "model": utility_model,
            }
        )
        return result


def _normalize_optional_code(value: Any) -> Optional[str]:
    token = str(value or "").strip()
    return token or None


def _invoke_query_normalization_utility(
    *,
    request: GraphRagAnswerRequest,
    route_decision: Dict[str, Any],
    enabled: bool,
    user_id: Optional[str],
    flow_run_id: Optional[str],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "enabled": enabled,
        "status": "skipped",
        "reason": "utility_disabled",
        "country_code": request.country_code,
        "region_code": request.region_code,
        "property_type": request.property_type,
        "time_range": request.time_range,
    }
    if not enabled:
        return result

    agent_model_policy = route_decision.get("agent_model_policy")
    if not isinstance(agent_model_policy, dict):
        agent_model_policy = _build_agent_model_policy()
    utility_model = str(agent_model_policy.get("query_normalization_utility") or LIGHTWEIGHT_UTILITY_MODEL).strip()

    google_api_key = (
        str(os.getenv("GOOGLE_API_KEY") or "").strip()
        or str(os.getenv("GEMINI_API_KEY") or "").strip()
    )
    if not google_api_key:
        result["reason"] = "missing_api_key"
        return result

    prompt = f"""
[Role]
당신은 질의 파라미터 정규화 유틸리티입니다.

[Question]
{request.question}

[CurrentRequest]
{json.dumps({
    "country": request.country,
    "country_code": request.country_code,
    "region_code": request.region_code,
    "property_type": request.property_type,
    "time_range": request.time_range,
}, ensure_ascii=False, indent=2)}

[Route]
{json.dumps({
    "selected_type": route_decision.get("selected_type"),
    "selected_question_id": route_decision.get("selected_question_id"),
}, ensure_ascii=False, indent=2)}

[AllowedCountryCodes]
{json.dumps(sorted(list(SUPPORTED_QA_COUNTRY_CODES)), ensure_ascii=False)}

[Rules]
1. 추정이 과하면 변경하지 않는다(원값 유지).
2. time_range는 7d/30d/90d/180d/365d 형태를 우선 사용.
3. 출력은 JSON만.

[Output JSON]
{{
  "country_code": "KR",
  "region_code": "11680",
  "property_type": "apartment_sale",
  "time_range": "30d",
  "applied": true,
  "reason": "정규화 사유"
}}
""".strip()

    try:
        utility_llm = _resolve_agent_llm(
            model_name=utility_model,
            timeout_sec=max(min(request.timeout_sec, 30), 10),
        )
        metadata_json = {
            "log_type": "query_normalization",
            "selected_type": str(route_decision.get("selected_type") or ""),
        }
        with track_llm_call(
            model_name=utility_model,
            provider="Google",
            service_name="graph_rag_query_normalization",
            request_prompt=prompt,
            user_id=user_id,
            flow_type="chatbot",
            flow_run_id=flow_run_id,
            agent_name="query_normalization_utility",
            metadata_json=metadata_json,
        ) as tracker:
            response = utility_llm.invoke(prompt)
            tracker.set_response(response)

        raw_text = _normalize_llm_text(getattr(response, "content", None)).strip()
        if not raw_text:
            raw_text = _normalize_llm_text(response).strip()
        raw_json = _extract_json_block(raw_text)

        normalized_country_code = _normalize_optional_code(raw_json.get("country_code")) or request.country_code
        if normalized_country_code:
            normalized_country_code = normalized_country_code.upper()
        if normalized_country_code and normalized_country_code not in SUPPORTED_QA_COUNTRY_CODES:
            normalized_country_code = request.country_code

        normalized_region_code = _normalize_optional_code(raw_json.get("region_code")) or request.region_code
        normalized_property_type = _normalize_optional_code(raw_json.get("property_type")) or request.property_type
        normalized_time_range = _normalize_optional_code(raw_json.get("time_range")) or request.time_range
        if normalized_time_range and not re.fullmatch(r"\d+[dmy]", normalized_time_range):
            normalized_time_range = request.time_range

        applied = bool(raw_json.get("applied")) and any(
            [
                normalized_country_code != request.country_code,
                normalized_region_code != request.region_code,
                normalized_property_type != request.property_type,
                normalized_time_range != request.time_range,
            ]
        )

        result.update(
            {
                "status": "ok",
                "reason": str(raw_json.get("reason") or "query_normalization_executed").strip() or "query_normalization_executed",
                "applied": applied,
                "country_code": normalized_country_code,
                "region_code": normalized_region_code,
                "property_type": normalized_property_type,
                "time_range": normalized_time_range,
                "model": utility_model,
                "raw_model_output": raw_json or {"raw_text": raw_text},
            }
        )
        return result
    except Exception as error:
        result.update(
            {
                "status": "degraded",
                "reason": "query_normalization_failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "model": utility_model,
            }
        )
        return result


def _apply_citation_postprocess_order(
    *,
    citations: List[GraphRagCitation],
    ordered_keys: List[str],
) -> List[GraphRagCitation]:
    if not citations or not ordered_keys:
        return citations

    key_to_citation: Dict[str, GraphRagCitation] = {}
    for index, citation in enumerate(citations):
        key = str(citation.evidence_id or citation.doc_id or f"idx:{index}")
        if key not in key_to_citation:
            key_to_citation[key] = citation

    reordered: List[GraphRagCitation] = []
    seen: Set[str] = set()
    for raw_key in ordered_keys:
        key = str(raw_key or "").strip()
        if not key or key in seen:
            continue
        citation = key_to_citation.get(key)
        if citation is None:
            continue
        seen.add(key)
        reordered.append(citation)

    for index, citation in enumerate(citations):
        key = str(citation.evidence_id or citation.doc_id or f"idx:{index}")
        if key in seen:
            continue
        reordered.append(citation)

    return reordered


def _merge_citations_with_dedupe(
    *,
    base: List[GraphRagCitation],
    extra: List[GraphRagCitation],
) -> List[GraphRagCitation]:
    merged: List[GraphRagCitation] = []
    seen: Set[tuple[str, str, str]] = set()

    def _append(citation: GraphRagCitation) -> None:
        key = (
            str(citation.evidence_id or "").strip(),
            str(citation.doc_id or "").strip(),
            str(citation.text or "").strip(),
        )
        if key in seen:
            return
        seen.add(key)
        merged.append(citation)

    for item in base:
        _append(item)
    for item in extra:
        _append(item)
    return merged


def _should_trigger_web_fallback(
    *,
    route_decision: Dict[str, Any],
    citation_count: int,
    min_citations: int,
    data_freshness: Dict[str, Any],
) -> tuple[bool, str]:
    selected_type = str(route_decision.get("selected_type") or "").strip()
    if selected_type == GENERAL_KNOWLEDGE_ROUTE_TYPE:
        return False, "general_knowledge_route"

    if citation_count < max(min_citations, 1):
        return True, "citation_shortage"

    freshness_status = str(data_freshness.get("status") or "").strip().lower()
    if freshness_status in {"missing", "stale"}:
        return True, f"freshness_{freshness_status}"
    if freshness_status == "warning" and _is_env_flag_enabled("GRAPH_RAG_WEB_FALLBACK_ON_WARNING", default=False):
        return True, "freshness_warning"
    return False, "not_required"


def _build_web_fallback_query(
    *,
    request: GraphRagAnswerRequest,
) -> str:
    parts = [str(request.question or "").strip()]
    country_name = get_country_name(str(request.country_code or "").strip().upper())
    if country_name and country_name not in parts[0]:
        parts.append(country_name)
    if request.region_code:
        parts.append(str(request.region_code).strip())
    if request.property_type:
        parts.append(str(request.property_type).strip())
    return " ".join([part for part in parts if part]).strip()


def _parse_rfc822_datetime_to_iso(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _strip_html_tags(text: str) -> str:
    stripped = re.sub(r"<[^>]+>", " ", str(text or ""))
    stripped = html.unescape(stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def _fetch_google_news_rss_results(
    *,
    query: str,
    country_code: Optional[str],
    max_results: int,
) -> List[Dict[str, Any]]:
    normalized_country = str(country_code or "").strip().upper()
    if normalized_country == "KR":
        hl, gl, ceid = "ko", "KR", "KR:ko"
    else:
        hl, gl, ceid = "en-US", "US", "US:en"

    encoded_query = quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl={hl}&gl={gl}&ceid={ceid}"
    response = requests.get(
        url,
        timeout=max(_safe_int(os.getenv("GRAPH_RAG_WEB_FALLBACK_TIMEOUT_SEC"), 7), 3),
        headers={
            "User-Agent": "Mozilla/5.0 (GraphRAGBot/1.0; +https://news.google.com)",
        },
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")
    results: List[Dict[str, Any]] = []
    for item in items:
        if len(results) >= max(max_results, 1):
            break
        title = str(item.findtext("title") or "").strip()
        link = str(item.findtext("link") or "").strip()
        description = _strip_html_tags(item.findtext("description") or "")
        pub_date = _parse_rfc822_datetime_to_iso(item.findtext("pubDate"))
        if not link and not title and not description:
            continue
        results.append(
            {
                "title": title,
                "url": link,
                "content": description,
                "published_at": pub_date,
                "source": "google_news_rss",
            }
        )
    return results


def _convert_web_results_to_citations(
    *,
    results: List[Dict[str, Any]],
    limit: int,
) -> List[GraphRagCitation]:
    citations: List[GraphRagCitation] = []
    for row in results:
        if len(citations) >= max(limit, 1):
            break
        url = str(row.get("url") or row.get("link") or "").strip()
        title = str(row.get("title") or row.get("name") or "").strip()
        content = str(row.get("content") or row.get("snippet") or row.get("raw_content") or "").strip()
        if not url and not content:
            continue
        if len(content) > 480:
            content = f"{content[:479].rstrip()}…"
        published_at = str(row.get("published_date") or row.get("published_at") or "").strip() or None
        identity_source = url or f"{title}|{content[:120]}"
        digest = hashlib.md5(identity_source.encode("utf-8")).hexdigest()[:16]
        evidence_id = f"WEB_{digest}"
        doc_id = f"web:{digest}"
        citation_text = content or title or url
        citations.append(
            GraphRagCitation(
                evidence_id=evidence_id,
                doc_id=doc_id,
                doc_url=url or None,
                doc_title=title or "Web fallback source",
                published_at=published_at,
                text=citation_text,
                support_labels=["WebFallback"],
                node_ids=[f"document:{doc_id}"],
            )
        )
    return citations


def _collect_web_fallback_citations(
    *,
    request: GraphRagAnswerRequest,
    route_decision: Dict[str, Any],
    citations: List[GraphRagCitation],
    min_citations: int,
    data_freshness: Dict[str, Any],
) -> Dict[str, Any]:
    enabled = _is_env_flag_enabled("GRAPH_RAG_WEB_FALLBACK_ENABLED", default=True)
    result: Dict[str, Any] = {
        "enabled": enabled,
        "status": "skipped",
        "reason": "disabled",
        "applied": False,
        "added_count": 0,
        "fallback_citations": [],
        "query": None,
        "freshness_before": data_freshness,
    }
    if not enabled:
        return result

    should_trigger, trigger_reason = _should_trigger_web_fallback(
        route_decision=route_decision,
        citation_count=len(citations),
        min_citations=min_citations,
        data_freshness=data_freshness,
    )
    result["trigger_reason"] = trigger_reason
    if not should_trigger:
        result["reason"] = "not_required"
        return result

    max_results = max(_safe_int(os.getenv("GRAPH_RAG_WEB_FALLBACK_MAX_RESULTS"), 3), 1)
    query = _build_web_fallback_query(request=request)
    if not query:
        result["status"] = "degraded"
        result["reason"] = "empty_query"
        return result

    result["query"] = query
    try:
        parsed_results = _fetch_google_news_rss_results(
            query=query,
            country_code=request.country_code,
            max_results=max_results,
        )
        fallback_citations = _convert_web_results_to_citations(
            results=parsed_results,
            limit=max_results,
        )
        result.update(
            {
                "status": "ok" if fallback_citations else "degraded",
                "reason": "web_search_executed" if fallback_citations else "web_search_no_results",
                "applied": bool(fallback_citations),
                "added_count": len(fallback_citations),
                "raw_result_count": len(parsed_results),
                "search_provider": "google_news_rss",
                "fallback_citations": fallback_citations,
            }
        )
        return result
    except Exception as error:
        result.update(
            {
                "status": "degraded",
                "reason": "web_search_failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        return result


def _invoke_citation_postprocess_utility(
    *,
    request: GraphRagAnswerRequest,
    route_decision: Dict[str, Any],
    citations: List[GraphRagCitation],
    enabled: bool,
    user_id: Optional[str],
    flow_run_id: Optional[str],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "enabled": enabled,
        "status": "skipped",
        "reason": "utility_disabled",
        "applied": False,
        "ordered_keys": [],
    }
    if not enabled:
        return result
    if not citations:
        result["reason"] = "no_citations"
        return result

    agent_model_policy = route_decision.get("agent_model_policy")
    if not isinstance(agent_model_policy, dict):
        agent_model_policy = _build_agent_model_policy()
    utility_model = str(agent_model_policy.get("citation_postprocess_utility") or LIGHTWEIGHT_UTILITY_MODEL).strip()

    google_api_key = (
        str(os.getenv("GOOGLE_API_KEY") or "").strip()
        or str(os.getenv("GEMINI_API_KEY") or "").strip()
    )
    if not google_api_key:
        result["reason"] = "missing_api_key"
        return result

    citation_compact: List[Dict[str, Any]] = []
    for index, citation in enumerate(citations[:12]):
        key = str(citation.evidence_id or citation.doc_id or f"idx:{index}")
        citation_compact.append(
            {
                "key": key,
                "published_at": citation.published_at,
                "title": citation.doc_title,
                "text": str(citation.text or "")[:160],
            }
        )

    prompt = f"""
[Role]
당신은 citation 정렬 후처리 유틸리티입니다.

[Question]
{request.question}

[Route]
{json.dumps({
    "selected_type": route_decision.get("selected_type"),
    "selected_question_id": route_decision.get("selected_question_id"),
}, ensure_ascii=False, indent=2)}

[Citations]
{json.dumps(citation_compact, ensure_ascii=False, indent=2)}

[Rules]
1. 질문 적합도와 최신성을 기준으로 key 순서를 제안한다.
2. 목록에 없는 key는 절대 만들지 않는다.
3. 출력은 JSON만.

[Output JSON]
{{
  "ordered_keys": ["key1", "key2"],
  "applied": true,
  "reason": "정렬 사유"
}}
""".strip()

    try:
        utility_llm = _resolve_agent_llm(
            model_name=utility_model,
            timeout_sec=max(min(request.timeout_sec, 30), 10),
        )
        metadata_json = {
            "log_type": "citation_postprocess",
            "selected_type": str(route_decision.get("selected_type") or ""),
            "citation_count": len(citations),
        }
        with track_llm_call(
            model_name=utility_model,
            provider="Google",
            service_name="graph_rag_citation_postprocess",
            request_prompt=prompt,
            user_id=user_id,
            flow_type="chatbot",
            flow_run_id=flow_run_id,
            agent_name="citation_postprocess_utility",
            metadata_json=metadata_json,
        ) as tracker:
            response = utility_llm.invoke(prompt)
            tracker.set_response(response)

        raw_text = _normalize_llm_text(getattr(response, "content", None)).strip()
        if not raw_text:
            raw_text = _normalize_llm_text(response).strip()
        raw_json = _extract_json_block(raw_text)
        raw_keys = raw_json.get("ordered_keys")
        ordered_keys = [str(item).strip() for item in raw_keys if str(item).strip()] if isinstance(raw_keys, list) else []
        applied = bool(raw_json.get("applied")) and bool(ordered_keys)
        result.update(
            {
                "status": "ok",
                "reason": str(raw_json.get("reason") or "citation_postprocess_executed").strip() or "citation_postprocess_executed",
                "applied": applied,
                "ordered_keys": ordered_keys,
                "model": utility_model,
                "raw_model_output": raw_json or {"raw_text": raw_text},
            }
        )
        return result
    except Exception as error:
        result.update(
            {
                "status": "degraded",
                "reason": "citation_postprocess_failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "model": utility_model,
            }
        )
        return result


def _build_agent_execution_prompt(
    *,
    agent_name: str,
    branch_name: str,
    request: GraphRagAnswerRequest,
    route_decision: Dict[str, Any],
    tool_probe: Dict[str, Any],
    context_meta: Dict[str, Any],
) -> str:
    role_map = {
        "macro_economy_agent": "거시경제 분석 전문가",
        "equity_analyst_agent": "주식/기업 분석 전문가",
        "real_estate_agent": "부동산 정량 분석 전문가",
        "ontology_master_agent": "지식그래프 구조 분석 전문가",
        "general_knowledge_agent": "일반 질의 응답 전문가",
    }
    role = role_map.get(agent_name, "도메인 분석 전문가")
    compact_meta = {
        "selected_type": route_decision.get("selected_type"),
        "selected_question_id": route_decision.get("selected_question_id"),
        "sql_need": route_decision.get("sql_need"),
        "graph_need": route_decision.get("graph_need"),
    }
    compact_counts = context_meta.get("counts") if isinstance(context_meta.get("counts"), dict) else {}

    return f"""
[Role]
당신은 {role}입니다. 주어진 도구 실행 결과만 근거로 간결하게 분석하세요.

[Question]
{request.question}

[Branch]
{branch_name}

[Route]
{json.dumps(compact_meta, ensure_ascii=False, indent=2)}

[ToolProbe]
{json.dumps(tool_probe, ensure_ascii=False, indent=2)}

[ContextCounts]
{json.dumps(compact_counts, ensure_ascii=False, indent=2)}

[Rules]
1. 제공된 ToolProbe 범위를 벗어난 수치/사실을 만들지 않는다.
2. 핵심 분석은 1~3문장 요약 + 핵심 포인트 최대 4개.
3. 내부 식별자(EVT_/EV_/EVID_/CLM_)는 사용자 문장에 노출하지 않는다.
4. JSON만 출력한다.

[Output JSON]
{{
  "summary": "도메인 요약",
  "key_points": ["포인트1", "포인트2"],
  "risks": ["리스크1"],
  "confidence": "High|Medium|Low"
}}
""".strip()


def _normalize_agent_execution_payload(raw_json: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    summary = str(raw_json.get("summary") or "").strip()
    key_points_raw = raw_json.get("key_points")
    risks_raw = raw_json.get("risks")
    confidence = str(raw_json.get("confidence") or "Low").strip() or "Low"

    key_points: List[str] = []
    if isinstance(key_points_raw, list):
        for item in key_points_raw[:4]:
            text = str(item or "").strip()
            if text:
                key_points.append(text)

    risks: List[str] = []
    if isinstance(risks_raw, list):
        for item in risks_raw[:3]:
            text = str(item or "").strip()
            if text:
                risks.append(text)

    if not summary:
        summary = str(raw_text or "").strip()
    if not summary:
        summary = "도메인 분석 결과를 생성하지 못했습니다."

    if confidence not in {"High", "Medium", "Low"}:
        confidence = "Low"

    return {
        "summary": summary,
        "key_points": key_points,
        "risks": risks,
        "confidence": confidence,
    }


def _execute_branch_agents(
    *,
    branch_name: str,
    enabled: bool,
    dispatch_mode: str,
    agents: List[str],
    request: GraphRagAnswerRequest,
    route_decision: Dict[str, Any],
    context_meta: Dict[str, Any],
    flow_type: Optional[str] = None,
    flow_run_id: Optional[str] = None,
    user_id: Optional[str] = None,
    agent_llm_enabled: bool = True,
) -> Dict[str, Any]:
    started_at = time.time()
    if not enabled:
        return {
            "branch": branch_name,
            "enabled": False,
            "dispatch_mode": "skip",
            "agent_runs": [],
            "duration_ms": 0,
        }

    agent_runs: List[Dict[str, Any]] = []
    agent_model_policy = route_decision.get("agent_model_policy")
    if not isinstance(agent_model_policy, dict):
        agent_model_policy = _build_agent_model_policy()
    for agent_name in agents:
        run_result = execute_agent_stub(
            agent_name,
            branch=branch_name,
            request=request,
            route_decision=route_decision,
            context_meta=context_meta,
        )
        configured_model = str(agent_model_policy.get(agent_name) or "").strip()
        if configured_model:
            run_result.setdefault("llm_model", configured_model)
        tool_probe = run_result.get("tool_probe") if isinstance(run_result.get("tool_probe"), dict) else {}

        agent_llm_result: Dict[str, Any] = {
            "enabled": agent_llm_enabled,
            "status": "skipped",
            "reason": "agent_llm_disabled",
        }
        if agent_llm_enabled:
            try:
                agent_model = configured_model or DOMAIN_AGENT_MODEL
                agent_prompt = _build_agent_execution_prompt(
                    agent_name=agent_name,
                    branch_name=branch_name,
                    request=request,
                    route_decision=route_decision,
                    tool_probe=tool_probe,
                    context_meta=context_meta,
                )
                agent_llm = _resolve_agent_llm(
                    model_name=agent_model,
                    timeout_sec=request.timeout_sec,
                )
                metadata_json = {
                    "log_type": "agent_execution",
                    "branch": branch_name,
                    "dispatch_mode": dispatch_mode,
                    "agent": agent_name,
                    "tool": str(tool_probe.get("tool") or ""),
                    "tool_status": str(tool_probe.get("status") or ""),
                    "row_count": int(tool_probe.get("row_count") or 0),
                    "metric_value": int(tool_probe.get("metric_value") or 0),
                }
                with track_llm_call(
                    model_name=agent_model,
                    provider="Google",
                    service_name="graph_rag_agent_execution",
                    request_prompt=agent_prompt,
                    user_id=user_id,
                    flow_type=flow_type,
                    flow_run_id=flow_run_id,
                    agent_name=agent_name,
                    metadata_json=metadata_json,
                ) as tracker:
                    agent_response = agent_llm.invoke(agent_prompt)
                    tracker.set_response(agent_response)

                agent_raw_text = _normalize_llm_text(getattr(agent_response, "content", None)).strip()
                if not agent_raw_text:
                    agent_raw_text = _normalize_llm_text(agent_response).strip()
                agent_raw_json = _extract_json_block(agent_raw_text)
                agent_payload = _normalize_agent_execution_payload(agent_raw_json, agent_raw_text)
                agent_llm_result = {
                    "enabled": True,
                    "status": "ok",
                    "reason": "agent_llm_executed",
                    "model": agent_model,
                    "payload": agent_payload,
                    "raw_model_output": agent_raw_json or {"raw_text": agent_raw_text},
                }
            except Exception as error:
                agent_llm_result = {
                    "enabled": True,
                    "status": "degraded",
                    "reason": "agent_llm_failed",
                    "model": configured_model or DOMAIN_AGENT_MODEL,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
        run_result["agent_llm"] = agent_llm_result
        agent_runs.append(run_result)

    return {
        "branch": branch_name,
        "enabled": True,
        "dispatch_mode": dispatch_mode,
        "agent_runs": agent_runs,
        "duration_ms": int((time.time() - started_at) * 1000),
    }


def _execute_supervisor_plan(
    *,
    request: GraphRagAnswerRequest,
    route_decision: Dict[str, Any],
    supervisor_execution: Dict[str, Any],
    context_meta: Dict[str, Any],
    flow_type: Optional[str] = None,
    flow_run_id: Optional[str] = None,
    user_id: Optional[str] = None,
    agent_llm_enabled: bool = True,
) -> Dict[str, Any]:
    branch_plan = supervisor_execution.get("branch_plan") if isinstance(supervisor_execution.get("branch_plan"), list) else []
    if not branch_plan:
        return {
            "status": "skipped",
            "reason": "branch_plan_missing",
            "branch_results": [],
            "invoked_agent_count": 0,
        }

    def _normalize_branch(branch_item: Optional[Dict[str, Any]], fallback_branch: str) -> Dict[str, Any]:
        if not isinstance(branch_item, dict):
            return {"branch": fallback_branch, "enabled": False, "dispatch_mode": "skip", "agents": []}
        raw_agents = branch_item.get("agents") if isinstance(branch_item.get("agents"), list) else []
        branch_name = str(branch_item.get("branch") or fallback_branch).strip() or fallback_branch
        dispatch_mode = str(branch_item.get("dispatch_mode") or ("single" if branch_item.get("enabled") else "skip")).strip().lower()
        if dispatch_mode not in {"skip", "single", "parallel"}:
            dispatch_mode = "single" if branch_item.get("enabled") else "skip"
        return {
            "branch": branch_name,
            "enabled": bool(branch_item.get("enabled")),
            "dispatch_mode": dispatch_mode,
            "agents": [str(agent).strip() for agent in raw_agents if str(agent).strip()],
        }

    normalized_branches: List[Dict[str, Any]] = []
    for index, branch_item in enumerate(branch_plan):
        fallback = f"branch_{index + 1}"
        normalized_branches.append(_normalize_branch(branch_item, fallback))

    branch_by_name = {item["branch"]: item for item in normalized_branches}
    sql_cfg = branch_by_name.get("sql", {"branch": "sql", "enabled": False, "dispatch_mode": "skip", "agents": []})
    graph_cfg = branch_by_name.get("graph", {"branch": "graph", "enabled": False, "dispatch_mode": "skip", "agents": []})
    tool_mode = str(supervisor_execution.get("tool_mode") or "single")
    parallel_mode = tool_mode == "parallel" and sql_cfg["enabled"] and graph_cfg["enabled"]
    branch_results_by_name: Dict[str, Dict[str, Any]] = {}
    fallback_used = False
    fallback_reason = ""

    def _branch_requests_companion(branch_result: Dict[str, Any], companion_branch: str) -> bool:
        if not isinstance(branch_result, dict):
            return False
        agent_runs = branch_result.get("agent_runs") if isinstance(branch_result.get("agent_runs"), list) else []
        for run in agent_runs:
            if not isinstance(run, dict):
                continue
            if str(run.get("companion_branch") or "").strip() != companion_branch:
                continue
            if bool(run.get("needs_companion_branch")):
                return True
        return False

    if parallel_mode:
        with ThreadPoolExecutor(max_workers=2) as executor:
            sql_future = executor.submit(
                _execute_branch_agents,
                branch_name="sql",
                enabled=sql_cfg["enabled"],
                dispatch_mode="parallel",
                agents=sql_cfg["agents"],
                request=request,
                route_decision=route_decision,
                context_meta=context_meta,
                flow_type=flow_type,
                flow_run_id=flow_run_id,
                user_id=user_id,
                agent_llm_enabled=agent_llm_enabled,
            )
            graph_future = executor.submit(
                _execute_branch_agents,
                branch_name="graph",
                enabled=graph_cfg["enabled"],
                dispatch_mode="parallel",
                agents=graph_cfg["agents"],
                request=request,
                route_decision=route_decision,
                context_meta=context_meta,
                flow_type=flow_type,
                flow_run_id=flow_run_id,
                user_id=user_id,
                agent_llm_enabled=agent_llm_enabled,
            )
            branch_results_by_name["sql"] = sql_future.result()
            branch_results_by_name["graph"] = graph_future.result()
    else:
        branch_results_by_name["sql"] = _execute_branch_agents(
            branch_name="sql",
            enabled=sql_cfg["enabled"],
            dispatch_mode="single" if sql_cfg["enabled"] else "skip",
            agents=sql_cfg["agents"],
            request=request,
            route_decision=route_decision,
            context_meta=context_meta,
            flow_type=flow_type,
            flow_run_id=flow_run_id,
            user_id=user_id,
            agent_llm_enabled=agent_llm_enabled,
        )
        branch_results_by_name["graph"] = _execute_branch_agents(
            branch_name="graph",
            enabled=graph_cfg["enabled"],
            dispatch_mode="single" if graph_cfg["enabled"] else "skip",
            agents=graph_cfg["agents"],
            request=request,
            route_decision=route_decision,
            context_meta=context_meta,
            flow_type=flow_type,
            flow_run_id=flow_run_id,
            user_id=user_id,
            agent_llm_enabled=agent_llm_enabled,
        )
        sql_result = branch_results_by_name.get("sql", {})
        graph_result = branch_results_by_name.get("graph", {})

        if sql_cfg["enabled"] and not graph_cfg["enabled"] and _branch_requests_companion(sql_result, "graph"):
            fallback_agents = graph_cfg["agents"] or sql_cfg["agents"]
            branch_results_by_name["graph"] = _execute_branch_agents(
                branch_name="graph",
                enabled=True,
                dispatch_mode="single",
                agents=fallback_agents,
                request=request,
                route_decision=route_decision,
                context_meta=context_meta,
                flow_type=flow_type,
                flow_run_id=flow_run_id,
                user_id=user_id,
                agent_llm_enabled=agent_llm_enabled,
            )
            fallback_used = True
            fallback_reason = "sql_branch_requested_graph_companion"
        elif graph_cfg["enabled"] and not sql_cfg["enabled"] and _branch_requests_companion(graph_result, "sql"):
            fallback_agents = sql_cfg["agents"] or graph_cfg["agents"]
            branch_results_by_name["sql"] = _execute_branch_agents(
                branch_name="sql",
                enabled=True,
                dispatch_mode="single",
                agents=fallback_agents,
                request=request,
                route_decision=route_decision,
                context_meta=context_meta,
                flow_type=flow_type,
                flow_run_id=flow_run_id,
                user_id=user_id,
                agent_llm_enabled=agent_llm_enabled,
            )
            fallback_used = True
            fallback_reason = "graph_branch_requested_sql_companion"

    for branch_cfg in normalized_branches:
        branch_name = branch_cfg["branch"]
        if branch_name in {"sql", "graph"}:
            continue
        branch_results_by_name[branch_name] = _execute_branch_agents(
            branch_name=branch_name,
            enabled=branch_cfg["enabled"],
            dispatch_mode="single" if branch_cfg["enabled"] else "skip",
            agents=branch_cfg["agents"],
            request=request,
            route_decision=route_decision,
            context_meta=context_meta,
            flow_type=flow_type,
            flow_run_id=flow_run_id,
            user_id=user_id,
            agent_llm_enabled=agent_llm_enabled,
        )

    branch_results = [
        branch_results_by_name[branch_cfg["branch"]]
        for branch_cfg in normalized_branches
        if branch_cfg["branch"] in branch_results_by_name
    ]

    invoked_agent_count = sum(len(item.get("agent_runs") or []) for item in branch_results)
    return {
        "status": "executed",
        "dispatch_mode": "parallel" if parallel_mode else "single",
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "branch_results": branch_results,
        "invoked_agent_count": invoked_agent_count,
    }


def _route_query_type_multi_agent(
    request: GraphRagAnswerRequest,
    *,
    router_llm=None,
    enable_llm_router: bool = True,
    user_id: Optional[str] = None,
    flow_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    agent_model_policy = _build_agent_model_policy()
    explicit_question_id = _normalize_question_id(request.question_id)
    explicit_route: Optional[Dict[str, Any]] = None
    if explicit_question_id:
        explicit_answer_type = (QUESTION_ID_SPECS.get(explicit_question_id) or {}).get("answer_type") or "general_macro"
        explicit_route = {
            "agent": "question_id_agent",
            "selected_type": explicit_answer_type,
            "confidence": 0.99,
            "reason": "explicit_question_id",
            "question_id": explicit_question_id,
            "scores": {explicit_answer_type: 0.99},
        }
    us_single_stock_route = _build_us_single_stock_forced_route(
        question=request.question,
        country_code=request.country_code,
        country=request.country,
    )

    if (not explicit_route) and (not us_single_stock_route) and _is_general_knowledge_question(request.question):
        selected_type = GENERAL_KNOWLEDGE_ROUTE_TYPE
        execution_strategy = _derive_conditional_parallel_strategy(
            request=request,
            selected_type=selected_type,
            selected_question_id=None,
        )
        general_agent = {
            "agent": "general_knowledge_agent",
            "selected_type": selected_type,
            "confidence": 0.99,
            "reason": "general_knowledge_shortcut",
            "scores": {selected_type: 0.99},
        }
        return {
            "selected_type": selected_type,
            "confidence": 0.99,
            "confidence_level": "High",
            "selected_question_id": None,
            "matched_symbols": [],
            "matched_security_ids": [],
            "matched_companies": [],
            "agents": [general_agent],
            "aggregated_scores": {selected_type: 0.99},
            "sql_need": execution_strategy["sql_need"],
            "graph_need": execution_strategy["graph_need"],
            "tool_mode": execution_strategy["tool_mode"],
            "target_agents": execution_strategy["target_agents"],
            "agent_model_policy": agent_model_policy,
        }

    llm_route = _invoke_router_llm_agent(
        request,
        router_llm=router_llm,
        user_id=user_id,
        flow_run_id=flow_run_id,
    ) if enable_llm_router else {
        "agent": "llm_router_agent",
        "selected_type": "general_macro",
        "confidence": 0.0,
        "reason": "llm_router_skipped",
        "scores": {},
    }
    keyword_route = _score_keyword_route(request.question)
    scope_route = _score_scope_route(
        question=request.question,
        country_code=request.country_code,
        country=request.country,
    )
    agents = [llm_route, keyword_route, scope_route]
    if us_single_stock_route:
        agents.insert(0, us_single_stock_route)
    if explicit_route:
        agents.insert(0, explicit_route)

    aggregated_scores: Dict[str, float] = {}
    for agent in agents:
        scores = agent.get("scores") or {}
        if not isinstance(scores, dict):
            continue
        weight = {
            "question_id_agent": 1.4,
            "us_single_stock_agent": 1.4,
            "llm_router_agent": 1.2,
            "keyword_agent": 1.0,
            "scope_agent": 1.0,
        }.get(str(agent.get("agent") or ""), 1.0)
        for route_type, score in scores.items():
            try:
                value = float(score)
            except Exception:
                value = 0.0
            aggregated_scores[route_type] = aggregated_scores.get(route_type, 0.0) + (value * weight)

    if not aggregated_scores:
        aggregated_scores["general_macro"] = 0.3

    selected_type, selected_score = max(aggregated_scores.items(), key=lambda item: item[1])
    selected_confidence = min(round(selected_score / max(float(len(agents)), 1.0), 3), 0.99)
    if explicit_route:
        selected_type = str(explicit_route.get("selected_type") or selected_type)
        selected_confidence = max(selected_confidence, 0.95)
    elif us_single_stock_route:
        selected_type = str(us_single_stock_route.get("selected_type") or selected_type)
        selected_confidence = max(selected_confidence, 0.9)
    confidence_level = "High" if selected_confidence >= 0.75 else "Medium" if selected_confidence >= 0.45 else "Low"

    inferred_question_id = _normalize_question_id(llm_route.get("question_id")) or _infer_required_question_id(
        request.question,
        explicit_question_id,
    )
    mapped_question_id = ANSWER_TYPE_TO_QUESTION_ID.get(selected_type)
    if selected_type == US_SINGLE_STOCK_ROUTE_TYPE and not explicit_question_id:
        selected_question_id = None
    else:
        selected_question_id = explicit_question_id or inferred_question_id or mapped_question_id
    execution_strategy = _derive_conditional_parallel_strategy(
        request=request,
        selected_type=selected_type,
        selected_question_id=selected_question_id,
    )

    matched_symbols: List[str] = []
    matched_security_ids: List[str] = []
    matched_companies: List[str] = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        if not matched_symbols:
            matched_symbols = GraphRagAnswerRequest._normalize_focus_list(agent.get("matched_symbols"))
        if not matched_security_ids:
            matched_security_ids = GraphRagAnswerRequest._normalize_focus_list(agent.get("matched_security_ids"))
        if not matched_companies:
            matched_companies = GraphRagAnswerRequest._normalize_focus_list(agent.get("matched_companies"))
        if matched_symbols and (matched_companies or matched_security_ids):
            break

    if not matched_security_ids:
        matched_security_ids = _derive_matched_security_ids(
            matched_symbols=matched_symbols,
            selected_type=selected_type,
            requested_country_code=request.country_code,
            target_agents=execution_strategy.get("target_agents") or [],
        )

    return {
        "selected_type": selected_type,
        "confidence": selected_confidence,
        "confidence_level": confidence_level,
        "selected_question_id": selected_question_id,
        "matched_symbols": matched_symbols,
        "matched_security_ids": matched_security_ids,
        "matched_companies": matched_companies,
        "agents": agents,
        "aggregated_scores": {k: round(v, 3) for k, v in sorted(aggregated_scores.items(), key=lambda item: item[1], reverse=True)},
        "sql_need": execution_strategy["sql_need"],
        "graph_need": execution_strategy["graph_need"],
        "tool_mode": execution_strategy["tool_mode"],
        "target_agents": execution_strategy["target_agents"],
        "agent_model_policy": agent_model_policy,
    }


def _format_region_scope_for_prompt(region_code: Optional[str]) -> str:
    raw = str(region_code or "").strip()
    if not raw:
        return "전체 지역"
    tokens = [token.strip() for token in raw.split(",") if token and token.strip()]
    if not tokens:
        return raw
    if all(re.fullmatch(r"\d{5}", token) for token in tokens):
        labels: List[str] = []
        for token in tokens:
            labels.append(LAWD_NAME_BY_CODE.get(token, token))
        if len(tokens) <= 4:
            return ", ".join(labels)
        return f"{', '.join(labels[:3])} ... (총 {len(tokens)}개 지역)"
    return raw


def _format_property_type_for_prompt(property_type: Optional[str]) -> str:
    value = str(property_type or "").strip().lower()
    if not value:
        return "미지정"
    return PROPERTY_TYPE_LABELS.get(value, value)


def _build_route_prompt_guidance(
    route: Dict[str, Any],
    *,
    request: Optional[GraphRagAnswerRequest] = None,
    context_meta: Optional[Dict[str, Any]] = None,
) -> str:
    selected_type = str(route.get("selected_type") or "general_macro")
    base = QUERY_TYPE_TO_PROMPT_GUIDANCE.get(selected_type) or QUERY_TYPE_TO_PROMPT_GUIDANCE["general_macro"]
    question_id = str(route.get("selected_question_id") or "").strip()
    meta = context_meta if isinstance(context_meta, dict) else {}
    parsed_scope = meta.get("parsed_scope") if isinstance(meta.get("parsed_scope"), dict) else {}

    request_country_code = str((request.country_code if request else "") or "").strip().upper()
    if request_country_code in {"USKR", "KRUS", "US/KR", "KR/US", "KR-US"}:
        request_country_code = "US-KR"
    scope_country_code = request_country_code or str(meta.get("resolved_country_code") or "").strip().upper()
    scope_region_code = (
        str((request.region_code if request else "") or "").strip()
        or str(parsed_scope.get("region_code") or "").strip()
    )
    scope_property_type = (
        str((request.property_type if request else "") or "").strip()
        or str(parsed_scope.get("property_type") or "").strip()
    )

    guidance_lines = [base]
    if question_id:
        guidance_lines.append(f"Question profile: {question_id}.")

    if selected_type in {"compare_outlook", "fx_driver"} and (scope_country_code == "US-KR" or question_id == "Q5"):
        guidance_lines.append(
            "US-KR 비교 템플릿 강제: 동일 지표/동일 기간으로 [미국 관측] → [한국 관측] → [격차/전이 경로] → [상방/하방 리스크] 순서로 서술."
        )

    if selected_type == US_SINGLE_STOCK_ROUTE_TYPE:
        matched_symbols = route.get("matched_symbols")
        if isinstance(matched_symbols, list) and matched_symbols:
            preview = ", ".join(str(symbol) for symbol in matched_symbols[:3] if str(symbol).strip())
            if preview:
                guidance_lines.append(f"Detected US ticker: {preview}.")
        guidance_lines.append(
            "US 개별종목 질의로 처리: 종목 직접 근거를 우선 사용하고, 종목 근거가 없으면 근거 부족을 명확히 표기."
        )
        guidance_lines.append(
            "key_points는 반드시 `가격/변동률`, `실적`, `밸류`, `리스크` 라벨 섹션을 모두 포함."
        )

    if selected_type == "real_estate_detail" or (
        scope_country_code in {"KR", "US-KR"} and (scope_region_code or scope_property_type)
    ):
        guidance_lines.append(
            f"KR 부동산 템플릿 강제: 대상 지역={_format_region_scope_for_prompt(scope_region_code)}, "
            f"유형={_format_property_type_for_prompt(scope_property_type)}. "
            "가격(가중 평균)·거래건수·전월 대비 흐름을 함께 설명."
        )

    if selected_type in CONDITIONAL_SCENARIO_ROUTE_TYPES or question_id in CONDITIONAL_SCENARIO_QUESTION_IDS:
        guidance_lines.append(
            "추천/타이밍 질의는 조건형 시나리오 출력만 허용: base/bull/bear의 조건과 함의를 제시하고, 직접 매수/매도 지시는 금지."
        )

    return "\n".join(guidance_lines)


def _guess_driver_direction(text: str) -> str:
    lowered = str(text or "").lower()
    if any(token in lowered for token in ["상승", "증가", "확대", "급등", "up", "rise"]):
        return "up"
    if any(token in lowered for token in ["하락", "감소", "둔화", "급락", "down", "drop"]):
        return "down"
    return "mixed"


def _guess_impact_horizon(text: str) -> str:
    lowered = str(text or "").lower()
    if any(token in lowered for token in ["장기", "long", "연간"]):
        return "long"
    if any(token in lowered for token in ["중기", "medium", "분기"]):
        return "medium"
    return "short"


def _infer_evidence_type(citation: GraphRagCitation) -> str:
    haystack = " ".join(
        [
            str(citation.doc_title or ""),
            str(citation.text or ""),
            " ".join(citation.support_labels or []),
        ]
    ).lower()
    if any(token in haystack for token in ["부동산", "아파트", "전세", "월세", "housing", "real estate"]):
        return "housing"
    if any(token in haystack for token in ["indicator", "지표"]):
        return "indicator"
    if any(token in haystack for token in ["event", "이벤트", "정책"]):
        return "event"
    return "document"


def _to_iso_date(value: Any) -> str:
    parsed = _parse_iso_datetime(value)
    if parsed:
        return parsed.date().isoformat()
    text = str(value or "").strip()
    if len(text) >= 10:
        return text[:10]
    return date.today().isoformat()


def _is_direct_buy_sell_instruction(summary: str, key_points: List[str]) -> bool:
    text = " ".join([str(summary or ""), " ".join(key_points or [])]).strip()
    if not text:
        return False
    return bool(DIRECT_BUY_SELL_PATTERN.search(text))


def _build_required_question_schema_payload(
    *,
    question_id: str,
    request: GraphRagAnswerRequest,
    as_of_date: date,
    payload: GraphRagAnswerPayload,
    citations: List[GraphRagCitation],
    confidence: Dict[str, Any],
    min_citations: int,
    context_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    spec = QUESTION_ID_SPECS.get(question_id) or {}
    parsed_scope = (context_meta or {}).get("parsed_scope") or {}
    direct_instruction = _is_direct_buy_sell_instruction(
        summary=payload.conclusion,
        key_points=payload.key_points,
    )

    drivers = [
        {
            "label": point,
            "direction": _guess_driver_direction(point),
            "impact_horizon": _guess_impact_horizon(point),
            "confidence": float(confidence.get("score") or 0.0),
        }
        for point in payload.key_points[:5]
    ]
    if not drivers:
        drivers = [
            {
                "label": payload.conclusion,
                "direction": _guess_driver_direction(payload.conclusion),
                "impact_horizon": _guess_impact_horizon(payload.conclusion),
                "confidence": float(confidence.get("score") or 0.0),
            }
        ]

    evidences = [
        {
            "id": citation.evidence_id or citation.doc_id or f"citation:{index + 1}",
            "type": _infer_evidence_type(citation),
            "source": citation.doc_title or citation.doc_url or "GraphEvidence",
            "date": _to_iso_date(citation.published_at),
            "snippet": str(citation.text or "")[:300],
        }
        for index, citation in enumerate(citations[:10])
    ]

    scenarios: List[Dict[str, Any]] = []
    scenario_names = ["base", "bull", "bear"]
    for idx, pathway in enumerate(payload.impact_pathways[:3]):
        scenarios.append(
            {
                "name": scenario_names[idx] if idx < len(scenario_names) else f"scenario_{idx + 1}",
                "conditions": [pathway.explanation],
                "implication": pathway.explanation,
            }
        )
    if question_id == "Q6" and not scenarios:
        scenarios = [
            {
                "name": "base",
                "conditions": ["금리 안정과 거래량 회복이 동시에 확인될 때"],
                "implication": "분할 매수/매도 시나리오를 검토합니다.",
            },
            {
                "name": "bull",
                "conditions": ["거래량 증가와 가격 상승 추세가 동반될 때"],
                "implication": "상향 추세 지속 가능성이 커집니다.",
            },
            {
                "name": "bear",
                "conditions": ["가격 하락과 거래량 위축이 함께 나타날 때"],
                "implication": "관망 또는 리스크 축소가 우선입니다.",
            },
        ]

    limitations = [payload.uncertainty] if payload.uncertainty else []
    if len(evidences) < min_citations:
        limitations.append("최소 근거 수(3건) 미달로 결론 해석에 제약이 있습니다.")

    return {
        "question_id": question_id,
        "question_text": request.question,
        "answer_type": spec.get("answer_type"),
        "scope": {
            "country_code": request.country_code or spec.get("country_code") or request.country or "",
            "region_code": request.region_code or parsed_scope.get("region_code"),
            "property_type": request.property_type or parsed_scope.get("property_type"),
            "time_range": request.time_range,
            "as_of_date": as_of_date.isoformat(),
        },
        "summary": payload.conclusion,
        "drivers": drivers,
        "evidences": evidences,
        "scenarios": scenarios,
        "recommendation_guardrail": {
            "is_direct_buy_sell_instruction": direct_instruction,
            "risk_notice": payload.uncertainty or "투자 판단은 추가 검증이 필요합니다.",
            "decision_checklist": [
                "데이터 최신성(발표 시점/반영 지연)을 확인합니다.",
                "시나리오별 손실 한도를 사전에 정의합니다.",
                "단일 지표가 아닌 복수 근거를 교차 확인합니다.",
            ],
        },
        "confidence": {
            "level": confidence.get("level") or "Low",
            "score": float(confidence.get("score") or 0.0),
        },
        "limitations": limitations,
    }


def _validate_required_question_schema_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return {"enabled": True, "is_valid": False, "errors": ["payload must be object"]}

    question_id = str(payload.get("question_id") or "")
    spec = QUESTION_ID_SPECS.get(question_id)
    if not spec:
        errors.append("question_id is invalid")
    answer_type = str(payload.get("answer_type") or "")
    if spec and answer_type != spec.get("answer_type"):
        errors.append("answer_type mismatch")

    scope = payload.get("scope")
    if not isinstance(scope, dict):
        errors.append("scope must be object")
    else:
        scope_country_code = str(scope.get("country_code") or "")
        if spec and scope_country_code != spec.get("country_code"):
            errors.append("scope.country_code mismatch")
        if not str(scope.get("as_of_date") or ""):
            errors.append("scope.as_of_date is required")

    summary = str(payload.get("summary") or "").strip()
    if not summary:
        errors.append("summary is required")

    drivers = payload.get("drivers")
    if not isinstance(drivers, list) or not drivers:
        errors.append("drivers must be non-empty array")

    evidences = payload.get("evidences")
    if not isinstance(evidences, list):
        errors.append("evidences must be array")
    else:
        if len(evidences) < 3 or len(evidences) > 10:
            errors.append("evidences must contain 3~10 items")

    recommendation_guardrail = payload.get("recommendation_guardrail")
    if not isinstance(recommendation_guardrail, dict):
        errors.append("recommendation_guardrail must be object")
    else:
        if bool(recommendation_guardrail.get("is_direct_buy_sell_instruction")):
            errors.append("direct buy/sell instruction is not allowed")

    confidence = payload.get("confidence")
    if not isinstance(confidence, dict):
        errors.append("confidence must be object")
    else:
        level = str(confidence.get("level") or "")
        if level not in {"High", "Medium", "Low"}:
            errors.append("confidence.level must be High|Medium|Low")
        try:
            score = float(confidence.get("score"))
            if score < 0.0 or score > 1.0:
                errors.append("confidence.score must be between 0 and 1")
        except Exception:
            errors.append("confidence.score must be numeric")

    return {
        "enabled": True,
        "is_valid": len(errors) == 0,
        "errors": errors,
    }


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _assess_data_freshness(
    *,
    citations: List[GraphRagCitation],
    as_of_date: date,
) -> Dict[str, Any]:
    freshness_warn_hours = max(
        _safe_int(os.getenv("GRAPH_RAG_DATA_FRESHNESS_WARN_HOURS"), 72),
        1,
    )
    freshness_fail_hours = max(
        _safe_int(os.getenv("GRAPH_RAG_DATA_FRESHNESS_FAIL_HOURS"), 168),
        freshness_warn_hours,
    )
    if not citations:
        return {
            "status": "missing",
            "age_hours": None,
            "warn_hours": freshness_warn_hours,
            "fail_hours": freshness_fail_hours,
            "reason": "no_citations",
        }

    published_at_values = [
        _parse_iso_datetime(citation.published_at)
        for citation in citations
        if citation.published_at
    ]
    published_at_values = [item for item in published_at_values if item is not None]
    if not published_at_values:
        return {
            "status": "unknown",
            "age_hours": None,
            "warn_hours": freshness_warn_hours,
            "fail_hours": freshness_fail_hours,
            "reason": "citation_timestamp_missing",
        }

    latest_published_at = max(published_at_values)
    as_of_dt = datetime.combine(as_of_date, datetime.min.time(), tzinfo=latest_published_at.tzinfo)
    age_hours = max(0.0, (as_of_dt - latest_published_at).total_seconds() / 3600.0)
    if age_hours >= freshness_fail_hours:
        status = "stale"
    elif age_hours >= freshness_warn_hours:
        status = "warning"
    else:
        status = "fresh"

    return {
        "status": status,
        "age_hours": round(age_hours, 1),
        "latest_evidence_published_at": latest_published_at.isoformat(),
        "warn_hours": freshness_warn_hours,
        "fail_hours": freshness_fail_hours,
    }


def _resolve_collection_eta_minutes(*, used_evidence_count: int) -> int:
    if used_evidence_count > 0:
        return 0
    return max(_safe_int(os.getenv("GRAPH_RAG_COLLECTION_ETA_MINUTES"), 120), 0)


def _apply_c_option_guardrail(
    *,
    payload: GraphRagAnswerPayload,
    used_evidence_count: int,
) -> GraphRagAnswerPayload:
    if used_evidence_count > 0:
        return payload

    key_points = [item for item in payload.key_points if item]
    key_points = list(dict.fromkeys(key_points + [
        "현재 질의에 직접 매핑되는 근거가 부족합니다.",
        "수집 스케줄 반영 후 재질의 시 보강된 답변을 제공합니다.",
    ]))[:7]
    return GraphRagAnswerPayload(
        conclusion="현재 수집된 근거가 부족하여 확정적 결론을 제공하기 어렵습니다.",
        uncertainty="근거 불충분: 데이터 수집/동기화 완료 후 재확인이 필요합니다.",
        key_points=key_points,
        impact_pathways=[],
    )


def _dedupe_preserve_order(values: List[str], limit: int = 7) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
        if len(deduped) >= max(limit, 1):
            break
    return deduped


def _sanitize_directive_text(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return normalized
    sanitized = BUY_SELL_TEXT_PATTERN.sub("포지션 조정", normalized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized


def _extract_us_single_stock_focus_terms(route_decision: Dict[str, Any]) -> set[str]:
    focus_terms: set[str] = set()
    for key in ("matched_symbols", "matched_security_ids", "matched_companies"):
        values = route_decision.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            token = str(value or "").strip()
            if not token:
                continue
            lowered = token.lower()
            focus_terms.add(lowered)
            compact = re.sub(r"\s+", "", lowered)
            compact = re.sub(r"[^0-9a-z가-힣]", "", compact)
            if compact:
                focus_terms.add(compact)
    return focus_terms


def _score_stock_citation_text(
    *,
    text: str,
    keywords: set[str],
    focus_terms: set[str],
    require_numeric: bool,
    require_focus_match: bool,
) -> int:
    lowered = text.lower()
    compact = re.sub(r"\s+", "", lowered)
    compact = re.sub(r"[^0-9a-z가-힣]", "", compact)

    has_keyword = any(keyword in lowered for keyword in keywords)
    if not has_keyword:
        return -1

    has_percent = bool(US_STOCK_PERCENT_PATTERN.search(text))
    has_price = bool(US_STOCK_PRICE_PATTERN.search(text))
    has_numeric_signal = has_percent or has_price
    if require_numeric and not has_numeric_signal:
        return -1

    has_focus_match = False
    for term in focus_terms:
        if not term:
            continue
        if term in lowered or term in compact:
            has_focus_match = True
            break

    if require_focus_match and not has_focus_match:
        return -1

    score = 2
    if has_percent:
        score += 4
    if has_price:
        score += 2
    if any(keyword in lowered for keyword in US_STOCK_PRICE_ACTION_KEYWORDS):
        score += 2

    if has_focus_match:
        score += 3

    return score


def _summarize_stock_signal_from_citations(
    citations: List[GraphRagCitation],
    keywords: set[str],
    *,
    focus_terms: Optional[set[str]] = None,
    require_numeric: bool = False,
    require_focus_match: bool = False,
    max_chars: int = 140,
) -> str:
    best_score = -1
    best_summary = ""
    normalized_focus_terms = focus_terms or set()
    for citation in citations:
        text = re.sub(r"\s+", " ", str(citation.text or "").strip())
        if not text:
            continue
        score = _score_stock_citation_text(
            text=text,
            keywords=keywords,
            focus_terms=normalized_focus_terms,
            require_numeric=require_numeric,
            require_focus_match=require_focus_match,
        )
        if score < 0:
            continue

        summary = text if len(text) <= max_chars else f"{text[: max_chars - 1].rstrip()}…"
        doc_id = str(citation.doc_id or "").strip()
        candidate = f"{summary} ({doc_id})" if doc_id else summary
        if score > best_score:
            best_score = score
            best_summary = candidate
    return best_summary


def _enforce_us_single_stock_template_output(
    *,
    payload: GraphRagAnswerPayload,
    route_decision: Dict[str, Any],
    citations: List[GraphRagCitation],
) -> tuple[GraphRagAnswerPayload, bool, List[str]]:
    selected_type = str(route_decision.get("selected_type") or "").strip()
    if selected_type != US_SINGLE_STOCK_ROUTE_TYPE:
        return payload, False, []

    focus_terms = _extract_us_single_stock_focus_terms(route_decision)
    template_points: List[str] = []
    missing_sections: List[str] = []
    for label, keywords, fallback in US_SINGLE_STOCK_TEMPLATE_SPECS:
        matched_summary = _summarize_stock_signal_from_citations(
            citations=citations,
            keywords=keywords,
            focus_terms=focus_terms,
            require_numeric=(label == "가격/변동률"),
            require_focus_match=(label in US_SINGLE_STOCK_STRICT_SECTION_LABELS),
        )
        if matched_summary:
            template_points.append(f"{label}: {matched_summary}")
        else:
            template_points.append(f"{label}: {fallback}")
            missing_sections.append(label)

    sanitized_points = [_sanitize_directive_text(point) for point in payload.key_points]
    key_points = _dedupe_preserve_order(template_points + sanitized_points, limit=7)

    uncertainty = str(payload.uncertainty or "").strip() or "근거 불충분"
    if missing_sections:
        missing_text = ", ".join(missing_sections)
        note = f"{missing_text} 항목은 종목 직접 근거가 부족할 수 있습니다."
        if note not in uncertainty:
            uncertainty = f"{uncertainty} {note}".strip()

    return (
        GraphRagAnswerPayload(
            conclusion=payload.conclusion,
            uncertainty=uncertainty,
            key_points=key_points,
            impact_pathways=payload.impact_pathways,
            confidence_level=payload.confidence_level,
            confidence_score=payload.confidence_score,
        ),
        True,
        missing_sections,
    )


def _has_bullish_conclusion_signal(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in US_STOCK_BULLISH_CONCLUSION_KEYWORDS)


def _build_us_single_stock_trend_snapshot(
    *,
    context: GraphRagContextResponse,
    route_decision: Dict[str, Any],
) -> Dict[str, Any]:
    focus_terms = _extract_us_single_stock_focus_terms(route_decision)
    if not focus_terms:
        return {
            "applied": False,
            "reason": "focus_terms_missing",
        }

    focus_evidences = [
        evidence
        for evidence in context.evidences
        if _has_focus_in_evidence_text(evidence, focus_terms)
        and _score_stock_focus_evidence(evidence, focus_terms) > 0
    ]
    if not focus_evidences:
        return {
            "applied": False,
            "reason": "focus_evidence_missing",
        }

    focus_evidences.sort(key=lambda evidence: _to_utc_sortable_datetime(evidence.published_at), reverse=True)
    recent_window = focus_evidences[:6]
    up_count = 0
    down_count = 0
    latest_direction = "mixed"
    for evidence in recent_window:
        direction = _classify_stock_direction(str(evidence.text or ""))
        if latest_direction == "mixed" and direction in {"up", "down"}:
            latest_direction = direction
        if direction == "up":
            up_count += 1
        elif direction == "down":
            down_count += 1

    if down_count > up_count:
        trend_direction = "down"
    elif up_count > down_count:
        trend_direction = "up"
    else:
        trend_direction = "mixed"

    return {
        "applied": True,
        "reason": "ok",
        "recent_focus_window": len(recent_window),
        "up_signals": up_count,
        "down_signals": down_count,
        "trend_direction": trend_direction,
        "latest_direction": latest_direction,
        "latest_focus_published_at": recent_window[0].published_at,
    }


def _enforce_us_single_stock_trend_consistency(
    *,
    payload: GraphRagAnswerPayload,
    context: GraphRagContextResponse,
    route_decision: Dict[str, Any],
) -> tuple[GraphRagAnswerPayload, Dict[str, Any]]:
    selected_type = str(route_decision.get("selected_type") or "").strip()
    if selected_type != US_SINGLE_STOCK_ROUTE_TYPE:
        return payload, {"applied": False, "reason": "route_not_us_single_stock"}

    snapshot = _build_us_single_stock_trend_snapshot(
        context=context,
        route_decision=route_decision,
    )
    if not snapshot.get("applied"):
        return payload, snapshot

    trend_direction = str(snapshot.get("trend_direction") or "mixed")
    latest_direction = str(snapshot.get("latest_direction") or "mixed")
    bullish_conclusion = _has_bullish_conclusion_signal(payload.conclusion)
    bearish_bias = trend_direction == "down" or latest_direction == "down"
    if not (bullish_conclusion and bearish_bias):
        snapshot["adjusted"] = False
        return payload, snapshot

    latest_date = str(snapshot.get("latest_focus_published_at") or "")[:10]
    adjusted_conclusion = (
        "실적 발표 직후 단기 상승 근거는 있으나, 최근 구간에서는 하락 신호가 우세해 단기 방향성은 보수적으로 해석하는 편이 안전합니다."
    )
    adjusted_uncertainty = str(payload.uncertainty or "").strip() or "근거 불충분"
    trend_note = "최근 종목 직접 근거 기준으로 하방 압력이 우세합니다."
    if latest_date:
        trend_note = f"{latest_date} 기준 최근 종목 직접 근거에서 하방 압력이 우세합니다."
    if trend_note not in adjusted_uncertainty:
        adjusted_uncertainty = f"{adjusted_uncertainty} {trend_note}".strip()

    snapshot["adjusted"] = True
    snapshot["reason"] = "bullish_conclusion_conflicts_with_recent_downtrend"
    return (
        GraphRagAnswerPayload(
            conclusion=adjusted_conclusion,
            uncertainty=adjusted_uncertainty,
            key_points=payload.key_points,
            impact_pathways=payload.impact_pathways,
            confidence_level=payload.confidence_level,
            confidence_score=payload.confidence_score,
        ),
        snapshot,
    )


def _build_conditional_scenario_points(
    *,
    payload: GraphRagAnswerPayload,
    route_type: str,
    question_id: Optional[str],
    context_meta: Optional[Dict[str, Any]],
) -> List[str]:
    labels = ["기준", "상방", "하방"]
    scenario_points: List[str] = []
    for idx, pathway in enumerate(payload.impact_pathways[:3]):
        explanation = _sanitize_directive_text(pathway.explanation)
        if not explanation:
            continue
        label = labels[idx] if idx < len(labels) else f"시나리오{idx + 1}"
        scenario_points.append(f"{label} 시나리오: {explanation}")

    if len(scenario_points) >= 3:
        return scenario_points[:3]

    parsed_scope = context_meta.get("parsed_scope") if isinstance(context_meta, dict) else {}
    if not isinstance(parsed_scope, dict):
        parsed_scope = {}
    region_label = _format_region_scope_for_prompt(str(parsed_scope.get("region_code") or ""))
    property_label = _format_property_type_for_prompt(str(parsed_scope.get("property_type") or ""))
    is_real_estate = bool(
        str(parsed_scope.get("property_type") or "").strip()
        or any(token in str(payload.conclusion or "") for token in ["부동산", "아파트", "전세", "월세"])
    )

    default_points: List[str]
    if is_real_estate or route_type == "timing_scenario" or question_id == "Q6":
        default_points = [
            f"기준 시나리오: {region_label} {property_label} 거래량이 유지되고 평균가 변동이 제한될 때 분할 대응을 검토.",
            f"상방 시나리오: {region_label} 거래량 증가와 평균가 동반 상승이 확인될 때 점진적 비중 확대를 검토.",
            f"하방 시나리오: {region_label} 거래량 위축과 가격 하락이 동반될 때 관망/리스크 축소를 우선.",
        ]
    elif route_type == "sector_recommendation" or question_id == "Q4":
        default_points = [
            "기준 시나리오: 실적과 밸류에이션이 컨센서스 범위 내에서 유지될 때 중립 비중을 유지.",
            "상방 시나리오: 이익 상향과 수급 개선이 동반될 때 상대 비중 확대를 검토.",
            "하방 시나리오: 실적 하향과 자금 유출이 동반될 때 방어 섹터 비중 확대를 검토.",
        ]
    else:
        default_points = [
            "기준 시나리오: 핵심 지표가 현재 추세를 유지할 때 기존 포지션을 점검.",
            "상방 시나리오: 성장/유동성 지표가 개선될 때 위험자산 선호 확대 가능성을 검토.",
            "하방 시나리오: 물가/금리 충격이 재확대될 때 방어적 비중 조정을 검토.",
        ]

    return (scenario_points + default_points)[:3]


def _enforce_conditional_scenario_output(
    *,
    payload: GraphRagAnswerPayload,
    route_decision: Dict[str, Any],
    required_question_id: Optional[str],
    context_meta: Optional[Dict[str, Any]],
) -> tuple[GraphRagAnswerPayload, bool]:
    selected_type = str(route_decision.get("selected_type") or "").strip()
    selected_question_id = str(route_decision.get("selected_question_id") or "").strip() or str(required_question_id or "").strip()
    should_enforce = (
        selected_type in CONDITIONAL_SCENARIO_ROUTE_TYPES
        or selected_question_id in CONDITIONAL_SCENARIO_QUESTION_IDS
    )
    if not should_enforce:
        return payload, False

    scenario_points = _build_conditional_scenario_points(
        payload=payload,
        route_type=selected_type,
        question_id=selected_question_id or None,
        context_meta=context_meta,
    )
    sanitized_points = [_sanitize_directive_text(point) for point in payload.key_points]
    key_points = _dedupe_preserve_order(scenario_points + sanitized_points, limit=7)
    if not key_points:
        key_points = scenario_points

    original_directive = _is_direct_buy_sell_instruction(payload.conclusion, payload.key_points)
    sanitized_conclusion = _sanitize_directive_text(payload.conclusion)
    if original_directive or not sanitized_conclusion:
        sanitized_conclusion = "조건 충족 여부에 따라 대응이 달라지는 시나리오 기반 해석이 필요합니다."
    if "조건" not in sanitized_conclusion:
        sanitized_conclusion = f"조건형 시나리오 기준 결론: {sanitized_conclusion}"

    uncertainty = str(payload.uncertainty or "").strip() or "근거 불충분"
    if "직접 매수/매도 지시는 제공하지 않습니다." not in uncertainty:
        uncertainty = f"{uncertainty} 직접 매수/매도 지시는 제공하지 않습니다."

    return (
        GraphRagAnswerPayload(
            conclusion=sanitized_conclusion,
            uncertainty=uncertainty,
            key_points=key_points,
            impact_pathways=payload.impact_pathways,
            confidence_level=payload.confidence_level,
            confidence_score=payload.confidence_score,
        ),
        True,
    )


def _format_yyyymm_label(value: Any) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if len(digits) >= 6:
        return f"{digits[:4]}-{digits[4:6]}"
    return str(value or "").strip()


def _format_signed_pct(value: Any) -> Optional[str]:
    try:
        number = float(value)
    except Exception:
        return None
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f}%"


def _extract_real_estate_trend_analysis(structured_data_context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(structured_data_context, dict):
        return None
    datasets = structured_data_context.get("datasets")
    if not isinstance(datasets, list):
        return None

    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        trend_analysis = dataset.get("trend_analysis")
        if not isinstance(trend_analysis, dict):
            continue
        months_available = int(trend_analysis.get("months_available") or 0)
        if months_available <= 0:
            continue
        return trend_analysis
    return None


def _build_real_estate_trend_point(trend_analysis: Dict[str, Any]) -> Optional[str]:
    months_available = int(trend_analysis.get("months_available") or 0)
    if months_available <= 1:
        return None

    earliest = _format_yyyymm_label(trend_analysis.get("earliest_month"))
    latest = _format_yyyymm_label(trend_analysis.get("latest_month"))
    period_label = f"{earliest}~{latest}" if earliest and latest else ""
    scope_label = str(trend_analysis.get("scope_label") or "").strip() or "전국"

    price_change = _format_signed_pct(trend_analysis.get("price_change_pct_vs_start"))
    tx_change = _format_signed_pct(trend_analysis.get("tx_change_pct_vs_start"))
    latest_tx = trend_analysis.get("latest_tx_count")

    fragments: List[str] = []
    if price_change is not None:
        fragments.append(f"가중평균 실거래가는 시작점 대비 {price_change}")
    if tx_change is not None:
        fragments.append(f"거래건수는 {tx_change}")
    if latest_tx is not None:
        fragments.append(f"최근 월 거래건수는 {latest_tx:,}건")

    if not fragments:
        return None
    prefix = f"시계열 추세({scope_label}, 최근 {months_available}개월"
    if period_label:
        prefix = f"{prefix}, {period_label}"
    prefix = f"{prefix})"
    return f"{prefix}: " + ", ".join(fragments) + "."


def _enforce_real_estate_trend_consistency(
    *,
    payload: GraphRagAnswerPayload,
    route_decision: Dict[str, Any],
    structured_data_context: Optional[Dict[str, Any]],
) -> tuple[GraphRagAnswerPayload, Dict[str, Any]]:
    selected_type = str(route_decision.get("selected_type") or "").strip()
    target_agents = route_decision.get("target_agents") if isinstance(route_decision.get("target_agents"), list) else []
    has_real_estate_agent = any(str(agent or "").strip() == "real_estate_agent" for agent in target_agents)
    if selected_type != "real_estate_detail" and not has_real_estate_agent:
        return payload, {"applied": False, "reason": "route_not_real_estate"}

    trend_analysis = _extract_real_estate_trend_analysis(structured_data_context)
    if not isinstance(trend_analysis, dict):
        return payload, {"applied": False, "reason": "trend_analysis_missing"}

    months_available = int(trend_analysis.get("months_available") or 0)
    if months_available < 6:
        return payload, {"applied": False, "reason": "trend_window_too_short", "months_available": months_available}

    trend_point = _build_real_estate_trend_point(trend_analysis)
    if not trend_point:
        return payload, {"applied": False, "reason": "trend_point_missing", "months_available": months_available}

    key_points = _dedupe_preserve_order([trend_point, *payload.key_points], limit=7)

    conclusion = str(payload.conclusion or "").strip()
    if REAL_ESTATE_TIMESERIES_LIMIT_PATTERN.search(conclusion):
        conclusion = REAL_ESTATE_TIMESERIES_LIMIT_PATTERN.sub("시계열 추세 확인이 가능합니다", conclusion).strip()
    if "시계열 추세" not in conclusion:
        conclusion = f"{conclusion} 최근 {months_available}개월 시계열 추세를 함께 반영했습니다.".strip()

    uncertainty = str(payload.uncertainty or "").strip()
    if REAL_ESTATE_TIMESERIES_LIMIT_PATTERN.search(uncertainty):
        uncertainty = REAL_ESTATE_TIMESERIES_LIMIT_PATTERN.sub("", uncertainty).strip(" .")
    if not uncertainty:
        uncertainty = "시계열 추세는 확인되지만 정책·금리 변수로 단기 변동성은 남아 있습니다."

    return (
        GraphRagAnswerPayload(
            conclusion=conclusion,
            uncertainty=uncertainty,
            key_points=key_points,
            impact_pathways=payload.impact_pathways,
            confidence_level=payload.confidence_level,
            confidence_score=payload.confidence_score,
        ),
        {
            "applied": True,
            "reason": "real_estate_trend_enforced",
            "months_available": months_available,
            "scope_label": trend_analysis.get("scope_label"),
        },
    )


def _replace_lawd_codes_with_labels(text: str) -> str:
    normalized = str(text or "")
    if not normalized:
        return normalized

    def _replace_prefixed(match: re.Match[str]) -> str:
        code = match.group(1)
        return LAWD_NAME_BY_CODE.get(code, code)

    normalized = re.sub(
        r"(?:법정동코드|법정동 코드|LAWD[_\s-]?CD|지역코드|지역 코드)\s*(\d{5})",
        _replace_prefixed,
        normalized,
        flags=re.IGNORECASE,
    )

    def _replace_standalone(match: re.Match[str]) -> str:
        code = match.group(1)
        return LAWD_NAME_BY_CODE.get(code, code)

    normalized = re.sub(r"\b(\d{5})\b", _replace_standalone, normalized)
    return normalized


def _sanitize_user_facing_text(text: Any) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""

    normalized = _replace_lawd_codes_with_labels(normalized)
    normalized = INTERNAL_REFERENCE_TOKEN_PATTERN.sub("", normalized)
    normalized = re.sub(r"\(\s*\)", "", normalized)
    normalized = re.sub(r"\[\s*\]", "", normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized).strip()
    normalized = re.sub(r"\s+([,.;:])", r"\1", normalized)
    return normalized.strip(" -")


def _sanitize_user_facing_payload(
    *,
    payload: GraphRagAnswerPayload,
) -> GraphRagAnswerPayload:
    conclusion = _sanitize_user_facing_text(payload.conclusion)
    uncertainty = _sanitize_user_facing_text(payload.uncertainty)
    key_points = _dedupe_preserve_order(
        [_sanitize_user_facing_text(point) for point in payload.key_points],
        limit=7,
    )
    cleaned_pathways: List[GraphRagPathway] = []
    for pathway in payload.impact_pathways:
        cleaned_pathways.append(
            GraphRagPathway(
                event_id=pathway.event_id,
                theme_id=pathway.theme_id,
                indicator_code=pathway.indicator_code,
                explanation=_sanitize_user_facing_text(pathway.explanation),
            )
        )

    return GraphRagAnswerPayload(
        conclusion=conclusion or payload.conclusion,
        uncertainty=uncertainty or payload.uncertainty,
        key_points=key_points,
        impact_pathways=cleaned_pathways,
        confidence_level=payload.confidence_level,
        confidence_score=payload.confidence_score,
    )


def _dedupe_friendly_points(points: List[str], limit: int = 6) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for raw_point in points or []:
        point = str(raw_point or "").strip()
        if not point:
            continue
        point = re.sub(r"^\s*[-*]\s*", "", point).strip()
        normalized = point.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(point)
        if len(deduped) >= limit:
            break
    return deduped


def _build_friendly_chat_text(payload: GraphRagAnswerPayload) -> str:
    summary = str(payload.conclusion or "").strip() or "요약할 핵심 결론을 찾지 못했어요."
    uncertainty = str(payload.uncertainty or "").strip()
    key_points = _dedupe_friendly_points(payload.key_points, limit=6)

    lines: List[str] = [
        "😊 한눈에 요약",
        summary,
    ]

    if key_points:
        lines.extend(["", "📌 핵심 포인트"])
        lines.extend([f"• {point}" for point in key_points])

    if uncertainty:
        lines.extend(["", "⚠️ 참고해요", uncertainty])

    lines.extend(
        [
            "",
            "💬 원하시면 기간(예: 최근 1주/1달)이나 비교 종목까지 같이 정리해드릴게요!",
        ]
    )
    return "\n".join(lines)


def _iter_text_chunks(text: str, chunk_size: int = 24):
    source = str(text or "")
    if not source:
        return
    step = max(int(chunk_size or 24), 1)
    for index in range(0, len(source), step):
        yield source[index : index + step]


def generate_graph_rag_answer(
    request: GraphRagAnswerRequest,
    context_response: Optional[GraphRagContextResponse] = None,
    llm=None,
    router_llm=None,
    analysis_run_writer: Optional[AnalysisRunWriter] = None,
    macro_state_generator: Optional[MacroStateGenerator] = None,
    user_id: Optional[str] = None,
    flow_run_id: Optional[str] = None,
) -> GraphRagAnswerResponse:
    model_name = resolve_graph_rag_model(request.model)
    effective_user_id = str(user_id or "").strip() or "system"
    effective_flow_run_id = str(flow_run_id or "").strip() or f"chatbot-{uuid.uuid4().hex[:24]}"
    as_of_date = request.as_of_date or date.today()
    structured_citations: List[GraphRagStructuredCitation] = []
    route_decision = _route_query_type_multi_agent(
        request,
        router_llm=router_llm,
        enable_llm_router=not (llm is not None and router_llm is None),
        user_id=effective_user_id,
        flow_run_id=effective_flow_run_id,
    )
    agent_model_policy = route_decision.get("agent_model_policy")
    if not isinstance(agent_model_policy, dict):
        agent_model_policy = _build_agent_model_policy()
    route_decision["agent_model_policy"] = agent_model_policy

    utility_llm_enabled = _is_env_flag_enabled("GRAPH_RAG_UTILITY_LLM_ENABLED", default=True)
    if llm is not None:
        allow_with_supplied_llm = _is_env_flag_enabled(
            "GRAPH_RAG_UTILITY_LLM_WHEN_SUPPLIED_SUPERVISOR_LLM",
            default=False,
        )
        if not allow_with_supplied_llm:
            utility_llm_enabled = False

    utility_execution: Dict[str, Any] = {
        "query_rewrite": {
            "enabled": False,
            "status": "skipped",
            "reason": "not_executed",
        },
        "query_normalization": {
            "enabled": False,
            "status": "skipped",
            "reason": "not_executed",
        },
        "citation_postprocess": {
            "enabled": False,
            "status": "skipped",
            "reason": "pending",
        },
    }
    web_fallback_result: Dict[str, Any] = {
        "enabled": _is_env_flag_enabled("GRAPH_RAG_WEB_FALLBACK_ENABLED", default=True),
        "status": "skipped",
        "reason": "pending",
        "applied": False,
        "added_count": 0,
        "fallback_citations": [],
    }
    effective_request = request
    rewrite_result = _invoke_query_rewrite_utility(
        request=request,
        route_decision=route_decision,
        enabled=utility_llm_enabled and _is_env_flag_enabled("GRAPH_RAG_QUERY_REWRITE_ENABLED", default=True),
        user_id=effective_user_id,
        flow_run_id=effective_flow_run_id,
    )
    utility_execution["query_rewrite"] = rewrite_result
    rewritten_question = str(rewrite_result.get("rewritten_question") or "").strip()
    if rewritten_question and rewritten_question != request.question:
        effective_request = _clone_answer_request_with_overrides(
            effective_request,
            question=rewritten_question,
        )

    normalization_result = _invoke_query_normalization_utility(
        request=effective_request,
        route_decision=route_decision,
        enabled=utility_llm_enabled and _is_env_flag_enabled("GRAPH_RAG_QUERY_NORMALIZATION_ENABLED", default=True),
        user_id=effective_user_id,
        flow_run_id=effective_flow_run_id,
    )
    utility_execution["query_normalization"] = normalization_result
    normalization_overrides: Dict[str, Any] = {}
    for field in ("country_code", "region_code", "property_type", "time_range"):
        normalized_value = normalization_result.get(field)
        if normalized_value is None:
            continue
        if str(normalized_value).strip() == "":
            continue
        if getattr(effective_request, field, None) != normalized_value:
            normalization_overrides[field] = normalized_value
    if normalization_overrides:
        effective_request = _clone_answer_request_with_overrides(
            effective_request,
            **normalization_overrides,
        )

    selected_type = str(route_decision.get("selected_type") or "").strip()
    if selected_type == GENERAL_KNOWLEDGE_ROUTE_TYPE:
        model_name = str(agent_model_policy.get("general_knowledge_agent") or DOMAIN_AGENT_MODEL)
    else:
        model_name = str(agent_model_policy.get("supervisor_agent") or SUPERVISOR_AGENT_MODEL)
    supervisor_execution = _build_supervisor_execution_trace(route_decision)
    supervisor_execution["execution_result"] = {"status": "pending"}
    agent_llm_enabled = str(os.getenv("GRAPH_RAG_AGENT_LLM_ENABLED", "1")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if llm is not None and context_response is not None:
        allow_with_supplied_llm = str(
            os.getenv("GRAPH_RAG_AGENT_LLM_WHEN_SUPPLIED_SUPERVISOR_LLM", "0")
        ).strip().lower() in {"1", "true", "yes", "on"}
        if not allow_with_supplied_llm:
            agent_llm_enabled = False

    if str(route_decision.get("selected_type") or "").strip() == GENERAL_KNOWLEDGE_ROUTE_TYPE:
        supervisor_execution["execution_result"] = _execute_supervisor_plan(
            request=effective_request,
            route_decision=route_decision,
            supervisor_execution=supervisor_execution,
            context_meta={},
            flow_type="chatbot",
            flow_run_id=effective_flow_run_id,
            user_id=effective_user_id,
            agent_llm_enabled=agent_llm_enabled,
        )

        if llm is None:
            llm = llm_gemini_flash(model=model_name, timeout=request.timeout_sec)

        direct_prompt = _build_general_knowledge_prompt(effective_request)
        started_at = time.time()
        with track_llm_call(
            model_name=model_name,
            provider="Google",
            service_name="graph_rag_answer",
            request_prompt=str(direct_prompt),
            user_id=effective_user_id,
            flow_type="chatbot",
            flow_run_id=effective_flow_run_id,
            agent_name="general_knowledge_agent",
        ) as tracker:
            llm_response = llm.invoke(direct_prompt)
            tracker.set_response(llm_response)

        raw_text = _normalize_llm_text(getattr(llm_response, "content", None)).strip()
        if not raw_text:
            raw_text = _normalize_llm_text(llm_response).strip()
        raw_json = _extract_json_block(raw_text)
        payload = _normalize_answer_payload(raw_json)

        if not raw_json:
            fallback_conclusion = raw_text or "일반 질의에 대한 답변을 생성하지 못했습니다."
            payload = GraphRagAnswerPayload(
                conclusion=fallback_conclusion,
                uncertainty="모델 내부 지식 기반 답변이며 최신성/정확성 재확인이 필요합니다.",
                key_points=[],
                impact_pathways=[],
            )

        caveat = "내부 DB/그래프를 조회하지 않은 모델 지식 기반 답변입니다."
        uncertainty = str(payload.uncertainty or "").strip()
        if caveat not in uncertainty:
            uncertainty = f"{uncertainty} {caveat}".strip() if uncertainty else caveat
        payload = GraphRagAnswerPayload(
            conclusion=payload.conclusion,
            uncertainty=uncertainty,
            key_points=payload.key_points,
            impact_pathways=[],
            confidence_level="Low",
            confidence_score=0.35,
        )

        data_freshness = {
            "status": "model_knowledge_only",
            "reason": "internal_context_skipped",
        }
        raw_output_payload = dict(raw_json or {"raw_text": raw_text})
        raw_output_payload["policy"] = "general_knowledge_direct_llm"
        raw_output_payload["query_route"] = route_decision
        raw_output_payload["supervisor_execution"] = supervisor_execution
        raw_output_payload["utility_execution"] = utility_execution
        raw_output_payload["web_fallback"] = web_fallback_result
        raw_output_payload["effective_request"] = {
            "question": effective_request.question,
            "country_code": effective_request.country_code,
            "region_code": effective_request.region_code,
            "property_type": effective_request.property_type,
            "time_range": effective_request.time_range,
        }

        return GraphRagAnswerResponse(
            question=request.question,
            model=model_name,
            as_of_date=as_of_date.isoformat(),
            answer=payload,
            citations=[],
            structured_citations=[],
            suggested_queries=[],
            context_meta={
                "policy": "general_knowledge_direct_llm",
                "query_route": route_decision,
                "supervisor_execution": supervisor_execution,
                "used_evidence_count": 0,
                "structured_citation_count": 0,
                "data_freshness": data_freshness,
                "utility_execution": utility_execution,
                "web_fallback": web_fallback_result,
                "effective_request": {
                    "question": effective_request.question,
                    "country_code": effective_request.country_code,
                    "region_code": effective_request.region_code,
                    "property_type": effective_request.property_type,
                    "time_range": effective_request.time_range,
                },
                "flow_type": "chatbot",
                "flow_run_id": effective_flow_run_id,
                "request_user_id": effective_user_id,
            },
            analysis_run_id=None,
            persistence={},
            data_freshness=data_freshness,
            collection_eta_minutes=_resolve_collection_eta_minutes(used_evidence_count=0),
            used_evidence_count=0,
            raw_model_output=raw_output_payload,
            context=None,
        )

    country_input, country_name, country_code = _resolve_country_filter(
        effective_request.country,
        effective_request.country_code,
    )
    _validate_scope_country(
        request_country=effective_request.country,
        request_country_code=effective_request.country_code,
        normalized_country_code=country_code,
    )
    country_for_metadata = country_name or country_input or country_code

    top50_scope = _evaluate_kr_top50_scope(
        question=effective_request.question,
        normalized_country_code=country_code,
    )
    if top50_scope.get("enforced") and top50_scope.get("allowed") is False:
        supervisor_execution["execution_result"] = {
            "status": "skipped",
            "reason": "kr_top50_scope_guard",
            "branch_results": [],
            "invoked_agent_count": 0,
        }
        out_of_scope_names = [
            str(item.get("corp_name") or item.get("stock_code") or "").strip()
            for item in (top50_scope.get("out_of_scope_companies") or [])
            if str(item.get("corp_name") or item.get("stock_code") or "").strip()
        ]
        names_text = ", ".join(out_of_scope_names[:5]) if out_of_scope_names else "요청 기업"
        conclusion = (
            f"{names_text}은(는) 현재 수집 범위(코스피 Top50) 밖으로 "
            "데이터를 제공하지 않습니다."
        )
        payload = GraphRagAnswerPayload(
            conclusion=conclusion,
            uncertainty="현재 KR 기업 질의는 Top50 고정 스냅샷 범위로 제한됩니다.",
            key_points=[
                KR_TOP50_SCOPE_MESSAGE,
                KR_TOP50_SCOPE_FOLLOWUP,
            ],
            impact_pathways=[],
        )
        return GraphRagAnswerResponse(
            question=request.question,
            model=model_name,
            as_of_date=as_of_date.isoformat(),
            answer=payload,
            citations=[],
            structured_citations=[],
            suggested_queries=[],
            context_meta={
                "policy": "kr_top50_scope_guard",
                "top50_scope": top50_scope,
                "query_route": route_decision,
                "supervisor_execution": supervisor_execution,
                "utility_execution": utility_execution,
                "web_fallback": web_fallback_result,
                "structured_citation_count": 0,
                "data_freshness": {
                    "status": "missing",
                    "reason": "kr_top50_scope_guard",
                },
            },
            analysis_run_id=None,
            persistence={},
            data_freshness={
                "status": "missing",
                "reason": "kr_top50_scope_guard",
            },
            collection_eta_minutes=_resolve_collection_eta_minutes(used_evidence_count=0),
            used_evidence_count=0,
            raw_model_output={
                "policy": "kr_top50_scope_guard",
                "top50_scope": top50_scope,
                "query_route": route_decision,
                "supervisor_execution": supervisor_execution,
                "utility_execution": utility_execution,
                "web_fallback": web_fallback_result,
            },
            context=None,
        )

    if llm is None and context_response is None:
        cached_response = _load_cached_answer(
            request=request,
            model_name=model_name,
            as_of_date=as_of_date,
        )
        if cached_response:
            supervisor_execution["execution_result"] = {
                "status": "skipped",
                "reason": "cached_response_hit",
                "branch_results": [],
                "invoked_agent_count": 0,
            }
            if isinstance(cached_response.context_meta, dict):
                cached_response.context_meta.setdefault("query_route", route_decision)
                cached_response.context_meta.setdefault("supervisor_execution", supervisor_execution)
                cached_response.context_meta.setdefault("utility_execution", utility_execution)
                cached_response.context_meta.setdefault("web_fallback", web_fallback_result)
                cached_response.context_meta.setdefault("utility_llm_enabled", utility_llm_enabled)
                cached_response.context_meta.setdefault(
                    "effective_request",
                    {
                        "question": effective_request.question,
                        "country_code": effective_request.country_code,
                        "region_code": effective_request.region_code,
                        "property_type": effective_request.property_type,
                        "time_range": effective_request.time_range,
                    },
                )
            if isinstance(cached_response.raw_model_output, dict):
                cached_response.raw_model_output.setdefault("query_route", route_decision)
                cached_response.raw_model_output.setdefault("supervisor_execution", supervisor_execution)
                cached_response.raw_model_output.setdefault("utility_execution", utility_execution)
                cached_response.raw_model_output.setdefault("web_fallback", web_fallback_result)
                cached_response.raw_model_output.setdefault("utility_llm_enabled", utility_llm_enabled)
            if request.persist_macro_state:
                try:
                    state_generator = macro_state_generator or MacroStateGenerator()
                    persistence = dict(cached_response.persistence)
                    persistence["macro_state"] = state_generator.generate_macro_state(
                        as_of_date=as_of_date,
                        theme_window_days=request.state_theme_window_days,
                        top_themes=request.state_top_themes,
                        top_signals=request.state_top_signals,
                    )
                    cached_response.persistence = persistence
                except Exception as error:
                    logger.warning("[GraphRAGAnswer] macro_state persistence failed: %s", error, exc_info=True)
            return cached_response

    context = context_response or build_graph_rag_context(
        effective_request.to_context_request(route=route_decision)
    )
    supervisor_execution["execution_result"] = _execute_supervisor_plan(
        request=effective_request,
        route_decision=route_decision,
        supervisor_execution=supervisor_execution,
        context_meta=context.meta if isinstance(context.meta, dict) else {},
        flow_type="chatbot",
        flow_run_id=effective_flow_run_id,
        user_id=effective_user_id,
        agent_llm_enabled=agent_llm_enabled,
    )
    structured_citations = _build_structured_citations_from_execution(
        supervisor_execution=supervisor_execution,
        as_of_date=as_of_date,
        time_range=request.time_range,
    )
    structured_data_context = _build_structured_data_context(
        supervisor_execution=supervisor_execution,
    )
    us_macro_reference = None
    if _should_attach_us_daily_macro_reference(
        request=effective_request,
        route_decision=route_decision,
        context=context,
    ):
        us_macro_reference = _load_us_daily_macro_reference(as_of_date=as_of_date)
        if isinstance(us_macro_reference, dict):
            structured_citations.append(
                _build_us_daily_macro_structured_citation(
                    us_macro_reference=us_macro_reference,
                    as_of_date=as_of_date,
                )
            )
    prompt = _make_prompt(
        request=effective_request,
        context=context,
        max_prompt_evidences=request.max_prompt_evidences,
        route=route_decision,
        us_macro_reference=us_macro_reference,
        structured_data_context=structured_data_context,
    )

    if llm is None:
        if model_name == "gemini-3-flash-preview":
            llm = llm_gemini_flash(model=model_name, timeout=request.timeout_sec)
        else:
            llm = llm_gemini_pro(model=model_name, timeout=request.timeout_sec)

    started_at = time.time()
    
    # LLM 호출 및 모니터링 (시스템 계정 사용)
    with track_llm_call(
        model_name=model_name,
        provider="Google",
        service_name="graph_rag_answer",
        request_prompt=str(prompt),
        user_id=effective_user_id,
        flow_type="chatbot",
        flow_run_id=effective_flow_run_id,
        agent_name="supervisor_agent",
    ) as tracker:
        llm_response = llm.invoke(prompt)
        # 응답 설정 (토큰 사용량 자동 추출)
        tracker.set_response(llm_response)

    duration_ms = int((time.time() - started_at) * 1000)
    raw_text = _normalize_llm_text(getattr(llm_response, "content", None)).strip()
    if not raw_text:
        raw_text = _normalize_llm_text(llm_response).strip()

    raw_json = _extract_json_block(raw_text)
    payload = _normalize_answer_payload(raw_json)

    cited_evidence_ids = raw_json.get("cited_evidence_ids")
    if not isinstance(cited_evidence_ids, list):
        cited_evidence_ids = []
    cited_evidence_ids = [str(item) for item in cited_evidence_ids if str(item)]

    cited_doc_ids = raw_json.get("cited_doc_ids")
    if not isinstance(cited_doc_ids, list):
        cited_doc_ids = []
    cited_doc_ids = [str(item) for item in cited_doc_ids if str(item)]

    citations = _build_citations(
        context=context,
        cited_evidence_ids=cited_evidence_ids,
        cited_doc_ids=cited_doc_ids,
    )
    min_citations, max_citations = _resolve_citation_bounds()
    citations_after_bounds = _enforce_citation_bounds(
        context=context,
        citations=citations,
        min_citations=min_citations,
        max_citations=max_citations,
    )
    citations_after_recent_first = _ensure_recent_citations(
        context=context,
        citations=citations_after_bounds,
        route_decision=route_decision,
        as_of_date=as_of_date,
        max_citations=max_citations,
    )
    citations_after_focus = _ensure_us_single_stock_focus_citations(
        citations=citations_after_recent_first,
        context=context,
        route_decision=route_decision,
        max_citations=max_citations,
    )
    citations = _ensure_recent_citations(
        context=context,
        citations=citations_after_focus,
        route_decision=route_decision,
        as_of_date=as_of_date,
        max_citations=max_citations,
    )
    pre_web_fallback_freshness = _assess_data_freshness(
        citations=citations,
        as_of_date=as_of_date,
    )
    web_fallback_result = _collect_web_fallback_citations(
        request=effective_request,
        route_decision=route_decision,
        citations=citations,
        min_citations=min_citations,
        data_freshness=pre_web_fallback_freshness,
    )
    fallback_citations_raw = web_fallback_result.get("fallback_citations")
    fallback_citations = (
        [item for item in fallback_citations_raw if isinstance(item, GraphRagCitation)]
        if isinstance(fallback_citations_raw, list)
        else []
    )
    if fallback_citations:
        citations = _merge_citations_with_dedupe(
            base=citations,
            extra=fallback_citations,
        )
        citations = _enforce_citation_bounds(
            context=context,
            citations=citations,
            min_citations=min_citations,
            max_citations=max_citations,
        )
    web_fallback_result["fallback_citations"] = [jsonable_encoder(item) for item in fallback_citations]
    web_fallback_result["fallback_citation_doc_ids"] = [
        str(item.doc_id or "").strip()
        for item in fallback_citations
        if str(item.doc_id or "").strip()
    ]

    citation_postprocess_result = _invoke_citation_postprocess_utility(
        request=effective_request,
        route_decision=route_decision,
        citations=citations,
        enabled=utility_llm_enabled and _is_env_flag_enabled("GRAPH_RAG_CITATION_POSTPROCESS_ENABLED", default=True),
        user_id=effective_user_id,
        flow_run_id=effective_flow_run_id,
    )
    utility_execution["citation_postprocess"] = citation_postprocess_result
    postprocess_keys = citation_postprocess_result.get("ordered_keys") if isinstance(citation_postprocess_result, dict) else []
    if isinstance(postprocess_keys, list) and postprocess_keys:
        citations = _apply_citation_postprocess_order(
            citations=citations,
            ordered_keys=postprocess_keys,
        )
        citations = _enforce_citation_bounds(
            context=context,
            citations=citations,
            min_citations=min_citations,
            max_citations=max_citations,
        )
    recent_citation_guard = _build_recent_citation_guard_debug(
        context=context,
        route_decision=route_decision,
        as_of_date=as_of_date,
        citations_before_recent=citations_after_bounds,
        citations_after_recent_first=citations_after_recent_first,
        citations_before_recent_second=citations_after_focus,
        citations_final=citations,
    )
    used_evidence_count = len(citations)
    support_evidence_count = used_evidence_count + _count_structured_support_evidences(structured_citations)
    payload = _apply_c_option_guardrail(
        payload=payload,
        used_evidence_count=support_evidence_count,
    )
    statement_stats = {
        "statement_total": 0,
        "statement_supported": 0,
        "statement_removed": 0,
    }
    if support_evidence_count > 0:
        payload, statement_stats = _filter_unsupported_statements(
            payload=payload,
            citations=citations,
            structured_citations=structured_citations,
        )
    data_freshness = _assess_data_freshness(
        citations=citations,
        as_of_date=as_of_date,
    )
    confidence = _derive_confidence(
        citations=citations,
        statement_stats=statement_stats,
        data_freshness=data_freshness,
        min_citations=min_citations,
        has_pathway=bool(payload.impact_pathways),
    )
    payload = GraphRagAnswerPayload(
        conclusion=payload.conclusion,
        uncertainty=payload.uncertainty,
        key_points=payload.key_points,
        impact_pathways=payload.impact_pathways,
        confidence_level=confidence.get("level"),
        confidence_score=confidence.get("score"),
    )
    required_question_id = str(route_decision.get("selected_question_id") or "").strip() or _infer_required_question_id(
        request.question,
        request.question_id,
    )
    payload, conditional_scenario_enforced = _enforce_conditional_scenario_output(
        payload=payload,
        route_decision=route_decision,
        required_question_id=required_question_id or None,
        context_meta=context.meta if isinstance(context.meta, dict) else None,
    )
    payload, us_single_stock_template_enforced, us_single_stock_missing_sections = _enforce_us_single_stock_template_output(
        payload=payload,
        route_decision=route_decision,
        citations=citations,
    )
    payload, us_single_stock_trend_guard = _enforce_us_single_stock_trend_consistency(
        payload=payload,
        context=context,
        route_decision=route_decision,
    )
    payload, real_estate_trend_guard = _enforce_real_estate_trend_consistency(
        payload=payload,
        route_decision=route_decision,
        structured_data_context=structured_data_context,
    )
    payload = _sanitize_user_facing_payload(payload=payload)
    collection_eta_minutes = _resolve_collection_eta_minutes(
        used_evidence_count=support_evidence_count,
    )
    required_question_schema: Optional[Dict[str, Any]] = None
    required_question_validation: Dict[str, Any] = {"enabled": False, "is_valid": True, "errors": []}
    if required_question_id:
        required_question_schema = _build_required_question_schema_payload(
            question_id=required_question_id,
            request=effective_request,
            as_of_date=as_of_date,
            payload=payload,
            citations=citations,
            confidence=confidence,
            min_citations=min_citations,
            context_meta=context.meta if isinstance(context.meta, dict) else None,
        )
        required_question_validation = _validate_required_question_schema_payload(required_question_schema)

    persistence: Dict[str, Any] = {}
    analysis_run_id: Optional[str] = None

    if request.persist_macro_state:
        try:
            state_generator = macro_state_generator or MacroStateGenerator()
            persistence["macro_state"] = state_generator.generate_macro_state(
                as_of_date=as_of_date,
                theme_window_days=request.state_theme_window_days,
                top_themes=request.state_top_themes,
                top_signals=request.state_top_signals,
            )
        except Exception as error:
            logger.warning("[GraphRAGAnswer] macro_state persistence failed: %s", error, exc_info=True)
            persistence["macro_state_error"] = str(error)

    if request.persist_analysis_run:
        try:
            run_writer = analysis_run_writer or AnalysisRunWriter()
            run_result = run_writer.persist_run(
                question=request.question,
                response_text=payload.conclusion,
                model=model_name,
                as_of_date=as_of_date,
                citations=citations,
                impact_pathways=payload.impact_pathways,
                duration_ms=duration_ms,
                run_metadata={
                    "time_range": effective_request.time_range,
                    "country": country_for_metadata,
                    "country_code": country_code,
                    "compare_mode": effective_request.compare_mode,
                    "region_code": effective_request.region_code,
                    "property_type": effective_request.property_type,
                    "uncertainty": payload.uncertainty,
                    "key_points": payload.key_points,
                    "used_evidence_count": used_evidence_count,
                    "support_evidence_count": support_evidence_count,
                    "structured_citation_count": len(structured_citations),
                    "structured_citations": _serialize_structured_citations(structured_citations),
                    "min_required_evidence_count": min_citations,
                    "max_allowed_evidence_count": max_citations,
                    "data_freshness": data_freshness,
                    "collection_eta_minutes": collection_eta_minutes,
                    "statement_filter": statement_stats,
                    "confidence": confidence,
                    "required_question_id": required_question_id,
                    "required_question_schema_validation": required_question_validation,
                    "conditional_scenario_enforced": conditional_scenario_enforced,
                    "us_single_stock_template_enforced": us_single_stock_template_enforced,
                    "us_single_stock_missing_sections": us_single_stock_missing_sections,
                    "us_single_stock_trend_guard": us_single_stock_trend_guard,
                    "real_estate_trend_guard": real_estate_trend_guard,
                    "recent_citation_guard": recent_citation_guard,
                    "query_route": route_decision,
                    "supervisor_execution": supervisor_execution,
                    "agent_llm_enabled": agent_llm_enabled,
                    "utility_llm_enabled": utility_llm_enabled,
                    "utility_execution": utility_execution,
                    "web_fallback": web_fallback_result,
                    "effective_request": {
                        "question": effective_request.question,
                        "country_code": effective_request.country_code,
                        "region_code": effective_request.region_code,
                        "property_type": effective_request.property_type,
                        "time_range": effective_request.time_range,
                    },
                    "us_macro_reference_0830": us_macro_reference,
                    "structured_data_context": structured_data_context,
                    "context_counts": context.meta.get("counts", {}),
                    "raw_model_output": raw_json,
                },
            )
            analysis_run_id = run_result.get("run_id")
            persistence["analysis_run"] = run_result
        except Exception as error:
            logger.warning("[GraphRAGAnswer] analysis_run persistence failed: %s", error, exc_info=True)
            persistence["analysis_run_error"] = str(error)

    raw_output_payload = dict(raw_json or {"raw_text": raw_text})
    raw_output_payload["required_question_id"] = required_question_id
    raw_output_payload["required_question_schema_validation"] = required_question_validation
    raw_output_payload["conditional_scenario_enforced"] = conditional_scenario_enforced
    raw_output_payload["us_single_stock_template_enforced"] = us_single_stock_template_enforced
    raw_output_payload["us_single_stock_missing_sections"] = us_single_stock_missing_sections
    raw_output_payload["us_single_stock_trend_guard"] = us_single_stock_trend_guard
    raw_output_payload["real_estate_trend_guard"] = real_estate_trend_guard
    raw_output_payload["recent_citation_guard"] = recent_citation_guard
    raw_output_payload["query_route"] = route_decision
    raw_output_payload["supervisor_execution"] = supervisor_execution
    raw_output_payload["agent_llm_enabled"] = agent_llm_enabled
    raw_output_payload["utility_llm_enabled"] = utility_llm_enabled
    raw_output_payload["utility_execution"] = utility_execution
    raw_output_payload["web_fallback"] = web_fallback_result
    raw_output_payload["effective_request"] = {
        "question": effective_request.question,
        "country_code": effective_request.country_code,
        "region_code": effective_request.region_code,
        "property_type": effective_request.property_type,
        "time_range": effective_request.time_range,
    }
    raw_output_payload["us_macro_reference_0830"] = us_macro_reference
    raw_output_payload["structured_data_context"] = structured_data_context
    raw_output_payload["structured_citations"] = _serialize_structured_citations(structured_citations)
    if required_question_schema is not None:
        raw_output_payload["required_question_schema"] = required_question_schema

    return GraphRagAnswerResponse(
        question=request.question,
        model=model_name,
        as_of_date=as_of_date.isoformat(),
        answer=payload,
        citations=citations,
        structured_citations=structured_citations,
        suggested_queries=context.suggested_queries,
        context_meta={
            **context.meta,
            "used_evidence_count": used_evidence_count,
            "support_evidence_count": support_evidence_count,
            "structured_citation_count": len(structured_citations),
            "min_required_evidence_count": min_citations,
            "max_allowed_evidence_count": max_citations,
            "data_freshness": data_freshness,
            "collection_eta_minutes": collection_eta_minutes,
            "statement_filter": statement_stats,
            "confidence": confidence,
            "required_question_id": required_question_id,
            "required_question_schema_validation": required_question_validation,
            "required_question_schema": required_question_schema,
            "conditional_scenario_enforced": conditional_scenario_enforced,
            "us_single_stock_template_enforced": us_single_stock_template_enforced,
            "us_single_stock_missing_sections": us_single_stock_missing_sections,
            "us_single_stock_trend_guard": us_single_stock_trend_guard,
            "real_estate_trend_guard": real_estate_trend_guard,
            "recent_citation_guard": recent_citation_guard,
            "query_route": route_decision,
            "supervisor_execution": supervisor_execution,
            "agent_llm_enabled": agent_llm_enabled,
            "utility_llm_enabled": utility_llm_enabled,
            "utility_execution": utility_execution,
            "web_fallback": web_fallback_result,
            "effective_request": {
                "question": effective_request.question,
                "country_code": effective_request.country_code,
                "region_code": effective_request.region_code,
                "property_type": effective_request.property_type,
                "time_range": effective_request.time_range,
            },
            "us_macro_reference_0830": us_macro_reference,
            "structured_data_context": structured_data_context,
            "flow_type": "chatbot",
            "flow_run_id": effective_flow_run_id,
            "request_user_id": effective_user_id,
        },
        analysis_run_id=analysis_run_id,
        persistence=persistence,
        data_freshness=data_freshness,
        collection_eta_minutes=collection_eta_minutes,
        used_evidence_count=used_evidence_count,
        raw_model_output=raw_output_payload,
        context=context if request.include_context else None,
    )


@router.post("/answer", response_model=GraphRagAnswerResponse)
def graph_rag_answer(request: GraphRagAnswerRequest, http_request: Request):
    started_at = time.time()
    as_of_value = request.as_of_date or date.today()
    model_name = resolve_graph_rag_model(request.model)
    request_user_id = _resolve_graph_rag_user_id(http_request)
    flow_run_id = f"chatbot-{uuid.uuid4().hex[:24]}"
    country_input, country_name, country_code = _resolve_country_filter(
        request.country,
        request.country_code,
    )
    country_for_log = country_name or country_input or country_code
    call_logger = GraphRagApiCallLogger()
    flow_context_token = set_llm_flow_context(
        flow_type="chatbot",
        flow_run_id=flow_run_id,
        user_id=request_user_id,
        metadata={
            "question": request.question[:300],
            "time_range": request.time_range,
            "country_code": country_code,
        },
    )

    try:
        response = generate_graph_rag_answer(
            request,
            user_id=request_user_id,
            flow_run_id=flow_run_id,
        )

        counts = response.context_meta.get("counts", {}) if isinstance(response.context_meta, dict) else {}
        call_logger.log_call(
            question=request.question,
            time_range=request.time_range,
            country=country_for_log,
            country_code=country_code,
            as_of_date=as_of_value,
            model=model_name,
            status="success",
            duration_ms=int((time.time() - started_at) * 1000),
            evidence_count=len(response.citations),
            node_count=int(counts.get("nodes") or 0),
            link_count=int(counts.get("links") or 0),
            response_text=response.answer.conclusion,
            analysis_run_id=response.analysis_run_id,
        )

        return response
    except ValueError as error:
        try:
            call_logger.log_call(
                question=request.question,
                time_range=request.time_range,
                country=country_for_log,
                country_code=country_code,
                as_of_date=as_of_value,
                model=model_name,
                status="error",
                duration_ms=int((time.time() - started_at) * 1000),
                error_message=str(error),
            )
        except Exception:
            logger.warning("[GraphRAGAnswer] failed to log ValueError call", exc_info=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        try:
            call_logger.log_call(
                question=request.question,
                time_range=request.time_range,
                country=country_for_log,
                country_code=country_code,
                as_of_date=as_of_value,
                model=model_name,
                status="error",
                duration_ms=int((time.time() - started_at) * 1000),
                error_message=str(error),
            )
        except Exception:
            logger.warning("[GraphRAGAnswer] failed to log exception call", exc_info=True)
        logger.error("[GraphRAGAnswer] failed: %s", error, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate GraphRAG answer") from error
    finally:
        reset_llm_flow_context(flow_context_token)


@router.post("/answer/stream")
def graph_rag_answer_stream(request: GraphRagAnswerRequest, http_request: Request):
    started_at = time.time()
    as_of_value = request.as_of_date or date.today()
    model_name = resolve_graph_rag_model(request.model)
    request_user_id = _resolve_graph_rag_user_id(http_request)
    flow_run_id = f"chatbot-{uuid.uuid4().hex[:24]}"
    country_input, country_name, country_code = _resolve_country_filter(
        request.country,
        request.country_code,
    )
    country_for_log = country_name or country_input or country_code
    call_logger = GraphRagApiCallLogger()

    def _event_line(payload: Dict[str, Any]) -> bytes:
        return (json.dumps(payload, ensure_ascii=False, default=str) + "\n").encode("utf-8")

    def _stream():
        flow_context_token = set_llm_flow_context(
            flow_type="chatbot",
            flow_run_id=flow_run_id,
            user_id=request_user_id,
            metadata={
                "question": request.question[:300],
                "time_range": request.time_range,
                "country_code": country_code,
                "stream": True,
            },
        )
        try:
            yield _event_line(
                {
                    "type": "started",
                    "flow_run_id": flow_run_id,
                    "message": "답변을 준비하고 있어요.",
                }
            )

            response = generate_graph_rag_answer(
                request,
                user_id=request_user_id,
                flow_run_id=flow_run_id,
            )
            counts = response.context_meta.get("counts", {}) if isinstance(response.context_meta, dict) else {}
            call_logger.log_call(
                question=request.question,
                time_range=request.time_range,
                country=country_for_log,
                country_code=country_code,
                as_of_date=as_of_value,
                model=model_name,
                status="success",
                duration_ms=int((time.time() - started_at) * 1000),
                evidence_count=len(response.citations),
                node_count=int(counts.get("nodes") or 0),
                link_count=int(counts.get("links") or 0),
                response_text=response.answer.conclusion,
                analysis_run_id=response.analysis_run_id,
            )

            friendly_text = _build_friendly_chat_text(response.answer)
            for chunk in _iter_text_chunks(friendly_text, chunk_size=22):
                yield _event_line({"type": "delta", "text": chunk})

            yield _event_line(
                {
                    "type": "done",
                    "flow_run_id": flow_run_id,
                    "response": jsonable_encoder(response),
                }
            )
        except ValueError as error:
            try:
                call_logger.log_call(
                    question=request.question,
                    time_range=request.time_range,
                    country=country_for_log,
                    country_code=country_code,
                    as_of_date=as_of_value,
                    model=model_name,
                    status="error",
                    duration_ms=int((time.time() - started_at) * 1000),
                    error_message=str(error),
                )
            except Exception:
                logger.warning("[GraphRAGAnswerStream] failed to log ValueError call", exc_info=True)
            yield _event_line({"type": "error", "error": str(error), "status_code": 400})
        except Exception as error:
            try:
                call_logger.log_call(
                    question=request.question,
                    time_range=request.time_range,
                    country=country_for_log,
                    country_code=country_code,
                    as_of_date=as_of_value,
                    model=model_name,
                    status="error",
                    duration_ms=int((time.time() - started_at) * 1000),
                    error_message=str(error),
                )
            except Exception:
                logger.warning("[GraphRAGAnswerStream] failed to log exception call", exc_info=True)
            logger.error("[GraphRAGAnswerStream] failed: %s", error, exc_info=True)
            yield _event_line(
                {
                    "type": "error",
                    "error": "답변 생성 중 오류가 발생했습니다.",
                    "status_code": 500,
                }
            )
        finally:
            reset_llm_flow_context(flow_context_token)

    return StreamingResponse(
        _stream(),
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
