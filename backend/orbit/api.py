"""FastAPI web API for ORBIT.

Read-only endpoints:
  GET    /api/health                       - is the server up?
  GET    /api/scan?folder=<subpath>        - scan the sample workspace + recommendations
  GET    /api/preferences                  - your keep-rules and preferred-copy choices

Preference endpoints (these write ONLY to ORBIT's own database, never to scanned files):
  PUT    /api/preferences/rules            - change preferred / avoided folders
  PUT    /api/preferences/choices          - mark a copy as the one to keep
  DELETE /api/preferences/choices/{sha256} - go back to ORBIT's suggestion

No endpoint accepts an arbitrary filesystem path. Every path is interpreted relative to the
sample workspace and checked by safety.resolve_inside().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Path as PathParam, Query, Request, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from . import __version__, config
from .duplicates import ScanReport, build_report
from .preferences import MAX_FOLDERS, KeepRules, PreferenceError, PreferenceStore, normalize_rules
from .recommend import Recommendation, recommend_all
from .safety import PathSafetyError, resolve_inside
from .scanner import ScanRootError, hash_file, scan_directory

SHA256_PATTERN = r"^[0-9a-f]{64}$"


@dataclass
class ScanResponse(ScanReport):
    """The scan report plus Milestone 2's recommendations and the rules that produced them."""

    recommendations: list[Recommendation] = field(default_factory=list)
    keep_rules: KeepRules = field(default_factory=KeepRules)


@dataclass
class PreferredChoice:
    sha256: str
    relative_path: str


@dataclass
class PreferencesResponse:
    keep_rules: KeepRules
    choices: list[PreferredChoice]


class RulesIn(BaseModel):
    preferred_folders: list[str] = Field(default_factory=list, max_length=MAX_FOLDERS)
    avoid_folders: list[str] = Field(default_factory=list, max_length=MAX_FOLDERS)


class ChoiceIn(BaseModel):
    sha256: str = Field(pattern=SHA256_PATTERN)
    relative_path: str = Field(min_length=1, max_length=1024)


def create_app(
    sample_root: Path = config.SAMPLE_WORKSPACE,
    allowed_hosts: list[str] = config.ALLOWED_HOSTS,
    db_path: Path | None = None,
) -> FastAPI:
    """Build the app. Tests pass temporary folders. The real server uses the defaults."""
    db_path = db_path or config.DB_PATH  # read at call time so tests can redirect it
    if db_path.resolve().is_relative_to(sample_root.resolve()):
        raise ValueError("ORBIT's database must not live inside the scanned workspace")
    store = PreferenceStore(db_path)

    app = FastAPI(title="ORBIT API", version=__version__)

    # Reject requests whose Host header isn't localhost. Combined with binding to
    # 127.0.0.1, this keeps the API private to this machine.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    def same_site_only(request: Request) -> None:
        """Block other websites from changing your preferences (cross-site request forgery).

        Browsers send an Origin header with these requests. Ours is localhost, and anything
        else is refused. (PUT/DELETE with JSON already need a CORS "preflight" that this
        API never approves. This check is a second lock on the same door.)
        """
        origin = request.headers.get("origin")
        if origin is not None and urlsplit(origin).hostname not in allowed_hosts:
            raise HTTPException(status_code=403, detail="Cross-site requests are not allowed")

    # ---------------- read-only ----------------

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/scan", response_model=ScanResponse)
    def scan(
        folder: str = Query(
            default="",
            max_length=255,
            description="Optional subfolder, relative to the sample workspace. Empty = whole workspace.",
        ),
    ) -> ScanResponse:
        try:
            target = resolve_inside(sample_root, folder)
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="The sample workspace folder is missing.")
        except PathSafetyError as exc:
            raise HTTPException(status_code=400, detail=f"Rejected path: {exc}")

        try:
            # Paths are always relative to the workspace root, even for a subfolder scan, so
            # keep rules ("downloads") and saved choices match the same way in every scan.
            result = scan_directory(target, relative_to=sample_root)
        except ScanRootError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        report = build_report(result)
        rules = store.get_rules()
        recommendations = recommend_all(report.duplicate_groups, report.files, rules, store.get_choices())
        return ScanResponse(**vars(report), recommendations=recommendations, keep_rules=rules)

    @app.get("/api/preferences", response_model=PreferencesResponse)
    def get_preferences() -> PreferencesResponse:
        choices = [PreferredChoice(h, p) for h, p in sorted(store.get_choices().items())]
        return PreferencesResponse(keep_rules=store.get_rules(), choices=choices)

    # ---------------- preference writes (ORBIT's database only) ----------------

    @app.put("/api/preferences/rules", response_model=KeepRules, dependencies=[Depends(same_site_only)])
    def put_rules(body: RulesIn) -> KeepRules:
        try:
            rules = normalize_rules(body.preferred_folders, body.avoid_folders)
        except PreferenceError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        store.save_rules(rules)
        return rules

    @app.put("/api/preferences/choices", response_model=PreferredChoice, dependencies=[Depends(same_site_only)])
    def put_choice(body: ChoiceIn) -> PreferredChoice:
        """Remember which copy to keep. We re-hash that one file to prove it belongs to the group."""
        try:
            target = resolve_inside(sample_root, body.relative_path)
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="The sample workspace folder is missing.")
        except PathSafetyError as exc:
            raise HTTPException(status_code=400, detail=f"Rejected path: {exc}")

        relative = target.relative_to(sample_root.resolve()).as_posix()
        if any(part.startswith(".") for part in relative.split("/")):
            raise HTTPException(status_code=400, detail="Hidden files can't be chosen")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="File not found in the sample workspace")
        try:
            digest, _ = hash_file(target)
        except OSError:
            raise HTTPException(status_code=404, detail="That file could not be read")
        if digest != body.sha256:
            raise HTTPException(status_code=409, detail="That file's contents don't match this duplicate group")

        store.set_choice(body.sha256, relative)
        return PreferredChoice(body.sha256, relative)

    @app.delete("/api/preferences/choices/{sha256}", status_code=204, dependencies=[Depends(same_site_only)])
    def delete_choice(sha256: str = PathParam(pattern=SHA256_PATTERN)) -> Response:
        store.clear_choice(sha256)
        return Response(status_code=204)

    return app


# The app object that uvicorn runs.
app = create_app()
