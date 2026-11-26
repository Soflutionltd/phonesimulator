# Changelog

All notable changes to Simtrail are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.11.6] - 2026-11-26

### Added

- `device.template_keep` ("iPhone 17 Pro" by default): the templates of the device types it names, on the newest iOS
  installed, are made ahead of any demand, made again when they went away, and never deleted by
  `device.template_days`. Every other template is still made on demand and deleted after its days unused.

## [3.11.5] - 2026-11-26

### Added

- `device.template_days` (30 by default, 0 keeps them): a simulator template no device has been copied from for that
  many days is deleted, and made again the next time a device of its runtime and type is asked for.

## [3.11.4] - 2026-11-26

### Fixed

- Text is typed with the keys of the Mac's own keyboard layout -- AZERTY, QWERTZ, US, Shift and Option included --
  instead of pasted wherever the layout was not US or ABC: no more "Allow Paste" prompt at every word on iOS 26, and
  no more paste refused on iOS 27. Only a character the layout has no key for (an emoji, an accent typed with a dead
  key) is still pasted.

## [3.11.3] - 2026-11-26

### Fixed

- `simtrail helper status` and `simtrail helper allow` read the helper's permissions while one is missing too: the
  helper exits 1 then, and its answer was dropped.

## [3.11.2] - 2026-11-26

### Added

- `simtrail helper allow` opens System Settings at the Accessibility and Screen Recording lists and shows the helper in
  the Finder, to drag it in.

### Changed

- `simtrail helper status` says which permissions the helper actually holds (and `--json` gives them), instead of always
  asking to allow it.

### Fixed

- A Flutter run test that sent a KILL after the TERM on a busy machine: its rig gave a stopping run 10 ms.

## [3.11.1] - 2026-11-26

### Removed

- The viewer's French: it speaks English alone, and the View menu's Language section shows only once it speaks two
  languages. The bundle has room again under its 45 KB budget; the catalogue machinery stays, so a language can be
  added back as a file.

## [3.11.0] - 2026-11-26

### Added

### Changed

- A tool's structured content carries its text too (`text`), unless the text is that content as JSON: a client that
  shows only the structured part -- Claude Code does -- now sees the screen after `sim_act`'s steps, and what
  `sim_login` and `sim_flow` said, without calling again. One call per action instead of two.
- `sim_app launch` answers with the screen the app opened on, once it settled (`snapshot: "none"` to leave it out): one
  call instead of a launch and a `sim_snapshot`.
- `simtrail mcp` and the other commands that start the daemon look for it every 50 ms instead of every 200 ms, so
  they go on sooner once it listens.

### Fixed

- An open viewer tab survives the daemon restarting -- `simtrail stop --daemon` then a start, an upgrade -- and comes
  back by itself, instead of "authentication required" and a Try again that could not work. Its session is kept
  beside the admin token, as its token's SHA-256 and its expiry, in `viewer-sessions.json` (0600), and still ends when
  it would have; a daemon stopping tells its viewers the devices it leaves running will be back (`CLOSE_RESTARTING`);
  and a viewer that cannot reach its server at all -- no answer, or a proxy's 502, 503 or 504 -- tries again every two
  seconds for as long as it takes, a person's Try again included.

## [3.10.1] - 2026-11-26

### Added

- `simtrail helper sign --identity "<identity>"`: sign the helper with a code-signing identity of yours -- a Developer
  ID -- kept in Simtrail's state folder, so every later install signs with it whoever installs it, and no certificate
  is made.
- `device.delete_created`: a simulator Simtrail created for a project is deleted once the reaper stops it as idle and
  shuts it down -- when it holds no app anybody installed (`empty`, the default), whatever it holds (`idle`), or never
  (`never`) -- and forgotten, so the project's next call creates a fresh one. A simulator a person picked, a real
  device, an Android emulator, one another project still remembers, and any while `device.shutdown_on_idle` is off are
  never deleted; a deletion that fails is logged and the device kept.
- `simtrail devices prune [--all] [--dry-run]`: delete the simulators Simtrail created that nothing runs and that hold
  no app (every one nothing runs with `--all`), naming each and the space freed -- through the daemon while it runs,
  else directly.
- `JsonDeviceMemory.all_created`, `holders` and `forget_created`: what lets Simtrail delete the simulators it made. A
  host's own `DeviceMemory` without them keeps every device, as before.

### Fixed

- A helper signed with an identity named only in `SIMTRAIL_HELPER_SIGN_IDENTITY` was installed again unsigned by the
  next run without it -- `simtrail helper status`, a daemon -- losing the grants made to it.
- The build tests no longer fail on a busy machine: a Flutter or Gradle build's length is measured by the test's clock.

## [3.10.0] - 2026-11-26

### Added

- `simtrail mcp --scope-from-roots [--roots-meta KEY]`: one server for several sessions acts, call by call, for the
  project of the folder each call comes from -- its roots, or the folders a call names in its `_meta` -- with an agent
  token of that project's own, made at its first call and revoked when the server closes.
- `login.sources` and `simtrail login --source` take `keychain`: a login saved in the macOS Keychain with the app as
  its service.
- `simtrail login <app>`: sign the project's app in with a login asked from the password manager in your own
  terminal, for a daemon that cannot ask it from inside a sandbox an MCP client runs it in. The login is handed to the
  daemon for one `sim_login` (`source: "given"`), kept in memory for two minutes at most, and typed as any other.
- `sim_flow`: save a walkthrough under a name -- steps and waits exactly as `sim_act` takes them, or batches of them
  -- and play it again in one call through `sim_act`'s own checks, observe mode and one-agent-at-a-time hold. Flows
  are kept as JSON files in `<state>/flows/<project>/`, with what each ref named so another agent finds the element
  again; long flows are played 20 steps a call; `{{variable}}` values are given to `run`, a missing one refuses the
  run, and typing into a secure field must go through a variable so a secret is never kept.
- `sim_matrix`: capture one screen on several devices (UDIDs, or the presets `small_iphone`, `large_iphone`, `ipad`
  and `android`) in light and dark and an optional text size, launching an app and playing a saved flow first; each
  screenshot is saved in one folder with a captioned contact sheet, each device gets back its appearance and text size,
  and a device another agent works on is skipped unless `steal: true`.
- The viewer draws the device in a frame of its own: an iPhone with its Dynamic Island or notch and its side buttons,
  an older iPhone or iPad with its Home button, an iPad, an Android phone with its camera hole -- in CSS, never from a
  picture of the device -- and a macOS app's window alone. The screen keeps the device's exact shape, so a touch lands
  where it did; the buttons on the frame press the device's own where it can. View > Show device frame hides it.
- The viewer zooms: zoom out, zoom in, fit to the window, actual size, and the scale shown. A device larger than the
  room scrolls.
- A toolbar floats under the device -- its buttons, a screenshot, recording, the appearance, Display -- and the bar
  has the device picker with its name and runtime, and Edit, Device and View menus with the iOS Simulator's shortcuts
  (Shift-Command-H Home, Command-S a screenshot, Command-plus and Command-minus to zoom...). A menu lists only what
  can be done now.
- Screenshots from the viewer: the screen's last picture at its own pixels, saved as a PNG or copied to the clipboard.
- A light theme, following the system or picked in View; `ViewerOptions` gains `theme` and `deviceFrame`, the
  element `::part(device)` and `::part(toolbar)`, and the custom properties `--simtrail-raised`, `--simtrail-device`
  and `--simtrail-device-edge`. The theme and the frame shown are kept in the browser for next time.
- The viewer speaks French as well as English: its Edit, Device and View menus, the toolbar and its tooltips, the
  device picker, the zoom, the settings panel's own words and its sections' titles, what it says of a device that
  starts, stops or fails, its notes and every accessible name. It speaks the first of the browser's languages it
  knows (`navigator.languages`), else English; View > Language picks Automatic, English or Français, kept in the
  browser for next time, and the change is made where the viewer stands, without reloading or reconnecting.
  `ViewerOptions` gains `lang` and `onLang`, `ViewHandle` `setLang`, and `<sim-trail>` the `lang` attribute, which
  changes the language without starting afresh; the viewer's root carries the language as its own `lang`, for a
  screen reader. Messages live in typed catalogues, one file a language (`viewer/src/locales/`): adding a language
  is adding a file. What the server says -- a setting's and a section's description, a refusal's reason, a
  recording's notes -- is shown as it wrote it, in English.
- `sim_login` signs an app in with a login from the person's password manager -- 1Password through its CLI and the
  1Password app (Touch ID), Bitwarden, or a program of their own (`command:/path`) -- searching every vault. With
  `account`, a login for any other account is refused; several logins matching are refused without `item`. The
  password goes only into a secure field, the username into the field before it, and `code: true` types the login's
  one-time code. The agent never reads a value: the answer names the login and the fields filled, the viewer shows
  `••••`, and every later answer of every tool has the password and the code masked. Refused in observe mode, while
  the screen is recorded, through adb's `input text`, and on real devices and macOS apps unless `login.real_devices`
  is on. See [Signing in](docs/login.md).
- Settings `login.sources`, `login.onepassword_path`, `login.bitwarden_path`, `login.timeout` and
  `login.real_devices`; all but `login.timeout` are sensitive.
- The viewer turns a simulator: Rotate left and Rotate right in the toolbar and the Device menu, Command-Left Arrow
  and Command-Right Arrow, as Simulator.app has them -- through the same path as `sim_device rotate`, where the
  device's connector can turn it. The device is drawn turned, frame and all, and a touch lands under the finger.
  The protocol gains `Device.orientation` (portrait until Simtrail turns the device; an agent's rotate is shown too),
  the client message `RotateInput` (`{"type": "rotate", "direction": "left" | "right"}`) and the enums
  `ORIENTATIONS` and `ROTATE_DIRECTIONS`; the icon names gain `rotate_left` and `rotate_right`.

- **Flutter.** A folder whose `pubspec.yaml` depends on flutter is built by flutter, for an iOS simulator or an Android
  device: `sim_build_run` runs `flutter build ios --simulator` or `flutter build apk`, then installs and launches the
  app as for any build; `sim_test` runs `flutter test`, or with the new `integration` argument the integration tests
  on the device, and answers with the counts and each failure where it happened. Both take the new `flavor` and
  `dart_defines` arguments; the values reach flutter in a file only the user can read, deleted once flutter is done.
  Compile errors are answered as `file:line:column` and their message. See [Flutter](docs/flutter.md).
- **`sim_flutter`**, a new build tool: `run` starts the app with `flutter run --machine` and keeps it running for the
  agent; `hot_reload` and `hot_restart` answer their time or each compile error; `stop` and `status`. The app is
  stopped when the agent's session ends, when it may no longer build, and when Simtrail stops.
- `build.flutter_path` names the flutter command; otherwise `PATH`, then where Homebrew and a manual install put it.
  `simtrail doctor` has a `flutter` check that shows the version found.
- A device choice says what stands in its way by a name as well, `detail_code` (`not_connected`,
  `system_image_missing`, `usb_debugging_not_allowed`…), for a viewer to say it in its own language; `detail` still
  says it in English.

### Changed

- A snapshot says the on-screen keyboard in one line -- its keys' refs and what each says -- rather than a line for
  each of its three dozen keys, which cost more than the rest of the screen: about 60% less text for a sign-in screen
  with the keyboard up. A diff says the keyboard once when it comes, changes or goes. `sim_snapshot keys: true` lists
  each key; a key's ref still taps it.
- Agents of one project share its devices, one driving at a time: two sessions, the CLI and an MCP server are no
  longer refused one another's device for half an hour. An agent of another project keeps a device only while it has
  called within 2 minutes, as `device.exclusive` always said; quiet longer, or gone without saying so, it passes the
  device over by itself.
- `simtrail mcp` started in a git worktree gives its project, while it has no device yet, the simulator of the main
  checkout, instead of a new blank one being created at its first call.
- The viewer draws the device at its actual size by default, as Simulator.app's Point Accurate does: one point a CSS
  pixel, an iPhone 17 Pro 402 by 874. In a window too small it is drawn just small enough to fit, and the scale says
  so (`67% · fitted`). Command-1 is actual size, Command-0 fit to the window, and the zoom a person picks is kept in
  the browser beside the theme and the frame.
- A quieter viewer, in light and dark: switches that are on -- the appearance, recording, fit, actual size -- read in
  the accent; the toolbar, menus, device picker and notes float on one soft layered shadow instead of borders; a menu
  row highlights in the accent as a Mac menu does; the settings panel has a larger title, accent tabs, switches for
  on/off settings, pill buttons and a readable measure; the start and error screens set their message in a measure
  and break a long path; the agent's label and pill are flat colour, without gradients; a filled control's accent is
  a shade deeper so white text on it meets AA. The device picker keeps to a column, the toolbar is hidden while no
  device is shown, and turning the device is animated except with reduced motion. Every part, custom property and
  option of `<sim-trail>` is kept.

### Fixed

- The viewer's device picker: a row keeps one line -- its name whole, what is said of it cut short with an ellipsis
  and whole in its tooltip -- and a long list scrolls instead of squeezing rows over each other. A real device not
  connected is said so once, and what stands in a device's way is said in the viewer's language.
- macOS apps lists only apps with a Dock icon: macOS's own agents -- loginwindow, WindowManager, the wallpaper --
  and other apps' helpers are left out, unless one was installed for the scope.
- `sim_login` fills a password field that says it is secure only once it has the focus, as a Flutter app's does: it
  taps that field first, and types the password only if the field then says it is secure.
- On iOS 16 to 26, text Simtrail pastes -- on a Mac whose keyboard is not US-shaped, say AZERTY -- no longer leaves
  the step "ok" with nothing typed: the Allow Paste prompt iOS shows for the simulator's pasteboard bridge is allowed,
  and the step's line says so, or says the text did not arrive.
- `simtrail stop`, `simtrail stop --device`, `simtrail token revoke` and a host revoking a token let go of the devices
  the agents concerned worked on, which kept refusing other agents until those went quiet for 30 minutes.
- `simtrail mcp` ended with SIGTERM -- as a proxy or `kill` ends it -- revokes its token as on a normal exit, rather
  than holding its device for a process that is gone.
- The viewer's bar stays on one line from 640 px wide: the settings and release buttons no longer drop to a second
  line alone; the device's name is shortened first.
- Scrolling with the wheel or trackpad over a simulator driven by the native helper scrolls it again. The scroll was
  sent to the helper as a macOS app's window action, which a simulator's helper refuses, so nothing moved and the
  viewer said "The simulator did not take that: this device is not a macOS app". Window pointer input -- a secondary
  click, a hover, a key chord, a wheel -- now goes only to a session that has `input_pointer`; on every other device a
  scroll is a finger's swipe, as it was.
- Security: text an agent typed with `sim_act` or `sim_flow` into a secure field -- a password field named by a ref or
  a point, the one its last touch landed on, or the one being edited -- was shown in clear beside the agent's pointer
  in the viewer and in the macOS overlay, and said back in the step's line. It now reads `••••` in the agent events,
  the caption, the activity, the step's line and the answers, and is masked in every later answer of every tool, as
  `sim_login`'s password is; a character that has no key is no longer named in the line either.
- Security: that mask is set before the first key is struck. A `sim_act` or `sim_flow` step whose typing failed
  midway, or a call cancelled with the password half typed, left the part that reached the field unmasked in every
  later answer.
- Security: characters struck into a secure field one key at a time -- a `keys` step, or a `press` of a character --
  were said in clear in the step's line and beside the agent's pointer. They read `••••` too, and what one `keys`
  step typed is masked afterwards. [Security](docs/security.md#what-an-agent-can-reach) says what the mask does not
  cover: a screenshot of a password shown in clear, a value shorter than four characters, a file on disk such as
  `build.log`, a password spelled over several steps.
- Security: a Flutter run's `dart-defines.json`, which may hold secrets, was left on disk when the run failed or was
  cancelled between being prepared and started -- the JDK or the source could not be read, the app running on the
  device could not be stopped, or flutter could not be started. It is now deleted in each
  case, and written anew for the user alone (0600) even where a file or a link of that name was already there.
- A build cancelled the instant it started kept running, and held its DerivedData folder so that no later build of the
  scope could start.
- The Gradle log fixtures the tests read are in the repository again: a global ignore of `*.log` had kept them out, so
  three tests failed on a fresh clone.
- The viewer's Edit, Device and View menus open over the settings panel: opened while it was showing, a menu was
  drawn under it, open and unseen.

## [3.9.0] - 2026-11-24

First release of Simtrail by Soflution Ltd: drive iOS Simulators, real iPhones and iPads, Android emulators and
phones, and macOS apps from Claude Code or any MCP agent, with a live viewer, an agent cursor, token-efficient UI
snapshots, screen recording, builds and tests.
