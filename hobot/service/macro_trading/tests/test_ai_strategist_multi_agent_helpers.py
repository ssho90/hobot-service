import unittest
from unittest.mock import patch
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

# `service.macro_trading.__init__`는 런타임 의존성이 커서 테스트에서 직접 import를 피한다.
_AI_STRATEGIST_PATH = Path(__file__).resolve().parents[1] / "ai_strategist.py"
_AI_STRATEGIST_SPEC = spec_from_file_location("ai_strategist_under_test", _AI_STRATEGIST_PATH)
assert _AI_STRATEGIST_SPEC and _AI_STRATEGIST_SPEC.loader
ai_strategist = module_from_spec(_AI_STRATEGIST_SPEC)
_AI_STRATEGIST_SPEC.loader.exec_module(ai_strategist)


class TestAIStrategistMultiAgentHelpers(unittest.TestCase):
    def test_normalize_sub_mp_payload_from_sub_allocations(self):
        raw_payload = {
            "sub_allocations": {
                "Stocks": {"id": "Eq-A", "reason": "stocks"},
                "Bonds": {"id": "Bnd-N", "reason": "bonds"},
                "Alternatives": {"id": "Alt-C", "reason": "alts"},
                "Cash": {"id": "Cash-N", "reason": "cash"},
            },
            "final_construction_summary": "summary",
        }

        normalized = ai_strategist._normalize_sub_mp_payload(raw_payload)
        self.assertEqual(normalized["stocks_sub_mp"], "Eq-A")
        self.assertEqual(normalized["bonds_sub_mp"], "Bnd-N")
        self.assertEqual(normalized["alternatives_sub_mp"], "Alt-C")
        self.assertEqual(normalized["cash_sub_mp"], "Cash-N")
        self.assertEqual(normalized["reasoning"], "summary")
        self.assertEqual(normalized["reasoning_by_asset"]["stocks"], "stocks")
        self.assertEqual(normalized["reasoning_by_asset"]["bonds"], "bonds")
        self.assertEqual(normalized["reasoning_by_asset"]["alternatives"], "alts")
        self.assertEqual(normalized["reasoning_by_asset"]["cash"], "cash")

    def test_normalize_sub_mp_payload_supports_legacy_keys(self):
        raw_payload = {
            "stocks": "Eq-N",
            "bonds": "Bnd-L",
            "alternatives": "Alt-I",
            "cash": "Cash-N",
            "reasoning": "legacy shape",
        }

        normalized = ai_strategist._normalize_sub_mp_payload(raw_payload)
        self.assertEqual(normalized["stocks_sub_mp"], "Eq-N")
        self.assertEqual(normalized["bonds_sub_mp"], "Bnd-L")
        self.assertEqual(normalized["alternatives_sub_mp"], "Alt-I")
        self.assertEqual(normalized["cash_sub_mp"], "Cash-N")
        self.assertEqual(normalized["reasoning"], "legacy shape")

    def test_merge_sub_mp_payloads_uses_supervisor_then_sub_allocator(self):
        supervisor_payload = {
            "sub_mp": {
                "stocks_sub_mp": "Eq-D",
                "bonds_sub_mp": None,
                "alternatives_sub_mp": "Alt-I",
                "cash_sub_mp": None,
                "reasoning": "supervisor reason",
                "reasoning_by_asset": {"stocks": "supervisor stocks"},
            }
        }
        sub_allocator_payload = {
            "sub_allocations": {
                "Stocks": {"id": "Eq-A", "reason": "stocks"},
                "Bonds": {"id": "Bnd-L", "reason": "bonds"},
                "Alternatives": {"id": "Alt-C", "reason": "alts"},
                "Cash": {"id": "Cash-N", "reason": "cash"},
            },
            "final_construction_summary": "allocator reason",
        }

        merged = ai_strategist._merge_sub_mp_payloads(supervisor_payload, sub_allocator_payload)
        self.assertEqual(merged["stocks_sub_mp"], "Eq-D")
        self.assertEqual(merged["bonds_sub_mp"], "Bnd-L")
        self.assertEqual(merged["alternatives_sub_mp"], "Alt-I")
        self.assertEqual(merged["cash_sub_mp"], "Cash-N")
        self.assertIn("Supervisor:", merged["reasoning"])
        self.assertIn("Sub-Allocator:", merged["reasoning"])
        self.assertEqual(merged["reasoning_by_asset"]["stocks"], "supervisor stocks")
        self.assertEqual(merged["reasoning_by_asset"]["bonds"], "bonds")
        self.assertEqual(merged["reasoning_by_asset"]["alternatives"], "alts")
        self.assertEqual(merged["reasoning_by_asset"]["cash"], "cash")

    @patch.object(ai_strategist, "_get_sub_model_candidates_by_group")
    @patch.object(ai_strategist, "get_model_portfolio_allocation")
    def test_validate_sub_mp_selection_filters_invalid_values(
        self,
        mock_get_model_portfolio_allocation,
        mock_get_sub_model_candidates_by_group,
    ):
        mock_get_model_portfolio_allocation.return_value = {
            "Stocks": 20.0,
            "Bonds": 50.0,
            "Alternatives": 20.0,
            "Cash": 10.0,
        }
        mock_get_sub_model_candidates_by_group.return_value = {
            "stocks": ["Eq-A", "Eq-N", "Eq-D"],
            "bonds": ["Bnd-L", "Bnd-N", "Bnd-S"],
            "alternatives": ["Alt-I", "Alt-C"],
            "cash": ["Cash-N"],
        }
        raw_payload = {
            "stocks_sub_mp": "Eq-INVALID",
            "bonds_sub_mp": "Bnd-N",
            "alternatives_sub_mp": "Alt-INVALID",
            "cash_sub_mp": "Cash-INVALID",
            "reasoning": "test",
        }

        validated = ai_strategist._validate_sub_mp_selection("MP-4", raw_payload)
        self.assertIsNone(validated["stocks_sub_mp"])
        self.assertEqual(validated["bonds_sub_mp"], "Bnd-N")
        self.assertIsNone(validated["alternatives_sub_mp"])
        self.assertEqual(validated["cash_sub_mp"], "Cash-N")
        self.assertEqual(validated["reasoning"], "test")
        self.assertIn("stocks", validated["reasoning_by_asset"])
        self.assertIn("alternatives", validated["reasoning_by_asset"])

    @patch.object(ai_strategist, "_get_sub_model_candidates_by_group")
    @patch.object(ai_strategist, "get_model_portfolio_allocation")
    def test_validate_sub_mp_selection_forces_null_when_allocation_zero(
        self,
        mock_get_model_portfolio_allocation,
        mock_get_sub_model_candidates_by_group,
    ):
        mock_get_model_portfolio_allocation.return_value = {
            "Stocks": 0.0,
            "Bonds": 60.0,
            "Alternatives": 0.0,
            "Cash": 40.0,
        }
        mock_get_sub_model_candidates_by_group.return_value = {
            "stocks": ["Eq-A", "Eq-N", "Eq-D"],
            "bonds": ["Bnd-L", "Bnd-N", "Bnd-S"],
            "alternatives": ["Alt-I", "Alt-C"],
            "cash": ["Cash-N"],
        }

        raw_payload = {
            "stocks_sub_mp": "Eq-A",
            "bonds_sub_mp": "Bnd-L",
            "alternatives_sub_mp": "Alt-I",
            "cash_sub_mp": "Cash-N",
            "reasoning": "test",
        }

        validated = ai_strategist._validate_sub_mp_selection("MP-5", raw_payload)
        self.assertIsNone(validated["stocks_sub_mp"])
        self.assertEqual(validated["bonds_sub_mp"], "Bnd-L")
        self.assertIsNone(validated["alternatives_sub_mp"])
        self.assertEqual(validated["cash_sub_mp"], "Cash-N")
        self.assertIn("Stocks 비중 0%로 선택 없음", validated["reasoning_by_asset"]["stocks"])
        self.assertIn("Alternatives 비중 0%로 선택 없음", validated["reasoning_by_asset"]["alternatives"])

    @patch.object(ai_strategist, "get_model_portfolios")
    def test_apply_mp_quality_gate_uses_previous_on_low_confidence(self, mock_get_model_portfolios):
        mock_get_model_portfolios.return_value = {"MP-1": {}, "MP-2": {}}
        mp_decision_data = {
            "mp_id": "MP-2",
            "confidence": 0.42,
            "reasoning": "supervisor result",
        }

        gated = ai_strategist._apply_mp_quality_gate(
            mp_decision_data=mp_decision_data,
            previous_mp_id="MP-1",
            risk_report={"recommended_action": "SHIFT_NEUTRAL"},
            constraints={"min_confidence_to_switch_mp": 0.6},
        )

        self.assertEqual(gated["mp_id"], "MP-1")
        self.assertIn("Quality Gate 적용", gated["reasoning"])

    @patch.object(ai_strategist, "_get_sub_model_candidates_by_group")
    @patch.object(ai_strategist, "get_model_portfolios")
    def test_build_objective_constraints_from_config_contract(
        self,
        mock_get_model_portfolios,
        mock_get_sub_model_candidates_by_group,
    ):
        mock_get_model_portfolios.return_value = {"MP-2": {}, "MP-1": {}}
        mock_get_sub_model_candidates_by_group.return_value = {
            "stocks": ["Eq-A"],
            "bonds": ["Bnd-L"],
            "alternatives": ["Alt-I"],
            "cash": ["Cash-N"],
        }
        fake_config = SimpleNamespace(
            rebalancing=SimpleNamespace(threshold=5.0, cash_reserve_ratio=0.12, min_trade_amount=50000),
            safety=SimpleNamespace(
                max_daily_loss_percent=2.5,
                max_monthly_loss_percent=7.0,
                manual_approval_required=True,
                dry_run_mode=False,
            ),
            llm=SimpleNamespace(model="gemini-3-pro-preview", temperature=0.2),
        )

        objective, constraints = ai_strategist._build_objective_constraints_from_config(
            fake_config,
            previous_decision={"decision_date": "2026-02-08"},
        )

        self.assertEqual(objective["rebalance_threshold_percent"], 5.0)
        self.assertEqual(objective["cash_reserve_ratio"], 0.12)
        self.assertEqual(constraints["allowed_mp_ids"], ["MP-1", "MP-2"])
        self.assertEqual(constraints["allowed_sub_mp_ids"]["stocks"], ["Eq-A"])
        self.assertEqual(constraints["previous_decision_date"], "2026-02-08")

    @patch.object(ai_strategist, "create_asset_sub_allocator_agent_prompt")
    @patch.object(ai_strategist, "_invoke_llm_json")
    @patch.object(ai_strategist, "get_model_portfolio_allocation")
    @patch.object(ai_strategist, "_get_sub_model_candidates_by_group")
    def test_invoke_parallel_sub_allocator_agents_with_fallback(
        self,
        mock_get_sub_model_candidates_by_group,
        mock_get_model_portfolio_allocation,
        mock_invoke_llm_json,
        mock_create_asset_sub_allocator_agent_prompt,
    ):
        mock_get_model_portfolio_allocation.return_value = {
            "Stocks": 60.0,
            "Bonds": 20.0,
            "Alternatives": 10.0,
            "Cash": 10.0,
        }
        mock_get_sub_model_candidates_by_group.return_value = {
            "stocks": ["Eq-A", "Eq-N", "Eq-D"],
            "bonds": ["Bnd-L", "Bnd-N", "Bnd-S"],
            "alternatives": ["Alt-I", "Alt-C"],
            "cash": ["Cash-N"],
        }
        mock_create_asset_sub_allocator_agent_prompt.return_value = "test prompt"

        def _invoke_side_effect(_prompt, _model_name, service_name, _max_retries):
            if service_name.endswith("_stocks"):
                return {"selected_sub_mp": "Eq-D", "reason": "stocks reason"}
            if service_name.endswith("_bonds"):
                return {"selected_sub_mp": "Bnd-INVALID", "reason": "bonds reason"}
            if service_name.endswith("_alternatives"):
                return {"selected_sub_mp": "Alt-C", "reason": "alts reason"}
            raise AssertionError(f"unexpected service_name: {service_name}")

        mock_invoke_llm_json.side_effect = _invoke_side_effect

        result = ai_strategist._invoke_parallel_sub_allocator_agents(
            mp_id="MP-2",
            quant_report={},
            narrative_report={},
            risk_report={},
            previous_sub_mp={"bonds": "Bnd-N", "cash": "Cash-N"},
            model_name="gemini-3-pro-preview",
            objective={},
            constraints={},
        )

        self.assertEqual(result["selection_mode"], "parallel_asset_agents_v2")
        self.assertEqual(result["sub_allocations"]["Stocks"]["id"], "Eq-D")
        self.assertEqual(result["sub_allocations"]["Bonds"]["id"], "Bnd-N")
        self.assertEqual(result["sub_allocations"]["Alternatives"]["id"], "Alt-C")
        self.assertEqual(result["sub_allocations"]["Cash"]["id"], "Cash-N")
        self.assertEqual(result["reasoning_by_asset"]["stocks"], "stocks reason")
        self.assertIn("bonds", result["reasoning_by_asset"])

    @patch.object(ai_strategist, "get_sub_mp_etf_details")
    @patch.object(ai_strategist, "get_sub_model_portfolios")
    def test_get_sub_mp_details_contains_reasoning_metadata(
        self,
        mock_get_sub_model_portfolios,
        mock_get_sub_mp_etf_details,
    ):
        mock_get_sub_model_portfolios.return_value = {
            "Eq-A": {"name": "Equity Aggressive", "description": "desc", "updated_at": "2026-02-09"},
            "Bnd-L": {"name": "Bond Long", "description": "desc", "updated_at": "2026-02-09"},
            "Alt-I": {"name": "Alt Inflation", "description": "desc", "updated_at": "2026-02-09"},
            "Cash-N": {"name": "Cash Neutral", "description": "desc", "updated_at": "2026-02-09"},
        }

        def _etf_side_effect(sub_mp_id):
            return [{"ticker": f"{sub_mp_id}_ETF", "weight": 1.0}]

        mock_get_sub_mp_etf_details.side_effect = _etf_side_effect

        details = ai_strategist.get_sub_mp_details(
            {
                "stocks": "Eq-A",
                "bonds": "Bnd-L",
                "alternatives": "Alt-I",
                "cash": "Cash-N",
                "reasoning": "overall reasoning",
                "reasoning_by_asset": {
                    "stocks": "stocks reasoning",
                    "bonds": "bonds reasoning",
                },
            }
        )

        self.assertEqual(details["stocks"]["sub_mp_id"], "Eq-A")
        self.assertEqual(details["stocks"]["reasoning"], "stocks reasoning")
        self.assertEqual(details["bonds"]["reasoning"], "bonds reasoning")
        self.assertEqual(details["reasoning"], "overall reasoning")
        self.assertEqual(details["reasoning_by_asset"]["stocks"], "stocks reasoning")


if __name__ == "__main__":
    unittest.main()
