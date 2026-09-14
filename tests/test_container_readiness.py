"""Tests for container readiness, static frontend serving, and port handling."""

import os
import tempfile
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from covenant.api.main import app
from covenant.config import Settings


@pytest.mark.asyncio
async def test_health_endpoint_intact():
    """Verify /api/health continues to return HTTP 200 with service metadata."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "covenant"
        assert "version" in data


@pytest.mark.asyncio
async def test_api_stats_endpoint_intact():
    """Verify normal API endpoints under /api continue to function."""
    from covenant.api.routes import repo
    await repo.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_commitments" in data


def test_port_configuration_override(monkeypatch):
    """Verify Settings honors PORT and HOST environment variable overrides."""
    monkeypatch.setenv("PORT", "8899")
    monkeypatch.setenv("HOST", "0.0.0.0")
    s = Settings()
    assert s.port == 8899
    assert s.host == "0.0.0.0"

    # Default fallback
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("HOST", raising=False)
    s_default = Settings()
    assert s_default.port == 8000
    assert s_default.host == "0.0.0.0"


@pytest.mark.asyncio
async def test_frontend_serving_and_spa_fallback(monkeypatch):
    """Verify frontend root, static assets, and client-side SPA routing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dist_dir = Path(tmpdir)
        assets_dir = dist_dir / "assets"
        assets_dir.mkdir(parents=True)

        index_file = dist_dir / "index.html"
        index_file.write_text("<!DOCTYPE html><html><body><div id='root'>Covenant UI</div></body></html>", encoding="utf-8")

        css_file = assets_dir / "index.css"
        css_file.write_text("body { background: #000; }", encoding="utf-8")

        monkeypatch.setenv("COVENANT_FRONTEND_DIST", str(dist_dir))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Root /
            resp_root = await client.get("/")
            assert resp_root.status_code == 200
            assert "Covenant UI" in resp_root.text

            # 2. Static asset
            resp_asset = await client.get("/assets/index.css")
            assert resp_asset.status_code == 200
            assert "background: #000" in resp_asset.text

            # 3. Client-side route (SPA fallback)
            resp_spa = await client.get("/decisions")
            assert resp_spa.status_code == 200
            assert "Covenant UI" in resp_spa.text

            resp_spa_nested = await client.get("/commitments/com_123")
            assert resp_spa_nested.status_code == 200
            assert "Covenant UI" in resp_spa_nested.text


@pytest.mark.asyncio
async def test_missing_frontend_build_handling(monkeypatch):
    """Verify missing frontend build produces an informative HTTP 404 error rather than crashing."""
    with tempfile.TemporaryDirectory() as empty_dir:
        nonexistent_dist = Path(empty_dir) / "nonexistent_dist"
        monkeypatch.setenv("COVENANT_FRONTEND_DIST", str(nonexistent_dist))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            assert resp.status_code == 404
            assert "Frontend production build not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_routes_not_intercepted_by_spa():
    """Verify unknown /api/* routes return 404 without returning the SPA index.html."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/unknown_endpoint_xyz")
        assert resp.status_code == 404
        assert "Covenant UI" not in resp.text
