import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class ScenarioFixtureLoader:
    FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"

    @classmethod
    def list_available_fixtures(cls) -> List[str]:
        if not cls.FIXTURE_ROOT.exists():
            return []
        return sorted(path.stem for path in cls.FIXTURE_ROOT.glob("*.json"))

    @classmethod
    def load_fixture(cls, fixture_name: str) -> Dict[str, Any]:
        fixture_path = cls.FIXTURE_ROOT / f"{fixture_name}.json"
        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture not found: {fixture_name}")
        with fixture_path.open("r", encoding="utf-8") as fixture_file:
            payload = json.load(fixture_file)
        if not isinstance(payload, dict):
            raise ValueError("Fixture payload must be a JSON object")
        return payload

    @classmethod
    def resolve_fixture_for_business_date(
        cls,
        fixture_payload: Optional[Any],
        business_date: Any,
    ) -> Optional[Dict[str, Any]]:
        if not fixture_payload:
            return None

        payload = fixture_payload
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            return None

        resolved_date = cls._coerce_date(business_date).isoformat()
        by_business_date = payload.get("by_business_date")
        if isinstance(by_business_date, dict):
            candidate = by_business_date.get(resolved_date) or by_business_date.get("*")
            if isinstance(candidate, dict):
                return candidate

        default_payload = payload.get("default")
        if isinstance(default_payload, dict):
            return default_payload

        return payload

    @staticmethod
    def _coerce_date(value: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value).date()
        raise ValueError(f"Unsupported business_date type: {type(value)}")
