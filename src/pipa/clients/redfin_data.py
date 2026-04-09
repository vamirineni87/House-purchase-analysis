"""Redfin Data Center — free CSV downloads for housing market metrics.

Downloads monthly/weekly housing market data by ZIP code from Redfin's
public data center. No API key required.

Source: https://www.redfin.com/news/data-center/
Data includes: median sale price, homes sold, inventory, DOM, sale-to-list ratio.
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import io
import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# Pickle protocol 5 — fastest binary serialization, supported in Python 3.8+.
_PICKLE_PROTO = 5


def _decompress_and_write(content: bytes, cache_path: Path, region_type: str) -> None:
    """Synchronous helper: gunzip + write TSV to disk.

    Run inside asyncio.to_thread() so the multi-hundred-MB decompression
    + disk write doesn't block the FastAPI event loop.
    """
    data = gzip.decompress(content)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(data)
    logger.info(
        "Redfin %s data downloaded: %.1f MB",
        region_type,
        len(data) / 1_000_000,
    )


def _build_zip_index(tsv_path: Path, index_path: Path) -> int:
    """One-time: read 500MB TSV, group rows by region, pickle the index.

    The pickle is a dict ``{normalized_region: list[row_dict]}`` where each
    row contains only the cleaned numeric fields we care about. Subsequent
    /market calls just load the pickle and do an O(1) dict lookup —
    instead of streaming the entire 500MB TSV every time.

    Run inside asyncio.to_thread().
    """
    import time
    t0 = time.monotonic()
    index: dict[str, list[dict]] = {}
    row_count = 0
    with open(tsv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            row_count += 1
            region = (row.get("region") or "").strip()
            if not region:
                continue
            # Redfin region values look like "Zip Code: 20148" — strip the
            # prefix so the lookup key is just the bare ZIP.
            for prefix in ("Zip Code:", "Zip code:", "zip code:"):
                if region.startswith(prefix):
                    region = region[len(prefix):].strip()
                    break
            cleaned = {
                "period_begin": row.get("period_begin", ""),
                "period_end": row.get("period_end", ""),
                "region": region,
                "median_sale_price": _safe_float(row.get("median_sale_price")),
                "median_list_price": _safe_float(row.get("median_list_price")),
                "homes_sold": _safe_float(row.get("homes_sold")),
                "new_listings": _safe_float(row.get("new_listings")),
                "inventory": _safe_float(row.get("inventory")),
                "median_dom": _safe_float(row.get("median_dom")),
                "avg_sale_to_list": _safe_float(row.get("avg_sale_to_list")),
                "price_drops": _safe_float(row.get("price_drops")),
                "median_ppsf": _safe_float(row.get("median_ppsf")),
            }
            index.setdefault(region, []).append(cleaned)

    # Sort each region's rows newest-first so lookups can take a slice
    # without re-sorting.
    for region_rows in index.values():
        region_rows.sort(key=lambda r: r.get("period_begin", ""), reverse=True)

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "wb") as f:
        pickle.dump(index, f, protocol=_PICKLE_PROTO)

    elapsed = time.monotonic() - t0
    logger.info(
        "Built Redfin index: %d rows → %d regions in %.1fs (%s)",
        row_count, len(index), elapsed, index_path.name,
    )
    return len(index)


def _build_county_index(tsv_path: Path, index_path: Path) -> int:
    """One-time: build a (county, state) → rows index for the county TSV."""
    import time
    t0 = time.monotonic()
    index: dict[tuple[str, str], list[dict]] = {}
    row_count = 0
    with open(tsv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            row_count += 1
            region = (row.get("region") or "").strip()
            state = (row.get("state") or "").strip()
            if not region:
                continue
            key = (region.lower(), state.lower())
            cleaned = {
                "period_begin": row.get("period_begin", ""),
                "period_end": row.get("period_end", ""),
                "region": region,
                "state": state,
                "median_sale_price": _safe_float(row.get("median_sale_price")),
                "median_list_price": _safe_float(row.get("median_list_price")),
                "homes_sold": _safe_float(row.get("homes_sold")),
                "new_listings": _safe_float(row.get("new_listings")),
                "inventory": _safe_float(row.get("inventory")),
                "median_dom": _safe_float(row.get("median_dom")),
                "avg_sale_to_list": _safe_float(row.get("avg_sale_to_list")),
                "price_drops": _safe_float(row.get("price_drops")),
                "median_ppsf": _safe_float(row.get("median_ppsf")),
            }
            index.setdefault(key, []).append(cleaned)

    for rows in index.values():
        rows.sort(key=lambda r: r.get("period_begin", ""), reverse=True)

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "wb") as f:
        pickle.dump(index, f, protocol=_PICKLE_PROTO)

    elapsed = time.monotonic() - t0
    logger.info(
        "Built Redfin county index: %d rows → %d (county,state) keys in %.1fs",
        row_count, len(index), elapsed,
    )
    return len(index)


def _lookup_zip(index_path: Path, zip_code: str, months: int) -> list[dict]:
    """O(1) lookup against the pre-built ZIP index pickle."""
    with open(index_path, "rb") as f:
        index = pickle.load(f)
    rows = index.get(zip_code, [])
    return rows[:months]


def _lookup_county(index_path: Path, county: str, state: str, months: int) -> list[dict]:
    """O(1) lookup against the pre-built county index pickle."""
    with open(index_path, "rb") as f:
        index = pickle.load(f)
    rows = index.get((county.lower(), state.lower()), [])
    return rows[:months]

# Redfin public data URLs (TSV format)
# These are direct download links from the Redfin Data Center
_BASE_URL = "https://redfin-public-data.s3.us-west-2.amazonaws.com/redfin_market_tracker"

# Region types: national, state, metro, county, city, zip, neighborhood
_REGION_URLS = {
    "zip": f"{_BASE_URL}/zip_code_market_tracker.tsv000.gz",
    "county": f"{_BASE_URL}/county_market_tracker.tsv000.gz",
}

# Cache directory for downloaded CSVs
_DEFAULT_CACHE_DIR = Path("storage/redfin_data")


class RedfinDataClient:
    """Client for Redfin's public housing market data.

    Downloads and caches large TSV files, then filters by region.
    The full ZIP-level file is ~200MB compressed — download once, filter locally.
    """

    def __init__(self, cache_dir: Path | None = None, cache_ttl_hours: int = 168):
        self.cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_hours = cache_ttl_hours

    async def get_zip_metrics(
        self,
        zip_code: str,
        months: int = 12,
    ) -> list[dict[str, Any]]:
        """Get monthly market metrics for a ZIP code.

        Returns list of monthly snapshots sorted newest first, with:
          - period_begin, period_end
          - median_sale_price, median_list_price
          - homes_sold, new_listings, inventory
          - median_dom, avg_sale_to_list
          - price_drops (% of listings with price drops)
        """
        rows = await self._load_filtered("zip", zip_code, months)
        return rows

    async def get_county_metrics(
        self,
        county_name: str,
        state: str = "Virginia",
        months: int = 12,
    ) -> list[dict[str, Any]]:
        """Get monthly market metrics for a county."""
        rows = await self._load_filtered_county(county_name, state, months)
        return rows

    def compute_market_indicators(
        self, metrics: list[dict],
    ) -> dict[str, Any]:
        """Compute buyer/seller market indicators from monthly metrics.

        Returns:
          - market_type: "buyer" | "seller" | "balanced"
          - months_of_supply: float
          - dom_trend: "increasing" | "decreasing" | "stable"
          - price_trend: "appreciating" | "declining" | "stable"
          - sale_to_list_avg: float
          - inventory_trend: "increasing" | "decreasing" | "stable"
        """
        if not metrics or len(metrics) < 2:
            return {"market_type": "unknown", "insufficient_data": True}

        latest = metrics[0]
        prior = metrics[min(5, len(metrics) - 1)]  # ~6 months ago

        # Months of supply = inventory / homes_sold
        inventory = _safe_float(latest.get("inventory"))
        homes_sold = _safe_float(latest.get("homes_sold"))
        months_of_supply = None
        if inventory and homes_sold and homes_sold > 0:
            months_of_supply = round(inventory / homes_sold, 1)

        # Market type based on months of supply
        market_type = "balanced"
        if months_of_supply is not None:
            if months_of_supply < 3:
                market_type = "seller"
            elif months_of_supply > 6:
                market_type = "buyer"

        # Trends
        dom_trend = _trend(
            _safe_float(prior.get("median_dom")),
            _safe_float(latest.get("median_dom")),
        )
        price_trend = _trend(
            _safe_float(prior.get("median_sale_price")),
            _safe_float(latest.get("median_sale_price")),
            labels=("declining", "stable", "appreciating"),
        )
        inventory_trend = _trend(
            _safe_float(prior.get("inventory")),
            _safe_float(latest.get("inventory")),
        )

        sale_to_list = _safe_float(latest.get("avg_sale_to_list"))

        return {
            "market_type": market_type,
            "months_of_supply": months_of_supply,
            "median_sale_price": _safe_float(latest.get("median_sale_price")),
            "median_list_price": _safe_float(latest.get("median_list_price")),
            "median_dom": _safe_float(latest.get("median_dom")),
            "homes_sold": _safe_float(latest.get("homes_sold")),
            "inventory": inventory,
            "sale_to_list_avg": round(sale_to_list, 3) if sale_to_list else None,
            "dom_trend": dom_trend,
            "price_trend": price_trend,
            "inventory_trend": inventory_trend,
            "period": latest.get("period_begin"),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _load_filtered(
        self, region_type: str, region_value: str, months: int
    ) -> list[dict]:
        """Get monthly market data for a region.

        Caching strategy (cheapest path first):

            1. ZIP index pickle exists + fresh
                → load pickle, dict[zip] lookup, slice last N months.
                  ~10-50ms regardless of TSV size. Used 99% of the time.

            2. TSV exists + fresh, pickle missing/stale
                → rebuild pickle from TSV (one-time, in thread), then go
                  back to step 1.

            3. TSV stale or missing
                → download 200MB.gz from Redfin (in thread), decompress
                  + write TSV (in thread), build pickle (in thread), then
                  step 1.

        Each step that touches large data runs inside ``asyncio.to_thread``
        so the FastAPI event loop stays responsive for parallel requests
        (the user's /schools, /decision/packet, /county all hit at once
        on every page load).
        """
        tsv_path = self.cache_dir / f"{region_type}_market.tsv"
        index_path = self.cache_dir / f"{region_type}_market.idx.pkl"

        if self._is_fresh(index_path):
            logger.debug("Redfin %s: pickle index hit", region_type)
            return await asyncio.to_thread(_lookup_zip, index_path, region_value, months)

        if self._is_fresh(tsv_path):
            logger.info("Redfin %s: TSV cached but pickle missing/stale, rebuilding index", region_type)
            await asyncio.to_thread(_build_zip_index, tsv_path, index_path)
            return await asyncio.to_thread(_lookup_zip, index_path, region_value, months)

        # Need a fresh download
        url = _REGION_URLS.get(region_type)
        if not url:
            logger.error("Unknown Redfin region type: %s", region_type)
            return []

        logger.info("Downloading Redfin %s market data (~200MB)...", region_type)
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.content
            await asyncio.to_thread(_decompress_and_write, content, tsv_path, region_type)
            await asyncio.to_thread(_build_zip_index, tsv_path, index_path)
        except Exception:
            logger.exception("Failed to download Redfin %s data", region_type)
            # Fall back to stale pickle if it exists, else stale TSV
            if index_path.exists():
                return await asyncio.to_thread(_lookup_zip, index_path, region_value, months)
            if tsv_path.exists():
                await asyncio.to_thread(_build_zip_index, tsv_path, index_path)
                return await asyncio.to_thread(_lookup_zip, index_path, region_value, months)
            return []

        return await asyncio.to_thread(_lookup_zip, index_path, region_value, months)

    async def _load_filtered_county(
        self, county_name: str, state: str, months: int
    ) -> list[dict]:
        """Get monthly market data for a county. Same caching strategy as
        _load_filtered — see its docstring.
        """
        tsv_path = self.cache_dir / "county_market.tsv"
        index_path = self.cache_dir / "county_market.idx.pkl"

        if self._is_fresh(index_path):
            return await asyncio.to_thread(
                _lookup_county, index_path, county_name, state, months
            )

        if self._is_fresh(tsv_path):
            logger.info("Redfin county: TSV cached but pickle missing/stale, rebuilding index")
            await asyncio.to_thread(_build_county_index, tsv_path, index_path)
            return await asyncio.to_thread(
                _lookup_county, index_path, county_name, state, months
            )

        url = _REGION_URLS["county"]
        logger.info("Downloading Redfin county market data...")
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.content
            await asyncio.to_thread(_decompress_and_write, content, tsv_path, "county")
            await asyncio.to_thread(_build_county_index, tsv_path, index_path)
        except Exception:
            logger.exception("Failed to download Redfin county data")
            if index_path.exists():
                return await asyncio.to_thread(
                    _lookup_county, index_path, county_name, state, months
                )
            if tsv_path.exists():
                await asyncio.to_thread(_build_county_index, tsv_path, index_path)
                return await asyncio.to_thread(
                    _lookup_county, index_path, county_name, state, months
                )
            return []

        return await asyncio.to_thread(
            _lookup_county, index_path, county_name, state, months
        )

    def _is_fresh(self, path: Path) -> bool:
        """True if the file exists and is younger than cache_ttl_hours."""
        if not path.exists():
            return False
        age_hours = (
            datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        ) / 3600
        return age_hours < self.cache_ttl_hours

    def _parse_tsv(
        self, path: Path, filter_col: str, filter_val: str, months: int
    ) -> list[dict]:
        """Parse TSV, filter by column value, return newest N months."""
        rows = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    region = row.get(filter_col, "")
                    # ZIP codes in Redfin data may have region type prefix
                    if filter_val in region or region.endswith(filter_val):
                        rows.append(self._clean_row(row))
        except Exception:
            logger.exception("Failed to parse TSV: %s", path)
            return []

        # Sort by period_begin descending
        rows.sort(key=lambda r: r.get("period_begin", ""), reverse=True)
        return rows[:months]

    def _parse_tsv_county(
        self, path: Path, county: str, state: str, months: int
    ) -> list[dict]:
        """Parse county TSV, filter by county + state."""
        county_lower = county.lower()
        state_lower = state.lower()
        rows = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    region = (row.get("region", "") or "").lower()
                    state_col = (row.get("state", "") or "").lower()
                    if county_lower in region and state_lower in state_col:
                        rows.append(self._clean_row(row))
        except Exception:
            logger.exception("Failed to parse county TSV: %s", path)
            return []

        rows.sort(key=lambda r: r.get("period_begin", ""), reverse=True)
        return rows[:months]

    @staticmethod
    def _clean_row(row: dict) -> dict:
        """Clean a TSV row into a normalized dict."""
        return {
            "period_begin": row.get("period_begin", ""),
            "period_end": row.get("period_end", ""),
            "region": row.get("region", ""),
            "median_sale_price": _safe_float(row.get("median_sale_price")),
            "median_list_price": _safe_float(row.get("median_list_price")),
            "homes_sold": _safe_float(row.get("homes_sold")),
            "new_listings": _safe_float(row.get("new_listings")),
            "inventory": _safe_float(row.get("inventory")),
            "median_dom": _safe_float(row.get("median_dom")),
            "avg_sale_to_list": _safe_float(row.get("avg_sale_to_list")),
            "price_drops": _safe_float(row.get("price_drops")),
            "median_ppsf": _safe_float(row.get("median_ppsf")),
        }


def _safe_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", "").replace("$", "").replace("%", ""))
    except (ValueError, TypeError):
        return None


def _trend(
    old: float | None,
    new: float | None,
    threshold: float = 0.05,
    labels: tuple = ("decreasing", "stable", "increasing"),
) -> str:
    if old is None or new is None or old == 0:
        return "unknown"
    pct_change = (new - old) / abs(old)
    if pct_change < -threshold:
        return labels[0]
    elif pct_change > threshold:
        return labels[2]
    return labels[1]
