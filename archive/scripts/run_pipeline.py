"""Run the full 7-step pipeline for a Zillow listing.

Usage:
    python run_pipeline.py https://www.zillow.com/homedetails/.../12345_zpid/

Steps:
    0. Scrape Zillow (GraphQL interception)
    1. Scrape Loudoun County (all tabs)
    2. AI PASS 1: extract components/upgrades from description
    3. Deterministic resolver: merge sources → canonical values
    4. Pure math: financial, condition, offer, stress, tax
    5. Deterministic warning engine: blockers, pursue signal
    6. AI PASS 2: interpretation, narrative, questions
    7. Decision packet output
"""

import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def scrape_zillow(url: str) -> dict:
    """Step 0a: Scrape Zillow via GraphQL interception."""
    from playwright.async_api import async_playwright

    print("=" * 70)
    print("STEP 0a: SCRAPING ZILLOW")
    print("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        await ctx.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        )
        page = await ctx.new_page()

        graphql_data = []

        async def on_resp(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" in ct and resp.status == 200:
                    if "graphql" in resp.url or "async-create" in resp.url:
                        body = await resp.text()
                        if len(body) > 1000:
                            graphql_data.append(body)
            except Exception:
                pass

        page.on("response", on_resp)

        print(f"  Loading {url}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(10000)

        # CAPTCHA handling
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            px = await frame.query_selector("#px-captcha")
            if px:
                box = await px.bounding_box()
                if box and box["width"] < 600:
                    print("  CAPTCHA detected — solving...")
                    cx = box["x"] + box["width"] / 2
                    cy = box["y"] + box["height"] / 2
                    await page.mouse.move(cx - 20, cy)
                    await page.wait_for_timeout(200)
                    await page.mouse.move(cx, cy)
                    await page.wait_for_timeout(300)
                    await page.mouse.down()
                    await page.wait_for_timeout(12000)
                    await page.mouse.up()
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(8000)
                break

        # Scroll to trigger lazy loads
        for i in range(8):
            try:
                await page.evaluate(f"window.scrollTo(0, {(i + 1) * 800})")
                await page.wait_for_timeout(800)
            except Exception:
                break
        await page.wait_for_timeout(5000)

        # Also capture HTML for description/facts
        html = await page.content()

        # Use ZillowScraper's extraction methods
        from pipa.clients.scrapers.zillow import ZillowScraper

        scraper = ZillowScraper.__new__(ZillowScraper)
        result = scraper._extract_from_graphql(graphql_data)
        jsonld = scraper._extract_from_jsonld(html)
        html_data = scraper._extract_from_html(html)

        # Merge: GraphQL > JSON-LD > HTML
        for k, v in jsonld.items():
            if k not in result or result[k] is None:
                result[k] = v
        for k, v in html_data.items():
            if k not in result or result[k] is None:
                result[k] = v

        await browser.close()

        field_count = len([v for v in result.values() if v is not None])
        print(f"  Extracted {field_count} fields from Zillow")
        if result.get("price"):
            print(f"  Price: ${result['price']:,}")
        if result.get("assigned_schools"):
            for s in result["assigned_schools"]:
                print(f"  School: {s.get('name')} — {s.get('rating')}/10")
        elif result.get("nearby_schools"):
            for s in result["nearby_schools"]:
                print(f"  School: {s.get('name')} — {s.get('rating')}/10")
        if result.get("cdom"):
            print(f"  CDOM: {result['cdom']} days | Episodes: {result.get('listing_episodes_count')}")

        return result


async def scrape_county(address: str) -> dict:
    """Step 0b: Scrape Loudoun County assessment (all tabs)."""
    print()
    print("=" * 70)
    print("STEP 0b: SCRAPING LOUDOUN COUNTY")
    print("=" * 70)

    from pipa.clients.scrapers.loudoun_parcel import LoudounParcelScraper

    scraper = LoudounParcelScraper(headless=False)
    try:
        result = await scraper.scrape_by_address_string(address)
        if result.get("_error"):
            print(f"  County scrape failed: {result['_error']}")
        else:
            summary = result.get("_summary", {})
            print(f"  Parcel: {summary.get('parcel_id', '?')}")
            print(f"  Year built: {summary.get('year_built', '?')}")
            print(f"  Sqft above grade: {summary.get('sqft_above_grade', '?')}")
            print(f"  Assessed: ${summary.get('assessed_total', '?')}")
            print(f"  Subdivision: {summary.get('subdivision', '?')}")
        return result
    finally:
        await scraper.close()


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.zillow.com/homedetails/42580-Deer-Isle-Dr-Chantilly-VA-20152/251682872_zpid/"

    # Parse address from URL for county lookup
    addr_match = re.search(r"/homedetails/([\w-]+)/", url)
    if addr_match:
        parts = addr_match.group(1).replace("-", " ").split()
        # Find where state abbreviation is (usually second to last)
        address_parts = []
        for i, part in enumerate(parts):
            if part.upper() in ("VA", "MD", "DC"):
                address_parts = parts[:i]
                break
        address_str = " ".join(address_parts) if address_parts else " ".join(parts[:5])
    else:
        address_str = "42580 Deer Isle Dr"

    print(f"\nFULL PIPELINE for: {url}")
    print(f"Address: {address_str}")
    print()

    # ================================================================
    # STEP 0: SCRAPE BOTH SOURCES
    # ================================================================
    zillow_data = await scrape_zillow(url)
    county_data = await scrape_county(address_str)

    # Save raw scrape data
    with open("pipeline_zillow_raw.json", "w") as f:
        json.dump(zillow_data, f, indent=2, default=str)
    with open("pipeline_county_raw.json", "w") as f:
        json.dump(county_data, f, indent=2, default=str)

    # ================================================================
    # STEPS 1-7: RUN THE PIPELINE
    # ================================================================
    print()
    print("=" * 70)
    print("RUNNING 7-STEP PIPELINE")
    print("=" * 70)

    from pipa.services.pipeline import PropertyPipeline

    # Extract description for AI
    description = zillow_data.get("description", "")

    # County summary for easier access
    county_summary = county_data.get("_summary", {})
    county_residential = county_data.get("Residential", {}).get("_key_values", {})
    county_values = county_data.get("Values", {}).get("_key_values", {})
    county_flat = {}
    county_flat.update(county_summary)
    county_flat.update(county_residential)
    county_flat.update(county_values)

    # Current home for sell-vs-rent
    current_home = {
        "purchase_price": 550000,
        "estimated_value": 725000,
        "remaining_mortgage": 350000,
        "years_as_primary": 6,
        "estimated_monthly_rent": 3200,
    }

    result = await PropertyPipeline.run_full_pipeline(
        db=None,  # Pipeline works without DB for standalone mode
        property_id="standalone",
        listing_data=zillow_data,
        county_data=county_flat,
        description=description,
        current_home=current_home,
    )

    # Save full result
    with open("pipeline_result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    # ================================================================
    # PRINT THE DECISION PACKET
    # ================================================================
    print()
    print("=" * 70)
    print("DECISION PACKET")
    print("=" * 70)

    packet = result.get("step7_decision_packet", {})

    # Quick Take
    qt = packet.get("quick_take", {})
    print(f"\n--- QUICK TAKE ---")
    print(f"  Pursue signal: {qt.get('pursue_signal', '?').upper()}")
    print(f"  AI recommendation: {qt.get('ai_recommendation', '?')}")
    print(f"  AI summary: {qt.get('ai_summary', 'N/A')}")
    if qt.get("blockers"):
        print(f"  BLOCKERS:")
        for b in qt["blockers"]:
            print(f"    ! {b}")

    # Price View
    pv = packet.get("price_view", {})
    print(f"\n--- PRICE VIEW ---")
    if pv:
        print(f"  Ask: ${pv.get('asking_price', 0):,.0f}")
        if pv.get("ask_vs_zestimate_pct") is not None:
            print(f"  vs Zestimate: {pv['ask_vs_zestimate_pct']:+.1f}%")
        if pv.get("ask_vs_assessed_pct") is not None:
            print(f"  vs Assessment: {pv['ask_vs_assessed_pct']:+.1f}%")
        if pv.get("ask_vs_county_derived_pct") is not None:
            print(f"  vs Assessed+7%: {pv['ask_vs_county_derived_pct']:+.1f}%")
        if pv.get("county_derived_market_value"):
            print(f"  County-derived market: ${pv['county_derived_market_value']:,.0f}")

    # Monthly Cost
    mc = packet.get("monthly_cost", {})
    print(f"\n--- MONTHLY COST ---")
    for scenario, data in mc.items():
        if isinstance(data, dict):
            total = data.get("total")
            cash = data.get("cash_at_closing")
            if total:
                print(f"  {scenario}: ${total:,.0f}/mo (cash: ${cash:,.0f})")

    # Hidden Cost
    hc = packet.get("hidden_cost", {})
    print(f"\n--- HIDDEN COST ---")
    print(f"  Condition score: {hc.get('condition_score', '?')}/100")
    capex = hc.get("capex_forecast", {})
    for yr, cost in sorted(capex.items(), key=lambda x: int(x[0])):
        print(f"  Next {yr}yr: ${cost:,.0f}")
    if hc.get("ai_components"):
        print(f"  AI-extracted upgrades:")
        for comp in hc["ai_components"]:
            yr = comp.get("year", "?")
            print(f"    {comp.get('component', '?')}: {yr} ({comp.get('confidence', '?')})")

    # Offer Strategy
    offer = packet.get("offer_strategy", {})
    print(f"\n--- OFFER STRATEGY ---")
    if offer.get("max_bid"):
        bid = offer["max_bid"]
        print(f"  Max bid: ${bid.get('max_price', 0):,.0f} ({bid.get('limiting_factor', '?')})")
    if offer.get("appraisal_gap"):
        gap = offer["appraisal_gap"]
        print(f"  Appraisal gap: ${gap.get('gap_amount', 0):,.0f} ({gap.get('risk_level', '?')})")

    # Warnings
    warns = packet.get("warnings", {})
    print(f"\n--- WARNINGS ---")
    print(f"  Pursue signal: {warns.get('pursue_signal', '?').upper()}")
    for b in warns.get("blockers", []):
        print(f"  [BLOCKER] {b}")
    for w in warns.get("warnings", []):
        print(f"  [WARNING] {w}")
    for i in warns.get("info", []):
        print(f"  [INFO] {i}")

    # Conflicts from resolver
    conflicts = result.get("step3_conflicts", [])
    if conflicts:
        print(f"\n--- DATA CONFLICTS ({len(conflicts)}) ---")
        for c in conflicts:
            print(f"  {c.get('field')}: listing={c.get('conflicting_value')} vs county={c.get('canonical_value')} [{c.get('severity', 'warning')}]")

    # AI Interpretation
    ai = packet.get("ai_interpretation", {})
    if ai:
        print(f"\n--- AI INTERPRETATION ---")
        if ai.get("top_3_pros"):
            print("  Pros:")
            for p in ai["top_3_pros"]:
                print(f"    + {p}")
        if ai.get("top_3_cons"):
            print("  Cons:")
            for c in ai["top_3_cons"]:
                print(f"    - {c}")
        if ai.get("red_flags"):
            print("  Red flags:")
            for r in ai["red_flags"]:
                print(f"    ! {r}")
        if ai.get("questions_for_agent"):
            print("  Questions for agent:")
            for q in ai["questions_for_agent"]:
                print(f"    ? {q}")

    # Schools (from Zillow)
    schools = zillow_data.get("assigned_schools") or zillow_data.get("nearby_schools", [])
    if schools:
        print(f"\n--- SCHOOLS ---")
        for s in schools:
            print(f"  {s.get('level', '?')}: {s.get('name')} — {s.get('rating')}/10 ({s.get('distance_mi')} mi)")

    # CDOM / Listing History
    if zillow_data.get("cdom"):
        print(f"\n--- LISTING HISTORY ---")
        print(f"  DOM: {zillow_data.get('dom', zillow_data.get('days_on_zillow', '?'))}")
        print(f"  CDOM: {zillow_data['cdom']} days cumulative")
        print(f"  Episodes: {zillow_data.get('listing_episodes_count', '?')}")
        print(f"  Original ask: ${zillow_data.get('original_ask', 0):,}")
        print(f"  Total reduction: ${zillow_data.get('total_reduction', 0):,}")
        if zillow_data.get("was_relisted"):
            print(f"  *** WAS RELISTED ***")

    print(f"\n{'=' * 70}")
    print("PIPELINE COMPLETE")
    print(f"Full result saved to pipeline_result.json")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
