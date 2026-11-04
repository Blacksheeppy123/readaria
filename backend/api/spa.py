"""Serve the built Vue application with history-mode routing support."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException


WEB_DIST = Path(__file__).resolve().parent.parent / "static" / "web"


class SPAStaticFiles(StaticFiles):
    """Serve SPA files and fall back to index.html for unknown non-API paths."""

    async def get_response(self, path: str, scope):
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
