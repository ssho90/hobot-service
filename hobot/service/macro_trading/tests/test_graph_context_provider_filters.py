import unittest
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import MagicMock

_PROVIDER_PATH = (
    Path(__file__).resolve().parents[2]
    / "graph"
    / "strategy"
    / "graph_context_provider.py"
)
_PROVIDER_SPEC = spec_from_file_location("graph_context_provider_under_test", _PROVIDER_PATH)
assert _PROVIDER_SPEC and _PROVIDER_SPEC.loader
graph_context_provider = module_from_spec(_PROVIDER_SPEC)
_PROVIDER_SPEC.loader.exec_module(graph_context_provider)


class TestGraphContextProviderFilters(unittest.TestCase):
    def test_resolve_country_filter_supports_name_and_code(self):
        provider = graph_context_provider.StrategyGraphContextProvider()
        self.assertEqual(
            provider._resolve_country_filter("United States"),
            ("United States", "US"),
        )
        self.assertEqual(provider._resolve_country_filter("US"), ("US", "US"))
        self.assertEqual(provider._resolve_country_filter(None), (None, None))

    def test_enforce_trading_scope_country_forces_us(self):
        provider = graph_context_provider.StrategyGraphContextProvider()
        self.assertEqual(
            provider._enforce_trading_scope_country("KR"),
            ("United States", "US"),
        )
        self.assertEqual(
            provider._enforce_trading_scope_country("Japan"),
            ("United States", "US"),
        )
        self.assertEqual(
            provider._enforce_trading_scope_country(None),
            ("United States", "US"),
        )

    def test_fetch_recent_events_includes_country_code_filter(self):
        provider = graph_context_provider.StrategyGraphContextProvider()
        client = MagicMock()
        client.run_read.return_value = []

        provider._fetch_recent_events(
            client=client,
            start_date=date(2026, 2, 7),
            end_date=date(2026, 2, 14),
            country="US",
            country_code="US",
            limit=5,
        )

        query = client.run_read.call_args.args[0]
        params = client.run_read.call_args.args[1]
        self.assertIn("e.country_code", query)
        self.assertIn("coalesce(e.event_type, e.type", query)
        self.assertEqual(params["country"], "US")
        self.assertEqual(params["country_code"], "US")

    def test_fetch_recent_stories_includes_country_code_filter(self):
        provider = graph_context_provider.StrategyGraphContextProvider()
        client = MagicMock()
        client.run_read.return_value = []

        provider._fetch_recent_stories(
            client=client,
            start_date=date(2026, 2, 7),
            end_date=date(2026, 2, 14),
            country="US",
            country_code="US",
            limit=3,
        )

        query = client.run_read.call_args.args[0]
        params = client.run_read.call_args.args[1]
        self.assertIn("[:CONTAINS|AGGREGATES]", query)
        self.assertIn("d.country_code", query)
        self.assertEqual(params["country"], "US")
        self.assertEqual(params["country_code"], "US")

    def test_fetch_relevant_evidences_includes_country_code_filter(self):
        provider = graph_context_provider.StrategyGraphContextProvider()
        client = MagicMock()
        client.run_read.return_value = []

        provider._fetch_relevant_evidences(
            client=client,
            start_date=date(2026, 2, 7),
            end_date=date(2026, 2, 14),
            country="US",
            country_code="US",
            theme_ids=None,
            limit=3,
        )

        query = client.run_read.call_args.args[0]
        params = client.run_read.call_args.args[1]
        self.assertIn("d.country_code", query)
        self.assertEqual(params["country"], "US")
        self.assertEqual(params["country_code"], "US")

    def test_fetch_relevant_evidences_with_theme_ids_uses_document_and_event_theme_paths(self):
        provider = graph_context_provider.StrategyGraphContextProvider()
        client = MagicMock()
        client.run_read.return_value = []

        provider._fetch_relevant_evidences(
            client=client,
            start_date=date(2026, 2, 7),
            end_date=date(2026, 2, 14),
            country="US",
            country_code="US",
            theme_ids=["rates", "inflation"],
            limit=3,
        )

        query = client.run_read.call_args.args[0]
        params = client.run_read.call_args.args[1]
        self.assertIn("OPTIONAL MATCH (d)-[:ABOUT_THEME]->(doc_theme:MacroTheme)", query)
        self.assertIn("OPTIONAL MATCH (ev)-[:SUPPORTS]->(:Claim)-[:ABOUT]->(:Event)-[:ABOUT_THEME]->(event_theme:MacroTheme)", query)
        self.assertEqual(params["theme_ids"], ["rates", "inflation"])

    def test_build_strategy_context_propagates_country_code(self):
        provider = graph_context_provider.StrategyGraphContextProvider()
        provider._get_client = MagicMock(return_value=MagicMock())
        provider._fetch_recent_events = MagicMock(return_value=[])
        provider._fetch_recent_stories = MagicMock(return_value=[])
        provider._fetch_relevant_evidences = MagicMock(return_value=[])
        provider._assemble_context_block = MagicMock(return_value="")

        provider.build_strategy_context(
            as_of_date=date(2026, 2, 14),
            time_range_days=7,
            country="United States",
            max_events=5,
            max_stories=3,
            max_evidences=4,
        )

        self.assertEqual(provider._fetch_recent_events.call_args.args[3], "United States")
        self.assertEqual(provider._fetch_recent_events.call_args.args[4], "US")
        self.assertEqual(provider._fetch_recent_stories.call_args.args[3], "United States")
        self.assertEqual(provider._fetch_recent_stories.call_args.args[4], "US")
        self.assertEqual(provider._fetch_relevant_evidences.call_args.args[3], "United States")
        self.assertEqual(provider._fetch_relevant_evidences.call_args.args[4], "US")

    def test_build_strategy_context_forces_us_even_when_non_us_requested(self):
        provider = graph_context_provider.StrategyGraphContextProvider()
        provider._get_client = MagicMock(return_value=MagicMock())
        provider._fetch_recent_events = MagicMock(return_value=[])
        provider._fetch_recent_stories = MagicMock(return_value=[])
        provider._fetch_relevant_evidences = MagicMock(return_value=[])
        provider._assemble_context_block = MagicMock(return_value="")

        provider.build_strategy_context(
            as_of_date=date(2026, 2, 14),
            time_range_days=7,
            country="South Korea",
            max_events=5,
            max_stories=3,
            max_evidences=4,
        )

        self.assertEqual(provider._fetch_recent_events.call_args.args[3], "United States")
        self.assertEqual(provider._fetch_recent_events.call_args.args[4], "US")


if __name__ == "__main__":
    unittest.main()
