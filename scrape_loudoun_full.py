"""Scrape ALL tabs from Loudoun County property assessment for 42580 Deer Isle Dr.

Tabs: Profile, Values, Sales/Transfers, Land, Land Use Status, Residential,
Detached Structures, Commercial, Map, WebLogis, Aerial Photos, Parcel Tracking,
Tax Payment/History
"""

import asyncio
import json
import re
from playwright.async_api import async_playwright


ALL_TABS = [
    "Profile",
    "Values",
    "Sales / Transfers",
    "Land",
    "Land Use Status",
    "Residential",
    "Detached Structures",
    "Commercial",
    "Parcel Tracking",
    "Tax Payment/History",
]


async def extract_table_data(page) -> list[dict]:
    """Extract all table rows as list of cell-text lists."""
    rows_data = []
    rows = await page.query_selector_all("table tr")
    for row in rows:
        cells = await row.query_selector_all("td, th")
        texts = []
        for c in cells:
            t = (await c.text_content() or "").strip()
            t = re.sub(r"\s+", " ", t)
            if t:
                texts.append(t)
        if texts and len(texts) <= 10:
            # Filter out navigation/footer rows
            joined = " ".join(texts).lower()
            if any(skip in joined for skip in [
                "return to search", "location google", "contact us",
                "site links", "loudoun.gov", "printable version",
                "actions", "glossary", "neighborhood sales",
            ]):
                continue
            rows_data.append(texts)
    return rows_data


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Navigate and search
        print("1. Searching for 42580 DEER ISLE DR...")
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

        await page.evaluate("""
            document.getElementById('hdAction').value = 'Search';
            document.forms[0].submit();
        """)
        await page.wait_for_timeout(5000)

        if "Datalet" not in page.url:
            print(f"   Not on detail page: {page.url}")
            # Try clicking first result
            links = await page.query_selector_all("a[href*='Datalet']")
            if links:
                await links[0].click()
                await page.wait_for_timeout(3000)

        print(f"   On: {page.url}")

        # Collect ALL data from ALL tabs
        all_tabs_data = {}

        for tab_name in ALL_TABS:
            print(f"\n{'='*60}")
            print(f"TAB: {tab_name}")
            print("=" * 60)

            # Find and click the tab link in the left sidebar
            clicked = False
            nav_links = await page.query_selector_all("a")
            for link in nav_links:
                text = (await link.text_content() or "").strip()
                if text == tab_name or text.lower() == tab_name.lower():
                    href = await link.get_attribute("href") or ""
                    if href and ("Datalet" in href or "datalet" in href or "#" in href):
                        try:
                            await link.click()
                            await page.wait_for_timeout(3000)
                            clicked = True
                            break
                        except Exception as e:
                            print(f"  Click failed: {e}")

            if not clicked:
                # Try partial match
                for link in nav_links:
                    text = (await link.text_content() or "").strip()
                    if tab_name.split("/")[0].strip().lower() in text.lower():
                        href = await link.get_attribute("href") or ""
                        if href:
                            try:
                                await link.click()
                                await page.wait_for_timeout(3000)
                                clicked = True
                                break
                            except Exception:
                                pass

            if not clicked:
                print(f"  Could not find tab link for '{tab_name}'")
                all_tabs_data[tab_name] = {"_status": "tab_not_found"}
                continue

            # Take screenshot of this tab
            safe_name = tab_name.replace("/", "_").replace(" ", "_").lower()
            await page.screenshot(path=f"loudoun_tab_{safe_name}.png")

            # Extract data
            rows = await extract_table_data(page)
            tab_data = {"_rows": rows, "_row_count": len(rows)}

            # Also try to extract structured key-value pairs
            kv_pairs = {}
            for row_texts in rows:
                if len(row_texts) == 2:
                    kv_pairs[row_texts[0]] = row_texts[1]
                elif len(row_texts) == 4:
                    kv_pairs[row_texts[0]] = row_texts[1]
                    kv_pairs[row_texts[2]] = row_texts[3]
                elif len(row_texts) == 6:
                    kv_pairs[row_texts[0]] = row_texts[1]
                    kv_pairs[row_texts[2]] = row_texts[3]
                    kv_pairs[row_texts[4]] = row_texts[5]

            tab_data["_key_values"] = kv_pairs

            # Print everything
            for row_texts in rows:
                print(f"  {' | '.join(row_texts)}")

            if kv_pairs:
                print(f"\n  Key-value pairs ({len(kv_pairs)}):")
                for k, v in kv_pairs.items():
                    print(f"    {k}: {v}")

            all_tabs_data[tab_name] = tab_data

        # Save everything
        output_path = "loudoun_county_full_42580_deer_isle.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_tabs_data, f, indent=2, default=str, ensure_ascii=False)

        print(f"\n{'='*60}")
        print(f"COMPLETE: Saved all tabs to {output_path}")
        print(f"{'='*60}")

        # Print summary of what we got
        for tab_name, data in all_tabs_data.items():
            status = data.get("_status", "ok")
            rows = data.get("_row_count", 0)
            kvs = len(data.get("_key_values", {}))
            print(f"  {tab_name:<25} rows={rows:<5} key-values={kvs}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
