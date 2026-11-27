# Installation

## Requirements

| | Needed for |
|---|---|
| A Mac with Apple Silicon and a logged-in desktop session | Simulators; they do not show over SSH |
| Xcode 26 or later, with an iOS runtime | Everything (`xcode-select -p` names the one used) |
| [uv](https://docs.astral.sh/uv/) or Homebrew | Installing and running PhoneSimulator (Python 3.10 or later; Homebrew brings its own) |
| idb_companion 1.5, optional | Another way to touch the screen and read it; PhoneSimulator's own helper needs no install |
| An iPhone or iPad in Developer Mode, optional | A [real device](real-devices.md); touching it needs WebDriverAgent, built with your own development team |

[Compatibility](compatibility.md) has the details.

## Install PhoneSimulator

As a command on your `PATH` (recommended):

```sh
uv tool install git+https://github.com/Soflutionltd/phonesimulator
```

Or with [Homebrew](https://github.com/Soflutionltd/homebrew-tap):

```sh
brew install soflutionltd/tap/phonesimulator
```

The formula builds PhoneSimulator from its PyPI release in its own Python 3.13 environment, so the first install compiles a
few Python extensions and takes a few minutes. The tap picks up a new release once it has been on PyPI for a day;
`brew upgrade phonesimulator` then brings it. An MCP client can run this install's command in place of `uvx`:
`claude mcp add phonesimulator -- phonesimulator mcp`.

Or run it without installing, as MCP client configurations do:

```sh
uvx --from git+https://github.com/Soflutionltd/phonesimulator phonesimulator doctor
```

Or as a library in a Python project that embeds it (see [Python host applications](embedding/python-fastapi.md)):

```sh
uv add "git+https://github.com/Soflutionltd/phonesimulator"
```

PhoneSimulator is [on PyPI](https://pypi.org/project/phonesimulator/). The viewer's page is built into the package, so none of
these needs Node.

## The native helper

PhoneSimulator touches, reads and streams a simulator's screen with its own helper, `phonesimulator-helper`
([Connectors](connectors.md#native)). The wheel on PyPI carries it, built for both Mac architectures, so `uv tool
install` and `uvx` need nothing more. An install without it -- Homebrew's, which builds from source, or a git checkout
-- builds it once with the Xcode it uses:

```sh
phonesimulator helper build     # a minute or two; kept in the state folder, under helpers/
phonesimulator helper status    # which helper PhoneSimulator runs, and whether it fits this PhoneSimulator
```

Until then `phonesimulator doctor` says so, and `auto` uses idb_companion if it is there, or simctl, view-only.

## idb_companion, optionally

```sh
brew install facebook/fb/idb-companion
```

PhoneSimulator finds it on `PATH` or where Homebrew puts it; set `connectors.idb.companion_path` for anywhere else. `auto`
uses it when the native helper cannot be used, and `connectors.preferred = "idb"` always. Check with
`phonesimulator doctor`.

## The viewer library, for your own pages

The viewer is [on npm](https://www.npmjs.com/package/@soflution/phonesimulator) as `@soflution/phonesimulator`:

```sh
npm install @soflution/phonesimulator@3.12.1
```

See [the web component](embedding/web-component.md).

## Where files live

| Folder | Holds | Moved by |
|---|---|---|
| `~/Library/Application Support/PhoneSimulator` | `config.toml`, the admin token, `tokens.json` (digests only), remembered devices, build results, the helpers built here (`helpers/`), WebDriverAgent's source and builds (`wda/`) | `PHONESIMULATOR_STATE_DIR` |
| `~/Library/Application Support/PhoneSimulator/claims` | Which process uses which device, shared by every PhoneSimulator on the Mac | `PHONESIMULATOR_CLAIMS_DIR` |
| `~/.phonesimulator/run` | `daemon.json`, the native helpers' and idb_companion's sockets and pid files (kept short: a socket path may have 104 bytes), and `device-changes.json`, what PhoneSimulator changed on a device and has yet to put back | `PHONESIMULATOR_RUN_DIR` |
| `~/Library/Logs/PhoneSimulator` | The daemon's, the native helpers' and the companions' logs | `PHONESIMULATOR_LOG_DIR` |
| `~/Movies/PhoneSimulator` | [Recordings](recording.md) | `recording.folder` |

`PHONESIMULATOR_CONFIG` points at a different `config.toml`. Every folder is private to your user.

## Update

```sh
uv tool upgrade phonesimulator
```

and change the version in your MCP client configurations (`phonesimulator==<new version>`). A running daemon keeps the old
version until it is restarted.

## Uninstall

Remove WebDriverAgent from each real device it was set up on first, with `phonesimulator wda uninstall <udid>`, or in the
device's Settings › General › VPN & Device Management. Then:

```sh
uv tool uninstall phonesimulator
rm -rf ~/Library/Application\ Support/PhoneSimulator ~/.phonesimulator ~/Library/Logs/PhoneSimulator
```

Recordings stay in `~/Movies/PhoneSimulator` until you remove them. Devices PhoneSimulator created are named `PhoneSimulator · …` in
Xcode's device list; delete them there if you no longer want them.
