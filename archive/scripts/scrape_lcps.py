"""Explore and scrape LCPS School Locator Dashboard interactively.

Keep browser open, explore the Qlik dashboard, learn the structure,
then extract school assignments for 42580 Deer Isle Dr.
"""

import asyncio
import json
import re
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # ---- LOAD ----
        print("Loading LCPS School Locator...")
        await page.goto(
            "https://dashboards.lcps.org/extensions/Dashboards/Label.html",
            timeout=30000,
        )
        await page.wait_for_timeout(8000)

        # ---- EXPLORE: what's on the page? ----
        print("\n--- PAGE STRUCTURE ---")
        content = await page.content()
        print(f"Page size: {len(content):,} chars")

        # Find all Qlik visualization objects
        qlik_objs = await page.query_selector_all(".qv-object")
        print(f"Qlik objects: {len(qlik_objs)}")
        for i, obj in enumerate(qlik_objs):
            text = (await obj.text_content() or "").strip()
            cls = await obj.get_attribute("class") or ""
            if text and len(text) < 500:
                clean = re.sub(r"\s+", " ", text)[:120]
                print(f"  obj[{i}]: {clean}")

        # ---- FIND THE ADDRESS FILTER ----
        print("\n--- FINDING ADDRESS FILTER ---")

        # Scroll down to see the filter
        await page.evaluate("window.scrollTo(0, 500)")
        await page.wait_for_timeout(1000)

        # The address filter is a folded-listbox — click to expand
        folded = await page.query_selector(".folded-listbox")
        if folded:
            print("Found folded-listbox, clicking to expand...")
            await folded.click()
            await page.wait_for_timeout(2000)

        # Now look for the search input
        search = await page.query_selector('input[placeholder*="Search"]')
        if not search:
            search = await page.query_selector("input.MuiInputBase-input")
        if not search:
            for inp in await page.query_selector_all("input"):
                if await inp.is_visible():
                    search = inp
                    break

        if search:
            print("Found search input!")
        else:
            print("No search input found, trying alternative...")
            # Maybe we need to click a specific element first
            addr_title = await page.query_selector('[title*="Address"]')
            if addr_title:
                await addr_title.click()
                await page.wait_for_timeout(2000)
                search = await page.query_selector("input")

        # ---- TYPE ADDRESS AND OBSERVE ----
        if search:
            print("\n--- SEARCHING FOR ADDRESS ---")
            await search.fill("42580 DEER ISLE")
            await page.wait_for_timeout(3000)

            # What appeared? Look for list items
            print("Looking for results...")

            # Qlik listbox items
            for selector in [
                "[role='option']",
                "[role='row']",
                "[role='listitem']",
                ".qv-listbox-item",
                "[class*='Row']",
                "[class*='listbox'] [class*='row']",
                "[class*='RowColumn']",
            ]:
                items = await page.query_selector_all(selector)
                if items:
                    print(f"  {selector}: {len(items)} items")
                    for item in items[:5]:
                        text = (await item.text_content() or "").strip()
                        if text:
                            print(f"    '{text}'")

            # Take screenshot to see what's showing
            await page.screenshot(path="lcps_search_results.png")
            print("  Screenshot: lcps_search_results.png")

            # Try to find and click the address in the dropdown
            # Look for any text containing our address
            addr_el = await page.query_selector("text=42580 DEER ISLE DR")
            if addr_el:
                print("Found exact match, clicking...")
                await addr_el.click()
                await page.wait_for_timeout(3000)
            else:
                # Try partial match
                addr_el = await page.query_selector("text=42580")
                if addr_el:
                    print("Found partial match '42580', clicking...")
                    await addr_el.click()
                    await page.wait_for_timeout(3000)
                else:
                    print("No clickable address found. Trying Enter key...")
                    await search.press("Enter")
                    await page.wait_for_timeout(3000)

            # ---- CHECK: did the page update with school info? ----
            await page.screenshot(path="lcps_after_select.png")
            print("  Screenshot after selection: lcps_after_select.png")

        # ---- CLOSE THE LISTBOX by clicking elsewhere ----
        await page.mouse.click(400, 200)
        await page.wait_for_timeout(2000)

        # Scroll back to top to see school results
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(2000)

        # ---- EXTRACT SCHOOL INFORMATION ----
        print("\n--- EXTRACTING SCHOOL DATA ---")

        # Get ALL text content from the page now
        all_text_elements = await page.query_selector_all("div, span, p, h1, h2, h3, h4, td, li")
        school_data = []
        seen = set()

        for el in all_text_elements:
            text = (await el.text_content() or "").strip()
            text = re.sub(r"\s+", " ", text)

            # Look for school-related content
            if any(kw in text.lower() for kw in [
                "elementary school", "middle school", "high school",
                "principal", "phone:", "website",
            ]):
                if 5 < len(text) < 400 and text not in seen:
                    seen.add(text)
                    school_data.append(text)

        print(f"School-related content ({len(school_data)} blocks):")
        for text in school_data:
            print(f"  {text[:150]}")

        # ---- Also check the Qlik objects again (they may have updated) ----
        print("\n--- QLIK OBJECTS AFTER SELECTION ---")
        qlik_objs = await page.query_selector_all(".qv-object")
        for i, obj in enumerate(qlik_objs):
            text = (await obj.text_content() or "").strip()
            text = re.sub(r"\s+", " ", text)
            if text and len(text) < 500 and any(kw in text.lower() for kw in ["school", "principal", "elementary", "middle", "high"]):
                print(f"  obj[{i}]: {text[:200]}")

        # ---- FULL PAGE SCREENSHOT ----
        await page.screenshot(path="lcps_full_result.png", full_page=True)
        print("\nFull page screenshot: lcps_full_result.png")

        # ---- SAVE EXTRACTED DATA ----
        result = {
            "address_searched": "42580 DEER ISLE DR",
            "school_data": school_data,
        }
        with open("lcps_schools_42580.json", "w") as f:
            json.dump(result, f, indent=2)

        # ---- KEEP BROWSER OPEN for manual inspection ----
        print("\n--- BROWSER STAYING OPEN ---")
        print("Waiting 30 seconds for manual inspection...")
        print("Check the screenshots and browser window.")
        await page.wait_for_timeout(30000)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
