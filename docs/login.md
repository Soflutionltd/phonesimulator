# Signing in

`sim_login` signs an app in with a login saved in your password manager -- 1Password first, Bitwarden, or a program
of your own -- and the agent never sees the password: Rocketwright asks the password manager for it, types it straight
into the device, and tells the agent only which login it used and which fields it filled.

## Turn it on

It is off until you name where logins come from, in the order they are tried:

```sh
rocketwright config set login.sources '["1password"]'
```

or in `config.toml`:

```toml
[login]
sources = ["1password", "bitwarden", "command:/Users/you/bin/test-logins"]
```

`login.sources` decides what Rocketwright runs, so a page cannot change it alone: the settings panel asks for a code from
`rocketwright settings confirm` ([The settings panel](settings.md)).

### 1Password

1. Install the CLI: `brew install 1password-cli`.
2. In the 1Password app, Settings > Developer: turn on **Integrate with 1Password CLI**.

The CLI then reaches your vaults through the app, which asks you to approve with Touch ID. A call waits for you up to
`login.timeout` seconds (90 by default). The CLI is found on PATH, then where Homebrew puts it
(`/opt/homebrew/bin`, `/usr/local/bin`); `login.onepassword_path` names another.

**Every vault is searched**: no vault is named anywhere, so the login can be in Private, a shared vault or another
team's. The list of logins (titles, usernames, websites -- nothing secret) is read once and kept ten minutes, so Touch ID
is not asked at every call; a login saved since is found because an app with no login in the kept list reads it
again.

### Bitwarden

`brew install bitwarden-cli`, `bw login`, then `bw unlock` and export the `BW_SESSION` it prints in the environment
the daemon starts with. `login.bitwarden_path` names another CLI than the one on PATH or Homebrew's.

### The macOS Keychain

Save the login with the app -- its bundle id, or its website -- as the service, and the account's username as the
account; `-w` last asks for the password without echoing it:

```sh
security add-generic-password -s com.example.notes -a ann@example.com -l "Notes test account" -w
```

`keychain` finds it by the app's id alone, and reads its password only to type it. Only a process that may run
`security` reaches the Keychain: `rocketwright login --source keychain` from your terminal does; a daemon started by an MCP
client that runs its servers in a sandbox forbidding the Keychain does not.

### A program of your own

`command:/absolute/path` runs that program with the app or website as its one argument. It prints the logins for it
as JSON -- one object, or a list -- and nothing when it has none:

```json
[{"id": "staging-ann", "title": "Staging", "username": "ann@example.com", "password": "…", "totp": "123456",
  "url": "https://staging.example.com"}]
```

`urls` (a list) may stand for `url`; `id` and `title` are optional. Use it for test accounts kept elsewhere: a
seed file, a secrets store, a script that makes a fresh account.

## Save the app with the login

A login is for an app when one of the websites or apps saved with it names the app:

- the same site as the website given: `accounts.example.com` and `www.example.com` are both example.com;
- the app's bundle id or package name itself, saved as `android://com.example.notes` (or the id alone);
- the site the bundle id is the reverse of: `com.example.notes` is example.com.

## Use it

Open the app's sign-in screen first, then:

```json
{"app": "com.example.notes", "account": "ann@example.com", "submit": true}
```

| Argument | What it does |
|---|---|
| `app` | The website or the app's bundle id or package name the login is saved for. Required. |
| `account` | The username or e-mail of the account the person named. Only a login for it is used. |
| `item` | The id or title of the login, when several match. |
| `field` | The ref of the password field -- or, with `code`, of the one-time code's field. |
| `code` | Type the login's one-time code (TOTP) instead of its password. |
| `submit` | Press return once it is filled. |
| `source` | Look only in this one of `login.sources`: `1password`, `bitwarden` or `command`. |

The answer:

```text
Used the 1password login "Notes" (ann@example.com, 1Password vault Private, id abc123): typed the username into e2,
the password into e3, then pressed return. Call sim_snapshot to see what the app answered.
```

With two-factor sign-in, call it again once the app asks for the code: `{"app": "com.example.notes", "account":
"ann@example.com", "code": true, "submit": true}`. A code the password manager does not hold -- an SMS, an e-mail --
is refused with "ask the person".

## From a sandboxed client: `rocketwright login`

The password manager is asked from the daemon, and a daemon started by an MCP client that runs its servers in a macOS
sandbox inherits that sandbox -- which may forbid what the password manager's CLI needs, such as the Keychain
(`1Password's item list failed: ... Operation not permitted`). Ask it from your own terminal instead:

```sh
rocketwright login com.example.notes --account ann@example.com --submit
```

It reads `login.sources`, or `--source 1password` (or `bitwarden`, `keychain`, `command:/path`; repeatable), finds the login as `sim_login` does, hands it to the
daemon for one use -- in memory, for this project and app, dropped once taken or after two minutes -- and has
`sim_login` type it (`source: "given"`), with the same fields found and the same masking. `--field` and `--code` are
`sim_login`'s. It prints which login was used and what was filled, never a value; no value is ever on its command
line. An agent cannot reach a login handed over: it is taken only with the item `rocketwright login` passed itself.

## Which login, and which field

- **The account asked for, and no other.** With `account`, a login for any other account is never used, even when it
  is the only one for the app; the refusal names the others found so the agent can tell you. A login whose revealed
  username turns out to be another account is refused before anything is typed.
- **No guessing.** Several logins for the app, with no `item`, are refused with each one's title, vault and id.
- **An item named for another app is refused**: save the app with it if it is really the same account.
- **A password goes only into a secure field**: the one `field` names -- refused when it is not secure -- or the only
  one on screen. Two secure fields (a password and its confirmation) need `field`. The username goes into the text
  field just before it, and a field that already holds it is left as it is.
- **A field secure only once it has the focus** -- a Flutter app's password field, say -- is tapped first: the field
  `field` names when it is a plain text field, else, with no secure field on screen, the last of two text fields or
  more. Only that field, if it then says it is secure, takes the password; otherwise the call is refused as before.
- **A password-only screen that shows another address than the login's is refused**: the password would be tried on
  that account.
- **A one-time code** goes into the field `field` names, or the one field whose label reads like a code.

## Security

What Rocketwright guarantees about the value -- the password and the one-time code:

- **Never in an answer.** `sim_login` answers with the login's title, where it is kept and its id, and what was filled.
  Every later answer of every tool -- a snapshot of a field whose eye was tapped, an app's log, an error -- has the
  password and the code masked as `••••` (the code for three minutes, the password for twelve hours). The mask keeps a
  keyed digest of each value, never the value, with a key made afresh for each run of the daemon.
- **Never shown to a viewer.** The agent's events say "Typing the password" and show `••••`; the macOS overlay, drawn
  from the same events, likewise.
- **Not hidden in a picture, a short value or a file.** The mask hides text in what Rocketwright answers, and is set
  before the first key is struck, so a login cancelled midway is masked too. It does not reach a screenshot, a
  recording or the live viewer: an app that shows the password in clear -- its eye tapped -- shows it there, and to
  the agent that asks for a screenshot. A value shorter than four characters is not masked, nor is what an app writes
  itself into a file on disk, such as a build's `build.log`
  ([what the mask does not cover](security.md#what-an-agent-can-reach)).
- **Never in a log, an argv or the environment.** A login is asked for by its id; the password comes back on the CLI's
  output, read into the daemon's memory alone. What a CLI says on failure is kept to its first line.
- **Never in a recording.** `sim_login` is refused while the device's screen is recorded.
- **Memory.** The list a source keeps between calls holds nothing secret -- Bitwarden's and a command's, which carry
  passwords, are read and dropped. A revealed login is emptied as soon as it is typed and kept by nothing once the call
  returns. Python cannot wipe a string's memory in place, so the value lives on in freed memory until it is reused.
- **The pasteboard.** A login is typed with the keys of the Mac's own layout -- AZERTY, QWERTZ, US -- and reaches a
  simulator through its pasteboard only when one of its characters has no key there, or `device.typing` says to
  paste: Rocketwright empties it again once the login is typed, and says so when it could not. With Simulator.app's
  *Automatically Sync Pasteboard* on, the Mac's own pasteboard briefly held it too: turn that off. iOS 16 to 26 ask to Allow Paste: the prompt
  names the simulator's pasteboard bridge, `CoreSimulatorBridge`, so Rocketwright knows it for its own paste and allows
  it, and the answer says so -- or says the text did not arrive when it could not tell the allow button. iOS 27 refuses
  a paste it did not ask for, and the answer says so.
- **Android without scrcpy is refused**: adb's `input text` would put the password in a command line other programs
  can read. Set scrcpy up (`rocketwright android setup`).

Refused before the password manager is asked:

- in **observe mode** (`agent.observe`): a person signs in themselves there;
- on a **real iPhone, iPad or Android phone, or in a macOS app**, which hold real data, unless you turn
  `login.real_devices` on -- by default only simulators and emulators;
- while the screen is **recorded**;
- where the screen has **no field** the value may go into.

What it does not do: decide whether an agent should sign in at all. An agent with `sim_login` can sign in with any
login saved for the app; give `account`, and keep test accounts in a vault of their own, or use `command:` with test
accounts only.

## Settings

| Setting | Default | What it does |
|---|---|---|
| `login.sources` | `[]` | Where logins come from, in order: `1password`, `bitwarden`, `command:/path`. Empty: no `sim_login`. |
| `login.onepassword_path` | empty | The 1Password CLI; empty: PATH, then Homebrew's. |
| `login.bitwarden_path` | empty | The Bitwarden CLI; empty: PATH, then Homebrew's. |
| `login.timeout` | `90` | Seconds a password manager has to answer, Touch ID included. |
| `login.real_devices` | `false` | Also sign in on real devices and in macOS apps. |

All but `login.timeout` are sensitive: a page changes them only with a code from the terminal. The full reference is
in [Configuration](reference/configuration.md).
