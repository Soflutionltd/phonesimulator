# SPDX-License-Identifier: Apache-2.0
"""The viewer's pages: ``/viewer/<scope>`` for a browser tab, ``/embed/<scope>`` for a frame, and their assets.

Both are the committed standalone viewer bundle (`server/static/viewer/`), so an install from a git tag needs no Node.
A page gets in with the code or ticket in its URL's fragment (`daemon.passes`), which never reaches the server. Pages
are never cached -- a new install's viewer is the one shown -- and an install without a bundle says so rather than
serving a blank page. Assets are the bundle's own files, by name, at ``/viewer-assets/<name>``: a page names them with
this install's version (``?v=3.10.0``), and they are served to be checked again before each use, so a browser that kept
an older install's script loads this one's. A page whose scope was named carries the name in a
``<meta name="phonesimulator-project">`` and as its ``<title>``: the project's name, not its id, from the first byte
(`daemon.scope_names`).
"""

from __future__ import annotations

import html as markup
import re
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, Response

from phonesimulator._version import __version__
from phonesimulator.scope import ID_PATTERN

STATIC_VIEWER = Path(__file__).parent / "static" / "viewer"
VIEWER_PAGE = "index.html"
EMBED_PAGE = "embed.html"
NO_STORE = {"Cache-Control": "no-store"}
#: An asset is kept, but checked again before each use: unchanged, it costs a 304.
REVALIDATE = {"Cache-Control": "no-cache"}
ASSETS = "/viewer-assets/"
NOT_BUILT = (
    "<!doctype html><meta charset=utf-8><title>PhoneSimulator</title>"
    "<p>This install of PhoneSimulator has no viewer built into it.</p>"
)
NO_SUCH_SCOPE = "<!doctype html><meta charset=utf-8><title>PhoneSimulator</title><p>There is no such scope.</p>"

_ASSET_NAME = re.compile(r"\A[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}\Z")


#: The meta tag a page's scope name goes in, read by the standalone viewer for its title.
PROJECT_META = "phonesimulator-project"


def create_page_router(
    static_dir: Path | None = STATIC_VIEWER, *, name_of: Callable[[str], str | None] = lambda scope_id: None
) -> APIRouter:
    router = APIRouter()

    def page(name: str, scope_id: str) -> Response:
        if not ID_PATTERN.match(scope_id):
            return HTMLResponse(NO_SUCH_SCOPE, status_code=404, headers=NO_STORE)
        path = static_dir / name if static_dir is not None else None
        if path is None or not path.is_file():
            return HTMLResponse(NOT_BUILT, status_code=503, headers=NO_STORE)
        # Each asset named with this install's version: a browser never runs an older install's script with it.
        html = path.read_text(encoding="utf-8")
        html = re.sub(rf'({re.escape(ASSETS)}[A-Za-z0-9_.-]+)(?=")', rf"\1?v={__version__}", html)
        project = name_of(scope_id)
        if project:
            named = markup.escape(project, quote=True)
            meta = f'<meta name="{PROJECT_META}" content="{named}" />'
            html = html.replace("</head>", f"    {meta}\n  </head>", 1)
            # The title the page loads with is the one a tab keeps -- a browser pane's card reads it before any script
            # runs -- so it is the project's name from the first byte, not the product's.
            html = re.sub(r"<title>[^<]*</title>", f"<title>{named}</title>", html, count=1)
        return HTMLResponse(html, headers=NO_STORE)

    @router.get("/viewer/{scope_id}")
    async def viewer_page(scope_id: str) -> Response:
        return page(VIEWER_PAGE, scope_id)

    @router.get("/embed/{scope_id}")
    async def embed_page(scope_id: str) -> Response:
        return page(EMBED_PAGE, scope_id)

    @router.get("/viewer-assets/{name}")
    async def viewer_asset(name: str) -> Response:
        path = static_dir / name if static_dir is not None and _ASSET_NAME.match(name) else None
        if path is None or not path.is_file():
            return Response(status_code=404)
        return FileResponse(path, headers=REVALIDATE)

    return router
