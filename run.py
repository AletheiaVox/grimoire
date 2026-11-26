"""Production-grade launcher for the Technowitch Grimoire server.

Binds 0.0.0.0:7940 without reload by default so Windows background daemons run rock-solid.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Technowitch Grimoire server.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=7940, help="Bind port (default: 7940)")
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable auto-reload (development only; off by default on Windows)",
    )
    parser.add_argument("--log-level", default="info", help="Uvicorn log level")
    args = parser.parse_args()

    if args.reload:
        uvicorn.run(
            "grimoire.app:app",
            host=args.host,
            port=args.port,
            reload=True,
            log_level=args.log_level,
        )
    else:
        from grimoire.app import app

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            reload=False,
            log_level=args.log_level,
        )


if __name__ == "__main__":
    main()
