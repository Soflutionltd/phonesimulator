# The settings panel

```sh
rocketwright open --settings
```

opens a project's simulator in a browser tab with its settings a click away: the gear in the viewer's toolbar opens a
panel with a tab for each section of `config.toml` -- General, Connectors, Device, Real devices, Android, macOS, Stream,
Agents, Screen reading, Build, Recording, Server and Security. It edits the same file `rocketwright config set` does, keeping its
comments, and the daemon acts on a change before the panel says it is saved.

![The settings panel on its Server tab: two settings that need a person at the terminal, one set by a variable](media/settings-panel.png)

## Changing a setting

Change any values in a tab and choose **Save**. A tab is saved as one change: all of it is written, or none of it and
each setting's problem is shown beside it.

- **This project** writes the project's own `[scopes."<project>"]` table; **Every project** writes the top of the file.
  The Server and Security tabs are always for the whole daemon, which is the only place those settings are read.
  `rocketwright config scope` prints the id of that table for the folder it runs in (or `--folder PATH`), so the
  command line can set the same thing: `rocketwright config set --scope "$(rocketwright config scope)" stream.fps 60`.
- **Reset** puts a value back to what applies without it, from wherever it was set.
- Each setting says where its value comes from (the default, `config.toml`, this project, or a `ROCKETWRIGHT_*`
  variable) and, when a change does not apply at once, when it does: on a viewer's next connection, on the next device
  brought up, or after the daemon restarts.

## What the panel cannot change

- **A value a variable or the command line sets.** `ROCKETWRIGHT_STREAM_QUALITY` in the daemon's environment wins over
  `config.toml`, so the panel shows it, disabled, and says where to change it.
- **Nothing, from a plain viewer.** `rocketwright open` without `--settings` shows the settings and changes none of them.
  A settings session lasts an hour; open it again with `--settings` after that.
- **Nothing, in a frame.** An iframe or a host's page never shows the gear.

## Sensitive settings

Twenty-nine settings decide what Rocketwright runs, what reaches a real device or an Android one, where recordings go,
which password manager signs apps in, or who may reach it: `connectors.native.helper_path`, `connectors.idb.companion_path`, `device.developer_dir`,
`real_devices.enabled`, `real_devices.agents_choose`, `real_devices.developer_dir`, `real_devices.team_id`,
`real_devices.wda.enabled`, `real_devices.wda.path`, `android.enabled`, `android.sdk_path`, `android.phones`,
`android.agents_choose`, `android.scrcpy.path`, `android.java_home`, `build.tools`, `build.flutter_path`, `recording.folder`, `server.host`,
`server.port`, `security.allowed_origins`, `security.frame_ancestors`, `mac.apps.enabled`, `mac.apps.agents_choose`,
`mac.apps.accessibility`, `login.sources`, `login.onepassword_path`, `login.bitwarden_path` and `login.real_devices`. A web page is not trusted with those alone, so saving a
change to one asks for a code:

1. The panel says the change is waiting.
2. In a terminal, run

   ```sh
   rocketwright settings confirm
   ```

   It shows each waiting change as it would be written -- `walk: build.tools = true` -- and its code.
3. If it is the change you asked for, type the code into the panel and choose **Confirm**.

A code confirms that change and no other, works once, lasts five minutes, and stops working after five wrong tries.
`rocketwright config set` changes these settings directly, as it always has.

## In a host application

The panel appears wherever the viewer's transport can read settings. A Python host that wants it mounts
`create_settings_router` with a settings store and authenticator of its own; one that keeps its own settings screens
mounts nothing and the gear never shows. See [A Python host application](embedding/python-fastapi.md#settings).
