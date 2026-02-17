"""
KR real-estate monthly summary loader.

RDB(kr_real_estate_monthly_summary) -> Neo4j 동기화:
- RealEstateRegion
- RealEstateMonthlySummary
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

from .neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)


class RealEstateSummaryLoader:
    """MySQL monthly summary -> Neo4j 동기화"""

    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    def _get_mysql_connection(self):
        from service.database.db import get_db_connection

        return get_db_connection()

    def ensure_graph_schema(self) -> Dict[str, Any]:
        """
        부동산 집계 노드 제약/인덱스 생성.
        """
        statements = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:RealEstateRegion) REQUIRE (r.country_code, r.lawd_cd) IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (m:RealEstateMonthlySummary) REQUIRE m.summary_key IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (m:RealEstateMonthlySummary) ON (m.stat_ym)",
            "CREATE INDEX IF NOT EXISTS FOR (m:RealEstateMonthlySummary) ON (m.lawd_cd)",
        ]
        summary = {
            "constraints_added": 0,
            "indexes_added": 0,
            "nodes_created": 0,
            "relationships_created": 0,
            "properties_set": 0,
        }
        for statement in statements:
            result = self.neo4j_client.run_write(statement)
            summary["constraints_added"] += int(result.get("constraints_added", 0))
            summary["indexes_added"] += int(result.get("indexes_added", 0))
            summary["nodes_created"] += int(result.get("nodes_created", 0))
            summary["relationships_created"] += int(result.get("relationships_created", 0))
            summary["properties_set"] += int(result.get("properties_set", 0))
        return summary

    @staticmethod
    def _to_first_day_iso(stat_ym: str) -> str:
        ym = str(stat_ym).strip()
        if len(ym) != 6 or not ym.isdigit():
            raise ValueError(f"Invalid stat_ym: {stat_ym}")
        return f"{ym[:4]}-{ym[4:6]}-01"

    def fetch_from_mysql(
        self,
        *,
        start_ym: str,
        end_ym: str,
        property_type: str = "apartment",
        transaction_type: str = "sale",
        lawd_codes: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        where_lawd = ""
        params: List[Any] = [start_ym, end_ym, property_type, transaction_type]
        if lawd_codes:
            cleaned = [str(code).strip() for code in lawd_codes if str(code).strip()]
            if cleaned:
                placeholders = ", ".join(["%s"] * len(cleaned))
                where_lawd = f" AND lawd_cd IN ({placeholders}) "
                params.extend(cleaned)

        query = f"""
            SELECT
              stat_ym,
              lawd_cd,
              country_code,
              property_type,
              transaction_type,
              tx_count,
              avg_price,
              avg_price_per_m2,
              avg_area_m2,
              min_price,
              max_price,
              total_price,
              as_of_date
            FROM kr_real_estate_monthly_summary
            WHERE stat_ym >= %s
              AND stat_ym <= %s
              AND property_type = %s
              AND transaction_type = %s
              {where_lawd}
            ORDER BY stat_ym, lawd_cd
        """

        with self._get_mysql_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

        mapped: List[Dict[str, Any]] = []
        for row in rows:
            stat_ym = str(row["stat_ym"])
            obs_date = self._to_first_day_iso(stat_ym)
            mapped.append(
                {
                    "summary_key": f"{row['country_code']}:{row['lawd_cd']}:{stat_ym}:{row['property_type']}:{row['transaction_type']}",
                    "stat_ym": stat_ym,
                    "obs_date": obs_date,
                    "lawd_cd": str(row["lawd_cd"]),
                    "country_code": str(row["country_code"]),
                    "property_type": str(row["property_type"]),
                    "transaction_type": str(row["transaction_type"]),
                    "tx_count": int(row["tx_count"] or 0),
                    "avg_price": float(row["avg_price"]) if row["avg_price"] is not None else None,
                    "avg_price_per_m2": float(row["avg_price_per_m2"]) if row["avg_price_per_m2"] is not None else None,
                    "avg_area_m2": float(row["avg_area_m2"]) if row["avg_area_m2"] is not None else None,
                    "min_price": int(row["min_price"]) if row["min_price"] is not None else None,
                    "max_price": int(row["max_price"]) if row["max_price"] is not None else None,
                    "total_price": int(row["total_price"]) if row["total_price"] is not None else None,
                    "as_of_date": (
                        row["as_of_date"].isoformat()
                        if hasattr(row["as_of_date"], "isoformat")
                        else str(row["as_of_date"])
                    ),
                }
            )
        return mapped

    def upsert_to_neo4j(
        self,
        rows: List[Dict[str, Any]],
        *,
        batch_size: int = 500,
    ) -> Dict[str, int]:
        if not rows:
            return {
                "rows": 0,
                "nodes_created": 0,
                "relationships_created": 0,
                "properties_set": 0,
            }

        query = """
        UNWIND $rows AS row
        MERGE (r:RealEstateRegion {country_code: row.country_code, lawd_cd: row.lawd_cd})
          ON CREATE SET r.created_at = datetime()
        SET r.updated_at = datetime()

        MERGE (m:RealEstateMonthlySummary {summary_key: row.summary_key})
          ON CREATE SET m.created_at = datetime()
        SET m.stat_ym = row.stat_ym,
            m.obs_date = date(row.obs_date),
            m.country_code = row.country_code,
            m.lawd_cd = row.lawd_cd,
            m.property_type = row.property_type,
            m.transaction_type = row.transaction_type,
            m.tx_count = toInteger(row.tx_count),
            m.avg_price = toFloat(row.avg_price),
            m.avg_price_per_m2 = toFloat(row.avg_price_per_m2),
            m.avg_area_m2 = toFloat(row.avg_area_m2),
            m.min_price = toInteger(row.min_price),
            m.max_price = toInteger(row.max_price),
            m.total_price = toInteger(row.total_price),
            m.as_of_date = date(row.as_of_date),
            m.source = 'kr_real_estate_monthly_summary',
            m.updated_at = datetime()

        MERGE (r)-[:HAS_MONTHLY_SUMMARY]->(m)
        """

        total_nodes_created = 0
        total_relationships_created = 0
        total_properties_set = 0

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            result = self.neo4j_client.run_write(query, {"rows": batch})
            total_nodes_created += int(result.get("nodes_created", 0))
            total_relationships_created += int(result.get("relationships_created", 0))
            total_properties_set += int(result.get("properties_set", 0))
            logger.info(
                "[RealEstateSummaryLoader] batch=%s size=%s result=%s",
                i // batch_size + 1,
                len(batch),
                result,
            )

        return {
            "rows": len(rows),
            "nodes_created": total_nodes_created,
            "relationships_created": total_relationships_created,
            "properties_set": total_properties_set,
        }

    def sync_monthly_summary(
        self,
        *,
        start_ym: str,
        end_ym: str,
        property_type: str = "apartment",
        transaction_type: str = "sale",
        lawd_codes: Optional[Iterable[str]] = None,
        batch_size: int = 500,
        ensure_schema: bool = True,
    ) -> Dict[str, Any]:
        if ensure_schema:
            schema_result = self.ensure_graph_schema()
        else:
            schema_result = {}

        rows = self.fetch_from_mysql(
            start_ym=start_ym,
            end_ym=end_ym,
            property_type=property_type,
            transaction_type=transaction_type,
            lawd_codes=lawd_codes,
        )
        if not rows:
            return {
                "status": "no_data",
                "rows_fetched": 0,
                "schema_result": schema_result,
            }

        upsert_result = self.upsert_to_neo4j(rows, batch_size=batch_size)
        return {
            "status": "success",
            "rows_fetched": len(rows),
            "schema_result": schema_result,
            "upsert_result": upsert_result,
        }

    def verify_sync(self, *, start_ym: Optional[str] = None, end_ym: Optional[str] = None) -> Dict[str, Any]:
        filters = []
        params: Dict[str, Any] = {}
        if start_ym:
            filters.append("m.stat_ym >= $start_ym")
            params["start_ym"] = start_ym
        if end_ym:
            filters.append("m.stat_ym <= $end_ym")
            params["end_ym"] = end_ym

        where_clause = ""
        if filters:
            where_clause = "WHERE " + " AND ".join(filters)

        query = f"""
        MATCH (m:RealEstateMonthlySummary)
        {where_clause}
        RETURN
          count(m) AS summary_nodes,
          count(DISTINCT m.stat_ym) AS month_count,
          count(DISTINCT m.lawd_cd) AS region_count,
          min(m.stat_ym) AS min_ym,
          max(m.stat_ym) AS max_ym
        """
        rows = self.neo4j_client.run_read(query, params)
        return rows[0] if rows else {}


def sync_kr_real_estate_monthly_summary(
    *,
    start_ym: str,
    end_ym: str,
    property_type: str = "apartment",
    transaction_type: str = "sale",
) -> Dict[str, Any]:
    loader = RealEstateSummaryLoader()
    result = loader.sync_monthly_summary(
        start_ym=start_ym,
        end_ym=end_ym,
        property_type=property_type,
        transaction_type=transaction_type,
    )
    verification = loader.verify_sync(start_ym=start_ym, end_ym=end_ym)
    return {
        "sync_result": result,
        "verification": verification,
    }
