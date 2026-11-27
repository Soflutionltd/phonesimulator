# Cursor

Add PhoneSimulator to your project's `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "phonesimulator": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Soflutionltd/phonesimulator", "phonesimulator", "mcp"]
    }
  }
}
```

and enable the server in Cursor's MCP settings.

- **Which project**: `phonesimulator mcp` uses the folder it starts in. If the tools act on the wrong project, append
  `"--scope", "my-app", "--root", "/absolute/path/to/my-app"` to `args`.
- **Watch**: `phonesimulator open` in the same folder.

A copy of this configuration is in [examples/cursor](../../examples/cursor/).

Install the matching [four workflow skills](skills.md) into your app project's `.agents/skills` for interaction,
setup/recovery, builds/tests and evidence capture. MCP configuration alone does not install them.
