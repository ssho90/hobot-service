"""GraphRAG multi-agent stub executors."""

import logging
from typing import Any, Dict

from .equity_agent import run_equity_agent_stub
from .general_knowledge_agent import run_general_knowledge_agent_stub
from .macro_agent import run_macro_agent_stub
from .ontology_agent import run_ontology_agent_stub
from .real_estate_agent import run_real_estate_agent_stub

logger = logging.getLogger(__name__)

AGENT_STUB_RUNNERS = {
    "macro_economy_agent": run_macro_agent_stub,
    "equity_analyst_agent": run_equity_agent_stub,
    "real_estate_agent": run_real_estate_agent_stub,
    "ontology_master_agent": run_ontology_agent_stub,
    "general_knowledge_agent": run_general_knowledge_agent_stub,
}


def execute_agent_stub(
    agent_name: str,
    *,
    branch: str,
    request: Any,
    route_decision: Dict[str, Any],
    context_meta: Dict[str, Any],
) -> Dict[str, Any]:
    normalized_name = str(agent_name or "").strip()
    runner = AGENT_STUB_RUNNERS.get(normalized_name)
    if runner is None:
        return {
            "agent": normalized_name or "unknown_agent",
            "branch": branch,
            "status": "skipped",
            "reason": "runner_not_found",
        }

    try:
        return runner(
            branch=branch,
            request=request,
            route_decision=route_decision,
            context_meta=context_meta,
        )
    except Exception as error:
        logger.warning("[GraphRAGAgentStub] %s failed: %s", normalized_name, error)
        return {
            "agent": normalized_name,
            "branch": branch,
            "status": "error",
            "reason": f"{type(error).__name__}",
        }


__all__ = ["execute_agent_stub", "AGENT_STUB_RUNNERS"]
