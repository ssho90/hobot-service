import unittest
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types


def _install_test_stubs() -> None:
    service_module = types.ModuleType("service")
    database_module = types.ModuleType("service.database")
    db_module = types.ModuleType("service.database.db")
    db_module.get_db_connection = lambda: None
    database_module.db = db_module

    graph_module = types.ModuleType("service.graph")
    neo4j_client_module = types.ModuleType("service.graph.neo4j_client")
    neo4j_client_module.get_neo4j_client = lambda: None
    graph_module.neo4j_client = neo4j_client_module

    service_module.database = database_module
    service_module.graph = graph_module

    pymysql_module = types.ModuleType("pymysql")
    pymysql_cursors_module = types.ModuleType("pymysql.cursors")
    pymysql_cursors_module.DictCursor = object
    pymysql_module.cursors = pymysql_cursors_module

    sys.modules.setdefault("service", service_module)
    sys.modules.setdefault("service.database", database_module)
    sys.modules.setdefault("service.database.db", db_module)
    sys.modules.setdefault("service.graph", graph_module)
    sys.modules.setdefault("service.graph.neo4j_client", neo4j_client_module)
    sys.modules.setdefault("pymysql", pymysql_module)
    sys.modules.setdefault("pymysql.cursors", pymysql_cursors_module)


_install_test_stubs()

_MIRROR_PATH = (
    Path(__file__).resolve().parents[1]
    / "service"
    / "graph"
    / "strategy"
    / "decision_mirror.py"
)
_MIRROR_SPEC = spec_from_file_location("decision_mirror_under_test", _MIRROR_PATH)
assert _MIRROR_SPEC and _MIRROR_SPEC.loader
decision_mirror = module_from_spec(_MIRROR_SPEC)
_MIRROR_SPEC.loader.exec_module(decision_mirror)


class StubNeo4jClient:
    def __init__(self, relationships_created: int):
        self.relationships_created = relationships_created
        self.calls = []

    def run_write(self, query, params=None):
        self.calls.append((query, params or {}))
        return {"relationships_created": self.relationships_created}


class TestPhaseEDecisionMirror(unittest.TestCase):
    def test_link_to_macro_state_uses_macrostate_date_property(self):
        mirror = decision_mirror.StrategyDecisionMirror()
        client = StubNeo4jClient(relationships_created=1)

        mirror._link_to_macro_state(
            client=client,
            decision_id="sd:2026-02-08:MP-4:abcd1234",
            decision_date=date(2026, 2, 8),
        )

        self.assertEqual(len(client.calls), 1)
        query, params = client.calls[0]
        self.assertIn("MATCH (ms:MacroState {date: date($decision_date)})", query)
        self.assertNotIn("ms.as_of_date", query)
        self.assertEqual(params["decision_date"], "2026-02-08")
        self.assertEqual(params["decision_id"], "sd:2026-02-08:MP-4:abcd1234")


if __name__ == "__main__":
    unittest.main()
