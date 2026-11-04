"""Serve the built Vue application with history-mode routing support."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import URL
from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse
from starlette.routing import Match


WEB_DIST = Path(__file__).resolve().parent.parent / "static" / "web"


class SPAStaticFiles(StaticFiles):
    """Serve SPA files and fall back to index.html for unknown non-API paths."""

    async def get_response(self, path: str, scope):
        # The root mount otherwise prevents Starlette's router from normalizing
        # trailing slashes on existing API and documentation routes.
        if scope["path"].endswith("/"):
            normalized_path = scope["path"].rstrip("/")
            for route in scope["app"].routes:
                if getattr(route, "app", None) is self:
                    continue
                match, _ = route.matches({**scope, "path": normalized_path})
                if match == Match.FULL:
                    redirect_url = URL(scope={**scope, "path": normalized_path})
                    return RedirectResponse(str(redirect_url), status_code=307)

        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def mount_spa(app: FastAPI) -> bool:
    """Mount the frontend when its build output is available."""
    if not WEB_DIST.exists():
        return False
    app.mount("/", SPAStaticFiles(directory=WEB_DIST, html=True), name="web")
    return True
