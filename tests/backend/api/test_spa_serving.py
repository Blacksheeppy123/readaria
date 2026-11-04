"""Unit tests for serving the Vue SPA from the API application."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api import spa


pytestmark = [pytest.mark.unit, pytest.mark.api]


async def _get(app, path):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.get(path)


@pytest.fixture
def spa_app(tmp_path, monkeypatch):
    web_dist = tmp_path / "web"
    assets = web_dist / "assets"
    assets.mkdir(parents=True)
    (web_dist / "index.html").write_text(
        '<!doctype html><div id="app">Readaria</div>', encoding="utf-8"
    )
    (assets / "app.js").write_text("console.log('readaria')", encoding="utf-8")
    monkeypatch.setattr(spa, "WEB_DIST", web_dist)

    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/user/{user_id}/feeds")
    async def feeds(user_id: str):
        return {"user_id": user_id, "feeds": []}

    assert spa.mount_spa(app) is True
    return app


async def test_mount_spa_returns_false_and_leaves_app_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(spa, "WEB_DIST", tmp_path / "missing")
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    routes_before = list(app.routes)

    assert spa.mount_spa(app) is False
    assert app.routes == routes_before
    assert (await _get(app, "/api/health")).status_code == 200
    assert (await _get(app, "/")).status_code == 404


async def test_root_serves_index_html(spa_app):
    response = await _get(spa_app, "/")

    assert response.status_code == 200
    assert response.text == '<!doctype html><div id="app">Readaria</div>'


async def test_unknown_frontend_route_falls_back_to_index_html(spa_app):
    response = await _get(spa_app, "/some/deep/route")

    assert response.status_code == 200
    assert response.text == '<!doctype html><div id="app">Readaria</div>'


@pytest.mark.parametrize("path", ["/api", "/api/nonexistent", "/api/nonexistent/"])
async def test_unknown_api_route_returns_404_instead_of_index_html(spa_app, path):
    response = await _get(spa_app, path)

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


async def test_existing_static_asset_is_served(spa_app):
    response = await _get(spa_app, "/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log('readaria')"


@pytest.mark.parametrize(
    ("path", "location"),
    [
        ("/api/health/?probe=1", "http://testserver/api/health?probe=1"),
        ("/user/123/feeds/", "http://testserver/user/123/feeds"),
        ("/docs/", "http://testserver/docs"),
    ],
)
async def test_existing_route_trailing_slash_still_redirects(spa_app, path, location):
    response = await _get(spa_app, path)

    assert response.status_code == 307
    assert response.headers["location"] == location


async def test_trailing_slash_method_mismatch_does_not_redirect(spa_app):
    async with AsyncClient(
        transport=ASGITransport(app=spa_app), base_url="http://testserver"
    ) as client:
        response = await client.post("/api/health/")

    assert response.status_code == 404
