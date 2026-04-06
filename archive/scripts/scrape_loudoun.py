"""Scrape Loudoun County property assessment for 42580 Deer Isle Dr.

Source: https://reparcelasmt.loudoun.gov/pt/search/commonsearch.aspx?mode=address
"""

import asyncio
import json
import re
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Step 1: Navigate to search
        print("1. Loading Loudoun County property search...")
        await page.goto(
            "https://reparcelasmt.loudoun.gov/pt/search/commonsearch.aspx?mode=address",
            timeout=30000,
        )
        await page.wait_for_timeout(3000)

        # Step 2: Fill in address
        print("2. Filling search: 42580 DEER ISLE DR...")
        await page.fill("#inpNumber", "42580")
        await page.fill("#inpStreet", "DEER ISLE")

        # Select DR from suffix dropdown
        suffix = await page.query_selector("#Select1")
        if suffix:
            await suffix.select_option("DR")

        await page.wait_for_timeout(500)

        # Step 3: Submit search via JavaScript
        print("3. Submitting search...")
        # Set the hidden action field and submit
        await page.evaluate("""
            document.getElementById('hdAction').value = 'Search';
            document.forms[0].submit();
        """)

        # Wait for navigation
        await page.wait_for_timeout(5000)
        current_url = page.url
        print(f"   Landed on: {current_url}")

        # If we're on search results, click through to property
        if "CommonSearch" in current_url:
            # Look for result links
            result_links = await page.query_selector_all("a[href*='Datalet']")
            if result_links:
                print(f"   Found {len(result_links)} result links, clicking first...")
                await result_links[0].click()
                await page.wait_for_timeout(3000)
                print(f"   Now on: {page.url}")

        # Step 4: We should be on the property detail page now
        if "Datalet" in page.url or "datalet" in page.url:
            print("4. On property detail page!")
        else:
            print(f"4. Not on detail page: {page.url}")
            # Try alternate approach - direct search
            print("   Trying alternate submit...")
            await page.goto(
                "https://reparcelasmt.loudoun.gov/pt/search/commonsearch.aspx?mode=address",
                timeout=30000,
            )
            await page.wait_for_timeout(2000)
            await page.fill("#inpNumber", "42580")
            await page.fill("#inpStreet", "DEER ISLE")
            suffix = await page.query_selector("#Select1")
            if suffix:
                await suffix.select_option("DR")
            # Try clicking the search button directly
            btn = await page.query_selector("input[type='button'][value='Search']")
            if btn:
                await btn.click()
            else:
                # Try any button with search text
                await page.click("text=Search")
            await page.wait_for_timeout(5000)
            print(f"   After retry: {page.url}")

        await page.screenshot(path="loudoun_detail.png")

        # Step 5: Extract data from property detail page
        print("\n" + "=" * 70)
        print("LOUDOUN COUNTY PROPERTY DATA")
        print("=" * 70)

        all_data = {}

        # Extract all label-value pairs from tables
        # Loudoun uses a datalet table structure
        rows = await page.query_selector_all("table tr")
        current_section = "General"
        for row in rows:
            cells = await row.query_selector_all("td")
            cell_texts = []
            for c in cells:
                t = (await c.text_content() or "").strip()
                t = re.sub(r"\s+", " ", t)
                if t:
                    cell_texts.append(t)

            if len(cell_texts) == 1 and len(cell_texts[0]) < 40:
                # Might be a section header
                current_section = cell_texts[0]
            elif len(cell_texts) >= 2:
                for i in range(0, len(cell_texts) - 1, 2):
                    label = cell_texts[i]
                    value = cell_texts[i + 1] if i + 1 < len(cell_texts) else ""
                    if label and value and len(label) < 80 and not label.startswith("http"):
                        key = f"{current_section} > {label}" if current_section != "General" else label
                        all_data[key] = value

        for k, v in sorted(all_data.items()):
            print(f"  {k}: {v}")

        # Step 6: Navigate to other tabs
        tab_links = await page.query_selector_all("a.section_header, a[class*='header'], td.DataletHeaderBottom a")
        tab_names_found = []
        for link in tab_links:
            text = (await link.text_content() or "").strip()
            href = await link.get_attribute("href") or ""
            if text and "Datalet" in href:
                tab_names_found.append((text, href))

        # Also look for links in the sidebar/navigation
        nav_links = await page.query_selector_all("a")
        for link in nav_links:
            text = (await link.text_content() or "").strip()
            href = await link.get_attribute("href") or ""
            if any(tab in text for tab in ["Sales", "Transfer", "Land Use", "Dwelling", "Tax Payment", "Sketch", "Improvement", "Parcel"]):
                if href and text not in [t for t, _ in tab_names_found]:
                    tab_names_found.append((text, href))

        print(f"\nAvailable tabs: {[t for t, _ in tab_names_found]}")

        for tab_text, tab_href in tab_names_found:
            if any(skip in tab_text for skip in ["Return", "Search", "Help"]):
                continue

            print(f"\n--- {tab_text.upper()} ---")
            try:
                tab_link = await page.query_selector(f"a:has-text('{tab_text}')")
                if tab_link:
                    await tab_link.click()
                    await page.wait_for_timeout(3000)

                    tab_rows = await page.query_selector_all("table tr")
                    for row in tab_rows:
                        cells = await row.query_selector_all("td, th")
                        texts = []
                        for c in cells:
                            t = (await c.text_content() or "").strip()
                            t = re.sub(r"\s+", " ", t)
                            if t and len(t) < 100:
                                texts.append(t)
                        if 2 <= len(texts) <= 8:
                            print(f"  {' | '.join(texts)}")
            except Exception as e:
                print(f"  Error: {e}")

        # Save all extracted data
        with open("loudoun_county_42580_deer_isle.json", "w") as f:
            json.dump(all_data, f, indent=2)
        print(f"\nSaved to loudoun_county_42580_deer_isle.json ({len(all_data)} fields)")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
