"""Domain template registries for agent SQL/Cypher execution."""

from __future__ import annotations

from typing import Any, Dict, List

from .equity_query_templates import EQUITY_GRAPH_TEMPLATE_SPEC, EQUITY_SQL_TEMPLATE_SPECS
from .macro_query_templates import MACRO_GRAPH_TEMPLATE_SPEC, MACRO_SQL_TEMPLATE_SPECS
from .ontology_query_templates import ONTOLOGY_GRAPH_TEMPLATE_SPEC, ONTOLOGY_SQL_TEMPLATE_SPECS
from .real_estate_query_templates import REAL_ESTATE_GRAPH_TEMPLATE_SPEC, REAL_ESTATE_SQL_TEMPLATE_SPECS


SQL_TEMPLATE_SPECS: Dict[str, List[Dict[str, Any]]] = {
    "macro_economy_agent": MACRO_SQL_TEMPLATE_SPECS,
    "equity_analyst_agent": EQUITY_SQL_TEMPLATE_SPECS,
    "real_estate_agent": REAL_ESTATE_SQL_TEMPLATE_SPECS,
    "ontology_master_agent": ONTOLOGY_SQL_TEMPLATE_SPECS,
}


GRAPH_TEMPLATE_SPECS: Dict[str, Dict[str, str]] = {
    "macro_economy_agent": MACRO_GRAPH_TEMPLATE_SPEC,
    "equity_analyst_agent": EQUITY_GRAPH_TEMPLATE_SPEC,
    "real_estate_agent": REAL_ESTATE_GRAPH_TEMPLATE_SPEC,
    "ontology_master_agent": ONTOLOGY_GRAPH_TEMPLATE_SPEC,
}


__all__ = ["SQL_TEMPLATE_SPECS", "GRAPH_TEMPLATE_SPECS"]
