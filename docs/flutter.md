# Flutter

A folder whose `pubspec.yaml` depends on flutter is a Flutter app, and Rocketwright's build tools build it with flutter
rather than xcodebuild or Gradle -- for an iOS simulator or an Android emulator or phone, whichever the agent works on.
Nothing to turn on but the build tools themselves: `rocketwright config set build.tools true`.

| Tool | Runs | Answers |
|---|---|---|
| `sim_build_run` | `flutter build ios --simulator --debug`, or `flutter build apk --debug` | Each compile error as `file:line:column` and its message; then the app installed and launched, as for any build |
| `sim_test` | `flutter test` -- the unit and widget tests | The counts, and each failure where it happened |
| `sim_test` with `integration: true` | `flutter test integration_test -d <device>` | The same, from the app on the device |
| `sim_flutter run` | `flutter run --machine -d <device>`, kept running | Once the app has started |
| `sim_flutter hot_reload`, `hot_restart` | A hot reload or restart of that app | Its time, or each compile error -- the app keeps the code it had |
| `sim_flutter stop`, `status` | Stops it, or says how it stands | |

## Building and testing

`flavor` picks a flavor (`--flavor`), and `dart_defines` gives the values the Dart code reads with
`String.fromEnvironment`:

```json
{"flavor": "staging", "dart_defines": {"API_BASE_URL": "http://localhost:5191"}}
```

The values reach flutter in a file only your user can read, deleted as soon as flutter is done with it -- never on its
command line, which any process on the Mac can read. `configuration` is a build mode -- `debug`, `profile` or
`release` -- and a simulator runs only `debug`. `only_testing` names test files or folders, from the app's folder:
`["test/login_test.dart"]`. Flutter's tests run once each, so `retries` and `skip_testing` are refused, and `scheme`,
`project`, `workspace` and `test_plan`, which are Xcode's, mean nothing here.

An integration test keeps the app installed after it (`--no-uninstall`): flutter would otherwise uninstall it, and
everything it had on the device with it.

## Hot reload

```text
sim_flutter run            → run ok · groceries (debug) · 14.9s · the app runs on the device …
(edit lib/…, save)
sim_flutter hot_reload     → hot reload ok · groceries (debug) · 0.2s · Reloaded 1 of 865 libraries
sim_flutter hot_reload     → hot reload FAILED · … · DevFS synchronization failed
                             error lib/screens/list_screen.dart:96:42 Expected an identifier, but got ','.
```

`run` builds and starts the app like a build -- one at a time in the project's DerivedData folder, the device busy and
said to be until the app has started -- and a first build longer than `wait_s` answers with its `build_id`, to call
again with. Then flutter keeps running for the agent: `hot_reload` puts its saved changes on the app and keeps its
state, `hot_restart` starts it again from `main`. While it runs the device takes `sim_act`, `sim_snapshot` and the rest
as usual.

One app runs this way on each device: a new `run`, or a build or integration test installed there, stops the one
before. It is stopped when the agent's session ends, when the build tools are switched off or commands no longer
allowed, and when Rocketwright stops -- flutter is asked to stop the app first, then ended if it does not go. Its whole
output is in the run's log, which `status` names.

## The flutter command

Rocketwright uses the flutter `build.flutter_path` names -- the command, or the Flutter SDK folder -- else the one on its own
`PATH`, else `/opt/homebrew/share/flutter/bin/flutter`, `~/flutter/bin/flutter` or `~/development/flutter/bin/flutter`:
a daemon started at login often has a shorter `PATH` than your shell. `rocketwright doctor` says which it found and its
version. flutter runs with its own folder, then Homebrew's, on its `PATH`, which an iOS build of a plugin needs for
CocoaPods.

## What it does not do

- **A real iPhone or a Mac.** A Flutter build for either has to be signed; build it from your shell with flutter and
  install it with `sim_app install`.
- **Checking the app before `run` installs it.** `flutter run` and an integration test install the app themselves, so
  with `build.expected_bundle_id` set they are refused only when the project's own files -- the iOS project's
  `PRODUCT_BUNDLE_IDENTIFIER`, the Android app's `applicationId` -- do not name it; a flavor that changes the id in a
  way those files do not show is not caught. `sim_build_run` checks the app it built, as for any project.
