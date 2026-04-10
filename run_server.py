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
    # Bind to 0.0.0.0 so the server is reachable from other devices on
    # the LAN — user VPNs into their home network when researching
    # properties on the road and needs PIPA to pull up from a phone/
    # laptop. There's no auth on the API; LAN exposure is acceptable
    # because reaching this host requires being on the trusted network
    # (or VPN'd into it).
    uvicorn.run(
        "pipa.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=reload,
        loop="none" if (sys.platform == "win32" and not reload) else "auto",
    )
