"""General knowledge agent stub executor."""

from typing import Any, Dict


def run_general_knowledge_agent_stub(
    *,
    branch: str,
    request: Any,
    route_decision: Dict[str, Any],
    context_meta: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "agent": "general_knowledge_agent",
        "branch": branch,
        "status": "executed",
        "selected_type": str(route_decision.get("selected_type") or ""),
        "primary_store": "llm_direct",
        "note": "phase2_stub_executor",
    }
