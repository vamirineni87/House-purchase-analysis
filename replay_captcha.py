"""Replay recorded CAPTCHA solution from captcha_recording.json.

Usage: .venv\Scripts\python replay_captcha.py

Replays the mouse events you recorded, with the same timing.
"""

import asyncio
import json
import random
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright

RECORDING_FILE = "captcha_recording.json"


async def replay():
    # Load recording
    with open(RECORDING_FILE) as f:
        events = json.load(f)

    print(f"Loaded {len(events)} events from {RECORDING_FILE}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50, args=["--start-maximized"])
        context = await browser.new_context(
            no_viewport=True,  # Use actual window size (maximized)
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()
        cdp = await context.new_cdp_session(page)

        print("Navigating to Zillow...")
        await page.goto(
            "https://www.zillow.com/homedetails/42580-Deer-Isle-Dr-Chantilly-VA-20152/251682872_zpid/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await page.wait_for_timeout(6000)

        # Check for CAPTCHA
        has_captcha = False
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                el = await frame.query_selector("#px-captcha")
                if el:
                    has_captcha = True
                    box = await el.bounding_box()
                    print(f"CAPTCHA found: {box}")
                    break
            except:
                pass

        if not has_captcha:
            print("No CAPTCHA! Page loaded clean.")
            await page.wait_for_timeout(5000)
            await browser.close()
            return

        # Replay events via CDP
        # Add small random offsets to avoid exact replay detection
        offset_x = random.uniform(-3, 3)
        offset_y = random.uniform(-3, 3)
        speed_factor = random.uniform(0.9, 1.1)  # Slight timing variation

        print(f"\nReplaying with offset ({offset_x:.1f}, {offset_y:.1f}), speed {speed_factor:.2f}x")

        prev_time = 0
        for i, evt in enumerate(events):
            # Wait for the right time
            delay_ms = int((evt["time_ms"] - prev_time) * speed_factor)
            if delay_ms > 0:
                # Add tiny random jitter to timing
                delay_ms = max(1, delay_ms + random.randint(-5, 5))
                await page.wait_for_timeout(delay_ms)
            prev_time = evt["time_ms"]

            x = evt["x"] + offset_x + random.uniform(-0.5, 0.5)
            y = evt["y"] + offset_y + random.uniform(-0.5, 0.5)
            evt_type = evt["type"]

            if evt_type in ("mousemove", "pointermove"):
                await cdp.send("Input.dispatchMouseEvent", {
                    "type": "mouseMoved",
                    "x": x,
                    "y": y,
                })
            elif evt_type in ("mousedown", "pointerdown"):
                print(f"  mousedown at ({x:.0f}, {y:.0f}) t={evt['time_ms']}ms")
                await cdp.send("Input.dispatchMouseEvent", {
                    "type": "mousePressed",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1,
                })
            elif evt_type in ("mouseup", "pointerup"):
                print(f"  mouseup at ({x:.0f}, {y:.0f}) t={evt['time_ms']}ms")
                await cdp.send("Input.dispatchMouseEvent", {
                    "type": "mouseReleased",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1,
                })

        print("\nReplay complete. Waiting for result...")
        await page.wait_for_timeout(8000)

        # Check result
        still = False
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                el = await frame.query_selector("#px-captcha")
                if el and await el.is_visible():
                    still = True
                    break
            except:
                pass

        if still:
            print("CAPTCHA NOT CLEARED")
        else:
            print("CAPTCHA CLEARED!")

        print("\nBrowser open for 20s...")
        await page.wait_for_timeout(20000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(replay())
