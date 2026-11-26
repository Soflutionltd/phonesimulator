# SPDX-License-Identifier: Apache-2.0
"""Which tools an agent is offered, and running a call to one.

Tools come from providers: the device tools always, the build tools while ``build.tools`` is on, `sim_login` while
``login.sources`` names a password manager -- and a host or a
later version adds a provider rather than editing this. A manifest lists every tool of a provider offered, whatever the
scope's device can do now: a tool its connector cannot serve -- `sim_act` on a view-only mirror, or on a real device
whose cable came out -- is refused when called, saying why and what would put it right (`context.require`). A list
that changed with the device would leave an agent unable to tell a tool that is not there from one it cannot use yet,
and a client that keeps the tools it was first given would never hear that one came back.

A call that fails on the device asks whether the device is still there: one shut down outside Rocketwright answers
`SHUT_DOWN` rather than what its tool said of it, and its session is ended so the next call starts it again.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any, Protocol

from rocketwright.build.provider import BuildToolProvider
from rocketwright.build.xcodebuild import BuildRefused
from rocketwright.config.model import SimConfig
from rocketwright.core.actions import ActionError
from rocketwright.core.masking import SecretMask
from rocketwright.platform.errors import DeviceControlError
from rocketwright.tools import act, app, device, flow, matrix, record, screenshot, snapshot
from rocketwright.tools.context import Tool, ToolContext
from rocketwright.tools.login import LoginToolProvider
from rocketwright.tools.results import SHUT_DOWN, Result, ToolRefused, text
from rocketwright.tools.schemas import LOOK_AND_ACT


class ToolProvider(Protocol):
    @property
    def tools(self) -> tuple[Tool, ...]:
        """Every tool this provider has, whether offered now or not."""
        ...

    def offered(self, config: SimConfig) -> bool:
        """Whether a scope with these settings is offered the tools."""
        ...

    def instructions(self, config: SimConfig) -> str:
        """What an agent is told, for these settings."""
        ...


class DeviceToolProvider:
    """Looking at and touching the device, and its apps: always offered."""

    tools: tuple[Tool, ...] = (
        device.TOOL,
        snapshot.TOOL,
        screenshot.TOOL,
        act.TOOL,
        app.TOOL,
        record.TOOL,
        flow.TOOL,
        matrix.TOOL,
    )

    def offered(self, config: SimConfig) -> bool:
        return True

    def instructions(self, config: SimConfig) -> str:
        return LOOK_AND_ACT


class ToolRegistry:
    def __init__(
        self,
        providers: Sequence[ToolProvider] | None = None,
        *,
        secrets: SecretMask | None = None,
    ) -> None:
        self._providers = tuple(
            providers if providers is not None else (DeviceToolProvider(), BuildToolProvider(), LoginToolProvider())
        )
        self._tools = {tool.name: tool for provider in self._providers for tool in provider.tools}
        #: The passwords `sim_login` typed, as digests: masked in every answer, whichever tool gives it.
        self.secrets = secrets or SecretMask()

    def names(self) -> list[str]:
        return list(self._tools)

    def manifest(self, config: SimConfig) -> dict[str, Any]:
        """The tools a scope with these settings is offered, whatever its device can do now, and how to use them."""
        offered = [provider for provider in self._providers if provider.offered(config)]
        return {
            "tools": [tool.listing() for provider in offered for tool in provider.tools],
            "instructions": "".join(provider.instructions(config) for provider in self._providers),
        }

    async def call(self, name: object, arguments: object, ctx: ToolContext) -> Result:
        """Run one tool call, answering with its result -- or with why not, as an error result -- with any password
        `sim_login` typed masked in it, wherever it came from: a screen, a log, an error."""
        return self.secrets.result(await self._call(name, arguments, ctx))

    async def _call(self, name: object, arguments: object, ctx: ToolContext) -> Result:
        tool = self._tools.get(name) if isinstance(name, str) else None
        if tool is None:
            return text(f"there is no tool named {name!r}", error=True)
        if not isinstance(arguments, dict):
            return text("arguments must be an object", error=True)
        try:
            return await tool.handler(arguments, dataclasses.replace(ctx, tool=tool, secrets=self.secrets))
        except (ActionError, DeviceControlError) as exc:
            # Only what the device's connector or its tool failed at can mean the device has gone, so only that asks.
            from_device = isinstance(exc, DeviceControlError) or exc.__cause__ is not None
            return text(
                SHUT_DOWN if from_device and await ctx.manager.gone(ctx.scope, ctx.udid) else str(exc), error=True
            )
        except (ToolRefused, BuildRefused) as exc:
            return text(str(exc), error=True)
