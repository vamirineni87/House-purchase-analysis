"""Deep Zillow scrape — inspect API responses + __NEXT_DATA__ + page content."""

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

        # Capture all sizable JSON responses
        responses = []

        async def on_resp(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" in ct and resp.status == 200:
                    body = await resp.text()
                    if len(body) > 500:
                        responses.append({"url": resp.url, "size": len(body), "body": body})
            except Exception:
                pass

        page.on("response", on_resp)

        print("1. Loading Zillow...")
        await page.goto(
            "https://www.zillow.com/homedetails/42580-Deer-Isle-Dr-Chantilly-VA-20152/251682872_zpid/",
            wait_until="domcontentloaded",
            timeout=45000,
        )

        print("2. Waiting 10s for page + potential CAPTCHA...")
        await page.wait_for_timeout(10000)

        # Handle captcha if present
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            px = await frame.query_selector("#px-captcha")
            if px:
                box = await px.bounding_box()
                if box and box["width"] < 600:
                    cx = box["x"] + box["width"] / 2
                    cy = box["y"] + box["height"] / 2
                    print(f"   CAPTCHA found, holding at ({cx:.0f}, {cy:.0f})...")
                    await page.mouse.move(cx, cy)
                    await page.mouse.down()
                    await page.wait_for_timeout(12000)
                    await page.mouse.up()
                    print("   Released, waiting 10s...")
                    await page.wait_for_timeout(10000)
                break

        # Scroll to trigger lazy loading
        print("3. Scrolling page to trigger lazy loads...")
        for i in range(8):
            await page.evaluate(f"window.scrollTo(0, {(i + 1) * 800})")
            await page.wait_for_timeout(1000)

        # Wait for more API calls
        await page.wait_for_timeout(5000)

        content = await page.content()
        print(f"4. Page: {len(content):,} chars | API responses: {len(responses)}")

        # =============================================
        # Check API responses for property data
        # =============================================
        print("\n=== API RESPONSES ===")
        property_keywords = ["bedrooms", "bathrooms", "livingArea", "yearBuilt", "hoaFee", "zestimate"]
        for r in responses:
            has_prop_data = any(kw in r["body"] for kw in property_keywords)
            if has_prop_data:
                print(f"\n  PROPERTY DATA FOUND in: {r['url'][:120]}")
                print(f"  Size: {r['size']:,} chars")
                for pat, name in [
                    (r'"bedrooms":(\d+)', "beds"),
                    (r'"bathrooms":(\d+)', "baths"),
                    (r'"livingArea":(\d+)', "sqft"),
                    (r'"yearBuilt":(\d+)', "yearBuilt"),
                    (r'"hoaFee":(\d+)', "hoaFee"),
                    (r'"zestimate":(\d+)', "zestimate"),
                    (r'"rentZestimate":(\d+)', "rentZestimate"),
                    (r'"daysOnZillow":(-?\d+)', "DOM"),
                    (r'"homeStatus":"([^"]+)"', "status"),
                    (r'"homeType":"([^"]+)"', "homeType"),
                    (r'"taxAnnualAmount":(\d+)', "annualTax"),
                    (r'"taxAssessedValue":(\d+)', "taxAssessed"),
                    (r'"lotSize":(\d+)', "lotSize"),
                    (r'"parcelId":"([^"]+)"', "parcel"),
                ]:
                    m = re.search(pat, r["body"])
                    if m:
                        print(f"    {name}: {m.group(1)}")
            else:
                # Just show URL for non-property responses
                if "zillow" in r["url"]:
                    print(f"  other: {r['url'][:100]} ({r['size']:,} chars)")

        # =============================================
        # Check __NEXT_DATA__
        # =============================================
        print("\n=== __NEXT_DATA__ ===")
        nd_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', content, re.DOTALL)
        if nd_match:
            nd_text = nd_match.group(1)
            print(f"Found: {len(nd_text):,} chars")
            try:
                nd = json.loads(nd_text)
                props = nd.get("props", {}).get("pageProps", {})
                print(f"pageProps keys: {list(props.keys())[:20]}")

                # Deep search for property fields
                def find_key(d, key, depth=0):
                    if depth > 10:
                        return None
                    if isinstance(d, dict):
                        if key in d:
                            return d[key]
                        for v in d.values():
                            r = find_key(v, key, depth + 1)
                            if r is not None:
                                return r
                    elif isinstance(d, list):
                        for item in d[:5]:
                            r = find_key(item, key, depth + 1)
                            if r is not None:
                                return r
                    return None

                for key in [
                    "bedrooms", "bathrooms", "livingArea", "yearBuilt", "price",
                    "zestimate", "hoaFee", "homeStatus", "daysOnZillow", "lotSize",
                    "homeType", "taxAnnualAmount", "parcelId", "description",
                    "rentZestimate", "county", "mlsid",
                ]:
                    val = find_key(nd, key)
                    if val is not None:
                        if isinstance(val, str) and len(val) > 100:
                            print(f"  {key}: {val[:100]}...")
                        else:
                            print(f"  {key}: {val}")
            except json.JSONDecodeError as e:
                print(f"  Parse error: {e}")
        else:
            print("Not found")

        # =============================================
        # Search raw page for data patterns
        # =============================================
        print("\n=== RAW PAGE SEARCH ===")
        # Zillow might embed data in different formats
        # Try gdpClientCache pattern
        cache_match = re.search(r'"gdpClientCache":\s*"(.*?)"(?:,|})', content)
        if cache_match:
            cache_text = cache_match.group(1).replace('\\"', '"').replace("\\\\", "\\")
            print(f"gdpClientCache: {len(cache_text):,} chars")
            for pat, name in [
                (r'"bedrooms":(\d+)', "beds"),
                (r'"bathrooms":(\d+)', "baths"),
                (r'"livingArea":(\d+)', "sqft"),
                (r'"yearBuilt":(\d+)', "yearBuilt"),
                (r'"hoaFee":(\d+)', "hoaFee"),
                (r'"zestimate":(\d+)', "zestimate"),
                (r'"daysOnZillow":(-?\d+)', "DOM"),
                (r'"homeStatus":"([^"]+)"', "status"),
                (r'"homeType":"([^"]+)"', "homeType"),
                (r'"taxAnnualAmount":(\d+)', "annualTax"),
                (r'"lotSize":(\d+)', "lotSize"),
                (r'"parcelId":"([^"]+)"', "parcel"),
            ]:
                m = re.search(pat, cache_text)
                if m:
                    print(f"  {name}: {m.group(1)}")
        else:
            print("No gdpClientCache found")

        # Try apiCache pattern
        api_cache = re.search(r'"apiCache":\s*"(.*?)"(?:,|})', content)
        if api_cache:
            api_text = api_cache.group(1).replace('\\"', '"').replace("\\\\", "\\")
            print(f"\napiCache: {len(api_text):,} chars")
            for pat, name in [
                (r'"bedrooms":(\d+)', "beds"),
                (r'"bathrooms":(\d+)', "baths"),
                (r'"livingArea":(\d+)', "sqft"),
                (r'"yearBuilt":(\d+)', "yearBuilt"),
                (r'"zestimate":(\d+)', "zestimate"),
            ]:
                m = re.search(pat, api_text)
                if m:
                    print(f"  {name}: {m.group(1)}")

        # Save a snippet of the page for debugging
        with open("zillow_debug.txt", "w", encoding="utf-8") as f:
            # Save first occurrence of each key pattern location
            for kw in ["bedrooms", "bathrooms", "yearBuilt", "livingArea", "zestimate"]:
                idx = content.find(kw)
                if idx >= 0:
                    snippet = content[max(0, idx - 100):idx + 200]
                    f.write(f"\n=== {kw} at {idx} ===\n{snippet}\n")

        print("\nDebug saved to zillow_debug.txt")
        await page.screenshot(path="zillow_result.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
