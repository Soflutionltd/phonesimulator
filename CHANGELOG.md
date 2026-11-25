# Changelog

All notable changes to Simtrail are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Fixed

- The Gradle log fixtures the tests read are in the repository: a global `*.log` ignore had kept them out, so three
  tests failed on a fresh clone.

## [3.9.0] - 2026-11-24

First release of Simtrail by Soflution Ltd: drive iOS Simulators, real iPhones and iPads, Android emulators and
phones, and macOS apps from Claude Code or any MCP agent, with a live viewer, an agent cursor, token-efficient UI
snapshots, screen recording, builds and tests.
