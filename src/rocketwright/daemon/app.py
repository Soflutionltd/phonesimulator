# SPDX-License-Identifier: Apache-2.0
"""The standalone daemon's application: Rocketwright's routers behind its security middleware, and the daemon's own.

    /healthz                                   whether it is up; given a nonce, proof it is this user's daemon
    /api/v1/scopes/{scope}[/devices|/device]   a person's routes (`server.http_routes`)
    /api/v1/scopes/{scope}/screen              the screen socket (`server.socket_routes`)
    /api/v1/scopes/{scope}/settings            the settings panel's (`server.settings_routes`), with a settings store
    /api/v1/scopes/{scope}/embed-tickets       a frame's way in, for a host's backend with its token
    /api/v1/scopes/{scope}/pause               a person's pause on agents' gestures, with an expiry (`daemon.pauses`)
    /api/v1/agent/manifest|call|lease|warm     an agent's routes, its lease (`daemon.lease`), and its device made
                                               ready before its first call (`DeviceManager.warm`)
    /api/v1/auth/exchange                      a code or an embed ticket, spent for a viewer token
    /api/v1/admin/reload|login-codes|tokens    the admin token's routes, every page's session ended
    /api/v1/admin/viewer-sessions              (`daemon.passes`), and the settings changes waiting to be
    /api/v1/admin/settings-confirmations       confirmed, with their codes (`daemon.confirmations`), and which
    /api/v1/admin/in-use                       scopes it serves now, and one device let go for every scope
    /api/v1/admin/devices/{udid}
    /api/v1/admin/devices/prune                the simulators Rocketwright made and nobody needs, deleted
    (`core.cleanup`) /api/v1/host[/tokens]                      a host token's own record, and the tokens it makes for
    its namespaces /viewer/{scope}, /embed/{scope}            the viewer's pages (`server.pages`)

`build_daemon` puts a daemon together from settings and a state folder; `create_app` serves it. The app starts the
runtime when it starts and closes it when it stops.

Several hosts can share one daemon, each with a host token for its namespaces (`daemon.tokens`): a scope in one host's
namespace never shares a device with a scope outside it.
"""

from __future__ import annotations

import contextlib
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from rocketwright._version import __version__
from rocketwright.connectors.registry import ConnectorRegistry
from rocketwright.core.manager import SimulatorUnavailable
from rocketwright.core.runtime import Runtime
from rocketwright.daemon import health
from rocketwright.daemon.auth import TokenAuthenticator
from rocketwright.daemon.confirmations import PendingChanges
from rocketwright.daemon.lease import LEASE_S, Leases
from rocketwright.daemon.passes import CODE_TTL_S, VIEWER_SESSIONS_FILE, OneShotCodes, ViewerSessions, ttl_of
from rocketwright.daemon.pauses import PAUSE_MAX_S, Pauses
from rocketwright.daemon.policy import ConfigPolicy
from rocketwright.daemon.scope_names import SCOPE_NAMES_FILE, ScopeNames
from rocketwright.daemon.tokens import TokenRecord, TokenRefused, TokenStore
from rocketwright.host_copy import HostCopy
from rocketwright.platform.errors import DeviceControlError
from rocketwright.platform.passwords import Credentials
from rocketwright.platform.xcrun import XcrunRunner, run_xcrun
from rocketwright.protocol import PROTOCOL_VERSION, SERVER
from rocketwright.scope import LABEL_MAX, Scope
from rocketwright.seams import ConfigSource, DeviceMemory, Refused, SettingsStore, StateStore
from rocketwright.server import log_redaction
from rocketwright.server.agent_routes import create_agent_router
from rocketwright.server.envelope import ok
from rocketwright.server.http_routes import create_http_router
from rocketwright.server.pages import STATIC_VIEWER, create_page_router
from rocketwright.server.security import SecurityMiddleware, SiteRules
from rocketwright.server.settings_routes import create_settings_router
from rocketwright.server.socket_routes import create_socket_router
from rocketwright.storage.claims import Claims

SCOPES = "/api/v1/scopes/{scope_id}"
AGENT = "/api/v1/agent"
ADMIN = "/api/v1/admin"
HOST = "/api/v1/host"
#: The settings the server itself runs with -- its origins and framing -- are the file's own, not any scope's.
SERVER_SCOPE = Scope.named("rocketwright")
BAD_CODE = "invalid or expired code"


class LoginCodeRequest(BaseModel):
    scope: str = Field(min_length=1, max_length=128)
    #: What a person calls the scope -- its project's name -- shown instead of its id (`daemon.scope_names`).
    label: str = Field(default="", max_length=LABEL_MAX)
    #: Open a session that may change settings, rather than only read them.
    settings: bool = False


class InheritRequest(BaseModel):
    #: The scope whose device the other is given: a git worktree's main checkout.
    source: str = Field(min_length=1, max_length=128)


class GivenLoginRequest(BaseModel):
    scope: str = Field(min_length=1, max_length=128)
    app: str = Field(min_length=1, max_length=255)
    title: str = Field(default="", max_length=255)
    username: str = Field(default="", max_length=1024)
    password: str = Field(default="", max_length=4096, repr=False)
    totp: str = Field(default="", max_length=64, repr=False)


class TokenRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=16)
    scopes: list[str] = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=200)
    roots: list[str] = Field(default_factory=list, max_length=32)


class HostTokenRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=16)
    scopes: list[str] = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=200)
    roots: list[str] = Field(default_factory=list, max_length=32)


class ExchangeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128)


class PruneRequest(BaseModel):
    #: Delete those that hold apps too, rather than only the empty ones.
    all: bool = False
    #: Say what would be deleted, deleting nothing.
    dry_run: bool = False


class PauseRequest(BaseModel):
    #: How long agents keep their gestures off the scope's device, unless it is lifted or set again first.
    seconds: float = Field(gt=0, le=PAUSE_MAX_S)


@dataclass
class Daemon:
    runtime: Runtime
    config: ConfigSource
    tokens: TokenStore
    port: int
    leases: Leases
    #: A person's pauses on agents' gestures, set through a scope's route: the daemon's `InputPause`.
    pauses: Pauses = field(default_factory=Pauses)
    codes: OneShotCodes = field(default_factory=OneShotCodes)
    viewers: ViewerSessions = field(default_factory=ViewerSessions)
    static_dir: Path | None = STATIC_VIEWER
    #: Where the settings panel reads and writes settings; without one, it is not served.
    settings: SettingsStore | None = None
    confirmations: PendingChanges = field(default_factory=PendingChanges)
    #: What each scope is called: its project's name, as what knows its folder told it.
    names: ScopeNames = field(default_factory=lambda: ScopeNames(None))

    def site_rules(self) -> SiteRules:
        """Who the server answers to, from the settings as they are now."""
        config = self.config.get(SERVER_SCOPE)
        return SiteRules(self.port, config.allowed_origins, config.frame_ancestors)


def build_daemon(
    *,
    config: ConfigSource,
    state: StateStore,
    memory: DeviceMemory,
    tokens: TokenStore,
    port: int,
    copy: HostCopy | None = None,
    registry: ConnectorRegistry | None = None,
    claims: Claims | None = None,
    xcrun: XcrunRunner = run_xcrun,
    static_dir: Path | None = STATIC_VIEWER,
    settings: SettingsStore | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    platform: str = sys.platform,
) -> Daemon:
    leases = Leases(clock=clock)
    pauses = Pauses(clock=clock)
    extra: dict[str, Any] = {} if sleep is None else {"sleep": sleep}

    def same_host(scope: Scope, other: Scope) -> bool:
        mine, theirs = tokens.host_of(scope.id), tokens.host_of(other.id)
        return (mine.id if mine else None) == (theirs.id if theirs else None)

    runtime = Runtime.build(
        config=config,
        state=state,
        memory=memory,
        policy=ConfigPolicy(config, tokens, state),
        copy=copy,
        usage=leases,
        pause=pauses,
        registry=registry,
        claims=claims,
        xcrun=xcrun,
        may_share=same_host,
        clock=clock,
        platform=platform,
        **extra,
    )
    return Daemon(
        runtime=runtime,
        config=config,
        tokens=tokens,
        port=port,
        leases=leases,
        pauses=pauses,
        codes=OneShotCodes(clock=clock),
        # Beside the admin token: a restart of the same install lets its open pages in again.
        viewers=ViewerSessions(clock=clock, path=tokens.path.with_name(VIEWER_SESSIONS_FILE)),
        names=ScopeNames(tokens.path.with_name(SCOPE_NAMES_FILE)),
        static_dir=static_dir,
        settings=settings,
        confirmations=PendingChanges(clock=clock),
    )


def create_app(daemon: Daemon, on_stopped: Callable[[], object] | None = None) -> FastAPI:
    """The daemon's app. `on_stopped` runs once its runtime is closed -- still inside the server's shutdown, which a
    signal the server caught may end the process right after."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log_redaction.install()
        await daemon.runtime.start()
        try:
            yield
        finally:
            await daemon.runtime.close()
            if on_stopped is not None:
                on_stopped()

    app = FastAPI(
        title="Rocketwright", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(SecurityMiddleware, rules=daemon.site_rules)
    auth = TokenAuthenticator(
        daemon.tokens, daemon.viewers, lambda: daemon.site_rules().own_origins, names=daemon.names.name
    )

    def source() -> Runtime:
        return daemon.runtime

    app.include_router(create_http_router(source, auth), prefix=SCOPES)
    app.include_router(create_socket_router(source, auth), prefix=SCOPES)
    app.include_router(create_agent_router(source, auth), prefix=AGENT)
    if daemon.settings is not None:
        settings = create_settings_router(
            source, daemon.settings, auth, confirmations=daemon.confirmations, daemon_scope=SERVER_SCOPE
        )
        app.include_router(settings, prefix=SCOPES + "/settings")
    app.include_router(create_page_router(daemon.static_dir, name_of=daemon.names.name))

    def admin(request: Request) -> None:
        try:
            auth.admin(request)
        except Refused as exc:
            raise HTTPException(exc.status, exc.message) from exc

    def named(scope_id: str) -> Scope:
        try:
            return auth.scope(scope_id)
        except Refused as exc:
            raise HTTPException(exc.status, exc.message) from exc

    def host(request: Request) -> TokenRecord:
        try:
            return auth.host(request)
        except Refused as exc:
            raise HTTPException(exc.status, exc.message) from exc

    @app.get("/healthz")
    async def healthz(
        nonce: str | None = Query(None, max_length=health.NONCE_MAX),
        token_id: str | None = Query(None, max_length=32),
    ) -> dict[str, Any]:
        """Whether the daemon is up. Given a nonce, it proves it holds the admin token (`daemon.health`), so the CLI
        can tell it from anything else listening on its port before sending a credential -- and, given a scoped
        token's id too, that it knows that token, for a host holding no admin token."""
        proof = token_proof = None
        if nonce is not None:
            proof = health.proof(daemon.tokens.admin_token(), nonce)
            known = daemon.tokens.find(token_id) if token_id else None
            if known is not None:
                token_proof = health.token_proof(known.digest, nonce)
        return ok(
            {
                "server": SERVER,
                "protocol": PROTOCOL_VERSION,
                "port": daemon.port,
                "proof": proof,
                "token_proof": token_proof,
            }
        )

    @app.post(SCOPES + "/embed-tickets")
    async def embed_ticket(scope_id: str, request: Request) -> dict[str, Any]:
        """A one-shot ticket a host's backend puts in a frame's URL: ``/embed/<scope>#ticket=…``."""
        try:
            scope = (await auth.person(request, scope_id)).scope
        except Refused as exc:
            raise HTTPException(exc.status, exc.message) from exc
        ticket = daemon.codes.mint(scope.id, "embed")
        return ok({"url": f"/embed/{scope.id}#ticket={ticket}", "expires_in_s": CODE_TTL_S})

    @app.post("/api/v1/auth/exchange")
    async def exchange(body: ExchangeRequest) -> dict[str, Any]:
        """Spend a login code or an embed ticket for a viewer token for its scope, of the kind the code was for."""
        spent = daemon.codes.redeem(body.code)
        if spent is None:
            raise HTTPException(401, BAD_CODE)
        token = daemon.viewers.open(spent.scope_id, spent.kind)
        return ok({"token": token, "scope": spent.scope_id, "kind": spent.kind, "expires_in_s": ttl_of(spent.kind)})

    async def pausing(request: Request, scope_id: str) -> Scope:
        """The scope a person's pause is for: a host's, a viewer's or the admin's, never an agent's -- an agent cannot
        lift what holds it back."""
        try:
            return (await auth.person(request, scope_id)).scope
        except Refused as exc:
            raise HTTPException(exc.status, exc.message) from exc

    def pause_of(scope: Scope) -> dict[str, Any]:
        left = daemon.pauses.left(scope.id)
        return ok({"scope": scope.id, "paused": left > 0, "expires_in_s": left})

    @app.get(SCOPES + "/pause")
    async def pause_status(scope_id: str, request: Request) -> dict[str, Any]:
        """Whether a person has paused agents' gestures on the scope's device, and for how much longer."""
        return pause_of(await pausing(request, scope_id))

    @app.put(SCOPES + "/pause")
    async def pause_hold(scope_id: str, body: PauseRequest, request: Request) -> dict[str, Any]:
        """Keep agents' gestures off the scope's device for `seconds` from now; set it again to keep it longer."""
        scope = await pausing(request, scope_id)
        daemon.pauses.hold(scope.id, body.seconds)
        return pause_of(scope)

    @app.delete(SCOPES + "/pause")
    async def pause_lift(scope_id: str, request: Request) -> dict[str, Any]:
        """Let agents touch the scope's device again."""
        scope = await pausing(request, scope_id)
        daemon.pauses.lift(scope.id)
        return pause_of(scope)

    @app.post(AGENT + "/lease")
    async def agent_lease(request: Request) -> dict[str, Any]:
        """Keep this agent's scope's device from being reaped for another while. The answer says how long its client
        may go without a tool call before it stops renewing (``device.agent_idle_minutes``)."""
        try:
            caller = await auth.agent(request)
        except Refused as exc:
            raise HTTPException(exc.status, exc.message) from exc
        daemon.leases.renew(caller.scope.id, caller.key)
        idle_s = daemon.config.get(caller.scope).agent_idle_minutes * 60
        return ok({"scope": caller.scope.id, "expires_in_s": LEASE_S, "agent_idle_s": idle_s})

    @app.post(AGENT + "/warm")
    async def agent_warm(request: Request) -> dict[str, Any]:
        """Get this agent's scope's simulator ready before its first tool call -- ``rocketwright mcp`` asks as it starts
        -- when that is free: only a simulator already booted is attached, in the background, and nothing is held for
        the agent (`DeviceManager.warm`). Answers at once, whatever it did."""
        try:
            caller = await auth.agent(request)
        except Refused as exc:
            raise HTTPException(exc.status, exc.message) from exc
        outcome, reason = await daemon.runtime.manager.warm(caller.scope)
        return ok({"scope": caller.scope.id, "warm": outcome, "reason": reason})

    @app.post(ADMIN + "/reload")
    async def reload(request: Request) -> dict[str, Any]:
        """Act on changed settings now: what was switched off stops before this answers."""
        admin(request)
        await daemon.runtime.reconcile()
        return ok({"reloaded": True})

    @app.get(ADMIN + "/in-use")
    async def in_use(request: Request) -> dict[str, Any]:
        """The scopes the daemon serves now -- running a device, held by an agent's lease, or building -- so stopping it
        (`rocketwright stop --daemon`) never ends another scope's session unasked, nor shutting a simulator down
        (`--shutdown`) another scope's device: each running scope's device is named, and its UDID beside it."""
        admin(request)
        devices = {
            scope_id: instance
            for instance in daemon.runtime.manager.instances()
            if instance.live
            for scope_id in instance.scopes
        }
        leased = daemon.leases.scopes()
        building = {run.scope.id for run in daemon.runtime.builds.runs()}
        served = sorted(set(devices) | leased | building)
        return ok(
            {
                "scopes": [
                    {
                        "id": scope_id,
                        "device": devices[scope_id].name if scope_id in devices else None,
                        "udid": devices[scope_id].udid if scope_id in devices else None,
                        "agent": scope_id in leased,
                        "building": scope_id in building,
                    }
                    for scope_id in served
                ]
            }
        )

    @app.delete(ADMIN + "/devices/{udid}")
    async def let_go(udid: str, request: Request) -> dict[str, Any]:
        """End a device's session for every scope using it -- ``rocketwright stop --device`` -- leaving the device
        running, and say which scopes used it and which agents held each."""
        admin(request)
        held = await daemon.runtime.manager.let_go(udid)
        # The agents working on it let it go too, or the next one to call would still be told it is in use.
        daemon.runtime.selections.release(udid=udid)
        holders = daemon.leases.holders()
        return ok(
            {
                "udid": udid,
                "stopped": held is not None,
                "scopes": [
                    {"id": scope.id, "agents": sorted(agent_label(key) for key in holders.get(scope.id, ()))}
                    for scope in held or ()
                ],
            }
        )

    @app.post(ADMIN + "/devices/prune")
    async def prune(body: PruneRequest, request: Request) -> dict[str, Any]:
        """Delete the simulators Rocketwright made that nothing runs and that hold no app -- every one nothing runs,
        with ``all`` -- forgetting each (``rocketwright devices prune``); ``dry_run`` only says which. Answers each one
        found."""
        admin(request)
        try:
            found = await daemon.runtime.manager.prune(everything=body.all, dry_run=body.dry_run)
        except SimulatorUnavailable as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        except DeviceControlError as exc:
            raise HTTPException(502, str(exc)) from exc
        return ok({"devices": [entry.as_json() for entry in found], "dry_run": body.dry_run})

    def agent_label(token_id: str) -> str:
        """How an agent holding a lease is named: its token's label -- ``rocketwright mcp (pid 4242)`` -- or its id."""
        record = daemon.tokens.find(token_id)
        return record.label if record is not None and record.label else token_id

    @app.post(ADMIN + "/login-codes")
    async def login_code(body: LoginCodeRequest, request: Request) -> dict[str, Any]:
        """A one-shot code that opens a scope's viewer: ``/viewer/<scope>#code=…`` -- able to change its settings when
        asked for with ``settings``."""
        admin(request)
        scope = named(body.scope)
        if body.label:
            daemon.names.remember(scope.id, body.label)
            # A simulator that came up while the scope was known by its id alone takes its project's name now.
            await daemon.runtime.manager.name_again(named(body.scope))
        code = daemon.codes.mint(scope.id, "settings" if body.settings else "viewer")
        return ok({"code": code, "url": f"/viewer/{scope.id}#code={code}", "expires_in_s": CODE_TTL_S})

    @app.delete(ADMIN + "/viewer-sessions")
    async def end_viewer_sessions(request: Request) -> dict[str, Any]:
        """End every page's session (``rocketwright token sign-out``): each open page needs ``rocketwright open``
        again."""
        admin(request)
        return ok({"ended": daemon.viewers.end_all()})

    @app.post(ADMIN + "/scopes/{scope_id}/inherit")
    async def inherit(scope_id: str, body: InheritRequest, request: Request) -> dict[str, Any]:
        """Give a scope with no device yet the device of another -- ``rocketwright mcp`` started in a git worktree asks
        for its main checkout's -- so its first call does not create a new one. Answers the UDID given, or null."""
        admin(request)
        return ok({"udid": daemon.runtime.manager.inherit(named(scope_id), named(body.source))})

    @app.post(ADMIN + "/logins")
    async def give_login(body: GivenLoginRequest, request: Request) -> dict[str, Any]:
        """Keep a login ``rocketwright login`` read from the person's password manager -- outside any sandbox the daemon
        runs in -- for one `sim_login` of this scope and app (`core.given`): answers the item to pass it as, never the
        login. Kept in memory only, and dropped once taken or after two minutes."""
        admin(request)
        scope = named(body.scope)
        if not body.password and not body.totp:
            raise HTTPException(400, "a login handed over has a password or a one-time code")
        credentials = Credentials(body.username, body.password, body.totp)
        title = body.title or body.username or body.app
        return ok({"item": daemon.runtime.given.give(scope.id, body.app, title, credentials)})

    @app.post(ADMIN + "/settings-confirmations")
    async def settings_confirmations(request: Request) -> dict[str, Any]:
        """The sensitive settings changes waiting for a person to confirm them, each with its code. A POST, so no
        cache keeps a code."""
        admin(request)
        return ok({"pending": daemon.confirmations.waiting()})

    @app.post(ADMIN + "/tokens")
    async def create_token(body: TokenRequest, request: Request) -> dict[str, Any]:
        admin(request)
        try:
            record, token = daemon.tokens.create(body.kind, body.scopes, label=body.label, roots=body.roots)
        except TokenRefused as exc:
            raise HTTPException(400, str(exc)) from exc
        daemon.names.remember_folders(body.scopes, body.roots)
        for scope_id in body.scopes:
            with contextlib.suppress(HTTPException):  # a scope no person names, such as a host's namespace
                await daemon.runtime.manager.name_again(named(scope_id))
        return ok({**record.public(), "token": token})

    @app.get(ADMIN + "/tokens")
    async def list_tokens(request: Request) -> dict[str, Any]:
        admin(request)
        return ok({"tokens": [record.public() for record in daemon.tokens.records()]})

    def let_go_of_leases(token_id: str) -> list[str]:
        """The ids of a token about to be revoked and of every token it made, whose leases end with it."""
        return [record.id for record in daemon.tokens.records() if token_id in (record.id, record.host)]

    @app.delete(ADMIN + "/tokens/{token_id}")
    async def revoke_token(token_id: str, request: Request) -> dict[str, Any]:
        """Revoke a token -- and, for a host token, every token that host made -- letting go of their leases and of the
        devices they drove (`core.drivers`)."""
        admin(request)
        going = let_go_of_leases(token_id)
        revoked = daemon.tokens.revoke(token_id)
        if revoked:
            for held_by in going:
                daemon.leases.release_holder(held_by)
                daemon.runtime.let_go(held_by)
        return ok({"revoked": revoked})

    @app.get(HOST)
    async def host_record(request: Request) -> dict[str, Any]:
        """The host token's own record: its namespaces and folders."""
        return ok(host(request).public())

    @app.post(HOST + "/tokens")
    async def host_create_token(body: HostTokenRequest, request: Request) -> dict[str, Any]:
        """An agent or viewer token for scopes in this host's namespaces, naming folders inside its own."""
        maker = host(request)
        try:
            record, token = daemon.tokens.create(body.kind, body.scopes, label=body.label, roots=body.roots, host=maker)
        except TokenRefused as exc:
            raise HTTPException(400, str(exc)) from exc
        return ok({**record.public(), "token": token})

    @app.get(HOST + "/tokens")
    async def host_list_tokens(request: Request) -> dict[str, Any]:
        """The tokens this host made."""
        return ok({"tokens": [record.public() for record in daemon.tokens.made_by(host(request))]})

    @app.delete(HOST + "/tokens/{token_id}")
    async def host_revoke_token(token_id: str, request: Request) -> dict[str, Any]:
        """Revoke a token this host made, letting go of its leases and of the devices it drove; any other is not its to
        revoke, and is left as it is."""
        revoked = daemon.tokens.revoke(token_id, host=host(request))
        if revoked:
            daemon.leases.release_holder(token_id)
            daemon.runtime.let_go(token_id)
        return ok({"revoked": revoked})

    return app
