# OpenAI Codex

Add Simtrail to `~/.codex/config.toml`:

```toml
[mcp_servers.simtrail]
command = "uvx"
args = ["--from", "git+https://github.com/Soflutionltd/simtrail", "simtrail", "mcp"]
tool_timeout_sec = 900
```

- **Which project**: `simtrail mcp` uses the folder Codex starts in -- its scope's own simulator, and that folder as
  the only place installs and builds may reach. Append `"--scope", "my-app", "--root", "/path/to/my-app"` to `args`
  to pin one.
- **Timeouts**: `sim_build_run` and `sim_test` can take minutes when build tools are on; Simtrail bounds each tool
  itself, and a long build answers with a `build_id` to wait on.
- **Watch**: `simtrail open` in the same folder.

A copy of this configuration is in [examples/codex](../../examples/codex/).

Install the matching [four workflow skills](skills.md) into your app project's `.agents/skills` for interaction,
setup/recovery, builds/tests and evidence capture. MCP configuration alone does not install them.
