"""Ontology agent live executor."""

import hashlib
from typing import Any, Dict

from .live_executor import execute_live_tool
from .tool_probe import detect_companion_branch
from ..templates.cypher_schema_prompt import (
    PROMPT_VERSION,
    build_ontology_cypher_prompt_contract,
    validate_cypher_direction,
)


def run_ontology_agent_stub(
    *,
    branch: str,
    request: Any,
    route_decision: Dict[str, Any],
    context_meta: Dict[str, Any],
) -> Dict[str, Any]:
    selected_type = str(route_decision.get("selected_type") or "")
    prompt_contract = build_ontology_cypher_prompt_contract(
        question=str(getattr(request, "question", "") or ""),
    )
    schema_string = str(prompt_contract.get("schema_string") or "")
    few_shots = prompt_contract.get("few_shots")
    few_shot_count = len(few_shots) if isinstance(few_shots, list) else 0
    tool_probe = execute_live_tool(
        agent_name="ontology_master_agent",
        branch=branch,
        request=request,
        route_decision=route_decision,
        context_meta=context_meta,
    )
    if branch == "graph":
        query_text = str(tool_probe.get("query") or "")
        direction_validation = validate_cypher_direction(query_text)
        tool_probe = {
            **tool_probe,
            "schema_prompt_version": PROMPT_VERSION,
            "cypher_direction_validation": direction_validation,
        }
    companion_branch = detect_companion_branch(branch, tool_probe)
    return {
        "agent": "ontology_master_agent",
        "branch": branch,
        "status": "executed" if str(tool_probe.get("status") or "") == "ok" else "degraded",
        "selected_type": selected_type,
        "primary_store": "neo4j",
        "tool_probe": tool_probe,
        "cypher_prompt_contract": {
            "prompt_version": str(prompt_contract.get("prompt_version") or PROMPT_VERSION),
            "schema_line_count": len([line for line in schema_string.splitlines() if line.strip()]),
            "few_shot_count": few_shot_count,
            "schema_hash": hashlib.sha1(schema_string.encode("utf-8")).hexdigest() if schema_string else None,
        },
        "needs_companion_branch": bool(companion_branch),
        "companion_branch": companion_branch,
        "note": "phase2_live_executor",
    }
