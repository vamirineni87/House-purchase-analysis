"""Scrape Zillow using GraphQL interception — capture the structured API response
that the browser naturally makes, then also parse HTML as fallback."""

import asyncio
import re
import json
from playwright.async_api import async_playwright


async def main():
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

        # Capture ALL JSON responses with their full bodies
        graphql_responses = []
        other_responses = []

        async def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" in ct and resp.status == 200:
                    body = await resp.text()
                    if len(body) > 200:
                        entry = {
                            "url": resp.url,
                            "size": len(body),
                            "body": body,
                        }
                        if "graphql" in resp.url or "zg-graph" in resp.url:
                            graphql_responses.append(entry)
                        elif "zillow" in resp.url:
                            other_responses.append(entry)
            except Exception:
                pass

        page.on("response", on_response)

        url = "https://www.zillow.com/homedetails/42580-Deer-Isle-Dr-Chantilly-VA-20152/251682872_zpid/"
        print(f"1. Loading {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)

        print("2. Waiting 10s for page + CAPTCHA check...")
        await page.wait_for_timeout(10000)

        # CAPTCHA handling
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            px = await frame.query_selector("#px-captcha")
            if px:
                box = await px.bounding_box()
                if box and box["width"] < 600:
                    cx = box["x"] + box["width"] / 2
                    cy = box["y"] + box["height"] / 2
                    print(f"   CAPTCHA found, pressing at ({cx:.0f}, {cy:.0f})...")
                    await page.mouse.move(cx - 30, cy)
                    await page.wait_for_timeout(200)
                    await page.mouse.move(cx, cy)
                    await page.wait_for_timeout(300)
                    await page.mouse.down()
                    await page.wait_for_timeout(12000)
                    await page.mouse.up()
                    print("   Released, waiting for page reload...")
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(10000)
                break

        # Scroll to trigger lazy-loaded API calls
        print("3. Scrolling to trigger all API calls...")
        for i in range(10):
            try:
                await page.evaluate(f"window.scrollTo(0, {(i + 1) * 800})")
                await page.wait_for_timeout(800)
            except Exception:
                # Page may have navigated, wait and retry
                await page.wait_for_timeout(2000)
                try:
                    await page.evaluate(f"window.scrollTo(0, {(i + 1) * 800})")
                except Exception:
                    break
        await page.wait_for_timeout(5000)

        print(f"4. Captured {len(graphql_responses)} GraphQL + {len(other_responses)} other responses")

        # =============================================
        # Find the MAIN GraphQL response with property data
        # =============================================
        main_graphql = None
        all_graphql_data = {}

        for resp in graphql_responses:
            body = resp["body"]
            # The main property response has bedrooms + bathrooms + price
            if '"bedrooms"' in body and '"bathrooms"' in body and '"price"' in body:
                if not main_graphql or resp["size"] > main_graphql["size"]:
                    main_graphql = resp

            # Parse ALL graphql responses and merge their data
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict) and "data" in parsed:
                    # Flatten the data
                    def flatten(d, prefix=""):
                        if isinstance(d, dict):
                            for k, v in d.items():
                                flatten(v, f"{prefix}.{k}" if prefix else k)
                        elif isinstance(d, list) and len(d) < 50:
                            for i, item in enumerate(d[:10]):
                                flatten(item, f"{prefix}[{i}]")
                        else:
                            all_graphql_data[prefix] = d
                    flatten(parsed["data"])
            except (json.JSONDecodeError, KeyError):
                pass

        # =============================================
        # Extract structured data from main GraphQL response
        # =============================================
        graphql_extracted = {}

        if main_graphql:
            print(f"\n5. Main GraphQL response: {main_graphql['size']:,} chars from {main_graphql['url'][:100]}")
            body = main_graphql["body"]

            # Save raw GraphQL response
            with open("zillow_graphql_raw.json", "w", encoding="utf-8") as f:
                try:
                    f.write(json.dumps(json.loads(body), indent=2))
                except json.JSONDecodeError:
                    f.write(body)
            print("   Saved raw to zillow_graphql_raw.json")

            # Extract fields
            field_patterns = [
                ("price", r'"price"\s*:\s*(\d+)'),
                ("bedrooms", r'"bedrooms"\s*:\s*(\d+)'),
                ("bathrooms", r'"bathrooms"\s*:\s*(\d+)'),
                ("fullBathrooms", r'"fullBathrooms"\s*:\s*(\d+)'),
                ("halfBathrooms", r'"halfBathrooms"\s*:\s*(\d+)'),
                ("livingArea", r'"livingArea"\s*:\s*(\d+)'),
                ("livingAreaAboveGrade", r'"aboveGradeFinishedArea"\s*:\s*"?(\d+)'),
                ("livingAreaBelowGrade", r'"belowGradeFinishedArea"\s*:\s*"?(\d+)'),
                ("yearBuilt", r'"yearBuilt"\s*:\s*(\d+)'),
                ("hoaFee", r'"hoaFee"\s*:\s*(\d+)'),
                ("monthlyHoaFee", r'"monthlyHoaFee"\s*:\s*(\d+)'),
                ("zestimate", r'"zestimate"\s*:\s*(\d+)'),
                ("rentZestimate", r'"rentZestimate"\s*:\s*(\d+)'),
                ("taxAnnualAmount", r'"taxAnnualAmount"\s*:\s*(\d+)'),
                ("taxAssessedValue", r'"taxAssessedValue"\s*:\s*(\d+)'),
                ("taxAssessedYear", r'"taxAssessedYear"\s*:\s*(\d+)'),
                ("homeStatus", r'"homeStatus"\s*:\s*"([^"]+)"'),
                ("homeType", r'"homeType"\s*:\s*"([^"]+)"'),
                ("daysOnZillow", r'"daysOnZillow"\s*:\s*(-?\d+)'),
                ("lotSize", r'"lotSize"\s*:\s*(\d+)'),
                ("lotAreaValue", r'"lotAreaValue"\s*:\s*([\d.]+)'),
                ("parcelId", r'"parcelId"\s*:\s*"([^"]+)"'),
                ("county", r'"county"\s*:\s*"([^"]+)"'),
                ("latitude", r'"latitude"\s*:\s*([\d.\-]+)'),
                ("longitude", r'"longitude"\s*:\s*([\d.\-]+)'),
                ("streetAddress", r'"streetAddress"\s*:\s*"([^"]+)"'),
                ("city", r'"city"\s*:\s*"([^"]+)"'),
                ("state", r'"state"\s*:\s*"([^"]+)"'),
                ("zipcode", r'"zipcode"\s*:\s*"([^"]+)"'),
                ("mlsId", r'"mlsId"\s*:\s*"([^"]+)"'),
                ("propertyTaxRate", r'"propertyTaxRate"\s*:\s*([\d.]+)'),
                ("timeOnZillow", r'"timeOnZillow"\s*:\s*"([^"]+)"'),
                ("pageViewCount", r'"pageViewCount"\s*:\s*(\d+)'),
                ("favoriteCount", r'"favoriteCount"\s*:\s*(\d+)'),
                ("brokerageName", r'"brokerageName"\s*:\s*"([^"]+)"'),
                ("agentName", r'"agentName"\s*:\s*"([^"]+)"'),
                ("agentPhoneNumber", r'"agentPhoneNumber"\s*:\s*"([^"]+)"'),
                ("listingSubType", r'"listingSubType"\s*:\s*\{[^}]*"is_([^"]+)"\s*:\s*true'),
                ("isNewConstruction", r'"isNewConstruction"\s*:\s*(true|false)'),
                ("contingentListingType", r'"contingentListingType"\s*:\s*"?([^",}]+)'),
            ]

            for name, pat in field_patterns:
                m = re.search(pat, body)
                if m:
                    graphql_extracted[name] = m.group(1)

            # Description
            desc = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', body)
            if desc:
                graphql_extracted["description"] = (
                    desc.group(1)
                    .replace("\\n", "\n")
                    .replace("\\u0027", "'")
                    .replace('\\"', '"')
                )

            # Price history
            # Look for priceHistory array
            ph_section = re.search(r'"priceHistory"\s*:\s*\[(.*?)\]', body, re.DOTALL)
            if ph_section:
                ph_items = re.findall(
                    r'\{[^}]*"date"\s*:\s*"([^"]+)"[^}]*"price"\s*:\s*(\d+)[^}]*"event"\s*:\s*"([^"]+)"[^}]*\}',
                    ph_section.group(1),
                )
                if not ph_items:
                    # Try alternate order
                    ph_items = re.findall(
                        r'\{[^}]*"event"\s*:\s*"([^"]+)"[^}]*"date"\s*:\s*"([^"]+)"[^}]*"price"\s*:\s*(\d+)[^}]*\}',
                        ph_section.group(1),
                    )
                    ph_items = [(d, p, e) for e, d, p in ph_items]
                graphql_extracted["priceHistory"] = [
                    {"date": d, "price": int(p), "event": e}
                    for d, p, e in ph_items
                ]

            # Tax history
            th_section = re.search(r'"taxHistory"\s*:\s*\[(.*?)\]', body, re.DOTALL)
            if th_section:
                th_items = re.findall(
                    r'"time"\s*:\s*(\d+)[^}]*"taxPaid"\s*:\s*([\d.]+)[^}]*"value"\s*:\s*(\d+)',
                    th_section.group(1),
                )
                graphql_extracted["taxHistory"] = [
                    {"year": int(t) // 1000 if int(t) > 100000 else int(t), "taxPaid": float(tp), "assessedValue": int(v)}
                    for t, tp, v in th_items
                ]

            # Schools
            school_section = re.findall(
                r'"schoolName"\s*:\s*"([^"]+)"[^}]*?"rating"\s*:\s*(\d+)[^}]*?"distance"\s*:\s*([\d.]+)[^}]*?"level"\s*:\s*"([^"]+)"',
                body,
            )
            if school_section:
                graphql_extracted["schools"] = [
                    {"name": n, "rating": int(r), "distance": float(d), "level": l}
                    for n, r, d, l in school_section
                ]

        # =============================================
        # Also check other Zillow responses for extra data
        # =============================================
        for resp in other_responses:
            if "async-create-search-page" in resp["url"]:
                body = resp["body"]
                for name, pat in [
                    ("zestimate_search", r'"zestimate"\s*:\s*(\d+)'),
                    ("rentZestimate_search", r'"rentZestimate"\s*:\s*(\d+)'),
                ]:
                    m = re.search(pat, body)
                    if m:
                        graphql_extracted[name] = m.group(1)

        # =============================================
        # Print results
        # =============================================
        print("\n" + "=" * 80)
        print("GRAPHQL EXTRACTED DATA")
        print("=" * 80)

        for k, v in sorted(graphql_extracted.items()):
            if k == "description":
                print(f"  {k}: {str(v)[:200]}...")
            elif k in ("priceHistory", "taxHistory", "schools"):
                print(f"  {k}:")
                for item in v:
                    print(f"    {item}")
            elif k in ("price", "zestimate", "rentZestimate", "taxAnnualAmount",
                       "taxAssessedValue", "lotSize", "zestimate_search", "rentZestimate_search"):
                print(f"  {k}: ${int(v):,}")
            elif k in ("hoaFee", "monthlyHoaFee"):
                print(f"  {k}: ${v}/mo")
            else:
                print(f"  {k}: {v}")

        # Save
        output = {
            "_source": "zillow_graphql",
            "_method": "browser_graphql_interception",
            "graphql_data": graphql_extracted,
            "graphql_response_count": len(graphql_responses),
            "other_response_count": len(other_responses),
        }
        with open("zillow_graphql_extracted.json", "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str, ensure_ascii=False)
        print(f"\nSaved to zillow_graphql_extracted.json")

        # =============================================
        # Compare: what GraphQL has that HTML doesn't
        # =============================================
        html_fields = {"price", "beds", "baths", "sqft", "year_built", "lot_acres",
                       "hoa", "mls", "parcel", "walk_score", "description", "schools",
                       "agent", "broker", "photos", "price_history_partial", "tax_history_partial",
                       "fireplace", "basement", "central_ac", "heating", "construction"}

        graphql_only = set(graphql_extracted.keys()) - html_fields
        print(f"\n=== GRAPHQL-ONLY FIELDS (not in HTML) ===")
        for f in sorted(graphql_only):
            v = graphql_extracted[f]
            if isinstance(v, (list, dict)):
                print(f"  {f}: [{len(v)} items]")
            else:
                print(f"  {f}: {v}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
