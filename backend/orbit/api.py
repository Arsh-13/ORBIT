"""FastAPI web API for ORBIT.

Endpoints (all read-only):
  GET /api/health                 - is the server up?
  GET /api/scan?folder=<subpath>  - scan the sample workspace, or a subfolder inside it

The API never accepts an arbitrary filesystem path. `folder` is always interpreted
relative to the sample workspace and checked by safety.resolve_inside().
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import ALLOWED_HOSTS, SAMPLE_WORKSPACE
from .duplicates import ScanReport, build_report
from .safety import PathSafetyError, resolve_inside
from .scanner import ScanRootError, scan_directory


def create_app(sample_root: Path = SAMPLE_WORKSPACE, allowed_hosts: list[str] = ALLOWED_HOSTS) -> FastAPI:
    """Build the app. Tests pass a temporary `sample_root`. The real server uses the default."""
    app = FastAPI(title="ORBIT API", version=__version__)

    # Reject requests whose Host header isn't localhost. Combined with binding to
    # 127.0.0.1, this keeps the API private to this machine.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/scan", response_model=ScanReport)
    def scan(
        folder: str = Query(
            default="",
            max_length=255,
            description="Optional subfolder, relative to the sample workspace. Empty = whole workspace.",
        ),
    ) -> ScanReport:
        try:
            target = resolve_inside(sample_root, folder)
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="The sample workspace folder is missing.")
        except PathSafetyError as exc:
            raise HTTPException(status_code=400, detail=f"Rejected path: {exc}")

        try:
            result = scan_directory(target)
        except ScanRootError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        return build_report(result)

    return app


# The app object that uvicorn runs.
app = create_app()
