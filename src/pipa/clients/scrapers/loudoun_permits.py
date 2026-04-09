"""Loudoun County permits scraper — Tyler EnerGov Civic Access portal.

Loudoun migrated permits from Accela LandMARC to Tyler EnerGov, and the
new portal exposes a clean unauthenticated REST API at:

    POST https://loudouncountyvaeg.tylerhost.net/prod/selfservice/api/energov/search/search

No API key, no cookies, no anti-bot tokens — just static tenant headers.
The browser SPA fires this same call when you submit the search form;
we replicate it directly with httpx.

Public surface:

    fetch_permits(address) -> list[dict]
        Returns normalized permit records for a single street address.
        Inspections (separate `INSP-*` records) are filtered out by
        default since each permit triggers many and the inspection
        dates are noise for component dating.

Sample normalized record::

    {
        "case_id":        "79E3AEFC-0958-4B90-B602-79F98685E7DE",
        "permit_number":  "Z40121260101",
        "type":           "Zoning (Residential) - County Typical Deck",
        "workclass":      "Deck - County Typical",
        "status":         "Expired",
        "description":    "DECK/CTY TYPICAL",
        "issue_date":     "2004-05-28T00:00:00",
        "apply_date":     "2004-05-28T00:00:00",
        "final_date":     None,
        "expire_date":    None,
        "complete_date":  None,
        "parcel":         "159486167000",
        "address":        "22817 PORTICO PL ASHBURN VA 20148",
    }
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Endpoint + tenant identification headers (no auth required)
# ----------------------------------------------------------------------

SEARCH_URL = (
    "https://loudouncountyvaeg.tylerhost.net"
    "/prod/selfservice/api/energov/search/search"
)

# Tenant headers are static — Loudoun's tenant id is 1 and the URL slug
# is LoudounCountyVAProd. Captured from a real browser session.
TENANT_HEADERS: dict[str, str] = {
    "tenantid": "1",
    "tenantname": "LoudounCountyVAProd",
    "tyler-tenant-culture": "en-US",
    "tyler-tenanturl": "LoudounCountyVAProd",
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US",
    "content-type": "application/json;charset=UTF-8",
    "referer": "https://loudouncountyvaeg.tylerhost.net/prod/selfservice",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}

# Tyler EnerGov rejects requests that omit the criteria/sort keys with
# a 500. Empty dicts/lists are accepted — we just need every key present.
_CRITERIA_KEYS = (
    "PlanCriteria", "PermitCriteria", "InspectionCriteria",
    "CodeCaseCriteria", "RequestCriteria", "BusinessLicenseCriteria",
    "ProfessionalLicenseCriteria", "LicenseCriteria", "ProjectCriteria",
)
_SORT_LIST_KEYS = (
    "PlanSortList", "PermitSortList", "InspectionSortList",
    "CodeCaseSortList", "RequestSortList", "LicenseSortList",
    "ProjectSortList",
)


def _build_search_body(
    keyword: str,
    *,
    page_number: int,
    page_size: int,
) -> dict[str, Any]:
    """Construct the minimal POST body Tyler EnerGov accepts."""
    body: dict[str, Any] = {
        "Keyword": keyword,
        "ExactMatch": True,
        "SearchModule": 1,
        "FilterModule": 1,
        "SearchMainAddress": False,
        "ExcludeCases": None,
        "HiddenInspectionTypeIDs": None,
        "SortOrderList": [],
        "PageNumber": page_number,
        "PageSize": page_size,
        "SortBy": None,
        "SortAscending": True,
    }
    for k in _CRITERIA_KEYS:
        body[k] = {}
    for k in _SORT_LIST_KEYS:
        body[k] = []
    return body


def _normalize_permit(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Tyler EnerGov EntityResult into a stable dict."""
    return {
        "case_id":       raw.get("CaseId"),
        "permit_number": raw.get("CaseNumber"),
        "type":          raw.get("CaseType"),
        "workclass":     raw.get("CaseWorkclass"),
        "status":        raw.get("CaseStatus"),
        "description":   (raw.get("Description") or "").strip() or None,
        "issue_date":    raw.get("IssueDate"),
        "apply_date":    raw.get("ApplyDate"),
        "final_date":    raw.get("FinalDate"),
        "expire_date":   raw.get("ExpireDate"),
        "complete_date": raw.get("CompleteDate"),
        "parcel":        raw.get("MainParcel"),
        "address":       raw.get("AddressDisplay"),
    }


def _is_inspection(raw: dict[str, Any]) -> bool:
    """Inspections are sub-records of permits — skip them by default."""
    case_number = raw.get("CaseNumber") or ""
    return case_number.startswith("INSP-")


async def fetch_permits(
    address: str,
    *,
    include_inspections: bool = False,
    page_size: int = 1000,
    timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Fetch all permit records for a Loudoun County street address.

    Args:
        address: Street address to search (e.g. ``"22817 PORTICO PL"``).
            Tyler matches against the full address index, so the city
            and zip can be omitted.
        include_inspections: When True, include the `INSP-*` sub-records
            for each permit. Default False because each permit triggers
            many inspections and they pollute the timeline.
        page_size: API page size. Tyler accepts large values; 1000 covers
            any single property in practice but pagination is still
            handled defensively if ``TotalFound`` exceeds it.
        timeout: Per-request HTTP timeout in seconds.
        client: Optional pre-built httpx.AsyncClient — useful for tests
            and connection reuse. A fresh client is created when None.

    Returns:
        List of normalized permit dicts (see module docstring for shape).
        Empty list when no records found OR on transport errors — failures
        are logged, never raised, so callers can degrade gracefully.
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, headers=TENANT_HEADERS)

    try:
        all_results: list[dict[str, Any]] = []
        page = 1
        total_found: int | None = None

        while True:
            body = _build_search_body(
                address, page_number=page, page_size=page_size,
            )
            try:
                r = await client.post(SEARCH_URL, json=body)
            except httpx.HTTPError as e:
                logger.warning(
                    "Loudoun permits search transport error for %r: %s",
                    address, e,
                )
                return []

            if r.status_code != 200:
                logger.warning(
                    "Loudoun permits search HTTP %d for %r: %s",
                    r.status_code, address, r.text[:300],
                )
                return []

            try:
                data = r.json()
            except ValueError:
                logger.warning(
                    "Loudoun permits search returned non-JSON for %r",
                    address,
                )
                return []

            result = (data or {}).get("Result") or {}
            entities = result.get("EntityResults") or []
            total_found = result.get("TotalFound", len(entities))

            all_results.extend(entities)

            # Stop when we've gathered everything Tyler reports.
            if len(all_results) >= total_found or not entities:
                break
            page += 1
            # Hard cap so we never spin forever on a buggy response.
            if page > 50:
                logger.warning(
                    "Loudoun permits pagination cap hit for %r at page 50",
                    address,
                )
                break

        if not include_inspections:
            all_results = [r for r in all_results if not _is_inspection(r)]

        normalized = [_normalize_permit(r) for r in all_results]
        logger.info(
            "Loudoun permits: %d records for %r (total reported %s)",
            len(normalized), address, total_found,
        )
        return normalized

    finally:
        if own_client:
            await client.aclose()


# ----------------------------------------------------------------------
# CLI smoke test — `python -m pipa.clients.scrapers.loudoun_permits "22817 PORTICO PL"`
# ----------------------------------------------------------------------

async def _cli(address: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    permits = await fetch_permits(address)
    print(f"\n=== {len(permits)} permits for {address!r} ===\n")
    for p in permits:
        issue = (p["issue_date"] or "")[:10] or "—"
        print(
            f"  {issue}  {p['permit_number']:<18} "
            f"{(p['workclass'] or p['type'] or '?')[:50]:<50} "
            f"[{p['status'] or '?'}]"
        )
        if p["description"]:
            print(f"      - {p['description']}")


if __name__ == "__main__":
    import sys
    addr = sys.argv[1] if len(sys.argv) > 1 else "22817 PORTICO PL"
    asyncio.run(_cli(addr))
