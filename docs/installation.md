# Installation

## Requirements

| | Needed for |
|---|---|
| A Mac with Apple Silicon and a logged-in desktop session | Simulators; they do not show over SSH |
| Xcode 26 or later, with an iOS runtime | Everything (`xcode-select -p` names the one used) |
| [uv](https://docs.astral.sh/uv/) or Homebrew | Installing and running Simtrail (Python 3.10 or later; Homebrew brings its own) |
| idb_companion 1.5, optional | Another way to touch the screen and read it; Simtrail's own helper needs no install |
| An iPhone or iPad in Developer Mode, optional | A [real device](real-devices.md); touching it needs WebDriverAgent, built with your own development team |

[Compatibility](compatibility.md) has the details.

## Install Simtrail

As a command on your `PATH` (recommended):

```sh
uv tool install git+https://github.com/Soflutionltd/simtrail
```

Or with [Homebrew](https://github.com/Soflutionltd/homebrew-tap):

```sh
brew install soflutionltd/tap/simtrail
```

The formula builds Simtrail from its PyPI release in its own Python 3.13 environment, so the first install compiles a
few Python extensions and takes a few minutes. The tap picks up a new release once it has been on PyPI for a day;
`brew upgrade simtrail` then brings it. An MCP client can run this install's command in place of `uvx`:
`claude mcp add simtrail -- simtrail mcp`.

Or run it without installing, as MCP client configurations do:

```sh
uvx --from git+https://github.com/Soflutionltd/simtrail simtrail doctor
```

Or as a library in a Python project that embeds it (see [Python host applications](embedding/python-fastapi.md)):

```sh
uv add "git+https://github.com/Soflutionltd/simtrail"
```

Simtrail is [on PyPI](https://pypi.org/project/simtrail/). The viewer's page is built into the package, so none of
these needs Node.

## The native helper

Simtrail touches, reads and streams a simulator's screen with its own helper, `simtrail-helper`
([Connectors](connectors.md#native)). The wheel on PyPI carries it, built for both Mac architectures, so `uv tool
install` and `uvx` need nothing more. An install without it -- Homebrew's, which builds from source, or a git checkout
-- builds it once with the Xcode it uses:

```sh
simtrail helper build     # a minute or two; kept in the state folder, under helpers/
simtrail helper status    # which helper Simtrail runs, and whether it fits this Simtrail
```

Until then `simtrail doctor` says so, and `auto` uses idb_companion if it is there, or simctl, view-only.

## idb_companion, optionally

```sh
brew install facebook/fb/idb-companion
```

Simtrail finds it on `PATH` or where Homebrew puts it; set `connectors.idb.companion_path` for anywhere else. `auto`
uses it when the native helper cannot be used, and `connectors.preferred = "idb"` always. Check with
`simtrail doctor`.

## The viewer library, for your own pages

The viewer is [on npm](https://www.npmjs.com/package/@soflution/simtrail) as `@soflution/simtrail`:

```sh
npm install @soflution/simtrail@3.9.0
```

See [the web component](embedding/web-component.md).

## Where files live

| Folder | Holds | Moved by |
|---|---|---|
| `~/Library/Application Support/Simtrail` | `config.toml`, the admin token, `tokens.json` (digests only), remembered devices, build results, the helpers built here (`helpers/`), WebDriverAgent's source and builds (`wda/`) | `SIMTRAIL_STATE_DIR` |
| `~/Library/Application Support/Simtrail/claims` | Which process uses which device, shared by every Simtrail on the Mac | `SIMTRAIL_CLAIMS_DIR` |
| `~/.simtrail/run` | `daemon.json`, the native helpers' and idb_companion's sockets and pid files (kept short: a socket path may have 104 bytes), and `device-changes.json`, what Simtrail changed on a device and has yet to put back | `SIMTRAIL_RUN_DIR` |
| `~/Library/Logs/Simtrail` | The daemon's, the native helpers' and the companions' logs | `SIMTRAIL_LOG_DIR` |
| `~/Movies/Simtrail` | [Recordings](recording.md) | `recording.folder` |

`SIMTRAIL_CONFIG` points at a different `config.toml`. Every folder is private to your user.

## Update

```sh
uv tool upgrade simtrail
```

and change the version in your MCP client configurations (`simtrail==<new version>`). A running daemon keeps the old
version until it is restarted.

## Uninstall

Remove WebDriverAgent from each real device it was set up on first, with `simtrail wda uninstall <udid>`, or in the
device's Settings › General › VPN & Device Management. Then:

```sh
uv tool uninstall simtrail
rm -rf ~/Library/Application\ Support/Simtrail ~/.simtrail ~/Library/Logs/Simtrail
```

Recordings stay in `~/Movies/Simtrail` until you remove them. Devices Simtrail created are named `Simtrail · …` in
Xcode's device list; delete them there if you no longer want them.
