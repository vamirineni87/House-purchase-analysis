"""Scrape Zillow listing with visible browser + CAPTCHA handling."""

import asyncio
import re
import json
from playwright.async_api import async_playwright


async def find_captcha(page):
    """Try multiple methods to locate the Press & Hold button.

    Returns (element, frame) — frame is needed so we can interact
    within the correct browsing context.
    """
    # Method 1: button directly on main page
    btn = await page.query_selector('button:has-text("Press & Hold")')
    if btn:
        print("   Found button on main page")
        return btn, page

    # Method 2: PerimeterX element on main page
    px = await page.query_selector("#px-captcha")
    if px:
        print("   Found #px-captcha on main page")
        return px, page

    # Method 3: search INSIDE iframes for the actual button
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            # Look for the Press & Hold button inside this frame
            btn = await frame.query_selector('button:has-text("Press & Hold")')
            if btn:
                print(f"   Found button inside iframe: {frame.url[:80]}")
                return btn, frame

            # Look for #px-captcha inside frame
            px = await frame.query_selector("#px-captcha")
            if px:
                print(f"   Found #px-captcha inside iframe: {frame.url[:80]}")
                return px, frame

            # Look for any pressable element with "hold" text
            hold = await frame.query_selector('text=Hold')
            if hold:
                print(f"   Found 'Hold' text inside iframe: {frame.url[:80]}")
                return hold, frame
        except Exception:
            pass

    # Method 4: look for the captcha iframe itself and interact with its center
    # PerimeterX typically uses an iframe — find it and click its center
    for sel in ["iframe[src*='captcha']", "iframe[src*='perim']", "iframe[src*='px-']",
                "iframe[title*='challenge']", "iframe[title*='Human']"]:
        iframe_el = await page.query_selector(sel)
        if iframe_el:
            print(f"   Found captcha iframe via {sel}")
            return iframe_el, page

    # Method 5: look for visible challenge overlay div
    for sel in ["#px-captcha-wrapper", "[class*='challenge']", "[class*='Captcha']"]:
        el = await page.query_selector(sel)
        if el:
            vis = await el.is_visible()
            if vis:
                print(f"   Found visible challenge: {sel}")
                return el, page

    return None, None


async def solve_captcha(page, el):
    """Press and hold on the CAPTCHA element using the main page mouse.

    Even if the element is inside an iframe, bounding_box() returns
    coordinates relative to the main page viewport, so we always use
    page.mouse (not frame.mouse).
    """
    box = await el.bounding_box()
    if not box:
        print("   No bounding box for captcha element")
        return False

    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    w, h = box["width"], box["height"]
    print(f"   Element at ({cx:.0f}, {cy:.0f}), size {w:.0f}x{h:.0f}")

    # If the element is the full page, it matched the iframe container
    # not the button — try to click center-ish where the button usually is
    if w > 500 and h > 500:
        print("   Element is full-page (iframe container) — targeting center button area")
        # PerimeterX button is usually centered, roughly 280x50
        cx = box["x"] + box["width"] / 2
        cy = box["y"] + box["height"] / 2 + 30  # slightly below center

    # Human-like approach to the button
    await page.mouse.move(cx - 40, cy - 20)
    await page.wait_for_timeout(200)
    await page.mouse.move(cx - 10, cy - 5)
    await page.wait_for_timeout(150)
    await page.mouse.move(cx, cy)
    await page.wait_for_timeout(400)

    print(f"   Pressing and holding at ({cx:.0f}, {cy:.0f}) for 12s...")
    await page.mouse.down()
    await page.wait_for_timeout(12000)
    await page.mouse.up()
    print("   Released!")
    await page.wait_for_timeout(5000)
    return True


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        await ctx.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        )
        page = await ctx.new_page()

        # Capture JSON API responses
        api_data = {}

        async def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" in ct and resp.status == 200:
                    body = await resp.json()
                    api_data[resp.url[:200]] = body
            except Exception:
                pass

        page.on("response", on_response)

        url = "https://www.zillow.com/homedetails/42580-Deer-Isle-Dr-Chantilly-VA-20152/251682872_zpid/"
        print(f"1. Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)

        print("2. Waiting 10s for page + potential CAPTCHA...")
        await page.wait_for_timeout(10000)

        # CAPTCHA detection + solving loop
        for attempt in range(3):
            captcha_el, captcha_frame = await find_captcha(page)
            if not captcha_el:
                print(f"   Attempt {attempt+1}: No CAPTCHA found")
                break
            print(f"3. CAPTCHA found (attempt {attempt+1}), solving...")
            solved = await solve_captcha(page, captcha_el)
            if not solved:
                break
            # Check if cleared
            await page.wait_for_timeout(3000)
            still, _ = await find_captcha(page)
            if not still:
                print("   CAPTCHA CLEARED!")
                # Wait for the real page to load now
                print("   Waiting 10s for content to load...")
                await page.wait_for_timeout(10000)
                break
            else:
                print("   CAPTCHA still present, retrying...")

        # Extract data from page content
        content = await page.content()
        print(f"4. Extracting from {len(content):,} chars...")

        data = {}
        patterns = [
            (r'"price":(\d+)', "price"),
            (r'"bedrooms":(\d+)', "beds"),
            (r'"bathrooms":(\d+\.?\d*)', "baths"),
            (r'"livingArea":(\d+)', "sqft"),
            (r'"yearBuilt":(\d+)', "year_built"),
            (r'"hoaFee":(\d+)', "hoa"),
            (r'"monthlyHoaFee":(\d+)', "hoa_alt"),
            (r'"zestimate":(\d+)', "zestimate"),
            (r'"rentZestimate":(\d+)', "rent_zestimate"),
            (r'"taxAnnualAmount":(\d+)', "annual_tax"),
            (r'"taxAssessedValue":(\d+)', "tax_assessed"),
            (r'"taxAssessedYear":(\d+)', "tax_assessed_year"),
            (r'"homeStatus":"([^"]+)"', "status"),
            (r'"daysOnZillow":(-?\d+)', "days_on_zillow"),
            (r'"lotSize":(\d+)', "lot_sqft"),
            (r'"lotAreaValue":([\d\.]+)', "lot_acres"),
            (r'"parcelId":"([^"]+)"', "parcel_id"),
            (r'"homeType":"([^"]+)"', "home_type"),
            (r'"county":"([^"]+)"', "county"),
            (r'"latitude":([\d\.\-]+)', "lat"),
            (r'"longitude":([\d\.\-]+)', "lon"),
            (r'"mlsid":"([^"]+)"', "mls"),
        ]
        for pattern, key in patterns:
            m = re.search(pattern, content)
            if m:
                data[key] = m.group(1)

        # Description
        desc = re.search(r'"description":"((?:[^"\\]|\\.)*)"', content)
        if desc:
            data["description"] = (
                desc.group(1)
                .replace("\\n", " ")
                .replace("\\u0027", "'")[:400]
            )

        # Price history
        price_events = re.findall(
            r'"date":"([^"]+)"[^}]*?"price":(\d+)[^}]*?"event":"([^"]+)"',
            content[:300000],
        )

        # Schools
        schools = re.findall(
            r'"name":"([^"]+)"[^}]*?"rating":(\d+)[^}]*?"distance":([\d\.]+)',
            content[:300000],
        )

        print()
        print("=" * 70)
        print("ZILLOW DATA: 42580 Deer Isle Dr, Chantilly VA 20152")
        print("=" * 70)

        if len(data) <= 3:
            print("LIMITED DATA extracted. Zillow may have blocked content.")
            print(f"Fields found: {list(data.keys())}")
            print(f"API responses captured: {len(api_data)}")
            for url_key in list(api_data.keys())[:5]:
                d = api_data[url_key]
                if isinstance(d, dict):
                    print(f"  {url_key}")
                    print(f"    keys: {list(d.keys())[:10]}")
        else:
            money_fields = {"price", "zestimate", "annual_tax", "lot_sqft", "rent_zestimate", "tax_assessed"}
            for k, v in sorted(data.items()):
                if k == "description":
                    print(f"  {k}: {v[:200]}...")
                elif k in money_fields:
                    print(f"  {k}: ${int(v):,}")
                elif k in ("hoa", "hoa_alt"):
                    print(f"  {k}: ${v}/mo")
                else:
                    print(f"  {k}: {v}")

            if price_events:
                print("  price_history:")
                seen = set()
                for date, price, event in price_events[:15]:
                    key = f"{date}|{price}"
                    if key not in seen:
                        seen.add(key)
                        print(f"    {date} | {event} | ${int(price):,}")

            if schools:
                print("  schools:")
                seen = set()
                for name, rating, dist in schools[:8]:
                    if name not in seen:
                        seen.add(name)
                        print(f"    {name}: {rating}/10 ({dist} mi)")

        print(f"\n  API responses captured: {len(api_data)}")

        await page.screenshot(path="zillow_result.png")
        print("  Screenshot saved: zillow_result.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
