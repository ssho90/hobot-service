"""
Phase 5 golden-set regression helpers for GraphRAG answers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

FAILURE_SCHEMA_MISMATCH = "schema_mismatch"
FAILURE_CITATION_MISSING = "citation_missing"
FAILURE_FRESHNESS_STALE = "freshness_stale"
FAILURE_SCOPE_VIOLATION = "scope_violation"
FAILURE_GUARDRAIL_VIOLATION = "guardrail_violation"
FAILURE_ROUTING_MISMATCH = "routing_mismatch"
FAILURE_EVALUATOR_ERROR = "evaluator_error"
GOLDEN_SET_DEFAULT_PATH = Path(__file__).resolve().parent / "golden_sets" / "phase5_q1_q6_v1.json"


@dataclass
class GoldenQuestionCase:
    case_id: str
    question_id: str
    question: str
    expected_country_codes: List[str] = field(default_factory=list)
    expected_target_agents: List[str] = field(default_factory=list)
    min_citations: int = 3
    required_keys: List[str] = field(default_factory=list)
    disallowed_phrases: List[str] = field(default_factory=list)
    max_data_age_hours: Optional[float] = None
    expected_tool_mode: Optional[str] = None


def _normalize_string_list(values: Optional[Sequence[Any]]) -> List[str]:
    normalized: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_tool_mode(value: Any) -> Optional[str]:
    normalized = str(value or "").strip().lower()
    if normalized in {"single", "parallel"}:
        return normalized
    return None


def _get_nested_value(payload: Dict[str, Any], dotted_key: str) -> Any:
    current: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current.get(part)
    return current


def load_golden_question_cases(path: str | Path) -> List[GoldenQuestionCase]:
    file_path = Path(path)
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Golden set file must be a JSON list.")

    cases: List[GoldenQuestionCase] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("case_id") or "").strip()
        question_id = str(row.get("question_id") or "").strip()
        question = str(row.get("question") or "").strip()
        if not case_id or not question_id or not question:
            continue
        cases.append(
            GoldenQuestionCase(
                case_id=case_id,
                question_id=question_id,
                question=question,
                expected_country_codes=[code.upper() for code in _normalize_string_list(row.get("expected_country_codes"))],
                expected_target_agents=_normalize_string_list(row.get("expected_target_agents")),
                min_citations=max(int(row.get("min_citations") or 0), 0),
                required_keys=_normalize_string_list(row.get("required_keys")),
                disallowed_phrases=_normalize_string_list(row.get("disallowed_phrases")),
                max_data_age_hours=(
                    float(row["max_data_age_hours"])
                    if row.get("max_data_age_hours") is not None
                    else None
                ),
                expected_tool_mode=_normalize_tool_mode(row.get("expected_tool_mode")),
            )
        )
    return cases


def _extract_country_codes(response: Dict[str, Any]) -> List[str]:
    context_meta = response.get("context_meta")
    if isinstance(context_meta, dict):
        codes = context_meta.get("resolved_country_codes")
        if isinstance(codes, list):
            return [str(code or "").strip().upper() for code in codes if str(code or "").strip()]

    context = response.get("context")
    if isinstance(context, dict):
        meta = context.get("meta")
        if isinstance(meta, dict):
            codes = meta.get("resolved_country_codes")
            if isinstance(codes, list):
                return [str(code or "").strip().upper() for code in codes if str(code or "").strip()]
    return []


def _flatten_text_for_guardrail(response: Dict[str, Any]) -> str:
    chunks: List[str] = []
    answer = response.get("answer")
    if isinstance(answer, dict):
        for key in ("conclusion", "uncertainty"):
            value = answer.get(key)
            if isinstance(value, str):
                chunks.append(value)
        key_points = answer.get("key_points")
        if isinstance(key_points, list):
            for item in key_points:
                if isinstance(item, str):
                    chunks.append(item)
    for key in ("conclusion", "uncertainty"):
        value = response.get(key)
        if isinstance(value, str):
            chunks.append(value)
    return " ".join(chunks).lower()


def _extract_query_route(response: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Any] = []
    context_meta = response.get("context_meta")
    if isinstance(context_meta, dict):
        candidates.append(context_meta.get("query_route"))
    candidates.append(response.get("query_route"))
    raw_output = response.get("raw_model_output")
    if isinstance(raw_output, dict):
        candidates.append(raw_output.get("query_route"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return {}


def _extract_target_agents(query_route: Dict[str, Any]) -> List[str]:
    raw_agents = query_route.get("target_agents")
    if not isinstance(raw_agents, list):
        return []
    return _normalize_string_list(raw_agents)


def _extract_tool_mode(query_route: Dict[str, Any]) -> Optional[str]:
    return _normalize_tool_mode(query_route.get("tool_mode"))


def _extract_structured_citation_count(response: Dict[str, Any]) -> int:
    structured_citations = response.get("structured_citations")
    if isinstance(structured_citations, list):
        return len(structured_citations)

    context_meta = response.get("context_meta")
    if isinstance(context_meta, dict):
        count_value = context_meta.get("structured_citation_count")
        try:
            return max(int(count_value), 0)
        except (TypeError, ValueError):
            pass

    raw_output = response.get("raw_model_output")
    if isinstance(raw_output, dict):
        structured_citations = raw_output.get("structured_citations")
        if isinstance(structured_citations, list):
            return len(structured_citations)
    return 0


def _build_regression_observability(case_results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    tool_mode_counts: Dict[str, int] = {}
    target_agent_counts: Dict[str, int] = {}
    freshness_status_counts: Dict[str, int] = {}
    structured_citation_total = 0
    structured_citation_max = 0
    structured_citation_cases = 0

    for item in case_results:
        tool_mode = str(item.get("tool_mode") or "unknown").strip().lower() or "unknown"
        tool_mode_counts[tool_mode] = tool_mode_counts.get(tool_mode, 0) + 1

        target_agents = item.get("target_agents")
        if isinstance(target_agents, list):
            for agent_name in target_agents:
                normalized = str(agent_name or "").strip()
                if not normalized:
                    continue
                target_agent_counts[normalized] = target_agent_counts.get(normalized, 0) + 1

        freshness_status = str(item.get("freshness_status") or "unknown").strip().lower() or "unknown"
        freshness_status_counts[freshness_status] = freshness_status_counts.get(freshness_status, 0) + 1

        try:
            structured_count = max(int(item.get("structured_citation_count") or 0), 0)
        except (TypeError, ValueError):
            structured_count = 0
        structured_citation_total += structured_count
        structured_citation_max = max(structured_citation_max, structured_count)
        if structured_count > 0:
            structured_citation_cases += 1

    total_cases = len(case_results)
    structured_citation_avg = round(structured_citation_total / total_cases, 3) if total_cases else 0.0
    return {
        "tool_mode_counts": dict(sorted(tool_mode_counts.items())),
        "target_agent_counts": dict(sorted(target_agent_counts.items())),
        "freshness_status_counts": dict(sorted(freshness_status_counts.items())),
        "structured_citation_stats": {
            "total_count": structured_citation_total,
            "average_count": structured_citation_avg,
            "max_count": structured_citation_max,
            "cases_with_structured_citations": structured_citation_cases,
        },
    }


def evaluate_golden_case_response(
    case: GoldenQuestionCase,
    response: Dict[str, Any],
) -> Dict[str, Any]:
    failures: List[Dict[str, str]] = []
    context_meta = response.get("context_meta")
    recent_guard: Dict[str, Any] = {}
    if isinstance(context_meta, dict):
        guard_payload = context_meta.get("recent_citation_guard")
        if isinstance(guard_payload, dict):
            recent_guard = guard_payload

    data_freshness = response.get("data_freshness")
    freshness_status = ""
    freshness_age_hours: Optional[float] = None
    latest_evidence_published_at: Optional[str] = None
    if isinstance(data_freshness, dict):
        freshness_status = str(data_freshness.get("status") or "").strip().lower()
        raw_age_hours = data_freshness.get("age_hours")
        if raw_age_hours is not None:
            try:
                freshness_age_hours = float(raw_age_hours)
            except (TypeError, ValueError):
                freshness_age_hours = None
        latest_value = data_freshness.get("latest_evidence_published_at")
        if latest_value is not None:
            latest_evidence_published_at = str(latest_value)

    query_route = _extract_query_route(response)
    tool_mode = _extract_tool_mode(query_route)
    target_agents = _extract_target_agents(query_route)
    structured_citation_count = _extract_structured_citation_count(response)

    for required_key in case.required_keys:
        if _get_nested_value(response, required_key) is None:
            failures.append(
                {
                    "category": FAILURE_SCHEMA_MISMATCH,
                    "message": f"required_key_missing:{required_key}",
                }
            )

    citations = response.get("citations")
    citation_count = len(citations) if isinstance(citations, list) else 0
    if citation_count < case.min_citations:
        failures.append(
            {
                "category": FAILURE_CITATION_MISSING,
                "message": f"min_citations_not_met:{citation_count}<{case.min_citations}",
            }
        )

    if case.max_data_age_hours is not None:
        if freshness_status in {"stale", "missing"}:
            failures.append(
                {
                    "category": FAILURE_FRESHNESS_STALE,
                    "message": f"freshness_status:{freshness_status}",
                }
            )
        elif freshness_age_hours is not None and freshness_age_hours > float(case.max_data_age_hours):
            failures.append(
                {
                    "category": FAILURE_FRESHNESS_STALE,
                    "message": f"data_age_exceeded:{freshness_age_hours}>{case.max_data_age_hours}",
                }
            )

    expected_codes = {code.upper() for code in case.expected_country_codes}
    if expected_codes:
        actual_codes = set(_extract_country_codes(response))
        if not expected_codes.issubset(actual_codes):
            failures.append(
                {
                    "category": FAILURE_SCOPE_VIOLATION,
                    "message": f"country_scope_mismatch:expected={sorted(expected_codes)} actual={sorted(actual_codes)}",
                }
            )

    if case.disallowed_phrases:
        text_blob = _flatten_text_for_guardrail(response)
        for phrase in case.disallowed_phrases:
            lowered = phrase.lower()
            if lowered and lowered in text_blob:
                failures.append(
                    {
                        "category": FAILURE_GUARDRAIL_VIOLATION,
                        "message": f"disallowed_phrase_detected:{phrase}",
                    }
                )
                break

    if case.expected_tool_mode:
        if tool_mode != case.expected_tool_mode:
            failures.append(
                {
                    "category": FAILURE_ROUTING_MISMATCH,
                    "message": f"expected_tool_mode:{case.expected_tool_mode} actual:{tool_mode or 'unknown'}",
                }
            )

    expected_target_agents = _normalize_string_list(case.expected_target_agents)
    missing_target_agents: List[str] = []
    if expected_target_agents:
        actual_target_set = {str(agent).strip() for agent in target_agents if str(agent).strip()}
        missing_target_agents = [
            expected_agent
            for expected_agent in expected_target_agents
            if expected_agent not in actual_target_set
        ]
        if missing_target_agents:
            failures.append(
                {
                    "category": FAILURE_ROUTING_MISMATCH,
                    "message": (
                        "expected_target_agents_missing:"
                        f"{','.join(missing_target_agents)} actual:{','.join(sorted(actual_target_set))}"
                    ),
                }
            )

    return {
        "case_id": case.case_id,
        "question_id": case.question_id,
        "passed": len(failures) == 0,
        "citation_count": citation_count,
        "structured_citation_count": structured_citation_count,
        "tool_mode": tool_mode,
        "expected_tool_mode": case.expected_tool_mode,
        "target_agents": target_agents,
        "expected_target_agents": expected_target_agents,
        "missing_target_agents": missing_target_agents,
        "freshness_status": freshness_status or None,
        "freshness_age_hours": freshness_age_hours,
        "latest_evidence_published_at": latest_evidence_published_at,
        "recent_guard_enabled": recent_guard.get("enabled"),
        "recent_guard_target_count": recent_guard.get("target_count"),
        "recent_guard_max_age_hours": recent_guard.get("max_age_hours"),
        "recent_guard_require_focus_match": recent_guard.get("require_focus_match"),
        "recent_guard_candidate_recent_evidence_count": recent_guard.get("candidate_recent_evidence_count"),
        "recent_guard_selected_recent_citation_count": recent_guard.get("selected_recent_citation_count"),
        "recent_guard_added_recent_citation_count": recent_guard.get("added_recent_citation_count"),
        "recent_guard_target_satisfied": recent_guard.get("target_satisfied"),
        "failures": failures,
    }


def run_phase5_golden_set_regression(
    *,
    cases: Iterable[GoldenQuestionCase],
    evaluator: Callable[[GoldenQuestionCase], Dict[str, Any]],
) -> Dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    case_results: List[Dict[str, Any]] = []
    failure_counts: Dict[str, int] = {}

    for case in cases:
        try:
            response = evaluator(case)
            if not isinstance(response, dict):
                raise ValueError("evaluator must return dict response")
            result = evaluate_golden_case_response(case, response)
        except Exception as exc:  # pragma: no cover - error path coverage from tests
            result = {
                "case_id": case.case_id,
                "question_id": case.question_id,
                "passed": False,
                "citation_count": 0,
                "failures": [
                    {
                        "category": FAILURE_EVALUATOR_ERROR,
                        "message": str(exc),
                    }
                ],
            }

        for failure in result.get("failures") or []:
            category = str(failure.get("category") or "").strip()
            if category:
                failure_counts[category] = failure_counts.get(category, 0) + 1

        case_results.append(result)

    total_cases = len(case_results)
    passed_cases = sum(1 for item in case_results if item.get("passed"))
    failed_cases = total_cases - passed_cases
    observability = _build_regression_observability(case_results)

    return {
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "pass_rate_pct": round((passed_cases / total_cases) * 100.0, 2) if total_cases else 0.0,
        "failure_counts": dict(sorted(failure_counts.items())),
        "tool_mode_counts": observability.get("tool_mode_counts", {}),
        "target_agent_counts": observability.get("target_agent_counts", {}),
        "freshness_status_counts": observability.get("freshness_status_counts", {}),
        "structured_citation_stats": observability.get("structured_citation_stats", {}),
        "case_results": case_results,
    }


def run_phase5_golden_set_regression_from_file(
    *,
    golden_set_path: str | Path,
    evaluator: Callable[[GoldenQuestionCase], Dict[str, Any]],
) -> Dict[str, Any]:
    cases = load_golden_question_cases(golden_set_path)
    return run_phase5_golden_set_regression(cases=cases, evaluator=evaluator)


__all__ = [
    "GOLDEN_SET_DEFAULT_PATH",
    "FAILURE_CITATION_MISSING",
    "FAILURE_EVALUATOR_ERROR",
    "FAILURE_FRESHNESS_STALE",
    "FAILURE_GUARDRAIL_VIOLATION",
    "FAILURE_ROUTING_MISMATCH",
    "FAILURE_SCHEMA_MISMATCH",
    "FAILURE_SCOPE_VIOLATION",
    "GoldenQuestionCase",
    "evaluate_golden_case_response",
    "load_golden_question_cases",
    "run_phase5_golden_set_regression",
    "run_phase5_golden_set_regression_from_file",
]
