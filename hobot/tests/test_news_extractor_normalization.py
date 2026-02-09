import sys
import types
import unittest

if "google" not in sys.modules:
    google_module = types.ModuleType("google")
    genai_module = types.ModuleType("google.genai")
    genai_types_module = types.ModuleType("google.genai.types")

    class _DummyClient:
        def __init__(self, *args, **kwargs):
            pass

    genai_module.Client = _DummyClient
    google_module.genai = genai_module

    sys.modules["google"] = google_module
    sys.modules["google.genai"] = genai_module
    sys.modules["google.genai.types"] = genai_types_module

from service.graph.news_extractor import (
    LLMEvidence,
    LLMEvent,
    LLMExtractionResponse,
    LLMFact,
    LLMLink,
    LLMClaim,
    NewsExtractor,
)


class TestNewsExtractorNormalization(unittest.TestCase):
    def _build_extractor(self):
        extractor = NewsExtractor.__new__(NewsExtractor)
        extractor.model_name = "test-model"
        extractor.extractor_version = "test"
        return extractor

    def test_convert_llm_response_normalizes_invalid_literals(self):
        extractor = self._build_extractor()
        llm_response = LLMExtractionResponse(
            events=[
                LLMEvent(
                    event_name="CPI update",
                    event_type="economic_data",
                    impact_level="critical",
                    description="Inflation release",
                )
            ],
            facts=[
                LLMFact(
                    fact_text="Headline CPI slowed.",
                    fact_type="economic_data",
                    entities_mentioned=["Fed"],
                    evidence=LLMEvidence(
                        evidence_text="short",
                        confidence="strong",
                    ),
                )
            ],
            claims=[
                LLMClaim(
                    claim_text="Market remains optimistic.",
                    claim_type="market_view",
                    author="analyst",
                    sentiment="bullish",
                    evidence=LLMEvidence(
                        evidence_text="tiny",
                        confidence="certain",
                    ),
                )
            ],
            links=[
                LLMLink(
                    source="CPI update",
                    target="inflation",
                    relationship="correlated_with",
                    evidence=LLMEvidence(
                        evidence_text="small",
                        confidence="weak",
                    ),
                )
            ],
        )

        result = extractor._convert_llm_response(
            doc_id="te:test",
            llm_response=llm_response,
            article_text="Inflation release showed easing pressure on prices.",
        )

        self.assertEqual(result.events[0].event_type, "economic_release")
        self.assertEqual(result.events[0].impact_level, "high")
        self.assertEqual(result.facts[0].fact_type, "data_release")
        self.assertEqual(result.claims[0].claim_type, "opinion")
        self.assertEqual(result.claims[0].sentiment.value, "positive")
        self.assertEqual(result.links[0].link_type.value, "CORRELATES")

        self.assertEqual(result.facts[0].evidences[0].confidence.value, "high")
        self.assertEqual(result.claims[0].evidences[0].confidence.value, "high")
        self.assertEqual(result.links[0].evidence.confidence.value, "low")
        self.assertGreaterEqual(len(result.facts[0].evidences[0].evidence_text), 10)

    def test_convert_llm_response_fallbacks_to_other_or_default(self):
        extractor = self._build_extractor()
        llm_response = LLMExtractionResponse(
            events=[LLMEvent(event_name="Unknown signal", event_type="strange_type", impact_level="tiny")],
            facts=[
                LLMFact(
                    fact_text="Unknown fact type sample.",
                    fact_type="totally_unknown",
                    entities_mentioned=[],
                    evidence=LLMEvidence(evidence_text="", confidence="unknown"),
                )
            ],
            claims=[
                LLMClaim(
                    claim_text="Unknown claim type sample.",
                    claim_type="random",
                    sentiment="mixed",
                    evidence=LLMEvidence(evidence_text="", confidence="unknown"),
                )
            ],
            links=[
                LLMLink(
                    source="Unknown signal",
                    target="rates",
                    relationship="irrelevant",
                    evidence=LLMEvidence(evidence_text="", confidence="unknown"),
                )
            ],
        )

        result = extractor._convert_llm_response(
            doc_id="te:test2",
            llm_response=llm_response,
            article_text="Fallback text for normalization.",
        )

        self.assertEqual(result.events[0].event_type, "other")
        self.assertEqual(result.events[0].impact_level, "medium")
        self.assertEqual(result.facts[0].fact_type, "other")
        self.assertEqual(result.claims[0].claim_type, "other")
        self.assertEqual(result.claims[0].sentiment.value, "neutral")
        self.assertEqual(result.links[0].link_type.value, "MENTIONS")
        self.assertEqual(result.facts[0].evidences[0].confidence.value, "medium")
        self.assertGreaterEqual(len(result.facts[0].evidences[0].evidence_text), 10)


if __name__ == "__main__":
    unittest.main()
