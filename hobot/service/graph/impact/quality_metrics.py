"""
Phase C-5: 데이터 품질/모니터링 지표 수집.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..neo4j_client import get_neo4j_client
from ..normalization.country_mapping import ISO_TO_NAME, normalize_country

logger = logging.getLogger(__name__)


class PhaseCQualityMetrics:
    """Phase C 운영 지표를 Neo4j에서 집계한다."""

    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    @staticmethod
    def _coerce_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return datetime.fromisoformat(stripped.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    return date.fromisoformat(stripped[:10])
                except ValueError:
                    return None
        return None

    @staticmethod
    def _expected_observation_count(frequency: str, start_date: date, end_date: date) -> int:
        if end_date < start_date:
            return 0
        total_days = (end_date - start_date).days + 1
        normalized = str(frequency or "daily").strip().lower()

        if normalized == "daily":
            return total_days
        if normalized == "weekly":
            return max((total_days + 6) // 7, 1)
        if normalized == "monthly":
            month_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
            return max(month_diff + 1, 1)
        if normalized == "quarterly":
            start_quarter = start_date.year * 4 + ((start_date.month - 1) // 3)
            end_quarter = end_date.year * 4 + ((end_date.month - 1) // 3)
            return max(end_quarter - start_quarter + 1, 1)
        return total_days

    @staticmethod
    def _build_country_backfill_rows(rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        """raw country 분포를 normalize 가능한 update rows로 변환한다."""
        mapped_rows: Dict[str, Dict[str, str]] = {}
        unmapped_rows: List[Dict[str, Any]] = []

        for row in rows:
            raw_country = str(row.get("country_raw") or "").strip()
            if not raw_country:
                continue
            country_key = raw_country.lower()
            country_code = normalize_country(raw_country)
            count = int(row.get("count") or 0)
            if not country_code:
                unmapped_rows.append({"country_raw": raw_country, "count": count})
                continue
            mapped_rows[country_key] = {
                "country_key": country_key,
                "country_code": country_code,
            }

        return list(mapped_rows.values()), unmapped_rows

    def _missing_country_code_counts(self) -> Dict[str, int]:
        rows = self.neo4j_client.run_read(
            """
            // phase_c_country_backfill_missing_counts
            CALL () {
                MATCH (d:Document)
                WHERE coalesce(trim(toString(d.country_code)), "") = ""
                RETURN count(d) AS missing_documents
            }
            CALL () {
                MATCH (e:Event)
                WHERE coalesce(trim(toString(e.country_code)), "") = ""
                RETURN count(e) AS missing_events
            }
            CALL () {
                MATCH (c:GraphRagApiCall)
                WHERE coalesce(trim(toString(c.country_code)), "") = ""
                RETURN count(c) AS missing_calls
            }
            RETURN missing_documents, missing_events, missing_calls
            """
        )
        if not rows:
            return {"missing_documents": 0, "missing_events": 0, "missing_calls": 0}

        row = rows[0]
        return {
            "missing_documents": int(row.get("missing_documents") or 0),
            "missing_events": int(row.get("missing_events") or 0),
            "missing_calls": int(row.get("missing_calls") or 0),
        }

    def backfill_country_codes(self, sample_limit: int = 500) -> Dict[str, Any]:
        """
        country -> country_code 보정 백필.
        - Document/Event/GraphRagApiCall의 self country 기반 보정
        - Event는 연결된 Document의 country_code로 2차 보정
        """
        limit = max(1, int(sample_limit))
        before = self._missing_country_code_counts()

        document_raw_rows = self.neo4j_client.run_read(
            """
            // phase_c_country_backfill_document_missing_raw
            MATCH (d:Document)
            WHERE coalesce(trim(toString(d.country_code)), "") = ""
              AND coalesce(trim(toString(d.country)), "") <> ""
            RETURN d.country AS country_raw, count(*) AS count
            ORDER BY count DESC
            LIMIT $sample_limit
            """,
            {"sample_limit": limit},
        )
        document_updates, document_unmapped = self._build_country_backfill_rows(document_raw_rows)

        event_raw_rows = self.neo4j_client.run_read(
            """
            // phase_c_country_backfill_event_missing_raw
            MATCH (e:Event)
            WHERE coalesce(trim(toString(e.country_code)), "") = ""
              AND coalesce(trim(toString(e.country)), "") <> ""
            RETURN e.country AS country_raw, count(*) AS count
            ORDER BY count DESC
            LIMIT $sample_limit
            """,
            {"sample_limit": limit},
        )
        event_updates, event_unmapped = self._build_country_backfill_rows(event_raw_rows)

        call_raw_rows = self.neo4j_client.run_read(
            """
            // phase_c_country_backfill_call_missing_raw
            MATCH (c:GraphRagApiCall)
            WHERE coalesce(trim(toString(c.country_code)), "") = ""
              AND coalesce(trim(toString(c.country)), "") <> ""
            RETURN c.country AS country_raw, count(*) AS count
            ORDER BY count DESC
            LIMIT $sample_limit
            """,
            {"sample_limit": limit},
        )
        call_updates, call_unmapped = self._build_country_backfill_rows(call_raw_rows)

        document_update_result: Dict[str, Any] = {"skipped": True}
        if document_updates:
            document_update_result = self.neo4j_client.run_write(
                """
                // phase_c_country_backfill_document_apply
                UNWIND $rows AS row
                MATCH (d:Document)
                WHERE coalesce(trim(toString(d.country_code)), "") = ""
                  AND toLower(trim(coalesce(toString(d.country), ""))) = row.country_key
                SET d.country_code = row.country_code,
                    d.updated_at = datetime()
                """,
                {"rows": document_updates},
            )

        event_update_result: Dict[str, Any] = {"skipped": True}
        if event_updates:
            event_update_result = self.neo4j_client.run_write(
                """
                // phase_c_country_backfill_event_apply
                UNWIND $rows AS row
                MATCH (e:Event)
                WHERE coalesce(trim(toString(e.country_code)), "") = ""
                  AND toLower(trim(coalesce(toString(e.country), ""))) = row.country_key
                SET e.country_code = row.country_code,
                    e.updated_at = datetime()
                """,
                {"rows": event_updates},
            )

        call_update_result: Dict[str, Any] = {"skipped": True}
        if call_updates:
            call_update_result = self.neo4j_client.run_write(
                """
                // phase_c_country_backfill_call_apply
                UNWIND $rows AS row
                MATCH (c:GraphRagApiCall)
                WHERE coalesce(trim(toString(c.country_code)), "") = ""
                  AND toLower(trim(coalesce(toString(c.country), ""))) = row.country_key
                SET c.country_code = row.country_code
                """,
                {"rows": call_updates},
            )

        infer_event_from_document_result = self.neo4j_client.run_write(
            """
            // phase_c_country_backfill_event_infer_from_document
            MATCH (e:Event)
            WHERE coalesce(trim(toString(e.country_code)), "") = ""
            MATCH (e)<-[:MENTIONS]-(d:Document)
            WHERE coalesce(trim(toString(d.country_code)), "") <> ""
            WITH e, d.country_code AS country_code, coalesce(d.country, "") AS country, count(*) AS hits
            ORDER BY hits DESC, country_code
            WITH e, collect({country_code: country_code, country: country})[0] AS best
            SET e.country_code = best.country_code,
                e.country = CASE
                    WHEN coalesce(trim(toString(e.country)), "") = "" THEN best.country
                    ELSE e.country
                END,
                e.updated_at = datetime()
            """
        )

        after = self._missing_country_code_counts()
        repaired = {
            "documents": max(before["missing_documents"] - after["missing_documents"], 0),
            "events": max(before["missing_events"] - after["missing_events"], 0),
            "calls": max(before["missing_calls"] - after["missing_calls"], 0),
        }

        result = {
            "sample_limit": limit,
            "before": before,
            "after": after,
            "repaired": repaired,
            "document": {
                "mapped_raw_values": len(document_updates),
                "unmapped_raw_values": len(document_unmapped),
                "write_result": document_update_result,
            },
            "event_from_self": {
                "mapped_raw_values": len(event_updates),
                "unmapped_raw_values": len(event_unmapped),
                "write_result": event_update_result,
            },
            "event_from_document": {
                "write_result": infer_event_from_document_result,
            },
            "graphrag_call": {
                "mapped_raw_values": len(call_updates),
                "unmapped_raw_values": len(call_unmapped),
                "write_result": call_update_result,
            },
            "unmapped_samples": {
                "document": document_unmapped[:20],
                "event": event_unmapped[:20],
                "graphrag_call": call_unmapped[:20],
            },
        }
        logger.info("[PhaseCMetrics][CountryBackfill] %s", result)
        return result

    def affects_observed_delta_coverage(self) -> Dict[str, Any]:
        query = """
        MATCH ()-[r:AFFECTS]->()
        WITH count(r) AS total,
             count(CASE WHEN r.observed_delta IS NOT NULL THEN 1 END) AS filled
        RETURN total, filled,
               CASE WHEN total = 0 THEN 0.0 ELSE toFloat(filled) / total * 100 END AS pct
        """
        rows = self.neo4j_client.run_read(query)
        return rows[0] if rows else {"total": 0, "filled": 0, "pct": 0.0}

    def affects_weight_distribution(self) -> List[Dict[str, Any]]:
        query = """
        MATCH ()-[r:AFFECTS]->()
        WHERE r.weight IS NOT NULL
        RETURN r.window_days AS window_days,
               count(r) AS count,
               min(r.weight) AS min_weight,
               percentileCont(r.weight, 0.5) AS median_weight,
               max(r.weight) AS max_weight
        ORDER BY window_days
        """
        return self.neo4j_client.run_read(query)

    def observed_delta_spikes(self, threshold: float = 2.0, limit: int = 20) -> List[Dict[str, Any]]:
        query = """
        MATCH (ev:Event)-[r:AFFECTS]->(i:EconomicIndicator)
        WHERE r.observed_delta IS NOT NULL
          AND abs(r.observed_delta) >= $threshold
        RETURN ev.event_id AS event_id,
               i.indicator_code AS indicator_code,
               r.observed_delta AS observed_delta,
               r.window_days AS window_days,
               r.as_of AS as_of
        ORDER BY abs(r.observed_delta) DESC
        LIMIT $limit
        """
        return self.neo4j_client.run_read(query, {"threshold": threshold, "limit": limit})

    def indicator_freshness_report(
        self,
        as_of_date: Optional[date] = None,
        indicator_codes: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        as_of_value = as_of_date or date.today()
        codes = [str(code).strip().upper() for code in (indicator_codes or []) if str(code).strip()]
        rows = self.neo4j_client.run_read(
            """
            // phase_c_indicator_freshness_report
            MATCH (i:EconomicIndicator)
            WHERE size($indicator_codes) = 0 OR i.indicator_code IN $indicator_codes
            OPTIONAL MATCH (i)-[:HAS_OBSERVATION]->(o:IndicatorObservation)
            RETURN i.indicator_code AS indicator_code,
                   coalesce(i.frequency, "daily") AS frequency,
                   max(o.obs_date) AS latest_obs_date,
                   max(coalesce(o.as_of_date, o.obs_date)) AS latest_as_of_date,
                   max(o.published_at) AS latest_published_at,
                   count(o) AS total_observations
            ORDER BY indicator_code
            """,
            {"indicator_codes": codes},
        )

        freshness_sla = {
            "daily": 3,
            "weekly": 10,
            "monthly": 40,
            "quarterly": 120,
        }

        report_rows: List[Dict[str, Any]] = []
        stale_indicators: List[Dict[str, Any]] = []

        for row in rows:
            indicator_code = str(row.get("indicator_code") or "").strip()
            frequency = str(row.get("frequency") or "daily").strip().lower()
            latest_obs_date = self._coerce_date(row.get("latest_obs_date"))
            latest_as_of_date = self._coerce_date(row.get("latest_as_of_date"))

            obs_lag_days = (
                max((as_of_value - latest_obs_date).days, 0) if latest_obs_date else None
            )
            as_of_lag_days = (
                max((as_of_value - latest_as_of_date).days, 0) if latest_as_of_date else None
            )

            row_item = {
                "indicator_code": indicator_code,
                "frequency": frequency,
                "latest_obs_date": latest_obs_date.isoformat() if latest_obs_date else None,
                "latest_as_of_date": latest_as_of_date.isoformat() if latest_as_of_date else None,
                "latest_published_at": str(row.get("latest_published_at")) if row.get("latest_published_at") else None,
                "total_observations": int(row.get("total_observations") or 0),
                "obs_lag_days": obs_lag_days,
                "as_of_lag_days": as_of_lag_days,
            }
            report_rows.append(row_item)

            lag = obs_lag_days if obs_lag_days is not None else 10**9
            if lag > freshness_sla.get(frequency, 7):
                stale_indicators.append(
                    {
                        "indicator_code": indicator_code,
                        "frequency": frequency,
                        "obs_lag_days": obs_lag_days,
                    }
                )

        return {
            "as_of_date": as_of_value.isoformat(),
            "rows": report_rows,
            "stale_count": len(stale_indicators),
            "stale_indicators": stale_indicators,
        }

    def indicator_missing_rate_report(
        self,
        window_days: int = 30,
        as_of_date: Optional[date] = None,
        indicator_codes: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        effective_window = max(int(window_days), 1)
        as_of_value = as_of_date or date.today()
        start_date = as_of_value - timedelta(days=effective_window - 1)
        codes = [str(code).strip().upper() for code in (indicator_codes or []) if str(code).strip()]

        rows = self.neo4j_client.run_read(
            """
            // phase_c_indicator_missing_rate_report
            MATCH (i:EconomicIndicator)
            WHERE size($indicator_codes) = 0 OR i.indicator_code IN $indicator_codes
            OPTIONAL MATCH (i)-[:HAS_OBSERVATION]->(o:IndicatorObservation)
            WHERE o.obs_date >= date($start_date)
              AND o.obs_date <= date($as_of_date)
              AND coalesce(o.effective_date, o.obs_date) <= date($as_of_date)
              AND date(coalesce(o.published_at, datetime(toString(o.obs_date) + "T00:00:00"))) <= date($as_of_date)
              AND coalesce(o.as_of_date, o.obs_date) <= date($as_of_date)
            RETURN i.indicator_code AS indicator_code,
                   coalesce(i.frequency, "daily") AS frequency,
                   collect(DISTINCT o.obs_date) AS observed_dates
            ORDER BY indicator_code
            """,
            {
                "indicator_codes": codes,
                "start_date": start_date.isoformat(),
                "as_of_date": as_of_value.isoformat(),
            },
        )

        report_rows: List[Dict[str, Any]] = []
        for row in rows:
            frequency = str(row.get("frequency") or "daily").strip().lower()
            observed_dates = [d for d in (row.get("observed_dates") or []) if d is not None]
            observed_count = len(observed_dates)
            expected_count = self._expected_observation_count(frequency, start_date=start_date, end_date=as_of_value)
            missing_count = max(expected_count - observed_count, 0)
            missing_rate_pct = round((missing_count / expected_count) * 100, 4) if expected_count else 0.0

            report_rows.append(
                {
                    "indicator_code": str(row.get("indicator_code") or "").strip(),
                    "frequency": frequency,
                    "expected_count": expected_count,
                    "observed_count": observed_count,
                    "missing_count": missing_count,
                    "missing_rate_pct": missing_rate_pct,
                }
            )

        report_rows.sort(key=lambda item: item["missing_rate_pct"], reverse=True)
        avg_missing_rate = (
            round(sum(item["missing_rate_pct"] for item in report_rows) / len(report_rows), 4)
            if report_rows
            else 0.0
        )

        return {
            "as_of_date": as_of_value.isoformat(),
            "window_days": effective_window,
            "avg_missing_rate_pct": avg_missing_rate,
            "rows": report_rows,
            "top_missing_indicators": report_rows[:10],
        }

    def country_mapping_quality_report(
        self,
        allowed_country_codes: Sequence[str] = ("US", "KR"),
        sample_limit: int = 20,
    ) -> Dict[str, Any]:
        normalized_allowed = sorted(
            {str(code or "").strip().upper() for code in allowed_country_codes if str(code or "").strip()}
        )
        rows = self.neo4j_client.run_read(
            """
            // phase_c_country_quality_rows
            CALL () {
                MATCH (d:Document)
                RETURN "Document" AS node_type, d.country AS country, d.country_code AS country_code
                UNION ALL
                MATCH (e:Event)
                RETURN "Event" AS node_type, e.country AS country, e.country_code AS country_code
            }
            WITH node_type,
                 trim(coalesce(toString(country), "")) AS country,
                 trim(toUpper(coalesce(toString(country_code), ""))) AS country_code
            RETURN node_type, country, country_code, count(*) AS count
            ORDER BY node_type, country_code, country
            """,
        )

        missing_samples = self.neo4j_client.run_read(
            """
            // phase_c_country_quality_missing_samples
            CALL () {
                MATCH (d:Document)
                WHERE coalesce(trim(toString(d.country_code)), "") = ""
                  AND coalesce(trim(toString(d.country)), "") <> ""
                RETURN "Document" AS node_type, d.country AS country_raw, count(*) AS count
                UNION ALL
                MATCH (e:Event)
                WHERE coalesce(trim(toString(e.country_code)), "") = ""
                  AND coalesce(trim(toString(e.country)), "") <> ""
                RETURN "Event" AS node_type, e.country AS country_raw, count(*) AS count
            }
            RETURN node_type, country_raw, count
            ORDER BY count DESC
            LIMIT $sample_limit
            """,
            {"sample_limit": int(sample_limit)},
        )

        summary: Dict[str, Any] = {
            "allowed_country_codes": normalized_allowed,
            "total_nodes": 0,
            "ok": 0,
            "missing_country_code": 0,
            "out_of_scope_country_code": 0,
            "country_mismatch": 0,
            "by_node_type": {},
            "top_missing_country_raw_values": missing_samples,
        }

        for row in rows:
            node_type = str(row.get("node_type") or "Unknown")
            raw_country = str(row.get("country") or "").strip()
            country_code = str(row.get("country_code") or "").strip().upper()
            count = int(row.get("count") or 0)
            normalized_from_country = normalize_country(raw_country) if raw_country else None
            canonical_country_name = ISO_TO_NAME.get(country_code, country_code)

            if not country_code:
                quality_status = "missing_country_code"
            elif country_code not in normalized_allowed:
                quality_status = "out_of_scope_country_code"
            elif (
                raw_country
                and raw_country.upper() != country_code
                and raw_country.lower() != canonical_country_name.lower()
                and normalized_from_country != country_code
            ):
                quality_status = "country_mismatch"
            else:
                quality_status = "ok"

            node_bucket = summary["by_node_type"].setdefault(
                node_type,
                {
                    "total": 0,
                    "ok": 0,
                    "missing_country_code": 0,
                    "out_of_scope_country_code": 0,
                    "country_mismatch": 0,
                },
            )
            node_bucket["total"] += count
            node_bucket[quality_status] = node_bucket.get(quality_status, 0) + count

            summary["total_nodes"] += count
            if quality_status in summary:
                summary[quality_status] += count
            else:
                summary[quality_status] = summary.get(quality_status, 0) + count

        total_nodes = summary.get("total_nodes") or 0
        if total_nodes:
            summary["mapping_accuracy_pct"] = round(summary.get("ok", 0) / total_nodes * 100, 4)
            summary["missing_rate_pct"] = round(summary.get("missing_country_code", 0) / total_nodes * 100, 4)
        else:
            summary["mapping_accuracy_pct"] = 0.0
            summary["missing_rate_pct"] = 0.0

        return summary

    def persist_weekly_country_quality_snapshot(
        self,
        snapshot_date: Optional[date] = None,
        allowed_country_codes: Sequence[str] = ("US", "KR"),
    ) -> Dict[str, Any]:
        target_date = snapshot_date or date.today()
        report = self.country_mapping_quality_report(allowed_country_codes=allowed_country_codes)

        write_result = self.neo4j_client.run_write(
            """
            // phase_c_country_quality_snapshot
            MERGE (s:CountryMappingQualitySnapshot {snapshot_date: date($snapshot_date), scope_key: $scope_key})
            SET s.allowed_country_codes = $allowed_country_codes,
                s.total_nodes = $total_nodes,
                s.ok = $ok,
                s.missing_country_code = $missing_country_code,
                s.out_of_scope_country_code = $out_of_scope_country_code,
                s.country_mismatch = $country_mismatch,
                s.mapping_accuracy_pct = $mapping_accuracy_pct,
                s.missing_rate_pct = $missing_rate_pct,
                s.report_json = $report_json,
                s.updated_at = datetime()
            """,
            {
                "snapshot_date": target_date.isoformat(),
                "scope_key": "|".join(report.get("allowed_country_codes", [])),
                "allowed_country_codes": report.get("allowed_country_codes", []),
                "total_nodes": int(report.get("total_nodes", 0)),
                "ok": int(report.get("ok", 0)),
                "missing_country_code": int(report.get("missing_country_code", 0)),
                "out_of_scope_country_code": int(report.get("out_of_scope_country_code", 0)),
                "country_mismatch": int(report.get("country_mismatch", 0)),
                "mapping_accuracy_pct": float(report.get("mapping_accuracy_pct", 0.0)),
                "missing_rate_pct": float(report.get("missing_rate_pct", 0.0)),
                "report_json": json.dumps(report, ensure_ascii=False),
            },
        )

        return {
            "snapshot_date": target_date.isoformat(),
            "report": report,
            "write_result": write_result,
        }

    def collect_summary(
        self,
        as_of_date: Optional[date] = None,
        indicator_window_days: int = 30,
    ) -> Dict[str, Any]:
        coverage = self.affects_observed_delta_coverage()
        distribution = self.affects_weight_distribution()
        spikes = self.observed_delta_spikes()
        country_quality = self.country_mapping_quality_report()
        indicator_freshness = self.indicator_freshness_report(as_of_date=as_of_date)
        indicator_missing_rate = self.indicator_missing_rate_report(
            window_days=indicator_window_days,
            as_of_date=as_of_date,
        )
        summary = {
            "coverage": coverage,
            "weight_distribution": distribution,
            "spikes": spikes,
            "country_quality": country_quality,
            "indicator_freshness": indicator_freshness,
            "indicator_missing_rate": indicator_missing_rate,
        }
        logger.info("[PhaseCMetrics] %s", summary)
        return summary
