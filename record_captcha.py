"""Record your mouse solving the CAPTCHA, save to captcha_recording.json.

Usage: .venv\Scripts\python record_captcha.py

1. Browser opens to Zillow
2. Solve the CAPTCHA manually (press and hold the button)
3. Press Enter in the terminal when done
4. Recording saved to captcha_recording.json
"""

import asyncio
import json
import sys
import time

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright

RECORDING_FILE = "captcha_recording.json"


async def record():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--start-maximized"])
        context = await browser.new_context(
            no_viewport=True,  # Use actual window size (maximized)
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()
        cdp = await context.new_cdp_session(page)

        events = []
        start_time = None

        def on_event(method, params):
            nonlocal start_time
            if start_time is None:
                start_time = time.monotonic()
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            events.append({
                "time_ms": elapsed_ms,
                "type": params.get("type"),
                "x": params.get("x"),
                "y": params.get("y"),
                "button": params.get("button", "none"),
            })

        # Enable input event monitoring
        await cdp.send("Input.setInterceptDrags", {"enabled": True})

        # We can't directly intercept input events via CDP easily.
        # Instead, inject JS to capture mouse events on the page.
        print("Navigating to Zillow...")
        await page.goto(
            "https://www.zillow.com/homedetails/42580-Deer-Isle-Dr-Chantilly-VA-20152/251682872_zpid/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await page.wait_for_timeout(5000)

        # Inject mouse event recorder into all frames
        recorder_js = """
        (() => {
            if (window.__pipa_recording) return;
            window.__pipa_recording = [];
            window.__pipa_start = Date.now();
            const log = (e) => {
                window.__pipa_recording.push({
                    time_ms: Date.now() - window.__pipa_start,
                    type: e.type,
                    x: e.clientX,
                    y: e.clientY,
                    button: e.button,
                });
            };
            document.addEventListener('mousemove', log, true);
            document.addEventListener('mousedown', log, true);
            document.addEventListener('mouseup', log, true);
            document.addEventListener('click', log, true);
            document.addEventListener('pointerdown', log, true);
            document.addEventListener('pointerup', log, true);
            document.addEventListener('pointermove', log, true);
        })();
        """

        # Inject into main page
        await page.evaluate(recorder_js)

        # Also inject into all iframes (CAPTCHA lives in an iframe)
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                await frame.evaluate(recorder_js)
            except:
                pass

        print("\n" + "=" * 60)
        print("RECORDING - Solve the CAPTCHA manually now!")
        print("Press and hold the button until it clears.")
        print("When done, come back here and press Enter.")
        print("=" * 60)

        # Wait for user to press Enter
        await asyncio.get_event_loop().run_in_executor(None, input)

        # Collect events from main page
        try:
            main_events = await page.evaluate("window.__pipa_recording || []")
            events.extend(main_events)
        except:
            pass

        # Collect from iframes
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                frame_events = await frame.evaluate("window.__pipa_recording || []")
                # Frame events have coordinates relative to the frame.
                # We need to adjust them to page coordinates.
                # For now, get the iframe's position on the page.
                iframes = await page.query_selector_all("iframe")
                for iframe_el in iframes:
                    try:
                        cf = await iframe_el.content_frame()
                        if cf == frame:
                            iframe_box = await iframe_el.bounding_box()
                            if iframe_box:
                                for evt in frame_events:
                                    evt["x"] += iframe_box["x"]
                                    evt["y"] += iframe_box["y"]
                                    evt["from_frame"] = True
                            break
                    except:
                        pass
                events.extend(frame_events)
            except:
                pass

        # Sort by time
        events.sort(key=lambda e: e.get("time_ms", 0))

        # Filter to relevant events (mousemove, mousedown, mouseup, pointerdown, pointerup)
        relevant = [e for e in events if e.get("type") in (
            "mousemove", "mousedown", "mouseup",
            "pointerdown", "pointerup", "pointermove",
        )]

        # Thin out mousemove events (keep every 50ms worth)
        thinned = []
        last_move_time = -100
        for e in relevant:
            if e["type"] in ("mousemove", "pointermove"):
                if e["time_ms"] - last_move_time >= 30:
                    thinned.append(e)
                    last_move_time = e["time_ms"]
            else:
                thinned.append(e)

        print(f"\nRecorded {len(thinned)} events ({len(relevant)} raw)")

        # Save
        with open(RECORDING_FILE, "w") as f:
            json.dump(thinned, f, indent=2)

        print(f"Saved to {RECORDING_FILE}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(record())
