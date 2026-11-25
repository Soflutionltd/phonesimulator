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

## [3.9.0] - 2026-11-24

First release of Simtrail by Soflution Ltd: drive iOS Simulators, real iPhones and iPads, Android emulators and
phones, and macOS apps from Claude Code or any MCP agent, with a live viewer, an agent cursor, token-efficient UI
snapshots, screen recording, builds and tests.
