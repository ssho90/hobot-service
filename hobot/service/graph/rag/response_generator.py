"""
Phase D-2: GraphRAG response generator.
"""

import json
import logging
import re
import time
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from service.llm_monitoring import track_llm_call

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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph/rag", tags=["graph-rag"])

ALLOWED_GRAPH_RAG_MODELS = {"gemini-3-flash-preview", "gemini-3-pro-preview"}
DEFAULT_GRAPH_RAG_MODEL = "gemini-3-pro-preview"
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


class GraphRagAnswerRequest(BaseModel):
    question: str = Field(..., min_length=3)
    time_range: str = Field(default="30d")
    country: Optional[str] = None
    country_code: Optional[str] = None
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

    def to_context_request(self) -> GraphRagContextRequest:
        return GraphRagContextRequest(
            question=self.question,
            time_range=self.time_range,
            country=self.country,
            country_code=self.country_code,
            as_of_date=self.as_of_date,
            top_k_events=self.top_k_events,
            top_k_documents=self.top_k_documents,
            top_k_stories=self.top_k_stories,
            top_k_evidences=self.top_k_evidences,
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


class GraphRagAnswerPayload(BaseModel):
    conclusion: str
    uncertainty: str
    key_points: List[str] = Field(default_factory=list)
    impact_pathways: List[GraphRagPathway] = Field(default_factory=list)
    evidence_policy: str = "Evidence-grounded only"


class GraphRagAnswerResponse(BaseModel):
    question: str
    model: str
    as_of_date: str
    answer: GraphRagAnswerPayload
    citations: List[GraphRagCitation] = Field(default_factory=list)
    suggested_queries: List[str] = Field(default_factory=list)
    context_meta: Dict[str, Any] = Field(default_factory=dict)
    analysis_run_id: Optional[str] = None
    persistence: Dict[str, Any] = Field(default_factory=dict)
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


def _resolve_country_filter(
    country: Optional[str],
    country_code: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    raw_country = (country or "").strip() or None
    raw_country_code = (country_code or "").strip().upper() or None

    normalized_code = raw_country_code or normalize_country(raw_country or "")
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

    if normalized_country_code == "KR":
        return has_keyword or has_stock_code or has_tokens
    if normalized_country_code and normalized_country_code != "KR":
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

    if not citations:
        return None

    logger.info("[GraphRAGAnswer] cache hit run_id=%s", run_id)
    return GraphRagAnswerResponse(
        question=request.question,
        model=model_name,
        as_of_date=as_of_date.isoformat(),
        answer=payload,
        citations=citations,
        suggested_queries=[],
        context_meta={
            "cache_hit": True,
            "cache_source": "AnalysisRun",
            "cached_run_id": run_id,
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


def _make_prompt(
    question: str,
    context: GraphRagContextResponse,
    max_prompt_evidences: int,
) -> str:
    event_nodes = [node for node in context.nodes if node.type == "Event"][:15]
    indicator_nodes = [node for node in context.nodes if node.type == "EconomicIndicator"][:15]
    theme_nodes = [node for node in context.nodes if node.type == "MacroTheme"][:10]
    story_nodes = [node for node in context.nodes if node.type == "Story"][:10]
    evidences = context.evidences[:max_prompt_evidences]

    compact_context = {
        "events": [
            {
                "node_id": node.id,
                "event_id": node.properties.get("event_id"),
                "summary": node.label,
                "event_time": node.properties.get("event_time"),
                "country": node.properties.get("country"),
            }
            for node in event_nodes
        ],
        "indicators": [
            {
                "node_id": node.id,
                "indicator_code": node.properties.get("indicator_code"),
                "name": node.label,
                "unit": node.properties.get("unit"),
            }
            for node in indicator_nodes
        ],
        "themes": [
            {
                "node_id": node.id,
                "theme_id": node.properties.get("theme_id"),
                "name": node.label,
            }
            for node in theme_nodes
        ],
        "stories": [
            {
                "node_id": node.id,
                "story_id": node.properties.get("story_id"),
                "title": node.label,
                "story_date": node.properties.get("story_date"),
            }
            for node in story_nodes
        ],
        "links": [
            {
                "source": link.source,
                "target": link.target,
                "type": link.type,
            }
            for link in context.links[:160]
        ],
        "evidences": [
            {
                "evidence_id": evidence.evidence_id,
                "doc_id": evidence.doc_id,
                "doc_url": evidence.doc_url,
                "doc_title": evidence.doc_title,
                "text": evidence.text,
                "support_labels": evidence.support_labels,
                "event_id": evidence.event_id,
                "claim_id": evidence.claim_id,
            }
            for evidence in evidences
        ],
    }

    return f"""
[Role]
You are a macro analysis assistant grounded strictly in provided graph context.

[Question]
{question}

[GraphContext]
{json.dumps(compact_context, ensure_ascii=False, indent=2)}

[Rules]
1. Only use facts present in GraphContext, especially evidences.
2. If evidence is weak or missing, say "근거 불충분" explicitly.
3. Explain at least one impact chain in Event -> Theme -> Indicator form when possible.
4. Every key claim must be traceable to evidence_id or doc_id in GraphContext.
5. Do not invent entities, events, indicators, dates, or numbers.
6. Output JSON only (no markdown).

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
        node_ids = []
        if evidence.event_id:
            node_ids.append(f"event:{evidence.event_id}")
        if evidence.doc_id:
            node_ids.append(f"document:{evidence.doc_id}")

        citations.append(
            GraphRagCitation(
                evidence_id=evidence.evidence_id,
                doc_id=evidence.doc_id,
                doc_url=evidence.doc_url,
                doc_title=evidence.doc_title,
                published_at=evidence.published_at,
                text=evidence.text,
                support_labels=evidence.support_labels,
                node_ids=node_ids,
            )
        )

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


def generate_graph_rag_answer(
    request: GraphRagAnswerRequest,
    context_response: Optional[GraphRagContextResponse] = None,
    llm=None,
    analysis_run_writer: Optional[AnalysisRunWriter] = None,
    macro_state_generator: Optional[MacroStateGenerator] = None,
) -> GraphRagAnswerResponse:
    model_name = resolve_graph_rag_model(request.model)
    as_of_date = request.as_of_date or date.today()
    country_input, country_name, country_code = _resolve_country_filter(
        request.country,
        request.country_code,
    )
    _validate_scope_country(
        request_country=request.country,
        request_country_code=request.country_code,
        normalized_country_code=country_code,
    )
    country_for_metadata = country_name or country_input or country_code

    top50_scope = _evaluate_kr_top50_scope(
        question=request.question,
        normalized_country_code=country_code,
    )
    if top50_scope.get("enforced") and top50_scope.get("allowed") is False:
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
            suggested_queries=[],
            context_meta={
                "policy": "kr_top50_scope_guard",
                "top50_scope": top50_scope,
            },
            analysis_run_id=None,
            persistence={},
            raw_model_output={
                "policy": "kr_top50_scope_guard",
                "top50_scope": top50_scope,
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

    context = context_response or build_graph_rag_context(request.to_context_request())
    prompt = _make_prompt(
        question=request.question,
        context=context,
        max_prompt_evidences=request.max_prompt_evidences,
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
        user_id="system"
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
                    "time_range": request.time_range,
                    "country": country_for_metadata,
                    "country_code": country_code,
                    "uncertainty": payload.uncertainty,
                    "key_points": payload.key_points,
                    "context_counts": context.meta.get("counts", {}),
                    "raw_model_output": raw_json,
                },
            )
            analysis_run_id = run_result.get("run_id")
            persistence["analysis_run"] = run_result
        except Exception as error:
            logger.warning("[GraphRAGAnswer] analysis_run persistence failed: %s", error, exc_info=True)
            persistence["analysis_run_error"] = str(error)

    return GraphRagAnswerResponse(
        question=request.question,
        model=model_name,
        as_of_date=as_of_date.isoformat(),
        answer=payload,
        citations=citations,
        suggested_queries=context.suggested_queries,
        context_meta=context.meta,
        analysis_run_id=analysis_run_id,
        persistence=persistence,
        raw_model_output=raw_json or {"raw_text": raw_text},
        context=context if request.include_context else None,
    )


@router.post("/answer", response_model=GraphRagAnswerResponse)
def graph_rag_answer(request: GraphRagAnswerRequest):
    started_at = time.time()
    as_of_value = request.as_of_date or date.today()
    model_name = resolve_graph_rag_model(request.model)
    country_input, country_name, country_code = _resolve_country_filter(
        request.country,
        request.country_code,
    )
    country_for_log = country_name or country_input or country_code
    call_logger = GraphRagApiCallLogger()

    try:
        response = generate_graph_rag_answer(request)

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
