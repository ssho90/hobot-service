"""
KR real-estate collector and canonical schema normalizer.

Phase 2 (P4):
- region_code/property_type/transaction_type canonicalization
- transaction rows persisted into dedicated table
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from service.database.db import get_db_connection

logger = logging.getLogger(__name__)


PROPERTY_TYPE_ALIASES = {
    "APT": "apartment",
    "아파트": "apartment",
    "APARTMENT": "apartment",
    "연립다세대": "multi_family",
    "다세대": "multi_family",
    "연립": "multi_family",
    "MULTI_FAMILY": "multi_family",
    "오피스텔": "officetel",
    "OFFICETEL": "officetel",
    "단독다가구": "single_family",
    "단독주택": "single_family",
    "SINGLE_FAMILY": "single_family",
}

TRANSACTION_TYPE_ALIASES = {
    "매매": "sale",
    "SALE": "sale",
    "전세": "jeonse",
    "JEONSE": "jeonse",
    "월세": "monthly_rent",
    "MONTHLY_RENT": "monthly_rent",
    "전월세": "rent",
    "임대": "rent",
    "RENT": "rent",
}


SEOUL_ALL_LAWD_CODES = (
    "11110", "11140", "11170", "11200", "11215",
    "11230", "11260", "11290", "11305", "11320",
    "11350", "11380", "11410", "11440", "11470",
    "11500", "11530", "11545", "11560", "11590",
    "11620", "11650", "11680", "11710", "11740",
)

GYEONGGI_ALL_LAWD_CODES = (
    "41111", "41113", "41115", "41117",
    "41131", "41133", "41135",
    "41150", "41171", "41173", "41190", "41210", "41220", "41250",
    "41271", "41273", "41281", "41285", "41287",
    "41290", "41310", "41360", "41370", "41390",
    "41410", "41430", "41450", "41460", "41463", "41465", "41480",
    "41500", "41550", "41570", "41590",
    "41610", "41630", "41650", "41670",
    "41800", "41820", "41830",
)

LOCAL_MAJOR_CITY_LAWD_CODES = (
    # 6대 광역시 + 세종
    "26110", "26140", "26170", "26200", "26230", "26260", "26290", "26320", "26350",
    "26380", "26410", "26440", "26470", "26500", "26530", "26710",
    "27110", "27140", "27170", "27200", "27230", "27260", "27290", "27710", "27720",
    "28110", "28140", "28177", "28185", "28200", "28237", "28245", "28260", "28710", "28720",
    "29110", "29140", "29155", "29170", "29200",
    "30110", "30140", "30170", "30200", "30230",
    "31110", "31140", "31170", "31200", "31710",
    "36110",
    # 지방 권역 주요 도시
    "42110", "42130", "42150",
    "43111", "43112", "43113", "43114",
    "44131", "44133", "44200",
    "45111", "45113", "45140",
    "46110", "46130", "46150",
    "47111", "47113", "47130", "47190", "47210", "47290",
    "48121", "48123", "48125", "48127", "48129", "48170", "48250",
    "50110", "50130",
)

DEFAULT_MOLIT_REGION_SCOPE = "seoul_gyeonggi_all_major_cities"


def _uniq_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _write_json_atomic(file_path: str, payload: Dict[str, Any]) -> None:
    tmp_path = f"{file_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp_path, file_path)


MOLIT_REGION_SCOPE_CODES = {
    "seoul_gyeonggi_all": _uniq_preserve_order(
        [*SEOUL_ALL_LAWD_CODES, *GYEONGGI_ALL_LAWD_CODES]
    ),
    "major_cities_only": _uniq_preserve_order([*LOCAL_MAJOR_CITY_LAWD_CODES]),
    "seoul_gyeonggi_all_major_cities": _uniq_preserve_order(
        [*SEOUL_ALL_LAWD_CODES, *GYEONGGI_ALL_LAWD_CODES, *LOCAL_MAJOR_CITY_LAWD_CODES]
    ),
}


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _molit_manwon_to_krw(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    # MOLIT 실거래 금액 필드는 만원 단위이므로 canonical KRW로 환산한다.
    return value * 10_000


class KRRealEstateCollector:
    """KR real-estate ingestion with canonical schema."""

    def __init__(self, db_connection_factory=None):
        self._db_connection_factory = db_connection_factory or get_db_connection

    def _get_db_connection(self):
        return self._db_connection_factory()

    @staticmethod
    def normalize_region_code(value: Any) -> Optional[str]:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        if not digits:
            return None
        if len(digits) >= 10:
            return digits[:10]
        if len(digits) == 5:
            return digits + "00000"
        return digits.zfill(10)

    @staticmethod
    def normalize_lawd_cd(value: Any) -> Optional[str]:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        if len(digits) < 5:
            return None
        return digits[:5]

    @staticmethod
    def normalize_property_type(value: Any) -> str:
        key = str(value or "").strip().upper()
        if key in PROPERTY_TYPE_ALIASES:
            return PROPERTY_TYPE_ALIASES[key]
        if key:
            return key.lower()
        return "unknown"

    def resolve_target_lawd_codes(
        self,
        *,
        scope: Optional[str] = None,
        lawd_codes: Optional[Iterable[str]] = None,
    ) -> List[str]:
        if lawd_codes:
            explicit = [
                code
                for code in (self.normalize_lawd_cd(v) for v in lawd_codes)
                if code
            ]
            return _uniq_preserve_order(explicit)

        env_codes = os.getenv("MOLIT_TARGET_LAWD_CODES", "").strip()
        if env_codes:
            parsed = [
                code
                for code in (
                    self.normalize_lawd_cd(token)
                    for token in env_codes.split(",")
                )
                if code
            ]
            if parsed:
                return _uniq_preserve_order(parsed)

        resolved_scope = (
            (scope or os.getenv("MOLIT_REGION_SCOPE") or DEFAULT_MOLIT_REGION_SCOPE)
            .strip()
            .lower()
        )
        if resolved_scope not in MOLIT_REGION_SCOPE_CODES:
            logger.warning(
                "알 수 없는 MOLIT scope(%s). 기본값(%s)으로 대체합니다.",
                resolved_scope,
                DEFAULT_MOLIT_REGION_SCOPE,
            )
            resolved_scope = DEFAULT_MOLIT_REGION_SCOPE
        return list(MOLIT_REGION_SCOPE_CODES[resolved_scope])

    @staticmethod
    def iter_deal_months(start_ym: str, end_ym: str) -> List[str]:
        start = datetime.strptime(start_ym, "%Y%m").date().replace(day=1)
        end = datetime.strptime(end_ym, "%Y%m").date().replace(day=1)
        if start > end:
            raise ValueError(f"start_ym must be <= end_ym: {start_ym} > {end_ym}")

        months: List[str] = []
        current = start
        while current <= end:
            months.append(current.strftime("%Y%m"))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        return months

    @staticmethod
    def normalize_transaction_type(value: Any) -> str:
        key = str(value or "").strip().upper()
        if key in TRANSACTION_TYPE_ALIASES:
            return TRANSACTION_TYPE_ALIASES[key]
        if key:
            return key.lower()
        return "unknown"

    @staticmethod
    def _parse_contract_date(raw: Dict[str, Any]) -> Optional[date]:
        direct = raw.get("contract_date") or raw.get("dealDate") or raw.get("계약일")
        if direct:
            text = str(direct).strip()
            if len(text) >= 10:
                try:
                    return date.fromisoformat(text[:10])
                except ValueError:
                    pass

        year = raw.get("dealYear") or raw.get("년")
        month = raw.get("dealMonth") or raw.get("월")
        day = raw.get("dealDay") or raw.get("일")
        if year and month and day:
            try:
                return date(int(year), int(month), int(day))
            except ValueError:
                pass

        ym = raw.get("DEAL_YMD") or raw.get("deal_ym") or raw.get("계약년월")
        if ym:
            digits = "".join(ch for ch in str(ym) if ch.isdigit())
            if len(digits) >= 6:
                try:
                    return date(int(digits[:4]), int(digits[4:6]), 1)
                except ValueError:
                    return None
        return None

    @staticmethod
    def _build_source_record_id(raw: Dict[str, Any], source: str) -> str:
        explicit = (
            raw.get("source_record_id")
            or raw.get("거래ID")
            or raw.get("dealId")
            or raw.get("id")
        )
        if explicit:
            return str(explicit).strip()

        payload = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha1(f"{source}|{payload}".encode("utf-8")).hexdigest()
        return digest[:24]

    def normalize_transaction_record(
        self,
        raw: Dict[str, Any],
        *,
        source: str,
        as_of_date: Optional[date] = None,
    ) -> Optional[Dict[str, Any]]:
        region_code = self.normalize_region_code(
            raw.get("region_code")
            or raw.get("법정동코드")
            or raw.get("LAWD_CD")
            or raw.get("sggCd")
        )
        if not region_code:
            return None

        contract_date = self._parse_contract_date(raw)
        effective_date = contract_date or as_of_date or date.today()
        published_at = raw.get("published_at")
        if isinstance(published_at, datetime):
            published_dt = published_at
        elif isinstance(published_at, date):
            published_dt = datetime.combine(published_at, datetime.min.time())
        elif isinstance(published_at, str) and published_at.strip():
            try:
                published_dt = datetime.fromisoformat(published_at.strip().replace("Z", "+00:00"))
            except ValueError:
                published_dt = datetime.combine(effective_date, datetime.min.time())
        else:
            published_dt = datetime.combine(effective_date, datetime.min.time())

        source_record_id = self._build_source_record_id(raw, source=source)
        source_upper = str(source).strip().upper()
        default_property_type = "apartment" if source_upper == "MOLIT" else None
        default_transaction_type = "sale" if source_upper == "MOLIT" else None
        price = _to_int(raw.get("price") or raw.get("거래금액") or raw.get("dealAmount"))
        deposit = _to_int(raw.get("deposit") or raw.get("보증금액") or raw.get("depositAmount"))
        monthly_rent = _to_int(raw.get("monthly_rent") or raw.get("월세금액") or raw.get("monthlyRent"))
        if source_upper == "MOLIT":
            price = _molit_manwon_to_krw(price)
            deposit = _molit_manwon_to_krw(deposit)
            monthly_rent = _molit_manwon_to_krw(monthly_rent)

        normalized = {
            "source": source_upper,
            "source_record_id": source_record_id,
            "country_code": "KR",
            "region_code": region_code,
            "property_type": self.normalize_property_type(
                raw.get("property_type")
                or raw.get("주택유형")
                or raw.get("housingType")
                or default_property_type
            ),
            "transaction_type": self.normalize_transaction_type(
                raw.get("transaction_type")
                or raw.get("거래유형")
                or raw.get("rentType")
                or default_transaction_type
            ),
            "contract_date": contract_date,
            "effective_date": effective_date,
            "published_at": published_dt,
            "as_of_date": as_of_date or date.today(),
            "price": price,
            "deposit": deposit,
            "monthly_rent": monthly_rent,
            "area_m2": _to_float(raw.get("area_m2") or raw.get("전용면적") or raw.get("excluUseAr")),
            "floor_no": _to_int(raw.get("floor_no") or raw.get("층")),
            "build_year": _to_int(raw.get("build_year") or raw.get("건축년도")),
            "metadata_json": json.dumps(raw, ensure_ascii=False, default=str),
        }
        return normalized

    def ensure_table(self):
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kr_real_estate_transactions (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    source VARCHAR(64) NOT NULL,
                    source_record_id VARCHAR(128) NOT NULL,
                    country_code VARCHAR(8) NOT NULL DEFAULT 'KR',
                    region_code VARCHAR(10) NOT NULL,
                    property_type VARCHAR(32) NOT NULL,
                    transaction_type VARCHAR(32) NOT NULL,
                    contract_date DATE NULL,
                    effective_date DATE NULL,
                    published_at DATETIME NULL,
                    as_of_date DATE NULL,
                    price BIGINT NULL,
                    deposit BIGINT NULL,
                    monthly_rent BIGINT NULL,
                    area_m2 DECIMAL(14, 4) NULL,
                    floor_no INT NULL,
                    build_year INT NULL,
                    metadata_json JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_source_record (source, source_record_id),
                    INDEX idx_region_contract (region_code, contract_date),
                    INDEX idx_type_contract (property_type, transaction_type, contract_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

    def save_transactions(self, records: List[Dict[str, Any]]) -> int:
        if not records:
            return 0
        self.ensure_table()

        columns = [
            "source",
            "source_record_id",
            "country_code",
            "region_code",
            "property_type",
            "transaction_type",
            "contract_date",
            "effective_date",
            "published_at",
            "as_of_date",
            "price",
            "deposit",
            "monthly_rent",
            "area_m2",
            "floor_no",
            "build_year",
            "metadata_json",
        ]
        placeholders = ", ".join(["%s"] * len(columns))
        update_columns = [col for col in columns if col not in {"source", "source_record_id"}]
        updates = ", ".join([f"`{col}` = VALUES(`{col}`)" for col in update_columns])

        query = f"""
            INSERT INTO kr_real_estate_transactions ({", ".join([f"`{c}`" for c in columns])})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {updates}
        """
        payload = [tuple(record.get(column) for column in columns) for record in records]

        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, payload)
            affected = int(cursor.rowcount or 0)
        return affected

    def ingest_transactions(
        self,
        rows: Iterable[Dict[str, Any]],
        *,
        source: str,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        normalized: List[Dict[str, Any]] = []
        skipped = 0
        total_input = 0
        for raw in rows:
            total_input += 1
            record = self.normalize_transaction_record(raw, source=source, as_of_date=as_of_date)
            if record is None:
                skipped += 1
                continue
            normalized.append(record)

        affected = self.save_transactions(normalized)
        return {
            "source": source,
            "input_rows": total_input,
            "normalized_rows": len(normalized),
            "skipped_rows": skipped,
            "db_affected": affected,
        }

    def fetch_molit_trade_rows(
        self,
        *,
        lawd_cd: str,
        deal_ym: str,
        num_of_rows: int = 1000,
        page_no: int = 1,
        endpoint: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch MOLIT transaction rows from XML API.
        """
        service_key = os.getenv("MOLIT_API_KEY", "").strip()
        if not service_key:
            raise ValueError("MOLIT_API_KEY is required")

        url = endpoint or os.getenv(
            "MOLIT_TRADE_API_URL",
            "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
        )
        params = {
            "serviceKey": service_key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ym,
            "numOfRows": num_of_rows,
            "pageNo": page_no,
        }
        request_url = f"{url}?{urlencode(params)}"
        req = Request(request_url, headers={"User-Agent": "hobot-kr-real-estate-collector/1.0"})
        with urlopen(req, timeout=30) as response:  # nosec B310
            xml_payload = response.read().decode("utf-8")

        root = ET.fromstring(xml_payload)
        items: List[Dict[str, Any]] = []
        for item_node in root.findall(".//item"):
            row: Dict[str, Any] = {}
            for child in list(item_node):
                row[child.tag] = child.text
            items.append(row)
        return items

    def collect_molit_apartment_trades(
        self,
        *,
        start_ym: str,
        end_ym: str,
        scope: Optional[str] = None,
        lawd_codes: Optional[Iterable[str]] = None,
        num_of_rows: int = 1000,
        max_pages: int = 100,
        as_of_date: Optional[date] = None,
        progress_file: Optional[str] = None,
        progress_log_interval: int = 100,
    ) -> Dict[str, Any]:
        """
        월/지역 단위로 MOLIT 아파트 실거래를 수집/적재합니다.

        기본 scope:
        - 서울 전 지역
        - 경기 전 지역
        - 지방 주요 도시
        """
        if num_of_rows <= 0:
            raise ValueError("num_of_rows must be > 0")
        if max_pages <= 0:
            raise ValueError("max_pages must be > 0")

        target_lawd_codes = self.resolve_target_lawd_codes(scope=scope, lawd_codes=lawd_codes)
        if not target_lawd_codes:
            raise ValueError("No LAWD_CD targets resolved")

        target_months = self.iter_deal_months(start_ym, end_ym)
        run_as_of_date = as_of_date or date.today()
        started_at = datetime.utcnow()
        total_pairs = len(target_months) * len(target_lawd_codes)

        summary: Dict[str, Any] = {
            "scope": scope or os.getenv("MOLIT_REGION_SCOPE") or DEFAULT_MOLIT_REGION_SCOPE,
            "start_ym": start_ym,
            "end_ym": end_ym,
            "target_month_count": len(target_months),
            "target_region_count": len(target_lawd_codes),
            "target_lawd_codes": target_lawd_codes,
            "total_pairs": total_pairs,
            "completed_pairs": 0,
            "remaining_pairs": total_pairs,
            "progress_pct": 0.0,
            "api_requests": 0,
            "fetched_rows": 0,
            "normalized_rows": 0,
            "skipped_rows": 0,
            "db_affected": 0,
            "failed_requests": 0,
            "started_at": started_at.isoformat() + "Z",
            "updated_at": started_at.isoformat() + "Z",
        }

        def emit_progress(last_pair: Optional[Dict[str, Any]], *, force: bool = False, status: str = "running"):
            completed = int(summary["completed_pairs"])
            remaining = max(total_pairs - completed, 0)
            progress_pct = (float(completed) / float(total_pairs) * 100.0) if total_pairs else 100.0
            updated_at = datetime.utcnow().isoformat() + "Z"
            summary["remaining_pairs"] = remaining
            summary["progress_pct"] = round(progress_pct, 2)
            summary["updated_at"] = updated_at

            should_log = force
            if not should_log and progress_log_interval > 0:
                should_log = (completed == 1) or (completed == total_pairs) or (completed % progress_log_interval == 0)
            if should_log:
                logger.info(
                    "MOLIT 적재 진행률: %s/%s (%.2f%%), fetched_rows=%s, db_affected=%s, failed_requests=%s, current=%s",
                    completed,
                    total_pairs,
                    summary["progress_pct"],
                    summary["fetched_rows"],
                    summary["db_affected"],
                    summary["failed_requests"],
                    last_pair,
                )

            if progress_file:
                payload = {
                    "status": status,
                    "summary": summary,
                    "last_pair": last_pair,
                }
                try:
                    _write_json_atomic(progress_file, payload)
                except Exception as exc:
                    logger.warning("progress file 기록 실패(%s): %s", progress_file, exc)

        for deal_ym in target_months:
            for lawd_cd in target_lawd_codes:
                page_no = 1
                pair_fetched_rows = 0
                pair_api_requests = 0
                pair_failed = False
                while page_no <= max_pages:
                    try:
                        rows = self.fetch_molit_trade_rows(
                            lawd_cd=lawd_cd,
                            deal_ym=deal_ym,
                            num_of_rows=num_of_rows,
                            page_no=page_no,
                        )
                    except Exception as exc:
                        summary["failed_requests"] += 1
                        logger.warning(
                            "MOLIT 수집 실패: lawd_cd=%s deal_ym=%s page=%s err=%s",
                            lawd_cd,
                            deal_ym,
                            page_no,
                            exc,
                        )
                        pair_failed = True
                        break

                    summary["api_requests"] += 1
                    pair_api_requests += 1
                    if not rows:
                        break

                    for row in rows:
                        row.setdefault("LAWD_CD", lawd_cd)
                        row.setdefault("DEAL_YMD", deal_ym)

                    ingest_result = self.ingest_transactions(
                        rows,
                        source="MOLIT",
                        as_of_date=run_as_of_date,
                    )
                    summary["fetched_rows"] += len(rows)
                    pair_fetched_rows += len(rows)
                    summary["normalized_rows"] += int(ingest_result.get("normalized_rows", 0))
                    summary["skipped_rows"] += int(ingest_result.get("skipped_rows", 0))
                    summary["db_affected"] += int(ingest_result.get("db_affected", 0))

                    if len(rows) < num_of_rows:
                        break
                    page_no += 1

                summary["completed_pairs"] += 1
                emit_progress(
                    {
                        "deal_ym": deal_ym,
                        "lawd_cd": lawd_cd,
                        "pair_api_requests": pair_api_requests,
                        "pair_fetched_rows": pair_fetched_rows,
                        "pair_failed": pair_failed,
                    },
                    force=False,
                    status="running",
                )

        duration_seconds = int((datetime.utcnow() - started_at).total_seconds())
        summary["duration_seconds"] = duration_seconds
        emit_progress(last_pair=None, force=True, status="completed")

        return summary

    def ensure_monthly_summary_table(self):
        """
        월×지역(시군구 5자리) 집계 테이블 생성.
        서울 구별/경기 시군구별 조회를 빠르게 하기 위한 서빙 테이블이다.
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kr_real_estate_monthly_summary (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    stat_ym CHAR(6) NOT NULL,
                    lawd_cd CHAR(5) NOT NULL,
                    country_code VARCHAR(8) NOT NULL DEFAULT 'KR',
                    property_type VARCHAR(32) NOT NULL,
                    transaction_type VARCHAR(32) NOT NULL,
                    tx_count INT NOT NULL,
                    avg_price DECIMAL(16, 2) NULL,
                    avg_price_per_m2 DECIMAL(18, 4) NULL,
                    avg_area_m2 DECIMAL(14, 4) NULL,
                    min_price BIGINT NULL,
                    max_price BIGINT NULL,
                    total_price BIGINT NULL,
                    as_of_date DATE NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_month_region_type (stat_ym, lawd_cd, property_type, transaction_type),
                    INDEX idx_lawd_month (lawd_cd, stat_ym),
                    INDEX idx_month_type (stat_ym, property_type, transaction_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

    def aggregate_monthly_region_summary(
        self,
        *,
        start_ym: str,
        end_ym: str,
        property_type: str = "apartment",
        transaction_type: str = "sale",
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        원천 실거래 row를 월×지역 요약으로 집계하여 upsert.

        집계 축:
        - month: contract_date -> YYYYMM
        - region: LEFT(region_code, 5) (LAWD_CD)
        - type: property_type + transaction_type
        """
        run_as_of = as_of_date or date.today()
        normalized_property_type = self.normalize_property_type(property_type)
        normalized_transaction_type = self.normalize_transaction_type(transaction_type)
        start_month = datetime.strptime(start_ym, "%Y%m").date().replace(day=1)
        end_month = datetime.strptime(end_ym, "%Y%m").date().replace(day=1)
        if end_month.month == 12:
            end_month_exclusive = end_month.replace(year=end_month.year + 1, month=1)
        else:
            end_month_exclusive = end_month.replace(month=end_month.month + 1)
        self.ensure_monthly_summary_table()

        query = """
            INSERT INTO kr_real_estate_monthly_summary (
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
            )
            SELECT
                DATE_FORMAT(contract_date, '%%Y%%m') AS stat_ym,
                LEFT(region_code, 5) AS lawd_cd,
                'KR' AS country_code,
                property_type,
                transaction_type,
                COUNT(*) AS tx_count,
                AVG(price) AS avg_price,
                AVG(CASE WHEN area_m2 IS NOT NULL AND area_m2 > 0 THEN (price / area_m2) END) AS avg_price_per_m2,
                AVG(area_m2) AS avg_area_m2,
                MIN(price) AS min_price,
                MAX(price) AS max_price,
                SUM(price) AS total_price,
                %s AS as_of_date
            FROM kr_real_estate_transactions
            WHERE contract_date IS NOT NULL
              AND contract_date >= %s
              AND contract_date < %s
              AND property_type = %s
              AND transaction_type = %s
              AND price IS NOT NULL
            GROUP BY DATE_FORMAT(contract_date, '%%Y%%m'), LEFT(region_code, 5), property_type, transaction_type
            ON DUPLICATE KEY UPDATE
                tx_count = VALUES(tx_count),
                avg_price = VALUES(avg_price),
                avg_price_per_m2 = VALUES(avg_price_per_m2),
                avg_area_m2 = VALUES(avg_area_m2),
                min_price = VALUES(min_price),
                max_price = VALUES(max_price),
                total_price = VALUES(total_price),
                as_of_date = VALUES(as_of_date),
                updated_at = CURRENT_TIMESTAMP
        """

        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                query,
                (
                    run_as_of,
                    start_month,
                    end_month_exclusive,
                    normalized_property_type,
                    normalized_transaction_type,
                ),
            )
            affected = int(cursor.rowcount or 0)

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS summary_rows,
                    COUNT(DISTINCT stat_ym) AS month_count,
                    COUNT(DISTINCT lawd_cd) AS region_count
                FROM kr_real_estate_monthly_summary
                WHERE stat_ym >= %s
                  AND stat_ym <= %s
                  AND property_type = %s
                  AND transaction_type = %s
                """,
                (start_ym, end_ym, normalized_property_type, normalized_transaction_type),
            )
            stats = cursor.fetchone() or {}

        return {
            "start_ym": start_ym,
            "end_ym": end_ym,
            "property_type": normalized_property_type,
            "transaction_type": normalized_transaction_type,
            "db_affected": affected,
            "summary_rows": int(stats.get("summary_rows", 0)),
            "month_count": int(stats.get("month_count", 0)),
            "region_count": int(stats.get("region_count", 0)),
            "as_of_date": run_as_of.isoformat(),
        }


_kr_real_estate_collector_singleton: Optional[KRRealEstateCollector] = None


def get_kr_real_estate_collector() -> KRRealEstateCollector:
    global _kr_real_estate_collector_singleton
    if _kr_real_estate_collector_singleton is None:
        _kr_real_estate_collector_singleton = KRRealEstateCollector()
    return _kr_real_estate_collector_singleton
