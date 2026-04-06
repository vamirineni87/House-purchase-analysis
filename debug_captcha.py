"""CAPTCHA bypass using real Chrome (not Playwright's Chromium).

Uses your actual Chrome installation which has normal fingerprints,
extensions, and isn't flagged as automated.

Usage: .venv\Scripts\python debug_captcha.py
"""

import asyncio
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright

URL = "https://www.zillow.com/homedetails/42580-Deer-Isle-Dr-Chantilly-VA-20152/251682872_zpid/"
COOKIES_FILE = Path("storage/zillow_cookies.json")
PROFILE_DIR = Path("storage/chrome_profile")


async def find_captcha(page):
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            el = await frame.query_selector("#px-captcha")
            if el and await el.is_visible():
                return True
        except:
            pass
    el = await page.query_selector("#px-captcha")
    if el:
        try:
            return await el.is_visible()
        except:
            pass
    return False


async def main():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        # Use REAL Chrome, not Playwright's Chromium
        # This uses your installed Chrome with normal fingerprints
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            channel="chrome",  # <-- Use real Chrome
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",  # Hide automation flag
            ],
            no_viewport=True,
            ignore_default_args=["--enable-automation"],  # Remove automation flag
        )

        # Load saved cookies
        if COOKIES_FILE.exists():
            try:
                cookies = json.loads(COOKIES_FILE.read_text())
                await context.add_cookies(cookies)
                print(f"Loaded {len(cookies)} saved cookies")
            except:
                pass

        page = context.pages[0] if context.pages else await context.new_page()

        # Patch navigator.webdriver
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // Also patch other automation markers
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """)

        print("Navigating with real Chrome...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(6000)

        # Check webdriver
        wd = await page.evaluate("navigator.webdriver")
        print(f"navigator.webdriver = {wd}")

        has_captcha = await find_captcha(page)

        if has_captcha:
            print("\nCAPTCHA detected.")
            print("=" * 50)
            print("Try solving it manually in the browser.")
            print("Press Enter here when done (or to skip).")
            print("=" * 50)
            await asyncio.get_event_loop().run_in_executor(None, input)

            await page.wait_for_timeout(2000)
            if await find_captcha(page):
                print("Still there. PerimeterX may have blocked this session.")
                print("\nLet's try a completely fresh approach...")
            else:
                print("CAPTCHA cleared!")
        else:
            print("NO CAPTCHA! Real Chrome + profile worked!")

        # Save cookies
        cookies = await context.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
        print(f"Saved {len(cookies)} cookies")

        # Test second URL
        print("\nTesting second listing...")
        await page.goto(
            "https://www.zillow.com/homedetails/23648-Amesfield-Pl-Aldie-VA-20105/119524498_zpid/",
            wait_until="domcontentloaded", timeout=30000,
        )
        await page.wait_for_timeout(6000)
        if await find_captcha(page):
            print("Second page: CAPTCHA")
        else:
            print("Second page: NO CAPTCHA!")

        print("\nBrowser open 60s for inspection...")
        await page.wait_for_timeout(60000)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
