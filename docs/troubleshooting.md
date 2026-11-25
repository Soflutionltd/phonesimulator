# Troubleshooting

Start with `simtrail doctor`: most problems show up there with a fix. Logs are in `~/Library/Logs/Simtrail`.

## Taps do nothing

The screen shows, snapshots read it, but taps, typing and buttons have no effect -- and `simtrail doctor` says
"Input was swallowed".

On Xcode 27, a simulator that **Device Hub** has taken over can take input only through Device Hub's own transport and
silently ignore idb_companion's. Close Device Hub, shut the device down, and boot it again with Device Hub closed
(Simtrail boots it headless when it starts it). Synthetic scrolling can also be dropped there; agents use drags.

Measured on Xcode 27.0 (27A266a): a device merely booted while Device Hub was open still took Simtrail's taps, so an
open Device Hub is not always the cause -- `simtrail doctor` warns while it is open, and its real tap says whether
input actually arrives.

## How typed text arrives

Text from the viewer or an agent's `type` step is **typed as key presses** when every character is on a US keyboard
and the Mac's keyboard layout is US or ABC, and **pasted** otherwise -- `device.typing` (`auto`, `keys` or `paste`)
changes that. Typed text needs no permission on any iOS, but iOS treats it as it treats a person's typing: in a field
that allows smart punctuation, `'` becomes `’` and `--` becomes `—`.

- **Text with a character no key types** -- an accented letter, an emoji, another script -- is pasted whole.
- **Another keyboard layout on the Mac**: keys go through it, so a Ukrainian layout would type "wifi" as "цшаш", and
  Simtrail pastes instead. Switch the Mac to ABC while typing, or set `device.typing` to `keys` if your layout puts
  every key where a US keyboard does.

## Typed text asks to "Allow Paste"

A paste asks first on iOS 26: the first time an app is pasted into, iOS asks whether it may paste from
"CoreSimulatorBridge". Choose **Allow Paste** once; that app then takes pastes without asking. Text typed as keys,
touches and named keys never ask.

## Typing does nothing on iOS 27

iOS 27 refuses a paste Simtrail sends without asking -- the pasteboard holds the text and Cmd+V arrives, yet nothing
appears (measured with Xcode 27.0, 27A266a, and idb_companion 1.5.7;
[#27](https://github.com/Soflutionltd/simtrail/issues/27)). Text typed as keys arrives, so this happens only when the
text is pasted: when it has a character no key types, when the Mac's layout is not US or ABC, or when `device.typing`
is `paste`. An agent's step says so -- `pasted, since 'é' has no key to type it with, and iOS 27.0 refuses a paste
without asking`. For such text, tap the on-screen keyboard.

## Two Xcodes on one Mac

Simtrail uses the Xcode a scope's `device.developer_dir` names, else a `DEVELOPER_DIR` it was started with, else the
one `xcode-select` names -- and it tells every program it starts which that is, simctl and idb_companion alike. It never
changes `xcode-select`, which is the whole machine's, so a Mac can keep one Xcode selected for everyday work while
Simtrail uses another:

```sh
simtrail config set device.developer_dir /Applications/Xcode27.app/Contents/Developer
```

Changing it brings a running device back up on the new Xcode; its viewers reconnect by themselves. `simtrail doctor`
says which Xcode it found and what named it, which Xcode the rest of the Mac uses when that differs, and which Xcode
each companion already running runs with. A companion keeps the Xcode it started with, so one started before
`xcode-select` was switched is still on the old one until its device is started again.

## Xcode has not approved Simtrail to use its tools

Reading the screen through Xcode 27 -- the `mcpbridge` connector, or `connectors.mcpbridge.merge` -- needs Xcode's
approval, which Xcode gives an agent that opens a project through its tools. Once, in a project's folder:

```sh
simtrail xcode approve            # or: simtrail xcode approve path/to/App.xcodeproj
```

Allow Simtrail if Xcode asks. The project is opened through Xcode's tools and closed again, unless you had it open.
`simtrail doctor` reads a booted simulator through Xcode to check.

## "Xcode's tools already have a session on this simulator"

A simulator can be in one of Xcode's device-interaction sessions at a time, and another agent -- one working in Xcode
-- has it. End that session where it was started, and Simtrail's next read opens its own. A session Simtrail itself
left, after a read that timed out or a process that stopped, is taken back without asking; Simtrail ends its own a
minute after its last read.

## Snapshots leave out a web page's text

The accessibility tree the native helper and idb_companion read does not reach inside Safari's pages and web views. With Xcode 27, turn on
`connectors.mcpbridge.merge`: snapshots then add what Xcode's UI hierarchy has there -- headings, text, links -- and a
tap on them works as on anything else. See [Connectors](connectors.md#merging-xcodes-hierarchy).

## The viewer is view-only

The viewer says it is a mirror, and agents are told `sim_act` needs a connector that can touch the screen.

With `connectors.preferred = "mcpbridge"` that is by design: it reads the screen but does not touch it. Otherwise,
Simtrail fell back to the `simctl` connector because neither the native helper nor idb_companion could be used; the
viewer and `simtrail doctor` say why. Build the helper with `simtrail helper build` (an install from Homebrew or a
git checkout has none until then), or install idb_companion (`brew install facebook/fb/idb-companion`). With
`connectors.preferred` set to `native` or `idb` Simtrail refuses instead of falling back, and says why.

## The native helper cannot be used

`simtrail helper status` says which helper Simtrail runs and why it cannot: none built, one from another Simtrail
version (build it again with `simtrail helper build --force`), or `connectors.native.helper_path` naming something
that does not run. With `auto`, Simtrail uses idb_companion or simctl meanwhile and says so. When it starts but a
device's input does not answer, try the other input path: `simtrail config set connectors.native.hid_transport
indigo` (or `dtuhid`); `simtrail doctor` checks the helper reaches a booted simulator. Its log is
`native-<udid>.log` in the log folder.

## Snapshots do not read an app's own views

An app shares its view hierarchy only when it links [SimtrailKit](app-sdk.md), calls `Simtrail.start()`, and runs
as a Debug build on the simulator; `simtrail app hierarchy` says whether an app shares one, and `simtrail doctor`
has an **app hierarchy** check. When the viewer shows no `· SDK` chip:

- **`connectors.app.merge` is off** for the project: turn it on in the settings panel's Connectors tab.
- **The app is not in front**, or is paused in the debugger: only the app in front answers, and a paused one cannot.
- **It answers too slowly**: a snapshot says the app did not answer within `connectors.app.timeout_ms`; raise it -- to
  1000 while the app reads SwiftUI's debug data, whose first read after launch takes seconds.
- **It is a Release build**, or a configuration SwiftPM builds for release: the SDK does nothing there.
- **The app's log** says why it did not start: filter the device log for `SimtrailKit`
  (`sim_app` `logs` with `filter: "SimtrailKit"`).

## The simulator does not boot or show

Simulators need a logged-in desktop session. Over SSH, from a launch daemon, or before anyone has logged in, they may
not boot. `simtrail doctor` reports the session. Check that an iOS runtime is installed (the `runtimes` check).

## "Another process is already using this simulator"

Two Simtrails -- the daemon and an application embedding Simtrail, say -- never drive one device at once. The message
names the other process. Stop it, or give this scope another device: `simtrail devices list`, then
`simtrail devices choose UDID`. A claim held by a process that has exited is taken over automatically.

## "Something answered that is not your Simtrail daemon"

Another program -- or another account on the Mac -- is listening on Simtrail's port and could not prove it is your
daemon, so the CLI sent it nothing. Stop that program, or move Simtrail with `simtrail config set server.port 7467`.

## A socket path is too long

The native helper and idb_companion serve on a unix socket, whose path may have at most 104 bytes. Simtrail keeps them in `~/.simtrail/run`
for that reason; if you moved it with `SIMTRAIL_RUN_DIR`, choose a shorter folder.

## Leftover helper or idb_companion processes

Each native helper and companion is ended when its device is let go, and a helper also ends when the Simtrail that
started it does. One a crashed Simtrail left behind is ended the next time that
Simtrail starts -- only if the process that started it is gone, and never one another host started. To end one
yourself, `simtrail stop` in the project's folder (or `--scope <id>`) ends that project's, and `--daemon` the daemon
once it serves nothing else: no need to find and kill processes, and no risk of ending another session's.

A simulator shut down outside Simtrail -- from Simulator.app, or `xcrun simctl shutdown` -- has its session ended, and
its companion with it, within a minute, even while an agent holds the device; at once when a tool fails on it, or
when a viewer's stream of it fails -- the viewer says "the simulator was shut down" rather than freezing. The
agent is told "The device is shut down. sim_device boot starts it." rather than simctl's own words, and quitting an app
there is done already: nothing runs on a device that is off.

## The viewer says the simulator is off

`enabled` is `false` for this scope (`simtrail config get enabled`), and the screen socket was closed with 4403.
Switch it on with `simtrail config set enabled true`.

## An iframe stays blank

The page's origin is not in `security.frame_ancestors`; the browser's console says so. See
[the iframe guide](embedding/iframe.md).

## The web component shows nothing

The page's origin is not in `security.allowed_origins`, so the daemon answers its requests with 403 and no CORS
headers -- the page's own `fetch` fails first, with "Failed to fetch" -- and refuses its screen socket at the handshake
(HTTP 403: the browser sees the connection fail, with no close code). See
[the web component guide](embedding/web-component.md).

## Only JPEG, never H.264

H.264 is decoded with WebCodecs, which needs a secure page -- HTTPS, or `http://127.0.0.1`/`localhost` -- and a browser
that decodes H.264. Anywhere else the viewer uses JPEG. `stream.encoding` can force either.

The daemon's log says what each viewer got and why: `a viewer of <udid> streams jpeg: it decodes jpeg, and h264, jpeg is
offered` means the browser could not decode H.264 there; `… and jpeg is offered` means Simtrail did not offer it -- the
connector cannot stream it, or `stream.encoding` is `jpeg`.

## Agent tools are missing

- `agent.tools` is `false` for the scope.
- `sim_build_run` and `sim_test` are listed only while `build.tools` is on.
- The client still has the list from before an upgrade: from 2.3 the Claude Code plugin's server is `device`, so its
  tools are `mcp__plugin_simtrail_device__sim_*`. Reconnect the MCP server, or start a new session.

Every other tool is listed whatever the device can do: one its connector cannot serve -- `sim_act` on a view-only
mirror, or on a real device whose cable came out -- answers with why and what puts it right, rather than going missing.
`simtrail tools` lists what this install offers.

## A real device cannot be touched, and nothing says why

- `sim_device health` says, one `key: value` line each, whether the screen, its reading and touch work now, the text
  reader's state, the device's `note:` -- its cable capture down, the Camera withheld -- and `last_error:`, what last
  kept WebDriverAgent from driving it, with when.
- `simtrail wda status` says, for every real device the daemon drives, whether WebDriverAgent is built for it and
  installed on it, whether it answers now, and its last error. The doctor's `camera` check says what the cable
  screen's helper last said, such as macOS withholding the Camera.
- `Authentication canceled` from WebDriverAgent can mean a passcode prompt on the device was cancelled: unlock the
  device and start it again, entering the passcode if it asks.

## A test run goes on for minutes after its tests finished

Left to itself, xcodebuild collects the simulator's diagnostics after a test fails -- `simctl diagnose`, for up to ten
minutes -- before it ends and Simtrail can answer. `sim_test` asks it not to, since the failures are already in the
result bundle. Set `build.test_diagnostics` to `true` when you want those diagnostics kept in the bundle anyway, and
raise `build.timeout_minutes` to leave room for them.

## Tests do not build

`sim_test` answers `the tests did not build` with the compile errors, where no test ran. Fix those first; a test id
from an earlier failure still works once they build.

## An agent's build is another app than yours

A project that gives each build configuration its own bundle id -- `com.example.app.debug` for Debug,
`com.example.app.staging` for Staging -- puts a second app on the device when a build uses another configuration than
yours: signed out, with its own data. `sim_build_run` builds the configuration the call names, then
`build.configuration`, then the one the scheme's Run action builds with in Xcode (its Test action's for `sim_test`),
and Debug for a scheme that has no file to say. The answer's first line names the configuration, with `its scheme's`
when it came from the scheme.

- A scheme Xcode made up has no file: make it Shared under Product > Scheme > Manage Schemes, so the configuration its
  Run action names is the one built.
- Set `build.configuration` for the project, as `simtrail config set build.configuration Staging`, to build one
  configuration whatever its scheme says.
- Set `build.expected_bundle_id` to the app you use: a build of any other is then not installed, and the answer names
  both. xcodebuild installs the app a `sim_test` run's tests run in itself, so a test run is checked before it
  starts: Simtrail reads the scheme's build settings for its Test action -- the same configuration and destination
  -- and a run whose unit tests are hosted by another app (`TEST_HOST`), or whose UI tests drive one
  (`TEST_TARGET_NAME`), is not started, with both ids named. Logic tests, hosted by no app, install none and are not
  held to it, and nor are targets `only_testing` leaves out or `skip_testing` skips whole. With test plans, only
  the targets the run's plan turns on are checked -- the plan `test_plan` names, else the scheme's default -- read
  from its `.xctestplan`, since the build settings list the targets a plan turns off too; a target `only_testing`
  names is checked all the same. A plan Simtrail cannot find or read leaves every target checked. A worktree with
  settings of its own is held to its own `build.expected_bundle_id`.

## "… is not a folder builds may run in here" for the main checkout

A session started in a git worktree builds the same folder of its other checkouts, but a main checkout made with
`--separate-git-dir` keeps its git folder elsewhere, and git leaves nothing there that names the checkout back: a copy
of its `.git` file would look the same, so from the worktree it is refused. Run `git config core.worktree "$PWD"` once
at the top of the main checkout. Its git folder then names it, git itself goes by that, and builds from the worktree
may go there ([Git worktrees](clients/claude-code-cli.md#git-worktrees)).

## An agent's device stopped between calls

A device nobody watches, no agent holds and nothing builds on is stopped after `device.idle_minutes` (15). `simtrail
mcp` holds its scope's device from its client's first tool call for as long as calls keep coming: a client that has
made none for `device.agent_idle_minutes` (30), or that exited or crashed, lets it go, and its next call holds it
again. Raise either, or set `device.shutdown_on_idle` to `false` to leave idle devices booted.

`simtrail stop` names the scopes still holding a device, and `simtrail stop --device <udid>` lets it go for all of
them at once, the agents working on it included.

## Simulators Simtrail created pile up, or one went away

A project with no device gets a blank simulator named `Simtrail · <project>`, which takes 1.5 to 3.5 GB on disk. Once
it is stopped as idle and shut down, Simtrail deletes it when it holds no app anybody installed
(`device.delete_created = "empty"`, the default); the project's next call creates a fresh one. Set it to `"idle"` to
delete it whatever it holds, or `"never"` to keep it. A simulator you picked, a real device or an Android emulator is
never deleted, nor one another project still uses, nor any while `device.shutdown_on_idle` is `false`.

For those already left, `simtrail devices prune` deletes every simulator Simtrail created that nothing runs and that
holds no app, and says how much space it freed; `--all` deletes those with apps too, and `--dry-run` only lists them.

## A device is "in use by" another session

Sessions of one project share its devices: a call is refused only while another session changed the device within
the last 2 minutes, and goes through after. A session of another project keeps a device it called on within 2
minutes; once quiet that long it passes it over by itself. `steal: true` takes it at once, and `simtrail token revoke
<id>` -- the ids are in `simtrail token list` -- ends a stale session for good.

## WebDriverAgent did not come back after it was killed

That is on purpose. When WebDriverAgent ends on a real device -- killed from the device, by `devicectl`, or its cable
pulled -- with no tool call asking for it, Simtrail leaves it ended: a person took the phone back. The next tool call
on that device, or a viewer opened on it, starts it again and waits for it. The daemon's log says each time which of
the two it did, and why.

## "Simtrail was stopped by `simtrail stop --daemon`"

Someone stopped the daemon on purpose while an agent's MCP client was still connected, so its tool call was not made.
Call again: `simtrail mcp` starts the daemon as it does on first launch, with the same token, and sends the call.
Reconnecting the MCP server does the same. A daemon that went away without being asked -- it crashed, or was killed --
is started again by the next call that finds it gone, without asking first. Only a call nothing received is sent
again: one the daemon may have been working on when it went answers that it could not be reached. A daemon that comes
back on another port -- `server.port` was changed meanwhile -- is followed there, once it proves it is yours.

## "Nothing listens at 127.0.0.1:7466 any more"

The relay was run by a host itself, not by `simtrail mcp`, so it cannot start the daemon it lost. Start it with
`simtrail serve --detach` and call again. A relay given the run folder (`--run-dir`,
[Running the relay yourself](clients/other-mcp.md#running-the-relay-yourself)) finds the daemon on whatever port it
came back on; one without it keeps the port it was started with, so after a port change reconnect the MCP server.

## Still stuck

Open a [bug report](https://github.com/Soflutionltd/simtrail/issues/new?template=bug.yml) with
`simtrail doctor --json` and the relevant lines from the log.
