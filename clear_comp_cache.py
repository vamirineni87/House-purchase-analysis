"""One-off: delete the polluted comp:{address} EvidenceItems.

The comp evidence rows written before the GraphQL body-picking fix
(commit 79aecd4) contain the subject property's Zillow data leaked
into every comp row (list=$1.3M, dom=4, etc. — all the same across
every comp). Rehydrating them from cache would bypass the new
scraping logic in deep_comp and feed bad data into the appraisal
engine.

This script deletes the comp:* EvidenceItems so the next Deep Comp
run does a fresh scrape with the fixed scraper. It leaves the
county_comp_enrichment SourceRecords untouched — that's pure
county data with no Zillow leak, and it's what pre-enrichment
uses to skip the slow Loudoun scrapes.

Run:
    python clear_comp_cache.py
"""

import asyncio
import sys


async def main():
    from sqlalchemy import delete, select
    from pipa.core.dependencies import get_session_factory
    from pipa.models.source import EvidenceItem

    factory = get_session_factory()
    async with factory() as db:
        # Count first
        count_rows = (await db.execute(
            select(EvidenceItem).where(EvidenceItem.field_name.like("comp:%"))
        )).scalars().all()
        total = len(count_rows)
        addresses = sorted({r.field_name for r in count_rows})

        print(f"Found {total} comp EvidenceItem rows across {len(addresses)} unique addresses:")
        for addr in addresses:
            count = sum(1 for r in count_rows if r.field_name == addr)
            dup_note = f" ({count} duplicates)" if count > 1 else ""
            print(f"  {addr}{dup_note}")

        if total == 0:
            print("Nothing to delete.")
            return

        # Delete
        result = await db.execute(
            delete(EvidenceItem).where(EvidenceItem.field_name.like("comp:%"))
        )
        await db.commit()
        print(f"\nDeleted {result.rowcount} rows.")
        print("Next Deep Comp run will do fresh pre-enrichment + Zillow scraping.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
