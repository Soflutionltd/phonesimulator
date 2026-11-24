# Client setup

Run Simtrail on the Mac attached to the device. Copying a localhost MCP configuration cannot connect a remote
agent to that Mac. Use the host's supported local integration; keep the relay loopback-only.

- **Claude plugin:** `/plugin marketplace add Soflutionltd/simtrail`, then
  `/plugin install simtrail@simtrail`. It bundles MCP, four skills and `/simtrail:open`. Update marketplace
  and plugin through `/plugin`, then reconnect/start a fresh session. Auto-update depends on client settings.
- **Other stdio clients:** configure `uvx` with arguments `--from`, `simtrail==3.9.0`, `simtrail`, `mcp`.
  Preserve unrelated settings. Append `--scope`, scope id, `--root`, absolute project path if needed. Configure
  supported call timeouts or use bounded build polling.
- **Portable skills:** install all four directories from `plugins/simtrail/skills` at the MCP release version,
  including references. Codex and Cursor support project `.agents/skills`. Installing skills does not register MCP;
  avoid duplicate copies in discovery paths.
- **Embedded hosts:** use host-provided tools/permissions. The host owns scope, authentication and lifecycle;
  standalone CLI settings need not affect it. Never start a competing daemon to bypass its policy.

Verify discovery, `sim_device info`, and a snapshot on the requested target; before physical gestures, health too.
Open the viewer only when wanted, with `simtrail open` in the same project. Do not report success if it failed.
