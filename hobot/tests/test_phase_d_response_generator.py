import unittest
import sys
import types
from datetime import date
import os

import pymysql
try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None

if callable(load_dotenv):
    load_dotenv(".env")

neo4j_stub = types.ModuleType("neo4j")


class _StubGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        raise RuntimeError("Neo4j driver should not be used in unit tests")


neo4j_stub.GraphDatabase = _StubGraphDatabase
neo4j_stub.Driver = object
sys.modules.setdefault("neo4j", neo4j_stub)

from service.graph.rag.context_api import (
    GraphEvidence,
    GraphLink,
    GraphNode,
    GraphRagContextResponse,
)
from service.graph.rag.response_generator import (
    GraphRagAnswerRequest,
    generate_graph_rag_answer,
    resolve_graph_rag_model,
)
from service.graph.rag.agents.tool_probe import run_sql_probe
import service.graph.rag.response_generator as response_generator_module


def _detect_db_ready():
    host = str(os.getenv("DB_HOST") or "127.0.0.1").strip()
    user = str(os.getenv("DB_USER") or "root").strip()
    db_name = str(os.getenv("DB_NAME") or "hobot").strip()
    try:
        port = int(str(os.getenv("DB_PORT") or "3306").strip())
    except Exception:
        port = 3306
    password = str(os.getenv("DB_PASSWORD") or "")

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db_name,
            connect_timeout=3,
            read_timeout=3,
            write_timeout=3,
            autocommit=True,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return True, "ok"
        finally:
            conn.close()
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


_DB_READY, _DB_READY_REASON = _detect_db_ready()
_REQUIRE_DB_TESTS = str(os.getenv("GRAPH_RAG_REQUIRE_DB_TESTS") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

if _REQUIRE_DB_TESTS and not _DB_READY:
    raise RuntimeError(f"GRAPH_RAG_REQUIRE_DB_TESTS=1 but DB is not reachable: {_DB_READY_REASON}")


class _StubLLMResponse:
    def __init__(self, content):
        self.content = content


class _StubLLM:
    def __init__(self, content):
        self._content = content

    def invoke(self, prompt: str):
        self.last_prompt = prompt
        return _StubLLMResponse(self._content)


class _FailingLLM:
    def invoke(self, prompt: str):
        raise AssertionError("LLM should not be called when Top50 scope guard is triggered")


class _AgentLLMResponse:
    def __init__(self, content: str):
        self.content = content
        self.response_metadata = {
            "usage_metadata": {
                "input_tokens": 17,
                "output_tokens": 9,
                "total_tokens": 26,
            }
        }


class _AgentLLM:
    def __init__(self, content: str):
        self._content = content
        self.last_prompt = None

    def invoke(self, prompt: str):
        self.last_prompt = prompt
        return _AgentLLMResponse(self._content)


class _StubMacroStateGenerator:
    def __init__(self):
        self.called = False

    def generate_macro_state(self, as_of_date, theme_window_days, top_themes, top_signals):
        self.called = True
        return {
            "as_of": as_of_date.isoformat(),
            "theme_window_days": theme_window_days,
            "top_themes": top_themes,
            "top_signals": top_signals,
        }


class _StubAnalysisRunWriter:
    def __init__(self):
        self.called = False
        self.last_kwargs = {}

    def persist_run(self, **kwargs):
        self.called = True
        self.last_kwargs = dict(kwargs)
        return {
            "run_id": "ar_test_run",
            "counts": {"evidences": 1},
        }


class TestPhaseDResponseGenerator(unittest.TestCase):
    def test_answer_request_to_context_request_includes_country_code(self):
        request = GraphRagAnswerRequest(
            question="US macro update",
            country_code="US",
            compare_mode="country_compare",
            region_code="SEOUL",
            property_type="apartment_sale",
        )
        context_request = request.to_context_request()
        self.assertEqual(context_request.country_code, "US")
        self.assertEqual(context_request.compare_mode, "country_compare")
        self.assertEqual(context_request.region_code, "SEOUL")
        self.assertEqual(context_request.property_type, "apartment_sale")

    def test_answer_request_to_context_request_uses_agent_focus_fallback(self):
        request = GraphRagAnswerRequest(
            question="팔란티어 전망 어때?",
            country_code="US",
        )
        route = {
            "selected_type": "us_single_stock",
            "agents": [
                {
                    "agent": "us_single_stock_agent",
                    "selected_type": "us_single_stock",
                    "matched_symbols": ["PLTR"],
                    "matched_companies": ["Palantir Technologies"],
                },
                {
                    "agent": "keyword_agent",
                    "selected_type": "general_macro",
                },
            ],
        }

        context_request = request.to_context_request(route=route)
        self.assertEqual(context_request.route_type, "us_single_stock")
        self.assertEqual(context_request.focus_symbols, ["PLTR"])
        self.assertEqual(context_request.focus_companies, ["Palantir Technologies"])

    def test_answer_request_to_context_request_uses_security_ids_when_symbols_missing(self):
        request = GraphRagAnswerRequest(
            question="팔란티어 전망 어때?",
            country_code="US",
        )
        route = {
            "selected_type": "us_single_stock",
            "matched_security_ids": ["US:PLTR"],
            "matched_companies": ["Palantir Technologies"],
        }

        context_request = request.to_context_request(route=route)
        self.assertEqual(context_request.route_type, "us_single_stock")
        self.assertEqual(context_request.focus_symbols, ["PLTR"])
        self.assertEqual(context_request.focus_companies, ["Palantir Technologies"])

    def _sample_context(self) -> GraphRagContextResponse:
        return GraphRagContextResponse(
            nodes=[
                GraphNode(
                    id="event:EVT_001",
                    type="Event",
                    label="CPI surprise",
                    properties={"event_id": "EVT_001", "event_time": "2026-02-07T10:00:00"},
                ),
                GraphNode(
                    id="theme:inflation",
                    type="MacroTheme",
                    label="Inflation",
                    properties={"theme_id": "inflation"},
                ),
                GraphNode(
                    id="indicator:CPIAUCSL",
                    type="EconomicIndicator",
                    label="CPI",
                    properties={"indicator_code": "CPIAUCSL"},
                ),
            ],
            links=[
                GraphLink(source="event:EVT_001", target="theme:inflation", type="ABOUT_THEME"),
                GraphLink(source="event:EVT_001", target="indicator:CPIAUCSL", type="AFFECTS"),
            ],
            evidences=[
                GraphEvidence(
                    evidence_id="EVID_1",
                    text="Inflation accelerated in January.",
                    doc_id="te:100",
                    doc_url="https://example.com/a",
                    doc_title="CPI article",
                    published_at="2026-02-07T11:00:00",
                    support_labels=["Fact"],
                    event_id="EVT_001",
                ),
                GraphEvidence(
                    evidence_id="EVID_2",
                    text="Core CPI remained elevated.",
                    doc_id="te:101",
                    doc_url="https://example.com/b",
                    doc_title="Core CPI article",
                    published_at="2026-02-07T11:30:00",
                    support_labels=["Claim"],
                    event_id="EVT_001",
                ),
                GraphEvidence(
                    evidence_id="EVID_3",
                    text="Treasury yield rose after inflation surprise.",
                    doc_id="te:102",
                    doc_url="https://example.com/c",
                    doc_title="Yield reaction",
                    published_at="2026-02-07T12:00:00",
                    support_labels=["Fact"],
                    event_id="EVT_001",
                ),
                GraphEvidence(
                    evidence_id="EVID_4",
                    text="Dollar strengthened amid rate repricing.",
                    doc_id="te:103",
                    doc_url="https://example.com/d",
                    doc_title="FX reaction",
                    published_at="2026-02-07T12:30:00",
                    support_labels=["Fact"],
                    event_id="EVT_001",
                ),
            ],
            suggested_queries=["최근 인플레이션 이벤트 Top 5는?"],
            meta={"window_days": 7},
        )

    def _sample_context_without_evidence(self) -> GraphRagContextResponse:
        context = self._sample_context()
        context.evidences = []
        return context

    def _sample_us_single_stock_context(self, symbol: str, company: str) -> GraphRagContextResponse:
        return GraphRagContextResponse(
            nodes=[
                GraphNode(
                    id="event:EVT_STOCK_001",
                    type="Event",
                    label=f"{company} earnings reaction",
                    properties={"event_id": "EVT_STOCK_001", "event_time": "2026-02-07T10:00:00"},
                ),
                GraphNode(
                    id="theme:growth",
                    type="MacroTheme",
                    label="Growth",
                    properties={"theme_id": "growth"},
                ),
                GraphNode(
                    id="indicator:GDP",
                    type="EconomicIndicator",
                    label="GDP",
                    properties={"indicator_code": "GDP"},
                ),
            ],
            links=[
                GraphLink(source="event:EVT_STOCK_001", target="theme:growth", type="ABOUT_THEME"),
                GraphLink(source="event:EVT_STOCK_001", target="indicator:GDP", type="AFFECTS"),
            ],
            evidences=[
                GraphEvidence(
                    evidence_id="EVID_S1",
                    text=f"{company} ({symbol}) shares rose 7.2% after earnings beat.",
                    doc_id="te:stock-1",
                    doc_url="https://example.com/stock-1",
                    doc_title=f"{company} price reaction",
                    published_at="2026-02-07T11:00:00",
                    support_labels=["Fact"],
                    event_id="EVT_STOCK_001",
                ),
                GraphEvidence(
                    evidence_id="EVID_S2",
                    text=f"{company} reported revenue growth of 24% and raised guidance.",
                    doc_id="te:stock-2",
                    doc_url="https://example.com/stock-2",
                    doc_title=f"{company} earnings",
                    published_at="2026-02-07T11:30:00",
                    support_labels=["Fact"],
                    event_id="EVT_STOCK_001",
                ),
                GraphEvidence(
                    evidence_id="EVID_S3",
                    text=f"{company} trades at a rich valuation multiple near 28x forward earnings.",
                    doc_id="te:stock-3",
                    doc_url="https://example.com/stock-3",
                    doc_title=f"{company} valuation",
                    published_at="2026-02-07T12:00:00",
                    support_labels=["Claim"],
                    event_id="EVT_STOCK_001",
                ),
                GraphEvidence(
                    evidence_id="EVID_S4",
                    text=f"Investors flagged capex and demand volatility as key risks for {company}.",
                    doc_id="te:stock-4",
                    doc_url="https://example.com/stock-4",
                    doc_title=f"{company} risks",
                    published_at="2026-02-07T12:30:00",
                    support_labels=["Claim"],
                    event_id="EVT_STOCK_001",
                ),
            ],
            suggested_queries=[f"{symbol} 최근 실적 요약"],
            meta={"window_days": 7},
        )

    def test_generate_answer_uses_cited_evidences(self):
        request = GraphRagAnswerRequest(
            question="최근 인플레이션 리스크는?",
            model="gemini-3-pro-preview",
            include_context=True,
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "인플레이션 압력이 단기적으로 높아졌습니다.",
              "uncertainty": "표본 기간이 짧아 추세 전환 판단은 제한적입니다.",
              "key_points": ["CPI 서프라이즈 발생", "핵심 물가 상승 지속"],
              "impact_pathways": [
                {
                  "event_id": "EVT_001",
                  "theme_id": "inflation",
                  "indicator_code": "CPIAUCSL",
                  "explanation": "이벤트가 인플레 테마를 강화하며 CPI 상방 압력을 시사합니다."
                }
              ],
              "cited_evidence_ids": ["EVID_1"]
            }
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )

        self.assertEqual(response.model, "gemini-3-pro-preview")
        self.assertEqual(response.answer.conclusion, "인플레이션 압력이 단기적으로 높아졌습니다.")
        self.assertGreaterEqual(len(response.citations), 3)
        self.assertLessEqual(len(response.citations), 10)
        self.assertEqual(response.citations[0].evidence_id, "EVID_1")
        self.assertEqual(response.used_evidence_count, len(response.citations))
        self.assertIn("data_freshness", response.context_meta)
        self.assertIn("collection_eta_minutes", response.context_meta)
        self.assertIn("confidence", response.context_meta)
        self.assertIsNotNone(response.context)

    def test_fallback_citation_from_doc_id(self):
        request = GraphRagAnswerRequest(
            question="최근 인플레이션 리스크는?",
            model="gemini-3-flash-preview",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            ```json
            {
              "conclusion": "물가 관련 리스크가 유지되고 있습니다.",
              "uncertainty": "근거 불충분",
              "key_points": [],
              "impact_pathways": [],
              "cited_doc_ids": ["te:101"]
            }
            ```
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )

        self.assertEqual(response.model, "gemini-3-pro-preview")
        self.assertGreaterEqual(len(response.citations), 3)
        self.assertEqual(response.citations[0].doc_id, "te:101")

    def test_generate_answer_handles_list_content(self):
        request = GraphRagAnswerRequest(
            question="최근 인플레이션 리스크는?",
            model="gemini-3-pro-preview",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            [
                {
                    "type": "text",
                    "text": """
                    {
                      "conclusion": "리스크는 유지되고 있습니다.",
                      "uncertainty": "근거 불충분",
                      "key_points": ["핵심 물가 강세"],
                      "impact_pathways": [],
                      "cited_evidence_ids": ["EVID_1"]
                    }
                    """,
                }
            ]
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )

        self.assertEqual(response.answer.conclusion, "리스크는 유지되고 있습니다.")
        self.assertGreaterEqual(len(response.citations), 3)
        self.assertEqual(response.citations[0].evidence_id, "EVID_1")

    def test_generate_answer_injects_recent_citation_when_llm_picks_stale_only(self):
        context = GraphRagContextResponse(
            nodes=self._sample_context().nodes,
            links=self._sample_context().links,
            evidences=[
                GraphEvidence(
                    evidence_id="EVID_OLD_1",
                    text="Older evidence 1.",
                    doc_id="te:old-1",
                    doc_url="https://example.com/old-1",
                    doc_title="Old evidence 1",
                    published_at="2026-02-01T09:00:00+00:00",
                    support_labels=["Fact"],
                ),
                GraphEvidence(
                    evidence_id="EVID_OLD_2",
                    text="Older evidence 2.",
                    doc_id="te:old-2",
                    doc_url="https://example.com/old-2",
                    doc_title="Old evidence 2",
                    published_at="2026-02-01T10:00:00+00:00",
                    support_labels=["Fact"],
                ),
                GraphEvidence(
                    evidence_id="EVID_OLD_3",
                    text="Older evidence 3.",
                    doc_id="te:old-3",
                    doc_url="https://example.com/old-3",
                    doc_title="Old evidence 3",
                    published_at="2026-02-01T11:00:00+00:00",
                    support_labels=["Fact"],
                ),
                GraphEvidence(
                    evidence_id="EVID_NEW_1",
                    text="Recent evidence after latest sync.",
                    doc_id="te:new-1",
                    doc_url="https://example.com/new-1",
                    doc_title="Recent evidence",
                    published_at="2026-02-19T12:00:00+00:00",
                    support_labels=["Fact"],
                ),
            ],
            suggested_queries=["최신 근거 테스트"],
            meta={"window_days": 30},
        )
        request = GraphRagAnswerRequest(
            question="최근 리스크 점검",
            model="gemini-3-pro-preview",
            as_of_date=date(2026, 2, 20),
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "Old evidence only selected by LLM.",
              "uncertainty": "근거 불충분",
              "key_points": ["Older evidence 1", "Older evidence 2"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_OLD_1", "EVID_OLD_2", "EVID_OLD_3"]
            }
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=context,
            llm=llm,
        )

        citation_ids = {item.evidence_id for item in response.citations}
        self.assertIn("EVID_NEW_1", citation_ids)
        self.assertIn(response.data_freshness.get("status"), {"fresh", "warning"})

    def test_resolve_model_fallback(self):
        self.assertEqual(
            resolve_graph_rag_model("gpt-4o"),
            "gemini-3-pro-preview",
        )

    def test_generate_answer_calls_state_persistence_hooks(self):
        request = GraphRagAnswerRequest(
            question="최근 인플레이션 리스크는?",
            model="gemini-3-pro-preview",
            persist_macro_state=True,
            persist_analysis_run=True,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "인플레이션 리스크가 유지되고 있습니다.",
              "uncertainty": "단기 데이터 중심으로 해석됨",
              "key_points": ["핵심 물가 강세"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1"]
            }
            """
        )
        state_generator = _StubMacroStateGenerator()
        run_writer = _StubAnalysisRunWriter()

        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
            analysis_run_writer=run_writer,
            macro_state_generator=state_generator,
        )

        self.assertTrue(state_generator.called)
        self.assertTrue(run_writer.called)
        self.assertEqual(response.analysis_run_id, "ar_test_run")
        self.assertIn("macro_state", response.persistence)
        self.assertIn("analysis_run", response.persistence)
        run_metadata = (run_writer.last_kwargs or {}).get("run_metadata") or {}
        self.assertIn("structured_citation_count", run_metadata)
        self.assertIn("structured_citations", run_metadata)
        self.assertIsInstance(run_metadata.get("structured_citations"), list)

    def test_build_structured_citations_from_execution_sql_branch(self):
        supervisor_execution = {
            "execution_result": {
                "status": "executed",
                "branch_results": [
                    {
                        "branch": "sql",
                        "enabled": True,
                        "agent_runs": [
                            {
                                "agent": "macro_economy_agent",
                                "branch": "sql",
                                "tool_probe": {
                                    "tool": "sql",
                                    "status": "ok",
                                    "template_id": "macro.sql.latest_fred_observations.v1",
                                    "table": "fred_data",
                                    "filters": {"indicator_code": "CPIAUCSL"},
                                    "query": "SELECT indicator_code, obs_date, value FROM `fred_data` LIMIT 5",
                                    "params": [],
                                    "row_count": 5,
                                },
                            }
                        ],
                    }
                ],
            }
        }
        structured = response_generator_module._build_structured_citations_from_execution(
            supervisor_execution=supervisor_execution,
            as_of_date=date(2026, 2, 19),
            time_range="30d",
        )

        self.assertEqual(len(structured), 1)
        citation = structured[0]
        self.assertEqual(citation.table, "fred_data")
        self.assertEqual(citation.dataset_code, "FRED_DATA")
        self.assertEqual(citation.date_range, "30d")
        self.assertEqual(citation.as_of_date, "2026-02-19")
        self.assertEqual(citation.row_count, 5)
        self.assertTrue(citation.query_fingerprint)

    def test_build_structured_data_context_from_execution_sql_rows(self):
        supervisor_execution = {
            "execution_result": {
                "status": "executed",
                "branch_results": [
                    {
                        "branch": "sql",
                        "enabled": True,
                        "agent_runs": [
                            {
                                "agent": "real_estate_agent",
                                "branch": "sql",
                                "tool_probe": {
                                    "tool": "sql",
                                    "status": "ok",
                                    "reason": "sql_template_executed",
                                    "template_id": "real_estate.sql.latest_monthly_summary.v1",
                                    "table": "kr_real_estate_monthly_summary",
                                    "selected_columns": ["stat_ym", "lawd_cd", "avg_price", "tx_count"],
                                    "filters": {"region_code": "11"},
                                    "row_count": 2,
                                    "rows": [
                                        {"stat_ym": "202601", "lawd_cd": "11110", "avg_price": 1280000000, "tx_count": 320},
                                        {"stat_ym": "202512", "lawd_cd": "11110", "avg_price": 1260000000, "tx_count": 298},
                                    ],
                                },
                            }
                        ],
                    }
                ],
            }
        }
        structured_data = response_generator_module._build_structured_data_context(
            supervisor_execution=supervisor_execution
        )

        self.assertEqual(structured_data.get("dataset_count"), 1)
        datasets = structured_data.get("datasets") or []
        self.assertEqual(len(datasets), 1)
        first = datasets[0]
        self.assertEqual(first.get("table"), "kr_real_estate_monthly_summary")
        self.assertEqual(first.get("row_count"), 2)
        sample_rows = first.get("sample_rows") or []
        self.assertGreaterEqual(len(sample_rows), 1)
        self.assertEqual(sample_rows[0].get("lawd_cd"), "서울 종로구")

    def test_build_structured_data_context_includes_real_estate_trend_analysis(self):
        supervisor_execution = {
            "execution_result": {
                "status": "executed",
                "branch_results": [
                    {
                        "branch": "sql",
                        "enabled": True,
                        "agent_runs": [
                            {
                                "agent": "real_estate_agent",
                                "branch": "sql",
                                "tool_probe": {
                                    "tool": "sql",
                                    "status": "ok",
                                    "reason": "sql_template_executed",
                                    "template_id": "real_estate.sql.latest_monthly_summary.v1",
                                    "table": "kr_real_estate_monthly_summary",
                                    "selected_columns": ["stat_ym", "lawd_cd", "avg_price", "tx_count"],
                                    "filters": {"region_code": "11380"},
                                    "row_count": 2,
                                    "rows": [
                                        {"stat_ym": "202601", "lawd_cd": "11380", "avg_price": 1080000000, "tx_count": 210},
                                        {"stat_ym": "202512", "lawd_cd": "11380", "avg_price": 1060000000, "tx_count": 198},
                                    ],
                                    "trend_analysis": {
                                        "status": "ok",
                                        "reason": "real_estate_trend_available",
                                        "scope_label": "서울 은평구",
                                        "months_available": 12,
                                        "earliest_month": "202502",
                                        "latest_month": "202601",
                                        "price_change_pct_vs_start": 4.2,
                                        "tx_change_pct_vs_start": 9.8,
                                        "latest_weighted_avg_price": 1080000000,
                                        "latest_tx_count": 210,
                                        "rows": [
                                            {"stat_ym": "202601", "weighted_avg_price": 1080000000, "tx_count": 210},
                                            {"stat_ym": "202512", "weighted_avg_price": 1060000000, "tx_count": 198},
                                        ],
                                    },
                                },
                            }
                        ],
                    }
                ],
            }
        }
        structured_data = response_generator_module._build_structured_data_context(
            supervisor_execution=supervisor_execution
        )

        datasets = structured_data.get("datasets") or []
        self.assertEqual(len(datasets), 1)
        trend_analysis = datasets[0].get("trend_analysis") or {}
        self.assertEqual(trend_analysis.get("months_available"), 12)
        self.assertEqual(trend_analysis.get("scope_label"), "서울 은평구")
        self.assertEqual((datasets[0].get("filters") or {}).get("region_code"), "서울 은평구")

    def test_build_structured_data_context_includes_equity_analysis(self):
        supervisor_execution = {
            "execution_result": {
                "status": "executed",
                "branch_results": [
                    {
                        "branch": "sql",
                        "enabled": True,
                        "agent_runs": [
                            {
                                "agent": "equity_analyst_agent",
                                "branch": "sql",
                                "tool_probe": {
                                    "tool": "sql",
                                    "status": "ok",
                                    "reason": "sql_template_executed",
                                    "template_id": "equity.sql.latest_us_ohlcv.v1",
                                    "table": "us_top50_daily_ohlcv",
                                    "selected_columns": ["trade_date", "symbol", "close_price", "volume"],
                                    "filters": {"symbol": "AAPL"},
                                    "row_count": 5,
                                    "rows": [
                                        {"trade_date": "2026-02-20", "symbol": "AAPL", "close_price": 210.2, "volume": 10000},
                                        {"trade_date": "2026-02-19", "symbol": "AAPL", "close_price": 208.0, "volume": 9800},
                                    ],
                                    "equity_analysis": {
                                        "status": "ok",
                                        "reason": "equity_trend_available",
                                        "country_code": "US",
                                        "bars_available": 160,
                                        "latest_trade_date": "2026-02-20",
                                        "latest_close": 210.2,
                                        "latest_volume": 10000,
                                        "moving_averages": {"ma20": 205.1, "ma60": 198.2, "ma120": 184.6},
                                        "trend": {"short_term": "상승", "long_term": "상승", "cross_signal": "none"},
                                        "returns": {"return_1d_pct": 1.06, "return_5d_pct": 3.2, "return_20d_pct": 8.5},
                                        "earnings_reaction": {
                                            "status": "ok",
                                            "event_count": 2,
                                            "latest_event_date": "2026-02-03",
                                            "latest_event_trade_date": "2026-02-03",
                                            "latest_event_day_pct_from_pre_close": 6.1,
                                            "latest_post_1d_pct_from_event_close": -1.9,
                                            "latest_post_5d_pct_from_event_close": -8.3,
                                            "events": [
                                                {
                                                    "event_date": "2026-02-03",
                                                    "event_trade_date": "2026-02-03",
                                                    "event_day_pct_from_pre_close": 6.1,
                                                }
                                            ],
                                        },
                                    },
                                },
                            }
                        ],
                    }
                ],
            }
        }

        structured_data = response_generator_module._build_structured_data_context(
            supervisor_execution=supervisor_execution
        )

        datasets = structured_data.get("datasets") or []
        self.assertEqual(len(datasets), 1)
        equity_analysis = datasets[0].get("equity_analysis") or {}
        self.assertEqual(equity_analysis.get("bars_available"), 160)
        self.assertEqual((equity_analysis.get("trend") or {}).get("short_term"), "상승")
        earnings_reaction = equity_analysis.get("earnings_reaction") or {}
        self.assertEqual(earnings_reaction.get("event_count"), 2)
        self.assertEqual(earnings_reaction.get("latest_event_date"), "2026-02-03")

    def test_build_structured_data_context_includes_agent_insights(self):
        supervisor_execution = {
            "execution_result": {
                "status": "executed",
                "branch_results": [
                    {
                        "branch": "graph",
                        "enabled": True,
                        "agent_runs": [
                            {
                                "agent": "real_estate_agent",
                                "branch": "graph",
                                "agent_llm": {
                                    "status": "ok",
                                    "model": "gemini-3-flash-preview",
                                    "payload": {
                                        "summary": "거래량 회복이 확인됩니다.",
                                        "key_points": ["최근 3개월 거래량 증가"],
                                        "risks": ["금리 변동성"],
                                        "confidence": "Medium",
                                    },
                                },
                            }
                        ],
                    }
                ],
            }
        }
        structured_data = response_generator_module._build_structured_data_context(
            supervisor_execution=supervisor_execution
        )
        self.assertEqual(structured_data.get("dataset_count"), 0)
        self.assertEqual(structured_data.get("agent_insight_count"), 1)
        insights = structured_data.get("agent_insights") or []
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0].get("agent"), "real_estate_agent")
        self.assertIn("거래량", str(insights[0].get("summary") or ""))

    def test_execute_branch_agents_can_skip_agent_llm(self):
        original_execute_agent_stub = response_generator_module.execute_agent_stub

        def _stub_execute_agent_stub(agent_name, **kwargs):
            return {
                "agent": agent_name,
                "branch": kwargs.get("branch"),
                "status": "executed",
                "tool_probe": {
                    "tool": "sql",
                    "status": "ok",
                    "reason": "sql_template_executed",
                    "row_count": 2,
                },
            }

        response_generator_module.execute_agent_stub = _stub_execute_agent_stub
        try:
            result = response_generator_module._execute_branch_agents(
                branch_name="sql",
                enabled=True,
                dispatch_mode="single",
                agents=["real_estate_agent"],
                request=GraphRagAnswerRequest(
                    question="한국 부동산 전망",
                    persist_macro_state=False,
                    persist_analysis_run=False,
                ),
                route_decision={
                    "selected_type": "real_estate_detail",
                    "sql_need": True,
                    "graph_need": False,
                    "agent_model_policy": {"real_estate_agent": "gemini-3-flash-preview"},
                },
                context_meta={},
                agent_llm_enabled=False,
            )
        finally:
            response_generator_module.execute_agent_stub = original_execute_agent_stub

        runs = result.get("agent_runs") or []
        self.assertEqual(len(runs), 1)
        agent_llm = runs[0].get("agent_llm") or {}
        self.assertFalse(agent_llm.get("enabled"))
        self.assertEqual(agent_llm.get("status"), "skipped")

    def test_execute_branch_agents_runs_agent_llm_and_tracks_call(self):
        original_execute_agent_stub = response_generator_module.execute_agent_stub
        original_resolve_agent_llm = response_generator_module._resolve_agent_llm
        original_track_llm_call = response_generator_module.track_llm_call

        tracker_calls = []
        stub_llm = _AgentLLM(
            '{"summary":"가격/거래 동시 개선","key_points":["최근 3개월 거래량 증가"],"risks":["금리 재상승"],"confidence":"Medium"}'
        )

        class _TrackerRecorder:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.responses = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

            def set_response(self, response):
                self.responses.append(response)

        def _stub_execute_agent_stub(agent_name, **kwargs):
            return {
                "agent": agent_name,
                "branch": kwargs.get("branch"),
                "status": "executed",
                "tool_probe": {
                    "tool": "sql",
                    "status": "ok",
                    "reason": "sql_template_executed",
                    "row_count": 3,
                },
            }

        def _stub_resolve_agent_llm(**kwargs):
            return stub_llm

        def _stub_track_llm_call(**kwargs):
            recorder = _TrackerRecorder(**kwargs)
            tracker_calls.append(recorder)
            return recorder

        response_generator_module.execute_agent_stub = _stub_execute_agent_stub
        response_generator_module._resolve_agent_llm = _stub_resolve_agent_llm
        response_generator_module.track_llm_call = _stub_track_llm_call
        try:
            result = response_generator_module._execute_branch_agents(
                branch_name="sql",
                enabled=True,
                dispatch_mode="single",
                agents=["real_estate_agent"],
                request=GraphRagAnswerRequest(
                    question="한국 부동산 전망",
                    persist_macro_state=False,
                    persist_analysis_run=False,
                ),
                route_decision={
                    "selected_type": "real_estate_detail",
                    "sql_need": True,
                    "graph_need": False,
                    "agent_model_policy": {"real_estate_agent": "gemini-3-flash-preview"},
                },
                context_meta={"counts": {"documents": 10}},
                agent_llm_enabled=True,
                flow_type="chatbot",
                flow_run_id="test-run-1",
                user_id="tester",
            )
        finally:
            response_generator_module.execute_agent_stub = original_execute_agent_stub
            response_generator_module._resolve_agent_llm = original_resolve_agent_llm
            response_generator_module.track_llm_call = original_track_llm_call

        runs = result.get("agent_runs") or []
        self.assertEqual(len(runs), 1)
        agent_llm = runs[0].get("agent_llm") or {}
        self.assertEqual(agent_llm.get("status"), "ok")
        self.assertEqual(agent_llm.get("reason"), "agent_llm_executed")
        payload = agent_llm.get("payload") or {}
        self.assertIn("가격/거래", str(payload.get("summary") or ""))

        self.assertEqual(len(tracker_calls), 1)
        self.assertEqual(tracker_calls[0].kwargs.get("service_name"), "graph_rag_agent_execution")
        self.assertEqual(tracker_calls[0].kwargs.get("agent_name"), "real_estate_agent")
        request_prompt = str(tracker_calls[0].kwargs.get("request_prompt") or "")
        self.assertIn("[Role]", request_prompt)
        self.assertIn("부동산 정량 분석 전문가", request_prompt)
        self.assertEqual(len(tracker_calls[0].responses), 1)
        self.assertIn("[Role]", str(stub_llm.last_prompt or ""))

    def test_make_prompt_includes_structured_data_context(self):
        request = GraphRagAnswerRequest(question="한국 부동산 가격 전망 해줘")
        prompt = response_generator_module._make_prompt(
            request=request,
            context=self._sample_context(),
            max_prompt_evidences=5,
            route={"selected_type": "real_estate_detail"},
            structured_data_context={
                "dataset_count": 1,
                "datasets": [
                    {
                        "agent": "real_estate_agent",
                        "table": "kr_real_estate_monthly_summary",
                        "row_count": 2,
                    }
                ],
            },
        )

        self.assertIn("[StructuredDataContextCompact]", prompt)
        self.assertIn("kr_real_estate_monthly_summary", prompt)

    def test_generate_answer_rejects_out_of_scope_country(self):
        request = GraphRagAnswerRequest(
            question="일본 금리 경로 요약",
            country_code="JP",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM("{}")

        with self.assertRaises(ValueError):
            generate_graph_rag_answer(
                request=request,
                context_response=self._sample_context(),
                llm=llm,
            )

    def test_generate_answer_accepts_us_kr_country_scope(self):
        request = GraphRagAnswerRequest(
            question="미국과 한국 환율/금리 비교",
            country_code="US-KR",
            compare_mode="country_compare",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "US-KR cross-market volatility remains elevated.",
              "uncertainty": "근거 불충분",
              "key_points": ["Dollar strengthened amid rate repricing"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        self.assertIsNotNone(response)

    def test_generate_answer_returns_top50_scope_guard_message(self):
        request = GraphRagAnswerRequest(
            question="한화손해보험 실적 알려줘",
            country_code="KR",
            persist_macro_state=False,
            persist_analysis_run=False,
        )

        original_evaluator = response_generator_module._evaluate_kr_top50_scope
        response_generator_module._evaluate_kr_top50_scope = lambda question, normalized_country_code: {
            "enforced": True,
            "allowed": False,
            "top50_snapshot_date": "2026-02-16",
            "out_of_scope_companies": [
                {"corp_name": "한화손해보험", "stock_code": "000370", "corp_code": "00100000"}
            ],
        }
        try:
            response = generate_graph_rag_answer(
                request=request,
                context_response=self._sample_context(),
                llm=_FailingLLM(),
            )
        finally:
            response_generator_module._evaluate_kr_top50_scope = original_evaluator

        self.assertIn("Top50", response.answer.conclusion)
        self.assertIn("데이터", response.answer.key_points[0])
        self.assertEqual(response.context_meta.get("policy"), "kr_top50_scope_guard")
        self.assertEqual(response.used_evidence_count, 0)
        self.assertEqual(response.collection_eta_minutes, 120)
        supervisor_execution = response.context_meta.get("supervisor_execution") or {}
        execution_result = supervisor_execution.get("execution_result") or {}
        self.assertEqual(execution_result.get("status"), "skipped")
        self.assertEqual(execution_result.get("reason"), "kr_top50_scope_guard")

    def test_generate_answer_applies_c_option_when_no_evidence(self):
        request = GraphRagAnswerRequest(
            question="최근 인플레이션 리스크는?",
            model="gemini-3-flash-preview",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "단기 리스크가 있습니다.",
              "uncertainty": "불확실성 존재",
              "key_points": ["단기 변동성 확대"],
              "impact_pathways": []
            }
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context_without_evidence(),
            llm=llm,
        )

        self.assertEqual(response.used_evidence_count, 0)
        self.assertEqual(response.data_freshness.get("status"), "missing")
        self.assertEqual(response.collection_eta_minutes, 120)
        self.assertIn("근거가 부족", response.answer.conclusion)

    def test_required_question_schema_validation_for_q1(self):
        request = GraphRagAnswerRequest(
            question="팔란티어 급락 원인 설명해줘",
            question_id="Q1",
            country_code="US",
            model="gemini-3-pro-preview",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "Inflation accelerated and growth concerns increased downside pressure.",
              "uncertainty": "단기 이벤트 중심이라 후속 확인 필요",
              "key_points": ["Inflation accelerated in January", "Core CPI remained elevated"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )

        validation = response.context_meta.get("required_question_schema_validation") or {}
        schema = response.context_meta.get("required_question_schema") or {}
        self.assertTrue(validation.get("enabled"))
        self.assertTrue(validation.get("is_valid"))
        self.assertEqual(schema.get("question_id"), "Q1")
        self.assertEqual(schema.get("answer_type"), "explain_drop")
        self.assertEqual(schema.get("scope", {}).get("country_code"), "US")
        self.assertGreaterEqual(len(schema.get("evidences", [])), 3)

    def test_required_question_schema_blocks_direct_buy_sell_instruction(self):
        request = GraphRagAnswerRequest(
            question="부동산 매수/매도 시점 알려줘",
            question_id="Q6",
            country_code="KR",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "Inflation accelerated, buy now.",
              "uncertainty": "변동성 존재",
              "key_points": ["Inflation accelerated in January", "Core CPI remained elevated"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        validation = response.context_meta.get("required_question_schema_validation") or {}
        self.assertTrue(validation.get("enabled"))
        self.assertTrue(validation.get("is_valid"))
        self.assertTrue(response.context_meta.get("conditional_scenario_enforced"))
        self.assertIn("조건", response.answer.conclusion)
        self.assertFalse(any(token in response.answer.conclusion.lower() for token in ["buy", "sell"]))
        self.assertTrue(any("시나리오" in str(point) for point in response.answer.key_points))

    def test_prompt_includes_us_kr_compare_template_guidance(self):
        request = GraphRagAnswerRequest(
            question="미국과 한국 환율/금리 비교해줘",
            country_code="US-KR",
            compare_mode="country_compare",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "US-KR spread remains elevated.",
              "uncertainty": "근거 불충분",
              "key_points": ["Dollar strengthened amid rate repricing"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        _ = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        self.assertIn("US-KR 비교 템플릿 강제", llm.last_prompt)

    def test_prompt_includes_kr_real_estate_template_guidance(self):
        request = GraphRagAnswerRequest(
            question="서울 아파트 매매 추이 요약",
            country_code="KR",
            region_code="11110,11140",
            property_type="apartment_sale",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "서울 도심권 가격은 완만한 흐름입니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["거래량은 보합"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        _ = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        self.assertIn("KR 부동산 템플릿 강제", llm.last_prompt)
        self.assertIn("유형=아파트 매매", llm.last_prompt)

    def test_prompt_includes_daily_us_macro_reference_for_kr_scope(self):
        request = GraphRagAnswerRequest(
            question="한국 부동산 가격 전망 해줘",
            country_code="KR",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "국내 부동산은 금리 민감도가 높은 구간입니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["지역별 편차 확대"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        original_should_attach = response_generator_module._should_attach_us_daily_macro_reference
        original_loader = response_generator_module._load_us_daily_macro_reference
        response_generator_module._should_attach_us_daily_macro_reference = lambda **kwargs: True
        response_generator_module._load_us_daily_macro_reference = lambda **kwargs: {
            "source": "ai_strategy_decisions",
            "schedule": "daily 08:30 KST",
            "decision_date": "2026-02-21 08:30:00",
            "summary": "미국 08:30 거시 브리핑 요약",
        }
        try:
            response = generate_graph_rag_answer(
                request=request,
                context_response=self._sample_context(),
                llm=llm,
            )
        finally:
            response_generator_module._should_attach_us_daily_macro_reference = original_should_attach
            response_generator_module._load_us_daily_macro_reference = original_loader

        self.assertIn("[USMacroReference0830]", llm.last_prompt)
        self.assertIn("daily 08:30 KST", llm.last_prompt)
        self.assertEqual(
            (response.context_meta.get("us_macro_reference_0830") or {}).get("source"),
            "ai_strategy_decisions",
        )
        self.assertTrue(
            any(citation.dataset_code == "AI_STRATEGY_DECISIONS" for citation in response.structured_citations)
        )

    def test_statement_filter_removes_unsupported_key_point(self):
        request = GraphRagAnswerRequest(
            question="최근 인플레이션 리스크는?",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "Inflation accelerated in January and remains elevated.",
              "uncertainty": "단기 데이터 중심이라 해석 한계",
              "key_points": ["Inflation accelerated in January", "외계행성 매크로 급등 시나리오"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        statement_filter = response.context_meta.get("statement_filter") or {}
        self.assertGreaterEqual(int(statement_filter.get("statement_removed") or 0), 1)

    def test_query_route_uses_explicit_question_id_priority(self):
        request = GraphRagAnswerRequest(
            question="일반 매크로 코멘트",
            question_id="Q5",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "FX volatility remains elevated.",
              "uncertainty": "근거 불충분",
              "key_points": ["Dollar strengthened amid rate repricing"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        route = response.context_meta.get("query_route") or {}
        self.assertEqual(route.get("selected_question_id"), "Q5")
        self.assertEqual(route.get("selected_type"), "fx_driver")
        self.assertEqual(route.get("confidence_level"), "High")

    def test_query_route_forces_us_single_stock_when_company_name_detected(self):
        request = GraphRagAnswerRequest(
            question="팔란티어 주가 어때?",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "개별 종목 변동성이 확대되고 있습니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["단기 변동성 확대"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        route = response.context_meta.get("query_route") or {}
        agents = route.get("agents") or []
        us_single_agent = next((agent for agent in agents if agent.get("agent") == "us_single_stock_agent"), {})
        self.assertEqual(route.get("selected_type"), "us_single_stock")
        self.assertIn("PLTR", us_single_agent.get("matched_symbols") or [])
        self.assertIn("PLTR", route.get("matched_symbols") or [])
        self.assertTrue(
            any("palantir" in str(item).lower() for item in (route.get("matched_companies") or []))
        )
        self.assertIsNone(route.get("selected_question_id"))
        self.assertIn("가격/변동률", llm.last_prompt)
        self.assertTrue(response.context_meta.get("us_single_stock_template_enforced"))

        section_labels = ["가격/변동률:", "실적:", "밸류:", "리스크:"]
        for section_label in section_labels:
            self.assertTrue(
                any(str(point).startswith(section_label) for point in response.answer.key_points),
                msg=f"missing section: {section_label}",
            )

    def test_query_route_forces_us_single_stock_when_ticker_detected(self):
        request = GraphRagAnswerRequest(
            question="PLTR 주가 어때?",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "개별 종목 변동성이 확대되고 있습니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["단기 변동성 확대"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        route = response.context_meta.get("query_route") or {}
        self.assertEqual(route.get("selected_type"), "us_single_stock")
        self.assertIn("PLTR", route.get("matched_symbols") or [])
        self.assertIn("US:PLTR", route.get("matched_security_ids") or [])
        self.assertTrue(
            any("palantir" in str(item).lower() for item in (route.get("matched_companies") or []))
        )

    def test_query_route_keeps_stock_focus_agent_with_explicit_question_id(self):
        request = GraphRagAnswerRequest(
            question="팔란티어 주가가 최근 하락한 이유를 알려줘.",
            question_id="Q1",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "하락 요인이 우세합니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["밸류 부담"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        route = response.context_meta.get("query_route") or {}
        agents = route.get("agents") or []
        us_single_agent = next((agent for agent in agents if agent.get("agent") == "us_single_stock_agent"), {})

        self.assertEqual(route.get("selected_type"), "explain_drop")
        self.assertEqual(route.get("selected_question_id"), "Q1")
        self.assertIn("PLTR", us_single_agent.get("matched_symbols") or [])

        context_request = request.to_context_request(route=route)
        self.assertIn("PLTR", context_request.focus_symbols)
        self.assertIn("Palantir Technologies", context_request.focus_companies)

    def test_us_single_stock_smoke_for_major_tickers(self):
        symbols = [("PLTR", "Palantir"), ("NVDA", "NVIDIA"), ("AAPL", "Apple")]
        for symbol, company in symbols:
            request = GraphRagAnswerRequest(
                question=f"{symbol} 주가 어때?",
                country_code="US",
                persist_macro_state=False,
                persist_analysis_run=False,
            )
            llm = _StubLLM(
                """
                {
                  "conclusion": "개별 종목 변동성이 확대되고 있습니다.",
                  "uncertainty": "근거 불충분",
                  "key_points": ["단기 변동성 확대"],
                  "impact_pathways": [],
                  "cited_evidence_ids": ["EVID_S1", "EVID_S2", "EVID_S3", "EVID_S4"]
                }
                """
            )
            response = generate_graph_rag_answer(
                request=request,
                context_response=self._sample_us_single_stock_context(symbol=symbol, company=company),
                llm=llm,
            )

            route = response.context_meta.get("query_route") or {}
            self.assertEqual(route.get("selected_type"), "us_single_stock")
            self.assertTrue(response.context_meta.get("us_single_stock_template_enforced"))
            self.assertEqual(response.context_meta.get("us_single_stock_missing_sections"), [])

            price_point = next(
                (str(point) for point in response.answer.key_points if str(point).startswith("가격/변동률:")),
                "",
            )
            self.assertIn("%", price_point)
            self.assertTrue(symbol in price_point or company in price_point)

    def test_us_single_stock_price_section_prefers_numeric_signal(self):
        symbol = "NVDA"
        company = "NVIDIA"
        context = self._sample_us_single_stock_context(symbol=symbol, company=company)
        context.evidences.insert(
            0,
            GraphEvidence(
                evidence_id="EVID_S0",
                text="Software stocks were mixed amid cautious sentiment.",
                doc_id="te:stock-0",
                doc_url="https://example.com/stock-0",
                doc_title="Market tone",
                published_at="2026-02-07T10:30:00",
                support_labels=["Claim"],
                event_id="EVT_STOCK_001",
            ),
        )
        request = GraphRagAnswerRequest(
            question=f"{symbol} 주가 어때?",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "개별 종목 변동성이 확대되고 있습니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["단기 변동성 확대"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_S0", "EVID_S1", "EVID_S2", "EVID_S3"]
            }
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=context,
            llm=llm,
        )
        price_point = next(
            (str(point) for point in response.answer.key_points if str(point).startswith("가격/변동률:")),
            "",
        )
        self.assertIn("7.2%", price_point)
        self.assertIn(symbol, price_point)

    def test_us_single_stock_strict_sections_fallback_without_focus_evidence(self):
        request = GraphRagAnswerRequest(
            question="PLTR 주가 전망 어때?",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "기술주 전반 변동성이 확대됐습니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["반도체 일부 종목이 강세", "연준 기대 변화"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )

        section_map = {
            "가격/변동률": next((str(point) for point in response.answer.key_points if str(point).startswith("가격/변동률:")), ""),
            "실적": next((str(point) for point in response.answer.key_points if str(point).startswith("실적:")), ""),
            "밸류": next((str(point) for point in response.answer.key_points if str(point).startswith("밸류:")), ""),
        }
        for section, point in section_map.items():
            self.assertIn("근거 불충분", point, msg=f"{section} section should fallback on missing focus evidence")

    def test_us_single_stock_citations_include_focus_evidence_even_when_llm_misses(self):
        request = GraphRagAnswerRequest(
            question="PLTR 주가 전망 어때?",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        context = self._sample_context()
        context.evidences.append(
            GraphEvidence(
                evidence_id="EVID_PLTR",
                text="Palantir fell 3.1% amid valuation concerns.",
                doc_id="te:pltr-1",
                doc_url="https://example.com/pltr-1",
                doc_title="Palantir drops",
                published_at="2026-02-07T12:00:00",
                support_labels=["Fact"],
                event_id="EVT_001",
            )
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "기술주 전반 변동성이 확대됐습니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["섹터 변동성 확대"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        response = generate_graph_rag_answer(
            request=request,
            context_response=context,
            llm=llm,
        )

        self.assertTrue(
            any("palantir" in str(citation.text or "").lower() for citation in response.citations),
            msg="focus evidence should be injected into citations for us_single_stock",
        )

    def test_us_single_stock_focus_injection_ignores_title_only_matches(self):
        request = GraphRagAnswerRequest(
            question="마이크로소프트 전망 어때?",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        context = self._sample_context_without_evidence()
        context.evidences = [
            GraphEvidence(
                evidence_id="EVID_T1",
                text="The S&P 500 fell 1.2% amid broad risk-off moves.",
                doc_id="te:msft-1",
                doc_url="https://example.com/msft-1",
                doc_title="US Stocks Lower, Microsoft Tumbles",
                published_at="2026-02-07T10:00:00",
                support_labels=["Fact"],
                event_id="EVT_001",
            ),
            GraphEvidence(
                evidence_id="EVID_T2",
                text="Nasdaq 100 dropped 2% as tech sold off.",
                doc_id="te:msft-2",
                doc_url="https://example.com/msft-2",
                doc_title="Wall Street Slips as Microsoft Shock Rekindles AI Valuation Fears",
                published_at="2026-02-07T10:10:00",
                support_labels=["Fact"],
                event_id="EVT_001",
            ),
            GraphEvidence(
                evidence_id="EVID_T3",
                text="Investors reassessed AI valuations across software names.",
                doc_id="te:msft-3",
                doc_url="https://example.com/msft-3",
                doc_title="US Stocks Lower, Microsoft Tumbles",
                published_at="2026-02-07T10:20:00",
                support_labels=["Claim"],
                event_id="EVT_001",
            ),
            GraphEvidence(
                evidence_id="EVID_MSFT_BODY",
                text="Microsoft slid 7% after reporting slower cloud growth and softer margin guidance.",
                doc_id="te:msft-4",
                doc_url="https://example.com/msft-4",
                doc_title="US Stocks Lower, Microsoft Tumbles",
                published_at="2026-02-07T10:30:00",
                support_labels=["Fact"],
                event_id="EVT_001",
            ),
        ]
        llm = _StubLLM(
            """
            {
              "conclusion": "기술주 전반 변동성이 확대됐습니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["섹터 변동성 확대"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_T1", "EVID_T2", "EVID_T3"]
            }
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=context,
            llm=llm,
        )

        self.assertTrue(
            any(citation.evidence_id == "EVID_MSFT_BODY" for citation in response.citations),
            msg="text-matched focus evidence should be injected even when title-only citations exist",
        )
        self.assertTrue(
            any("microsoft" in str(citation.text or "").lower() for citation in response.citations),
            msg="at least one citation text should include the stock keyword",
        )

    def test_us_single_stock_citations_include_latest_bearish_focus_signal(self):
        request = GraphRagAnswerRequest(
            question="PLTR 주가 전망 어때?",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        context = self._sample_context_without_evidence()
        context.evidences = [
            GraphEvidence(
                evidence_id="EVID_UP_1",
                text="Palantir rose 5.1% after earnings beat.",
                doc_id="te:pltr-up-1",
                doc_url="https://example.com/pltr-up-1",
                doc_title="Palantir rally",
                published_at="2026-02-03T10:00:00+00:00",
                support_labels=["Fact"],
                event_id="EVT_001",
            ),
            GraphEvidence(
                evidence_id="EVID_UP_2",
                text="Palantir jumped 4.0% on strong guidance.",
                doc_id="te:pltr-up-2",
                doc_url="https://example.com/pltr-up-2",
                doc_title="Palantir gains",
                published_at="2026-02-04T10:00:00+00:00",
                support_labels=["Fact"],
                event_id="EVT_001",
            ),
            GraphEvidence(
                evidence_id="EVID_UP_3",
                text="Palantir gained 3.2% in premarket.",
                doc_id="te:pltr-up-3",
                doc_url="https://example.com/pltr-up-3",
                doc_title="Palantir premarket",
                published_at="2026-02-05T10:00:00+00:00",
                support_labels=["Fact"],
                event_id="EVT_001",
            ),
            GraphEvidence(
                evidence_id="EVID_DOWN_NEW",
                text="Palantir fell 4.4% as AI valuation concerns deepened.",
                doc_id="te:pltr-down-new",
                doc_url="https://example.com/pltr-down-new",
                doc_title="Palantir drops",
                published_at="2026-02-13T10:00:00+00:00",
                support_labels=["Fact"],
                event_id="EVT_001",
            ),
        ]
        llm = _StubLLM(
            """
            {
              "conclusion": "실적 발표 이후 주가가 강세입니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["단기 변동성 확대"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_UP_1", "EVID_UP_2", "EVID_UP_3"]
            }
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=context,
            llm=llm,
        )

        self.assertTrue(
            any(citation.evidence_id == "EVID_DOWN_NEW" for citation in response.citations),
            msg="latest bearish focus evidence should be injected for us_single_stock",
        )

    def test_us_single_stock_trend_guard_adjusts_bullish_conclusion_on_recent_downtrend(self):
        request = GraphRagAnswerRequest(
            question="팔란티어 주가 전망 어때?",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        context = self._sample_context_without_evidence()
        context.evidences = [
            GraphEvidence(
                evidence_id="EVID_PLTR_UP_OLD",
                text="Palantir rose 6.0% right after earnings release.",
                doc_id="te:pltr-up-old",
                doc_url="https://example.com/pltr-up-old",
                doc_title="Palantir jumps",
                published_at="2026-02-03T10:00:00+00:00",
                support_labels=["Fact"],
                event_id="EVT_001",
            ),
            GraphEvidence(
                evidence_id="EVID_PLTR_DOWN_1",
                text="Palantir fell 3.3% as software names sold off.",
                doc_id="te:pltr-down-1",
                doc_url="https://example.com/pltr-down-1",
                doc_title="Palantir lower",
                published_at="2026-02-12T10:00:00+00:00",
                support_labels=["Fact"],
                event_id="EVT_001",
            ),
            GraphEvidence(
                evidence_id="EVID_PLTR_DOWN_2",
                text="Palantir slid 2.9% on renewed valuation pressure.",
                doc_id="te:pltr-down-2",
                doc_url="https://example.com/pltr-down-2",
                doc_title="Palantir slides",
                published_at="2026-02-13T10:00:00+00:00",
                support_labels=["Fact"],
                event_id="EVT_001",
            ),
        ]
        llm = _StubLLM(
            """
            {
              "conclusion": "팔란티어는 긍정적인 주가 흐름과 상승 전망을 보여주고 있습니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["실적 서프라이즈 이후 강세"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_PLTR_UP_OLD"]
            }
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=context,
            llm=llm,
        )

        self.assertIn("하락 신호", response.answer.conclusion)
        self.assertIn("하방 압력", response.answer.uncertainty)
        trend_guard = response.context_meta.get("us_single_stock_trend_guard") or {}
        self.assertTrue(trend_guard.get("adjusted"))
        self.assertEqual(trend_guard.get("trend_direction"), "down")

    def test_query_route_detects_compare_outlook_from_question(self):
        request = GraphRagAnswerRequest(
            question="스노우플레이크와 팔란티어 중 어떤 기업이 더 전망이 좋아?",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "Both companies face different risk/reward profiles.",
              "uncertainty": "근거 불충분",
              "key_points": ["Inflation accelerated in January", "Core CPI remained elevated"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        route = response.context_meta.get("query_route") or {}
        self.assertEqual(route.get("selected_type"), "compare_outlook")
        self.assertEqual(route.get("selected_question_id"), "Q2")

    def test_query_route_sets_parallel_flags_for_us_single_stock(self):
        request = GraphRagAnswerRequest(
            question="팔란티어 주가와 실적 전망 알려줘",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        route = response_generator_module._route_query_type_multi_agent(
            request,
            enable_llm_router=False,
        )

        self.assertEqual(route.get("selected_type"), "us_single_stock")
        self.assertTrue(route.get("sql_need"))
        self.assertTrue(route.get("graph_need"))
        self.assertEqual(route.get("tool_mode"), "parallel")
        self.assertIn("equity_analyst_agent", route.get("target_agents") or [])

    def test_query_route_sets_single_flags_for_macro_summary(self):
        request = GraphRagAnswerRequest(
            question="미국 거시 뉴스 흐름을 요약해줘",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        route = response_generator_module._route_query_type_multi_agent(
            request,
            enable_llm_router=False,
        )

        self.assertFalse(route.get("sql_need"))
        self.assertTrue(route.get("graph_need"))
        self.assertEqual(route.get("tool_mode"), "single")
        self.assertIn("macro_economy_agent", route.get("target_agents") or [])

    def test_query_route_sets_parallel_flags_for_indicator_lookup(self):
        request = GraphRagAnswerRequest(
            question="미국 CPI 최신값과 영향 경로 알려줘",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        route = response_generator_module._route_query_type_multi_agent(
            request,
            enable_llm_router=False,
        )

        self.assertTrue(route.get("sql_need"))
        self.assertTrue(route.get("graph_need"))
        self.assertEqual(route.get("tool_mode"), "parallel")
        self.assertIn("macro_economy_agent", route.get("target_agents") or [])

    def test_query_route_sets_direct_llm_flags_for_general_knowledge(self):
        request = GraphRagAnswerRequest(
            question="오늘 날씨 어때?",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        route = response_generator_module._route_query_type_multi_agent(
            request,
            enable_llm_router=False,
        )

        self.assertEqual(route.get("selected_type"), "general_knowledge")
        self.assertFalse(route.get("sql_need"))
        self.assertFalse(route.get("graph_need"))
        self.assertEqual(route.get("tool_mode"), "single")
        self.assertIn("general_knowledge_agent", route.get("target_agents") or [])

    def test_supervisor_execution_trace_parallel_for_us_single_stock(self):
        request = GraphRagAnswerRequest(
            question="팔란티어 주가와 실적 전망 알려줘",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "팔란티어는 단기 변동성이 높습니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["실적 이후 변동성 확대"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        execution = response.context_meta.get("supervisor_execution") or {}
        self.assertEqual(execution.get("execution_policy"), "conditional_parallel")
        self.assertEqual(execution.get("tool_mode"), "parallel")
        self.assertTrue(execution.get("sql_need"))
        self.assertTrue(execution.get("graph_need"))
        self.assertGreaterEqual(int(execution.get("selected_agent_count") or 0), 1)
        branch_plan = execution.get("branch_plan") or []
        sql_branch = next((item for item in branch_plan if item.get("branch") == "sql"), {})
        graph_branch = next((item for item in branch_plan if item.get("branch") == "graph"), {})
        self.assertTrue(sql_branch.get("enabled"))
        self.assertTrue(graph_branch.get("enabled"))
        self.assertEqual(sql_branch.get("dispatch_mode"), "parallel")
        self.assertEqual(graph_branch.get("dispatch_mode"), "parallel")
        execution_result = execution.get("execution_result") or {}
        self.assertEqual(execution_result.get("status"), "executed")
        self.assertEqual(execution_result.get("dispatch_mode"), "parallel")
        self.assertGreaterEqual(int(execution_result.get("invoked_agent_count") or 0), 2)

    def test_supervisor_execution_trace_single_for_macro_summary(self):
        request = GraphRagAnswerRequest(
            question="미국 거시 뉴스 흐름 요약해줘",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "거시 흐름은 혼조입니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["Core CPI remained elevated"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )

        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )
        execution = response.context_meta.get("supervisor_execution") or {}
        self.assertEqual(execution.get("tool_mode"), "single")
        self.assertFalse(execution.get("sql_need"))
        self.assertTrue(execution.get("graph_need"))
        branch_plan = execution.get("branch_plan") or []
        sql_branch = next((item for item in branch_plan if item.get("branch") == "sql"), {})
        graph_branch = next((item for item in branch_plan if item.get("branch") == "graph"), {})
        self.assertFalse(sql_branch.get("enabled"))
        self.assertEqual(sql_branch.get("dispatch_mode"), "skip")
        self.assertTrue(graph_branch.get("enabled"))
        self.assertEqual(graph_branch.get("dispatch_mode"), "single")
        execution_result = execution.get("execution_result") or {}
        self.assertEqual(execution_result.get("status"), "executed")
        self.assertEqual(execution_result.get("dispatch_mode"), "single")
        self.assertGreaterEqual(int(execution_result.get("invoked_agent_count") or 0), 1)

    def test_generate_answer_includes_structured_citations_when_sql_needed(self):
        request = GraphRagAnswerRequest(
            question="미국 CPI 최신값과 영향 알려줘",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "CPI 둔화 여부가 금리 기대에 영향을 주고 있습니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["Core CPI remained elevated"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=llm,
        )

        route = response.context_meta.get("query_route") or {}
        self.assertTrue(route.get("sql_need"))
        self.assertGreaterEqual(len(response.structured_citations), 1)
        self.assertGreaterEqual(int(response.context_meta.get("structured_citation_count") or 0), 1)
        first = response.structured_citations[0]
        self.assertTrue(first.dataset_code)
        self.assertEqual(first.source, "sql")
        self.assertTrue(first.query_fingerprint)

    def test_supervisor_single_mode_runs_companion_fallback_once(self):
        request = GraphRagAnswerRequest(
            question="미국 거시 뉴스 흐름 요약해줘",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        route_decision = {
            "selected_type": "general_macro",
            "sql_need": False,
            "graph_need": True,
            "tool_mode": "single",
            "target_agents": ["macro_economy_agent"],
            "agent_model_policy": {"macro_economy_agent": "gemini-3-flash-preview"},
        }
        supervisor_execution = response_generator_module._build_supervisor_execution_trace(route_decision)

        original_execute_agent = response_generator_module.execute_agent_stub

        def _fake_execute_agent(agent_name, *, branch, request, route_decision, context_meta):
            if branch == "graph":
                return {
                    "agent": agent_name,
                    "branch": branch,
                    "status": "degraded",
                    "needs_companion_branch": True,
                    "companion_branch": "sql",
                }
            if branch == "sql":
                return {
                    "agent": agent_name,
                    "branch": branch,
                    "status": "executed",
                    "needs_companion_branch": False,
                }
            return {
                "agent": agent_name,
                "branch": branch,
                "status": "executed",
            }

        response_generator_module.execute_agent_stub = _fake_execute_agent
        try:
            execution_result = response_generator_module._execute_supervisor_plan(
                request=request,
                route_decision=route_decision,
                supervisor_execution=supervisor_execution,
                context_meta={"counts": {"nodes": 1, "documents": 1}},
            )
        finally:
            response_generator_module.execute_agent_stub = original_execute_agent

        self.assertEqual(execution_result.get("status"), "executed")
        self.assertEqual(execution_result.get("dispatch_mode"), "single")
        self.assertTrue(execution_result.get("fallback_used"))
        self.assertEqual(execution_result.get("fallback_reason"), "graph_branch_requested_sql_companion")
        branch_results = execution_result.get("branch_results") or []
        sql_branch = next((item for item in branch_results if item.get("branch") == "sql"), {})
        graph_branch = next((item for item in branch_results if item.get("branch") == "graph"), {})
        self.assertTrue(sql_branch.get("enabled"))
        self.assertTrue(graph_branch.get("enabled"))
        self.assertEqual(sql_branch.get("dispatch_mode"), "single")
        self.assertEqual(graph_branch.get("dispatch_mode"), "single")
        self.assertGreaterEqual(len(sql_branch.get("agent_runs") or []), 1)

    def test_query_route_uses_gemini_25_flash_router_agent_when_provided(self):
        request = GraphRagAnswerRequest(
            question="최근 핵심 지표 업데이트 알려줘",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        answer_llm = _StubLLM(
            """
            {
              "conclusion": "Core indicators remain mixed.",
              "uncertainty": "근거 불충분",
              "key_points": ["Core CPI remained elevated"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )
        router_llm = _StubLLM(
            """
            {
              "query_type": "indicator_lookup",
              "confidence": 0.91,
              "reasoning": "indicator keyword detected",
              "question_id": null
            }
            """
        )
        response = generate_graph_rag_answer(
            request=request,
            context_response=self._sample_context(),
            llm=answer_llm,
            router_llm=router_llm,
        )
        route = response.context_meta.get("query_route") or {}
        agents = route.get("agents") or []
        llm_agent = next((agent for agent in agents if agent.get("agent") == "llm_router_agent"), {})
        self.assertEqual(llm_agent.get("model"), "gemini-2.5-flash")
        self.assertEqual(llm_agent.get("selected_type"), "indicator_lookup")
        model_policy = route.get("agent_model_policy") or {}
        self.assertEqual(model_policy.get("supervisor_agent"), "gemini-3-pro-preview")
        self.assertEqual(model_policy.get("ontology_master_agent"), "gemini-3-pro-preview")
        self.assertEqual(model_policy.get("macro_economy_agent"), "gemini-3-flash-preview")
        self.assertEqual(model_policy.get("equity_analyst_agent"), "gemini-3-flash-preview")
        self.assertEqual(model_policy.get("real_estate_agent"), "gemini-3-flash-preview")
        self.assertEqual(model_policy.get("router_intent_classifier"), "gemini-2.5-flash")
        self.assertEqual(model_policy.get("query_rewrite_utility"), "gemini-2.5-flash")
        self.assertEqual(model_policy.get("query_normalization_utility"), "gemini-2.5-flash")
        self.assertEqual(model_policy.get("citation_postprocess_utility"), "gemini-2.5-flash")

    def test_general_knowledge_route_skips_context_and_forces_flash_model(self):
        request = GraphRagAnswerRequest(
            question="오늘 날씨 어때?",
            model="gemini-3-pro-preview",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "실시간 날씨는 직접 확인이 필요하지만, 일반적으로 초봄에는 일교차가 큽니다.",
              "uncertainty": "실시간 데이터는 아닙니다.",
              "key_points": ["외출 전 기온 확인", "우산 여부 확인"]
            }
            """
        )

        original_build_context = response_generator_module.build_graph_rag_context

        def _should_not_build_context(*args, **kwargs):
            raise AssertionError("General knowledge route should not build graph context")

        response_generator_module.build_graph_rag_context = _should_not_build_context
        try:
            response = generate_graph_rag_answer(
                request=request,
                llm=llm,
            )
        finally:
            response_generator_module.build_graph_rag_context = original_build_context

        self.assertEqual(response.model, "gemini-3-flash-preview")
        self.assertEqual(response.context_meta.get("policy"), "general_knowledge_direct_llm")
        self.assertEqual(response.context_meta.get("used_evidence_count"), 0)
        self.assertEqual(response.used_evidence_count, 0)
        self.assertEqual(response.citations, [])

        route = response.context_meta.get("query_route") or {}
        self.assertEqual(route.get("selected_type"), "general_knowledge")

        execution = response.context_meta.get("supervisor_execution") or {}
        execution_result = execution.get("execution_result") or {}
        branch_results = execution_result.get("branch_results") or []
        llm_branch = next((item for item in branch_results if item.get("branch") == "llm_direct"), {})
        self.assertEqual(execution_result.get("status"), "executed")
        self.assertTrue(llm_branch.get("enabled"))
        self.assertGreaterEqual(len(llm_branch.get("agent_runs") or []), 1)

    def test_real_estate_answer_sanitizes_internal_tokens_and_enforces_trend(self):
        request = GraphRagAnswerRequest(
            question="한국 부동산 가격 전망 해줘",
            country_code="KR",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "법정동코드 48250 지역에서 EVT_8a5aad025471a4ca 영향이 있습니다.",
              "uncertainty": "제공된 데이터는 특정 시점 스냅샷이라 시계열 추세 확인에는 한계가 있습니다.",
              "key_points": [
                "실거래 현황: 48250 지역 거래가 유지됩니다.",
                "거시 리스크: EVT_8a5aad025471a4ca와 EV_1855be6d7dbe74c9 영향"
              ],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )

        original_execute_supervisor_plan = response_generator_module._execute_supervisor_plan

        def _stub_execute_supervisor_plan(**kwargs):
            return {
                "status": "executed",
                "branch_results": [
                    {
                        "branch": "sql",
                        "enabled": True,
                        "agent_runs": [
                            {
                                "agent": "real_estate_agent",
                                "branch": "sql",
                                "tool_probe": {
                                    "tool": "sql",
                                    "status": "ok",
                                    "reason": "sql_template_executed",
                                    "table": "kr_real_estate_monthly_summary",
                                    "template_id": "real_estate.sql.latest_monthly_summary.v1",
                                    "selected_columns": ["stat_ym", "lawd_cd", "avg_price", "tx_count"],
                                    "filters": {"region_code": "48250"},
                                    "row_count": 3,
                                    "rows": [
                                        {"stat_ym": "202601", "lawd_cd": "48250", "avg_price": 226000000, "tx_count": 275},
                                        {"stat_ym": "202512", "lawd_cd": "48250", "avg_price": 221000000, "tx_count": 261},
                                        {"stat_ym": "202511", "lawd_cd": "48250", "avg_price": 219000000, "tx_count": 254}
                                    ],
                                    "trend_analysis": {
                                        "status": "ok",
                                        "reason": "real_estate_trend_available",
                                        "scope_label": "경남 김해시",
                                        "months_available": 12,
                                        "earliest_month": "202502",
                                        "latest_month": "202601",
                                        "price_change_pct_vs_start": 3.71,
                                        "tx_change_pct_vs_start": 8.66,
                                        "latest_weighted_avg_price": 226000000,
                                        "latest_tx_count": 275,
                                        "rows": [
                                            {"stat_ym": "202601", "weighted_avg_price": 226000000, "tx_count": 275},
                                            {"stat_ym": "202512", "weighted_avg_price": 221000000, "tx_count": 261}
                                        ]
                                    }
                                }
                            }
                        ]
                    }
                ],
                "invoked_agent_count": 1
            }

        response_generator_module._execute_supervisor_plan = _stub_execute_supervisor_plan
        try:
            response = generate_graph_rag_answer(
                request=request,
                context_response=self._sample_context(),
                llm=llm,
            )
        finally:
            response_generator_module._execute_supervisor_plan = original_execute_supervisor_plan

        answer_blob = " ".join([response.answer.conclusion, response.answer.uncertainty, *response.answer.key_points])
        self.assertIn("경남 김해시", answer_blob)
        self.assertNotIn("48250", answer_blob)
        self.assertNotIn("EVT_", answer_blob)
        self.assertNotIn("EV_", answer_blob)
        self.assertNotIn("시계열 추세 확인에는 한계", answer_blob)
        self.assertTrue(any("시계열 추세(" in point for point in response.answer.key_points))
        trend_guard = response.context_meta.get("real_estate_trend_guard") or {}
        self.assertTrue(trend_guard.get("applied"))

    def test_generate_answer_applies_effective_request_from_utility_nodes(self):
        request = GraphRagAnswerRequest(
            question="팔란티어 주가 어때?",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "단기 변동성이 큽니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["실적 이후 변동성 확대"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )

        original_rewrite = response_generator_module._invoke_query_rewrite_utility
        original_normalization = response_generator_module._invoke_query_normalization_utility
        original_make_prompt = response_generator_module._make_prompt

        captured = {"request": None}

        def _stub_rewrite(**kwargs):
            return {
                "enabled": True,
                "status": "ok",
                "reason": "test_stub",
                "applied": True,
                "original_question": kwargs["request"].question,
                "rewritten_question": "미국 PLTR 주가 단기 흐름 요약해줘",
            }

        def _stub_normalization(**kwargs):
            req = kwargs["request"]
            return {
                "enabled": True,
                "status": "ok",
                "reason": "test_stub",
                "applied": True,
                "country_code": "US",
                "region_code": req.region_code,
                "property_type": req.property_type,
                "time_range": "90d",
            }

        def _stub_make_prompt(*, request, **kwargs):
            captured["request"] = request
            return original_make_prompt(request=request, **kwargs)

        response_generator_module._invoke_query_rewrite_utility = _stub_rewrite
        response_generator_module._invoke_query_normalization_utility = _stub_normalization
        response_generator_module._make_prompt = _stub_make_prompt
        try:
            response = generate_graph_rag_answer(
                request=request,
                context_response=self._sample_context(),
                llm=llm,
            )
        finally:
            response_generator_module._invoke_query_rewrite_utility = original_rewrite
            response_generator_module._invoke_query_normalization_utility = original_normalization
            response_generator_module._make_prompt = original_make_prompt

        effective = response.context_meta.get("effective_request") or {}
        self.assertEqual(effective.get("question"), "미국 PLTR 주가 단기 흐름 요약해줘")
        self.assertEqual(effective.get("time_range"), "90d")
        utility = response.context_meta.get("utility_execution") or {}
        self.assertEqual((utility.get("query_rewrite") or {}).get("status"), "ok")
        self.assertEqual((utility.get("query_normalization") or {}).get("status"), "ok")
        self.assertIsNotNone(captured.get("request"))
        self.assertEqual(captured["request"].question, "미국 PLTR 주가 단기 흐름 요약해줘")
        self.assertEqual(captured["request"].time_range, "90d")

    def test_generate_answer_applies_citation_postprocess_order(self):
        request = GraphRagAnswerRequest(
            question="미국 CPI 최신값과 영향 경로 알려줘",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "CPI 민감도가 높습니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["Core CPI remained elevated"],
              "impact_pathways": [],
              "cited_evidence_ids": ["EVID_1", "EVID_2", "EVID_3"]
            }
            """
        )

        original_postprocess = response_generator_module._invoke_citation_postprocess_utility

        def _stub_postprocess(**kwargs):
            return {
                "enabled": True,
                "status": "ok",
                "reason": "test_stub",
                "applied": True,
                "ordered_keys": ["EVID_3", "EVID_2", "EVID_1"],
            }

        response_generator_module._invoke_citation_postprocess_utility = _stub_postprocess
        try:
            response = generate_graph_rag_answer(
                request=request,
                context_response=self._sample_context(),
                llm=llm,
            )
        finally:
            response_generator_module._invoke_citation_postprocess_utility = original_postprocess

        ordered_ids = [citation.evidence_id for citation in response.citations]
        self.assertGreaterEqual(len(ordered_ids), 3)
        self.assertEqual(ordered_ids[:3], ["EVID_3", "EVID_2", "EVID_1"])
        utility = response.context_meta.get("utility_execution") or {}
        self.assertEqual((utility.get("citation_postprocess") or {}).get("status"), "ok")

    def test_generate_answer_merges_web_fallback_citations_without_tavily(self):
        request = GraphRagAnswerRequest(
            question="한국 부동산 가격 전망 해줘",
            country_code="KR",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        llm = _StubLLM(
            """
            {
              "conclusion": "시장 변동성이 높습니다.",
              "uncertainty": "근거 불충분",
              "key_points": ["추가 근거 필요"],
              "impact_pathways": [],
              "cited_evidence_ids": []
            }
            """
        )

        original_web_fallback = response_generator_module._collect_web_fallback_citations

        def _stub_web_fallback(**kwargs):
            return {
                "enabled": True,
                "status": "ok",
                "reason": "web_search_executed",
                "applied": True,
                "added_count": 1,
                "search_provider": "google_news_rss",
                "fallback_citations": [
                    response_generator_module.GraphRagCitation(
                        evidence_id="WEB_TEST_1",
                        doc_id="web:test1",
                        doc_url="https://news.google.com/test1",
                        doc_title="테스트 뉴스",
                        published_at="2026-02-21T00:00:00+00:00",
                        text="한국 부동산 거래량 관련 무료 검색 테스트 기사",
                        support_labels=["WebFallback"],
                        node_ids=["document:web:test1"],
                    )
                ],
            }

        response_generator_module._collect_web_fallback_citations = _stub_web_fallback
        try:
            response = generate_graph_rag_answer(
                request=request,
                context_response=self._sample_context_without_evidence(),
                llm=llm,
            )
        finally:
            response_generator_module._collect_web_fallback_citations = original_web_fallback

        self.assertTrue(any(citation.doc_id == "web:test1" for citation in response.citations))
        web_fallback = response.context_meta.get("web_fallback") or {}
        self.assertEqual(web_fallback.get("status"), "ok")
        self.assertTrue(web_fallback.get("applied"))
        self.assertEqual(web_fallback.get("search_provider"), "google_news_rss")


@unittest.skipUnless(_DB_READY, f"DB integration skipped: {_DB_READY_REASON}")
class TestPhaseDResponseGeneratorDBIntegration(unittest.TestCase):
    def test_sql_probe_macro_integration(self):
        probe = run_sql_probe("macro_economy_agent")
        self.assertEqual(probe.get("tool"), "sql")
        self.assertIn(probe.get("status"), {"ok", "degraded"})
        self.assertNotEqual(probe.get("status"), "error")

    def test_supervisor_single_execution_contains_sql_probe(self):
        request = GraphRagAnswerRequest(
            question="미국 거시 지표 요약해줘",
            country_code="US",
            persist_macro_state=False,
            persist_analysis_run=False,
        )
        route_decision = {
            "selected_type": "indicator_lookup",
            "sql_need": True,
            "graph_need": False,
            "tool_mode": "single",
            "target_agents": ["macro_economy_agent"],
            "agent_model_policy": {
                "macro_economy_agent": "gemini-3-flash-preview",
            },
        }
        execution_trace = response_generator_module._build_supervisor_execution_trace(route_decision)
        result = response_generator_module._execute_supervisor_plan(
            request=request,
            route_decision=route_decision,
            supervisor_execution=execution_trace,
            context_meta={"counts": {"nodes": 1, "documents": 1}},
        )

        self.assertEqual(result.get("status"), "executed")
        sql_branch = next((item for item in (result.get("branch_results") or []) if item.get("branch") == "sql"), {})
        self.assertTrue(sql_branch.get("enabled"))
        runs = sql_branch.get("agent_runs") or []
        self.assertGreaterEqual(len(runs), 1)
        sql_probe = runs[0].get("tool_probe") or {}
        self.assertEqual(sql_probe.get("tool"), "sql")
        self.assertIn(sql_probe.get("status"), {"ok", "degraded"})
        self.assertNotEqual(sql_probe.get("status"), "error")


if __name__ == "__main__":
    unittest.main()
