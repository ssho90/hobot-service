import unittest
import sys
import types

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


class _StubLLMResponse:
    def __init__(self, content):
        self.content = content


class _StubLLM:
    def __init__(self, content):
        self._content = content

    def invoke(self, prompt: str):
        self.last_prompt = prompt
        return _StubLLMResponse(self._content)


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

    def persist_run(self, **kwargs):
        self.called = True
        return {
            "run_id": "ar_test_run",
            "counts": {"evidences": 1},
        }


class TestPhaseDResponseGenerator(unittest.TestCase):
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
            ],
            suggested_queries=["최근 인플레이션 이벤트 Top 5는?"],
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
        self.assertEqual(len(response.citations), 1)
        self.assertEqual(response.citations[0].evidence_id, "EVID_1")
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

        self.assertEqual(response.model, "gemini-3-flash-preview")
        self.assertEqual(len(response.citations), 1)
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
        self.assertEqual(len(response.citations), 1)
        self.assertEqual(response.citations[0].evidence_id, "EVID_1")

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


if __name__ == "__main__":
    unittest.main()
