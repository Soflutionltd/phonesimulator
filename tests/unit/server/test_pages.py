# SPDX-License-Identifier: Apache-2.0
"""The viewer's pages and assets: served from the committed bundle, never cached, and honest when there is none."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI

from simtrail._version import __version__
from simtrail.server.pages import NOT_BUILT, STATIC_VIEWER, create_page_router
from simtrail.testing.asgi import HOST


def served(static_dir: Path | None) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(create_page_router(static_dir))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"http://{HOST}")


async def test_the_viewer_and_embed_pages_and_their_assets_come_from_the_bundle(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<p>viewer</p>")
    (tmp_path / "embed.html").write_text("<p>embed</p>")
    (tmp_path / "viewer.js").write_text("export {}")
    async with served(tmp_path) as http:
        viewer = await http.get("/viewer/project-notes-1a2b3c4d")
        embed = await http.get("/embed/tp-1")
        asset = await http.get("/viewer-assets/viewer.js")
        odd_scope = await http.get("/viewer/bad%20scope")
        hidden = await http.get("/viewer-assets/.env")
        missing = await http.get("/viewer-assets/nope.js")
    assert (viewer.status_code, viewer.text, viewer.headers["cache-control"]) == (200, "<p>viewer</p>", "no-store")
    assert viewer.headers["content-type"].startswith("text/html") and embed.text == "<p>embed</p>"
    assert asset.status_code == 200 and asset.text == "export {}"
    assert asset.headers["cache-control"] == "no-cache", "kept, but checked again before each use"
    assert odd_scope.status_code == 404 and "no such scope" in odd_scope.text
    assert hidden.status_code == 404 and missing.status_code == 404


async def test_an_install_without_a_bundle_says_so(tmp_path: Path) -> None:
    for static_dir in (None, tmp_path / "not-built"):
        async with served(static_dir) as http:
            page = await http.get("/viewer/tp-1")
            asset = await http.get("/viewer-assets/viewer.js")
        assert (page.status_code, page.text) == (503, NOT_BUILT) and asset.status_code == 404
    assert STATIC_VIEWER.parts[-2:] == ("static", "viewer")


async def test_a_page_names_its_assets_with_this_installs_version_so_no_older_script_runs_with_it(
    tmp_path: Path,
) -> None:
    (tmp_path / "index.html").write_text(
        '<script type="module" src="/viewer-assets/start.js"></script><link href="/viewer-assets/s.css">'
        '<a href="/elsewhere/x.js">'
    )
    async with served(tmp_path) as http:
        page = await http.get("/viewer/tp-1")
    assert page.text == (
        f'<script type="module" src="/viewer-assets/start.js?v={__version__}"></script>'
        f'<link href="/viewer-assets/s.css?v={__version__}"><a href="/elsewhere/x.js">'
    )


async def test_a_named_scopes_page_carries_its_name_made_safe_for_its_title(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html><head><title>Simtrail</title></head><body></body></html>")
    names = {"project-notes-1a2b3c4d": 'Notes "beta" <app>'}
    app = FastAPI()
    app.include_router(create_page_router(tmp_path, name_of=names.get))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"http://{HOST}") as http:
        named = await http.get("/viewer/project-notes-1a2b3c4d")
        unnamed = await http.get("/viewer/tp-1")
    assert '<meta name="simtrail-project" content="Notes &quot;beta&quot; &lt;app&gt;" />' in named.text
    assert named.text.index("simtrail-project") < named.text.index("</head>")
    assert "simtrail-project" not in unnamed.text
