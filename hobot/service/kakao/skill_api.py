"""Kakao OpenBuilder skill adapter for GraphRAG chatbot."""

from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from service.graph.rag.response_generator import (
    GraphRagAnswerRequest,
    generate_graph_rag_answer,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kakao/skill", tags=["kakao-skill"])

_TIME_RANGE_PATTERN = re.compile(r"^\d+[dmy]$", re.IGNORECASE)
_INTERNAL_REF_PATTERN = re.compile(r"\b(?:EVT|EV|EVID|CLM)_[A-Za-z0-9]+\b")


def _build_kakao_simple_text_response(text: str) -> Dict[str, Any]:
    normalized = str(text or "").strip()
    if not normalized:
        normalized = "응답을 생성하지 못했습니다. 다시 시도해 주세요."
    # Kakao simpleText 길이 안전 제한
    if len(normalized) > 950:
        normalized = f"{normalized[:949].rstrip()}…"
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": normalized,
                    }
                }
            ]
        },
    }


def _extract_utterance(payload: Dict[str, Any]) -> str:
    user_request = payload.get("userRequest") if isinstance(payload.get("userRequest"), dict) else {}
    utterance = str(user_request.get("utterance") or "").strip()
    if utterance:
        return utterance

    action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    fallback = str(params.get("question") or params.get("utterance") or "").strip()
    return fallback


def _extract_user_id(payload: Dict[str, Any]) -> str:
    user_request = payload.get("userRequest") if isinstance(payload.get("userRequest"), dict) else {}
    user = user_request.get("user") if isinstance(user_request.get("user"), dict) else {}
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        return "anonymous"
    return f"kakao:{user_id}"


def _extract_action_option(payload: Dict[str, Any], key: str) -> Optional[str]:
    action = payload.get("action") if isinstance(payload.get("action"), dict) else {}

    client_extra = action.get("clientExtra") if isinstance(action.get("clientExtra"), dict) else {}
    value = str(client_extra.get(key) or "").strip()
    if value:
        return value

    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    value = str(params.get(key) or "").strip()
    if value:
        return value

    detail_params = action.get("detailParams") if isinstance(action.get("detailParams"), dict) else {}
    detail = detail_params.get(key) if isinstance(detail_params.get(key), dict) else {}
    value = str(detail.get("value") or "").strip()
    if value:
        return value
    return None


def _sanitize_text_for_kakao(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    text = _INTERNAL_REF_PATTERN.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _build_kakao_answer_text(answer_response) -> str:
    answer = answer_response.answer
    lines = []

    conclusion = _sanitize_text_for_kakao(answer.conclusion)
    if conclusion:
        lines.append(f"😊 {conclusion}")

    key_points = []
    for item in answer.key_points or []:
        text = _sanitize_text_for_kakao(item)
        if text:
            key_points.append(text)
        if len(key_points) >= 4:
            break

    if key_points:
        lines.append("")
        lines.append("📌 핵심 포인트")
        for point in key_points:
            lines.append(f"• {point}")

    uncertainty = _sanitize_text_for_kakao(answer.uncertainty or "")
    if uncertainty:
        lines.append("")
        lines.append(f"⚠️ 참고: {uncertainty}")

    citation_titles = []
    seen = set()
    for citation in answer_response.citations or []:
        title = str(citation.doc_title or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        citation_titles.append(title)
        if len(citation_titles) >= 3:
            break

    if citation_titles:
        lines.append("")
        lines.append(f"🔎 근거: {', '.join(citation_titles)}")

    if not lines:
        lines = ["응답을 생성하지 못했습니다. 다시 시도해 주세요."]

    return "\n".join(lines).strip()


def _validate_webhook_secret(
    *,
    x_webhook_secret: Optional[str],
) -> None:
    expected_secret = str(os.getenv("KAKAO_SKILL_WEBHOOK_SECRET") or "").strip()
    if not expected_secret:
        return

    provided_secret = str(x_webhook_secret or "").strip()
    if provided_secret == expected_secret:
        return

    raise HTTPException(status_code=403, detail="Invalid webhook secret")


@router.post("/chatbot")
async def kakao_skill_chatbot(
    http_request: Request,
    x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
):
    _validate_webhook_secret(x_webhook_secret=x_webhook_secret)

    try:
        payload = await http_request.json()
        if not isinstance(payload, dict):
            return _build_kakao_simple_text_response("요청 형식이 올바르지 않습니다.")
    except Exception:
        return _build_kakao_simple_text_response("요청 본문을 읽을 수 없습니다.")

    utterance = _extract_utterance(payload)
    if len(utterance) < 2:
        return _build_kakao_simple_text_response("질문을 이해하지 못했어요. 다시 입력해 주세요.")

    request_user_id = _extract_user_id(payload)
    flow_run_id = f"kakao-{uuid.uuid4().hex[:24]}"

    country_code = _extract_action_option(payload, "country_code")
    region_code = _extract_action_option(payload, "region_code")
    property_type = _extract_action_option(payload, "property_type")
    time_range = _extract_action_option(payload, "time_range")
    if time_range and not _TIME_RANGE_PATTERN.fullmatch(time_range):
        time_range = None

    model_name = str(os.getenv("KAKAO_SKILL_GRAPH_RAG_MODEL") or "").strip() or None

    request_payload: Dict[str, Any] = {
        "question": utterance,
        "country_code": country_code,
        "region_code": region_code,
        "property_type": property_type,
        "time_range": time_range or "30d",
        "include_context": False,
    }
    if model_name:
        request_payload["model"] = model_name

    answer_request = GraphRagAnswerRequest(**request_payload)

    try:
        answer_response = generate_graph_rag_answer(
            answer_request,
            user_id=request_user_id,
            flow_run_id=flow_run_id,
        )
    except Exception as error:
        logger.error("[KakaoSkill] chatbot adapter failed: %s", error, exc_info=True)
        return _build_kakao_simple_text_response(
            "답변 생성 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요."
        )

    text = _build_kakao_answer_text(answer_response)
    return _build_kakao_simple_text_response(text)
