# Claude Code in a terminal

Claude Code drives the simulator through Simtrail's MCP tools; you watch, and take over, in a browser tab.

## With the plugin

The plugin adds the tools, a skill that teaches the snapshot-first way to use them, and `/simtrail:open`.

```
/plugin marketplace add Soflutionltd/simtrail
/plugin install simtrail@simtrail
```

Its tools are named `mcp__plugin_simtrail_device__sim_snapshot` and so on (`mcp__plugin_simtrail_simtrail__…` up to
2.2).

## Without the plugin

```sh
claude mcp add simtrail -- uvx --from git+https://github.com/Soflutionltd/simtrail simtrail mcp
```

Add `--scope project` before the name to write it to the project's `.mcp.json` for everyone working on it. Its tools
are named `mcp__simtrail__sim_snapshot` and so on; allow them all without a prompt with `mcp__simtrail` in your
permission settings.

`simtrail mcp` starts Simtrail's local server when it is not running, and gives the agent this folder's own
simulator (its scope) and this folder as the only place builds and installs may reach. Pass `--scope NAME` or
`--root DIR` after `mcp` to choose otherwise.

## Watch it

```sh
uvx --from git+https://github.com/Soflutionltd/simtrail simtrail open
```

opens this folder's viewer in your browser. Every gesture the agent makes is drawn there as a cursor just before it
lands, and you can tap, scroll and type into the device yourself at any time.

## Try it

> Open Settings → General → About and tell me which iOS version this simulator runs. Use sim_snapshot rather than
> screenshots.

A snapshot-first run reads the answer from a few hundred tokens of text; the same task done with screenshots costs
several thousand. See [token-budget](../token-budget/) to measure it on your own screens.

## Requirements

An Apple Silicon Mac with Xcode 26 or later, [uv](https://docs.astral.sh/uv/), and for touching the screen,
`brew install facebook/fb/idb-companion`. Without idb_companion the viewer still shows the screen, view-only. Run
`simtrail doctor` to see what this Mac has.
