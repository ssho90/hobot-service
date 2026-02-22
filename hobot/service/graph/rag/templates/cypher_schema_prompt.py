"""Ontology Text2Cypher schema prompt contract with direction guards."""

from __future__ import annotations

import re
from typing import Any, Dict, List

PROMPT_VERSION = "ontology.cypher.schema_prompt.v1"

SCHEMA_DIRECTION_LINES: List[str] = [
    "(Company)-[:HAS_DAILY_BAR]->(EquityDailyBar)",
    "(Company)-[:HAS_EARNINGS_EVENT]->(EarningsEvent)",
    "(Company)-[:IN_UNIVERSE]->(EquityUniverseSnapshot)",
    "(Event)-[:ABOUT_THEME]->(MacroTheme)",
    "(Event)-[:AFFECTS]->(EconomicIndicator)",
    "(Story)-[:CONTAINS]->(Document)",
    "(Evidence)-[:SUPPORTS]->(Claim)",
]

CYPHER_DIRECTION_FEW_SHOTS: List[Dict[str, str]] = [
    {
        "question": "AAPL 일봉 개수 알려줘",
        "bad_cypher": "MATCH (c:Company)<-[:HAS_DAILY_BAR]-(b:EquityDailyBar) WHERE c.security_id='US:AAPL' RETURN count(b)",
        "good_cypher": "MATCH (c:Company)-[:HAS_DAILY_BAR]->(b:EquityDailyBar) WHERE c.security_id='US:AAPL' RETURN count(b)",
        "why": "HAS_DAILY_BAR는 Company -> EquityDailyBar 방향이다.",
    },
    {
        "question": "이벤트가 어떤 테마와 연결됐는지",
        "bad_cypher": "MATCH (t:MacroTheme)-[:ABOUT_THEME]->(e:Event) RETURN t,e LIMIT 20",
        "good_cypher": "MATCH (e:Event)-[:ABOUT_THEME]->(t:MacroTheme) RETURN e,t LIMIT 20",
        "why": "ABOUT_THEME는 Event -> MacroTheme 방향이다.",
    },
]

_DIRECTION_VALIDATION_RULES: List[Dict[str, str]] = [
    {
        "rule_id": "company_has_daily_bar",
        "relation": "HAS_DAILY_BAR",
        "reverse_pattern": r"\([^)]*:Company[^)]*\)\s*<-\s*\[:HAS_DAILY_BAR\]\s*-\s*\([^)]*:EquityDailyBar[^)]*\)",
        "expected_direction": "(Company)-[:HAS_DAILY_BAR]->(EquityDailyBar)",
    },
    {
        "rule_id": "company_has_earnings_event",
        "relation": "HAS_EARNINGS_EVENT",
        "reverse_pattern": r"\([^)]*:Company[^)]*\)\s*<-\s*\[:HAS_EARNINGS_EVENT\]\s*-\s*\([^)]*:EarningsEvent[^)]*\)",
        "expected_direction": "(Company)-[:HAS_EARNINGS_EVENT]->(EarningsEvent)",
    },
    {
        "rule_id": "event_about_theme",
        "relation": "ABOUT_THEME",
        "reverse_pattern": r"\([^)]*:MacroTheme[^)]*\)\s*-\s*\[:ABOUT_THEME\]\s*->\s*\([^)]*:Event[^)]*\)",
        "expected_direction": "(Event)-[:ABOUT_THEME]->(MacroTheme)",
    },
]


def _render_few_shots() -> str:
    rows: List[str] = []
    for idx, item in enumerate(CYPHER_DIRECTION_FEW_SHOTS, start=1):
        rows.append(
            "\n".join(
                [
                    f"Example {idx}",
                    f"- Question: {item.get('question')}",
                    f"- Wrong: {item.get('bad_cypher')}",
                    f"- Correct: {item.get('good_cypher')}",
                    f"- Rule: {item.get('why')}",
                ]
            )
        )
    return "\n\n".join(rows)


def get_schema_string_with_direction() -> str:
    return "\n".join(SCHEMA_DIRECTION_LINES)


def get_direction_few_shots() -> List[Dict[str, str]]:
    return [dict(item) for item in CYPHER_DIRECTION_FEW_SHOTS]


def build_ontology_cypher_prompt_contract(question: str = "") -> Dict[str, Any]:
    schema_string = get_schema_string_with_direction()
    few_shots = get_direction_few_shots()
    rendered_few_shots = _render_few_shots()
    prompt = "\n".join(
        [
            "You are a Cypher generation assistant for ontology graph queries.",
            "Always obey relationship direction exactly as provided below.",
            "",
            "[Schema with Direction]",
            schema_string,
            "",
            "[Direction Few-shot]",
            rendered_few_shots,
            "",
            "[Generation Rules]",
            "1) Never reverse relationship direction.",
            "2) Prefer explicit labels for both nodes.",
            "3) If uncertain, return a conservative MATCH with LIMIT 20.",
            "",
            f"[User Question]\n{str(question or '').strip()}",
        ]
    )
    return {
        "prompt_version": PROMPT_VERSION,
        "schema_string": schema_string,
        "few_shots": few_shots,
        "system_prompt": prompt,
    }


def validate_cypher_direction(query: str) -> Dict[str, Any]:
    normalized = re.sub(r"\s+", " ", str(query or "")).strip()
    if not normalized:
        return {
            "is_valid": True,
            "checked_rule_count": len(_DIRECTION_VALIDATION_RULES),
            "violations": [],
        }

    violations: List[Dict[str, str]] = []
    for rule in _DIRECTION_VALIDATION_RULES:
        pattern = rule.get("reverse_pattern") or ""
        if not pattern:
            continue
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            violations.append(
                {
                    "rule_id": str(rule.get("rule_id") or ""),
                    "relation": str(rule.get("relation") or ""),
                    "expected_direction": str(rule.get("expected_direction") or ""),
                }
            )

    return {
        "is_valid": len(violations) == 0,
        "checked_rule_count": len(_DIRECTION_VALIDATION_RULES),
        "violations": violations,
    }


__all__ = [
    "PROMPT_VERSION",
    "build_ontology_cypher_prompt_contract",
    "get_direction_few_shots",
    "get_schema_string_with_direction",
    "validate_cypher_direction",
]
