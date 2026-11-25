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

## [3.9.0] - 2026-11-24

First release of Simtrail by Soflution Ltd: drive iOS Simulators, real iPhones and iPads, Android emulators and
phones, and macOS apps from Claude Code or any MCP agent, with a live viewer, an agent cursor, token-efficient UI
snapshots, screen recording, builds and tests.
