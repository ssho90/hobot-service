"""Kakao OpenBuilder skill adapter for GraphRAG chatbot."""

from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from service.graph.rag.response_generator import (
    GraphRagAnswerRequest,
    generate_graph_rag_answer,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kakao/skill", tags=["kakao-skill"])

_TIME_RANGE_PATTERN = re.compile(r"^\d+[dmy]$", re.IGNORECASE)
_INTERNAL_REF_PATTERN = re.compile(r"\b(?:EVT|EV|EVID|CLM)_[A-Za-z0-9]+\b")
_TEST_UTTERANCE_PLACEHOLDERS = {
    "발화 내용",
    "발화내용",
    "utterance",
}


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


def _build_kakao_use_callback_response() -> Dict[str, Any]:
    return {
        "version": "2.0",
        "useCallback": True,
    }


def _extract_utterance(payload: Dict[str, Any]) -> str:
    user_request = payload.get("userRequest") if isinstance(payload.get("userRequest"), dict) else {}
    action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    detail_params = action.get("detailParams") if isinstance(action.get("detailParams"), dict) else {}

    utterance = str(user_request.get("utterance") or "").strip()
    param_utterance = str(params.get("question") or params.get("utterance") or "").strip()
    if not param_utterance:
        detail_question = detail_params.get("question") if isinstance(detail_params.get("question"), dict) else {}
        detail_utterance = detail_params.get("utterance") if isinstance(detail_params.get("utterance"), dict) else {}
        param_utterance = str(
            detail_question.get("value") or detail_utterance.get("value") or ""
        ).strip()

    if param_utterance and (not utterance or utterance.lower() in _TEST_UTTERANCE_PLACEHOLDERS):
        return param_utterance
    if utterance:
        return utterance
    return param_utterance


def _extract_callback_url(payload: Dict[str, Any]) -> Optional[str]:
    user_request = payload.get("userRequest") if isinstance(payload.get("userRequest"), dict) else {}
    callback_url = str(user_request.get("callbackUrl") or "").strip()
    if callback_url.startswith("http://") or callback_url.startswith("https://"):
        return callback_url
    return None


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


def _is_callback_required() -> bool:
    raw_value = str(os.getenv("KAKAO_SKILL_REQUIRE_CALLBACK", "1") or "").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _post_kakao_callback_response(
    *,
    callback_url: str,
    payload: Dict[str, Any],
) -> None:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
    }
    response = requests.post(
        callback_url,
        headers=headers,
        json=payload,
        timeout=10,
    )
    response.raise_for_status()


def _run_kakao_callback_flow(
    *,
    request_payload: Dict[str, Any],
    request_user_id: str,
    flow_run_id: str,
    callback_url: str,
) -> None:
    try:
        answer_request = GraphRagAnswerRequest(**request_payload)
        answer_response = generate_graph_rag_answer(
            answer_request,
            user_id=request_user_id,
            flow_run_id=flow_run_id,
        )
        response_payload = _build_kakao_simple_text_response(_build_kakao_answer_text(answer_response))
    except Exception as error:
        logger.error("[KakaoSkill] callback flow failed: %s", error, exc_info=True)
        response_payload = _build_kakao_simple_text_response(
            "답변 생성 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요."
        )

    try:
        _post_kakao_callback_response(
            callback_url=callback_url,
            payload=response_payload,
        )
    except Exception as error:
        logger.error("[KakaoSkill] callback delivery failed: %s", error, exc_info=True)


@router.post("/chatbot")
async def kakao_skill_chatbot(
    http_request: Request,
    background_tasks: BackgroundTasks,
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

    callback_url = _extract_callback_url(payload)
    if callback_url:
        logger.info("[KakaoSkill] useCallback enabled: user_id=%s flow_run_id=%s", request_user_id, flow_run_id)
        background_tasks.add_task(
            _run_kakao_callback_flow,
            request_payload=request_payload,
            request_user_id=request_user_id,
            flow_run_id=flow_run_id,
            callback_url=callback_url,
        )
        return _build_kakao_use_callback_response()
    if _is_callback_required():
        return _build_kakao_simple_text_response(
            "카카오 스킬 5초 제한으로 즉시 분석 응답이 어렵습니다. "
            "OpenBuilder에서 Callback 응답을 활성화한 뒤 다시 시도해 주세요."
        )

    try:
        answer_request = GraphRagAnswerRequest(**request_payload)
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
