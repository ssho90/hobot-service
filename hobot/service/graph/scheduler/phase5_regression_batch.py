"""
Phase 5 골든셋 회귀 배치 실행기.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

from ..monitoring.phase5_regression import (
    GOLDEN_SET_DEFAULT_PATH,
    GoldenQuestionCase,
    load_golden_question_cases,
    run_phase5_golden_set_regression,
)
from ..rag.response_generator import GraphRagAnswerRequest, generate_graph_rag_answer


@dataclass
class Phase5RegressionRequestConfig:
    model: str = "gemini-3-flash-preview"
    time_range: str = "30d"
    as_of_date: Optional[date] = None
    timeout_sec: int = 90
    max_prompt_evidences: int = 12
    include_context: bool = False
    reuse_cached_run: bool = False
    persist_macro_state: bool = False
    persist_analysis_run: bool = False
    top_k_events: int = 25
    top_k_documents: int = 40
    top_k_stories: int = 20
    top_k_evidences: int = 40


def _resolve_case_country_code(expected_country_codes: Sequence[str]) -> Optional[str]:
    normalized = {str(code or "").strip().upper() for code in expected_country_codes if str(code or "").strip()}
    if not normalized:
        return None
    if {"US", "KR"}.issubset(normalized):
        return "US-KR"
    if "US" in normalized:
        return "US"
    if "KR" in normalized:
        return "KR"
    return None


def _response_to_dict(response: Any) -> Dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        dumped = response.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(response, "dict"):
        dumped = response.dict()
        if isinstance(dumped, dict):
            return dumped
    raise ValueError("GraphRAG response must be serializable as dict")


def _build_request(
    *,
    case: GoldenQuestionCase,
    config: Phase5RegressionRequestConfig,
) -> GraphRagAnswerRequest:
    return GraphRagAnswerRequest(
        question=case.question,
        question_id=case.question_id,
        time_range=config.time_range,
        country_code=_resolve_case_country_code(case.expected_country_codes),
        as_of_date=config.as_of_date,
        model=config.model,
        timeout_sec=max(int(config.timeout_sec), 10),
        max_prompt_evidences=max(int(config.max_prompt_evidences), 3),
        include_context=bool(config.include_context),
        reuse_cached_run=bool(config.reuse_cached_run),
        persist_macro_state=bool(config.persist_macro_state),
        persist_analysis_run=bool(config.persist_analysis_run),
        top_k_events=max(int(config.top_k_events), 5),
        top_k_documents=max(int(config.top_k_documents), 5),
        top_k_stories=max(int(config.top_k_stories), 5),
        top_k_evidences=max(int(config.top_k_evidences), 5),
    )


def run_phase5_golden_regression_jobs(
    *,
    golden_set_path: str | Path = GOLDEN_SET_DEFAULT_PATH,
    case_ids: Optional[Iterable[str]] = None,
    request_config: Optional[Phase5RegressionRequestConfig] = None,
) -> Dict[str, Any]:
    config = request_config or Phase5RegressionRequestConfig()
    all_cases = load_golden_question_cases(golden_set_path)
    case_filter = {
        str(case_id or "").strip()
        for case_id in (case_ids or [])
        if str(case_id or "").strip()
    }
    selected_cases = [case for case in all_cases if not case_filter or case.case_id in case_filter]
    if case_filter and not selected_cases:
        raise ValueError("No golden regression cases matched the requested case_ids.")

    def evaluator(case: GoldenQuestionCase) -> Dict[str, Any]:
        request = _build_request(case=case, config=config)
        response = generate_graph_rag_answer(request)
        return _response_to_dict(response)

    report = run_phase5_golden_set_regression(
        cases=selected_cases,
        evaluator=evaluator,
    )
    report["golden_set_path"] = str(Path(golden_set_path))
    report["total_loaded_cases"] = len(all_cases)
    report["selected_case_ids"] = [case.case_id for case in selected_cases]
    report["request_config"] = {
        "model": config.model,
        "time_range": config.time_range,
        "as_of_date": config.as_of_date.isoformat() if isinstance(config.as_of_date, date) else None,
        "timeout_sec": int(config.timeout_sec),
        "max_prompt_evidences": int(config.max_prompt_evidences),
        "include_context": bool(config.include_context),
        "reuse_cached_run": bool(config.reuse_cached_run),
        "persist_macro_state": bool(config.persist_macro_state),
        "persist_analysis_run": bool(config.persist_analysis_run),
        "top_k_events": int(config.top_k_events),
        "top_k_documents": int(config.top_k_documents),
        "top_k_stories": int(config.top_k_stories),
        "top_k_evidences": int(config.top_k_evidences),
    }
    return report


__all__ = [
    "Phase5RegressionRequestConfig",
    "run_phase5_golden_regression_jobs",
]
