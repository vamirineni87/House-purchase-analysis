"""Scrape Zillow + Loudoun County for 42459 Belmont Glen Pl, Ashburn VA 20148."""

import asyncio
import re
import json
from playwright.async_api import async_playwright


async def scrape_zillow():
    """Scrape Zillow via GraphQL interception."""
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

        print("ZILLOW: Loading...")
        await page.goto(
            "https://www.zillow.com/homedetails/42459-Belmont-Glen-Pl-Ashburn-VA-20148/61201516_zpid/",
            wait_until="domcontentloaded",
            timeout=45000,
        )
        await page.wait_for_timeout(10000)

        # CAPTCHA
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            px = await frame.query_selector("#px-captcha")
            if px:
                box = await px.bounding_box()
                if box and box["width"] < 600:
                    print("ZILLOW: CAPTCHA found, solving...")
                    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    await page.mouse.down()
                    await page.wait_for_timeout(12000)
                    await page.mouse.up()
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(8000)
                break

        # Scroll
        for i in range(8):
            try:
                await page.evaluate(f"window.scrollTo(0, {(i + 1) * 800})")
                await page.wait_for_timeout(800)
            except Exception:
                break
        await page.wait_for_timeout(5000)

        # Extract from GraphQL
        result = {}
        main = None
        search = None
        for body in graphql_data:
            if '"bedrooms"' in body and '"price"' in body:
                if not main or len(body) > len(main):
                    main = body
            if '"zestimate"' in body and '"rentZestimate"' in body:
                search = body

        if main:
            for pat, name, convert in [
                (r'"price":(\d+)', "price", int),
                (r'"bedrooms":(\d+)', "beds", int),
                (r'"bathrooms":(\d+)', "baths", int),
                (r'"livingArea":(\d+)', "sqft", int),
                (r'"yearBuilt":(\d+)', "year_built", int),
                (r'"hoaFee":(\d+)', "hoa", int),
                (r'"taxAnnualAmount":(\d+)', "annual_tax", int),
                (r'"taxAssessedValue":(\d+)', "tax_assessed", int),
                (r'"homeStatus":"([^"]+)"', "status", str),
                (r'"daysOnZillow":(-?\d+)', "dom", int),
                (r'"lotSize":(\d+)', "lot_sqft", int),
                (r'"parcelId":"([^"]+)"', "parcel", str),
                (r'"homeType":"([^"]+)"', "type", str),
                (r'"county":"([^"]+)"', "county", str),
            ]:
                m = re.search(pat, main)
                if m:
                    result[name] = convert(m.group(1))

            # Price history
            ph = re.findall(
                r'"date":"([^"]+)".*?"price":(\d+).*?"event":"([^"]*)"',
                main[:200000],
            )
            if ph:
                result["price_history"] = [
                    {"date": d, "price": int(p), "event": e} for d, p, e in ph
                ]

        if search:
            zest = re.search(r'"zestimate":(\d+)', search)
            rent = re.search(r'"rentZestimate":(\d+)', search)
            if zest:
                result["zestimate"] = int(zest.group(1))
            if rent:
                result["rent_zestimate"] = int(rent.group(1))

        # Also extract from HTML for beds/baths if missing
        content = await page.content()
        facts = re.findall(
            r'data-testid="bed-bath-sqft-fact-container"[^>]*>.*?'
            r'<span[^>]*>([\d,\.]+)</span>\s*<span[^>]*>(\w+)</span>',
            content,
        )
        for val, label in facts:
            if label == "beds" and "beds" not in result:
                result["beds"] = int(val.replace(",", ""))
            elif label == "baths" and "baths" not in result:
                result["baths"] = int(val.replace(",", ""))
            elif label == "sqft" and "sqft" not in result:
                result["sqft"] = int(val.replace(",", ""))

        await browser.close()
        return result


async def scrape_county(number, street, suffix):
    """Scrape Loudoun County assessment."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print("COUNTY: Searching...")
        await page.goto(
            "https://reparcelasmt.loudoun.gov/pt/search/commonsearch.aspx?mode=address",
            timeout=30000,
        )
        await page.wait_for_timeout(2000)
        await page.fill("#inpNumber", number)
        await page.fill("#inpStreet", street)
        sel = await page.query_selector("#Select1")
        if sel and suffix:
            await sel.select_option(suffix)
        await page.evaluate("""
            document.getElementById('hdAction').value = 'Search';
            document.forms[0].submit();
        """)
        await page.wait_for_timeout(5000)

        result = {}
        if "Datalet" not in page.url:
            result["_error"] = "not_found"
            await browser.close()
            return result

        print("COUNTY: Found property, extracting tabs...")

        # Helper to extract key fields
        async def get_tab(tab_name):
            link = await page.query_selector(f'a:has-text("{tab_name}")')
            if link:
                await link.click()
                await page.wait_for_timeout(3000)
            content = await page.content()
            return content

        # Profile
        content = await page.content()
        for pat, name in [
            (r'PARID:\s*([\d]+)', "parcel_id"),
            (r'Subdivision\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "subdivision"),
        ]:
            m = re.search(pat, content)
            if m:
                result[name] = m.group(1).strip()

        # Values
        content = await get_tab("Values")
        for pat, name in [
            (r'Fair Market Land\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "land_value"),
            (r'Fair Market Building\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "building_value"),
            (r'Fair Market Total\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "total_value"),
            (r'Total Taxable Value\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "taxable_value"),
        ]:
            m = re.search(pat, content)
            if m:
                result[name] = m.group(1).strip()

        # Residential
        content = await get_tab("Residential")
        for pat, name in [
            (r'Year Built\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "year_built"),
            (r'Net SFLA[^<]*</td[^>]*>\s*<td[^>]*>([\d,]+)', "sqft_above_grade"),
            (r'Style\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "style"),
            (r'Model\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "model"),
            (r'Full Baths\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "full_baths"),
            (r'Half Baths\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "half_baths"),
            (r'Condition\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "condition"),
            (r'Grade\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "grade"),
            (r'Roof Material\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "roof_material"),
            (r'Roof Type\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "roof_type"),
            (r'Exterior Wall[^<]*</td[^>]*>\s*<td[^>]*>([^<]+)', "exterior"),
            (r'Heating/AC\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "heating_ac"),
            (r'Total Basement Area\s*</td[^>]*>\s*<td[^>]*>([\d,]+)', "basement_total"),
            (r'Finished Basement[^<]*</td[^>]*>\s*<td[^>]*>([\d,]+)', "basement_finished"),
            (r'Basement Entrance\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "basement_entrance"),
            (r'Total Fireplaces\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "fireplaces"),
            (r'Story Height\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "stories"),
            (r'Foundation Type\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "foundation"),
        ]:
            m = re.search(pat, content)
            if m:
                result[name] = m.group(1).strip()

        # Sales
        content = await get_tab("Sales")
        for pat, name in [
            (r'Sale Date\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "sale_date"),
            (r'Sale Price\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "sale_price"),
            (r'Seller\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "seller"),
        ]:
            m = re.search(pat, content)
            if m:
                result[name] = m.group(1).strip()

        # Land
        content = await get_tab("Land")
        for pat, name in [
            (r'Primary Zoning\s*</td[^>]*>\s*<td[^>]*>([^<]+)', "zoning"),
            (r'Square Feet\s*</td[^>]*>\s*<td[^>]*>([\d,]+)', "land_sqft"),
            (r'Acres\s*</td[^>]*>\s*<td[^>]*>([\d.]+)', "land_acres"),
        ]:
            m = re.search(pat, content)
            if m:
                result[name] = m.group(1).strip()

        await browser.close()
        return result


async def main():
    # Run both scrapes
    print("Scraping Zillow + County for 42459 Belmont Glen Pl...")
    zillow, county = await asyncio.gather(
        scrape_zillow(),
        scrape_county("42459", "BELMONT GLEN", "PL"),
    )

    # Save raw data
    with open("belmont_glen_zillow.json", "w") as f:
        json.dump(zillow, f, indent=2, default=str)
    with open("belmont_glen_county.json", "w") as f:
        json.dump(county, f, indent=2, default=str)

    print("\n" + "=" * 90)
    print("42459 Belmont Glen Pl, Ashburn VA 20148")
    print("=" * 90)

    print("\nZILLOW:")
    for k, v in sorted(zillow.items()):
        if k == "price_history":
            print(f"  {k}:")
            for ph in v:
                print(f"    {ph['date']}: ${ph['price']:,} ({ph['event']})")
        elif isinstance(v, (int, float)) and k in ("price", "zestimate", "rent_zestimate", "annual_tax", "tax_assessed", "lot_sqft", "hoa"):
            print(f"  {k}: ${v:,}")
        else:
            print(f"  {k}: {v}")

    print("\nCOUNTY:")
    for k, v in sorted(county.items()):
        if not k.startswith("_"):
            print(f"  {k}: {v}")

    # Cross-reference
    print("\nCROSS-REFERENCE:")
    z_sqft = zillow.get("sqft", 0)
    c_sqft = int(county.get("sqft_above_grade", "0").replace(",", "")) if county.get("sqft_above_grade") else 0
    c_bsmt = int(county.get("basement_total", "0").replace(",", "")) if county.get("basement_total") else 0
    c_bsmt_fin = int(county.get("basement_finished", "0").replace(",", "")) if county.get("basement_finished") else 0
    print(f"  sqft: Zillow={z_sqft} vs County above-grade={c_sqft} + bsmt_fin={c_bsmt_fin} = {c_sqft + c_bsmt_fin}")
    print(f"  bsmt unfinished: {c_bsmt - c_bsmt_fin}")

    # Price benchmarks
    price = zillow.get("price", 0)
    assessed = int(county.get("total_value", "$0").replace("$", "").replace(",", "")) if county.get("total_value") else 0
    zest = zillow.get("zestimate", 0)
    if price and assessed:
        derived = assessed * 1.07
        print(f"\n  PRICE BENCHMARKS:")
        print(f"    Ask: ${price:,}")
        print(f"    vs Zestimate: ${price - zest:+,} ({(price/zest - 1)*100:+.1f}%)" if zest else "")
        print(f"    vs Assessment: ${price - assessed:+,} ({(price/assessed - 1)*100:+.1f}%)")
        print(f"    vs Assessed+7%: ${price - derived:+,.0f} ({(price/derived - 1)*100:+.1f}%)")
        print(f"    County-derived market: ${derived:,.0f}")


if __name__ == "__main__":
    asyncio.run(main())
