# Changelog

All notable changes to Simtrail are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Fixed

- The Gradle log fixtures two build tests read are in the repository again: a global ignore of `*.log` had kept them
  out.

## [3.9.0] - 2026-11-24

First release of Simtrail by Soflution Ltd: drive iOS Simulators, real iPhones and iPads, Android emulators and
phones, and macOS apps from Claude Code or any MCP agent, with a live viewer, an agent cursor, token-efficient UI
snapshots, screen recording, builds and tests.
