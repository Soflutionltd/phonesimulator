# Changelog

All notable changes to Simtrail are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Changed

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
