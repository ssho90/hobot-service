"""Macro agent live executor."""

from typing import Any, Dict

from .live_executor import execute_live_tool
from .tool_probe import detect_companion_branch


def run_macro_agent_stub(
    *,
    branch: str,
    request: Any,
    route_decision: Dict[str, Any],
    context_meta: Dict[str, Any],
) -> Dict[str, Any]:
    selected_type = str(route_decision.get("selected_type") or "")
    tool_probe = execute_live_tool(
        agent_name="macro_economy_agent",
        branch=branch,
        request=request,
        route_decision=route_decision,
        context_meta=context_meta,
    )
    companion_branch = detect_companion_branch(branch, tool_probe)
    return {
        "agent": "macro_economy_agent",
        "branch": branch,
        "status": "executed" if str(tool_probe.get("status") or "") == "ok" else "degraded",
        "selected_type": selected_type,
        "primary_store": "rdb" if branch == "sql" else "neo4j",
        "tool_probe": tool_probe,
        "needs_companion_branch": bool(companion_branch),
        "companion_branch": companion_branch,
        "note": "phase2_live_executor",
    }
