"""Run the local API server."""

from __future__ import annotations

import uvicorn

from agent.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
