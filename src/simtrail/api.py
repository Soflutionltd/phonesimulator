# SPDX-License-Identifier: Apache-2.0
"""The surface a host application embeds Simtrail through.

A host builds one `Runtime` from its seams -- where settings come from, where state lives, which device a scope
remembers, what a scope may do, who is asking, and the words its messages use -- mounts the router factories under its
own prefixes, and gives its agents the relay's command line. Everything a host needs is named here; anything else in
the package may change between minor versions.

What that promise is worth is `docs/stability.md`: from 1.0 these names, their parameters and their fields do not break
in a minor release. `tests/unit/test_api.py` writes the list down so one cannot leave it by accident, and
`compat/surface-v3.json` holds each to what 3.0 made it, which kept all of 2.0 and 1.0.

Three of these are here because a real host needed them and had to reach past this surface to get them:
`InvalidScope`, which `Scope` raises; `JsonDeviceMemory`, so a host need not write a `DeviceMemory` of its own; and
`claims_dir`, which is how every host on one Mac sees the same device claims and so refuses each other's devices
rather than fighting over one.

`InputPause`, optional to pass to `Runtime.build`, is how a host tells agents to keep their gestures off a device while
its person uses it: Simtrail sees a person's input through a viewer, never a finger on a real phone's own screen.

A host that lets a page change its settings mounts `create_settings_router` with a `SettingsStore`, a
`SettingsAuthenticator` and, for the settings a page may not change alone, `Confirmations`. One that keeps its own
settings screens mounts none of it.

A host can also run no Simtrail of its own and share the local daemon with other hosts instead: `DaemonHost`, with a
host token for its namespaces, answering `AgentAccess` for its agents and raising `DaemonRefused` or
`DaemonUnavailable`.
"""

from __future__ import annotations

from simtrail.config.model import SimConfig
from simtrail.config.provenance import SettingOrigin
from simtrail.core.devices import JsonDeviceMemory
from simtrail.core.manager import SimulatorUnavailable
from simtrail.core.runtime import Runtime
from simtrail.host_copy import HostCopy
from simtrail.hosting import AgentAccess, DaemonHost, DaemonRefused
from simtrail.mcp.launcher import DaemonUnavailable
from simtrail.mcp.relay import relay_command
from simtrail.scope import InvalidScope, Scope
from simtrail.seams import (
    Admission,
    Authenticator,
    Caller,
    ConfigSource,
    Confirmations,
    DeviceMemory,
    HeldDevice,
    InputPause,
    Person,
    Policy,
    Refused,
    SettingsAuthenticator,
    SettingsEditor,
    SettingsRefused,
    SettingsStore,
    StateStore,
    UsageProbe,
)
from simtrail.server.agent_routes import create_agent_router
from simtrail.server.http_routes import create_http_router
from simtrail.server.settings_routes import create_settings_router
from simtrail.server.socket_routes import create_socket_router
from simtrail.storage.app_support import claims_dir

__all__ = [
    "Admission",
    "AgentAccess",
    "Authenticator",
    "Caller",
    "ConfigSource",
    "Confirmations",
    "DaemonHost",
    "DaemonRefused",
    "DaemonUnavailable",
    "DeviceMemory",
    "HeldDevice",
    "HostCopy",
    "InputPause",
    "InvalidScope",
    "JsonDeviceMemory",
    "Person",
    "Policy",
    "Refused",
    "Runtime",
    "Scope",
    "SettingOrigin",
    "SettingsAuthenticator",
    "SettingsEditor",
    "SettingsRefused",
    "SettingsStore",
    "SimConfig",
    "SimulatorUnavailable",
    "StateStore",
    "UsageProbe",
    "claims_dir",
    "create_agent_router",
    "create_http_router",
    "create_settings_router",
    "create_socket_router",
    "relay_command",
]
