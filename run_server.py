"""Start the PIPA server.

Usage:
    python run_server.py            # Production: Playwright works
    python run_server.py --reload   # Dev: auto-reload on code changes (no Playwright)
"""

import asyncio
import sys

reload = "--reload" in sys.argv

if sys.platform == "win32" and not reload:
    # ProactorEventLoop needed for Playwright subprocess support.
    # Incompatible with uvicorn --reload on Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "pipa.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=reload,
        loop="none" if (sys.platform == "win32" and not reload) else "auto",
    )
