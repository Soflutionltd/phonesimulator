# The web component and the viewer library

The npm package `@soflution/simtrail` is the viewer: a `<sim-trail>` custom element for pages that would rather
write markup, and a `createViewer` function for applications that manage their own DOM. Both draw a scope's live
screen, take a person's input, and show the agent's cursor.

[examples/web-component](../../examples/web-component/) is a complete page.

## Install

It is [on npm](https://www.npmjs.com/package/@soflution/simtrail):

```sh
npm install @soflution/simtrail@3.11.5
```

It is an ES module with TypeScript types and no runtime dependencies; its styles are built in.

## The element

```html
<sim-trail server="http://127.0.0.1:7466" scope="demo" token="…" placement="page"></sim-trail>

<script type="module">
  import { defineSimtrailElement } from '@soflution/simtrail'
  defineSimtrailElement()   // or defineSimtrailElement('my-simulator')
</script>
```

| Attribute | Meaning |
|---|---|
| `server` | The Simtrail server, such as `http://127.0.0.1:7466`; the page's own origin when absent |
| `scope` | The scope whose simulator it shows; nothing is shown without one |
| `token` | A viewer token for the scope, sent as `Authorization: Bearer`; absent where the page's own origin or cookie lets it in |
| `placement` | `page` (the default), `dock` or `window` -- where the host shows it, which decides the buttons offered |
| `device` | One of the scope's devices, by UDID, to show instead of the scope's own; absent, it follows the scope's own device |
| `lang` | The language the viewer speaks: `en` (or a tag of it, such as `en-GB`), or `auto` for the browser's own; a language it does not speak is English |

Changing `server`, `scope`, `token` or `device` starts the viewer afresh; changing `placement` or `lang` does not
reconnect.
Removing the element closes its socket. It draws in an open shadow root.

| Event | `detail` |
|---|---|
| `simtrail:state` | `{device, connector, capabilities, viewOnly, connected}` whenever one of them changes |
| `simtrail:place` | `{placement}`: a person asked to move the viewer to a dock or a window (not offered on a page) |
| `simtrail:device` | `{udid}`: a person picked what it shows -- a device's UDID, or `null` to follow the scope's own again. The `device` attribute is set or removed to match, without starting afresh |
| `simtrail:close` | `null`: a person closed the viewer |

Events bubble and cross the shadow boundary.

### One device per view

A scope has a device of its own: the one its agents start on and a person's pick replaces. A view follows it -- when
a person or an agent moves the scope to another device, the view comes back on the new one by itself. Several agents of
one scope can each work on a device of their own, though, and a view can show any of them: give it `device`. It
then shows that device, comes back to it after a restart, and never moves the scope's own device or its agents, so two
elements side by side show two devices:

```html
<sim-trail scope="demo" token="…" device="00000000-0000-0000-0000-000000000001"></sim-trail>
<sim-trail scope="demo" token="…" device="00000000-0000-0000-0000-000000000002"></sim-trail>
```

Its device picker says which agents work on each device. Picking a row shows that device in this view alone (Show in
this tab); Use for the project makes the device shown the scope's own, which the views following the scope's own --
and the agents working on the old one -- move to; Follow the project drops the view's own device.

### Getting a token without putting one in the page

The page's backend mints a one-shot [embed ticket](iframe.md#2-mint-a-ticket-on-your-backend); the page spends it for
a viewer token that lives only in its memory:

```js
const { server, scope, ticket } = await (await fetch('/api/embed-ticket', { method: 'POST' })).json()
const exchanged = await fetch(`${server}/api/v1/auth/exchange`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ code: ticket }),
})
const { data } = await exchanged.json()
element.setAttribute('server', server)
element.setAttribute('token', data.token)
element.setAttribute('scope', scope)
```

The daemon must allow the page's origin, for its API and its screen socket:

```toml
[security]
allowed_origins = ["https://my-app.example"]
```

## What a person sees

The device is drawn in a frame of its own -- an iPhone's body with its Dynamic Island or notch and side buttons, an
iPad's, an Android phone's with its camera hole, or a macOS app's window alone -- drawn in CSS, never from a picture of
the device. The screen inside it keeps the device's exact shape, so a click is a touch on the same point of the device
at any zoom. The buttons on the frame's edges press the device's own buttons where it has them and its connector can
press them.

- **The bar**: the device picker (its name and runtime), the Edit, Device and View menus, the zoom (zoom out, the
  scale shown, zoom in, fit to the window, actual size), then settings, docking, letting the device go and closing.
- **Actual size by default**: the device is drawn as Simulator.app's Point Accurate draws it, one point of the device a
  CSS pixel -- an iPhone 17 Pro's screen 402 by 874 pixels. In a window too small for that it is drawn just small
  enough to fit, and the scale shown says so (`67% · fitted`). Command-1 is actual size, Command-0 fit to the window.
  Narrower than 640px, the menus and the zoom take a second line.
- **The toolbar** floating under the device: its buttons (Home, Lock, and an Android device's Back, Recents and
  volume), Rotate left and Rotate right, a screenshot, recording and its size, the appearance, and the Display menu.
- **Rotation**: Rotate left and Rotate right turn a simulator a quarter, as Simulator.app's Device > Rotate does --
  offered where its connector can turn it (the native one), never for a real device, which is turned in the hand. The
  server turns it the way an agent's `sim_device rotate` does and says how it stands (`Device.orientation`); every
  viewer then draws the device turned, its frame and screen with it, and a touch is turned back onto the device's
  portrait screen, so it lands under the finger. An agent turning the device turns every viewer's too.
- **The menus** list only what can be done now. Edit: save or copy a screenshot. Device: the device's buttons, the
  appearance, rotating, Display, recording, choosing a device, settings, letting it go. View: the zoom, showing the device's
  frame, the viewer's theme (the system's, light or dark).
- **Shortcuts**, as the iOS Simulator has them, anywhere in the viewer: Shift-Command-H Home, Command-L Lock,
  Command-Left Arrow rotate left, Command-Right Arrow rotate right,
  Shift-Command-A the appearance, Command-S save a screenshot, Control-Command-C copy it, Command-plus and
  Command-minus zoom, Command-0 fit, Command-1 actual size, Command-comma settings. A macOS app gets Command-keys
  itself.
- A screenshot is the screen's last picture at the device's own pixels, as a PNG, taken by the viewer: it needs
  nothing of the server.
- The theme, whether the frame is drawn and the zoom are kept in the browser (`localStorage`)
  for next time; nothing else is.

### Languages

The viewer speaks English: its menus, toolbar and tooltips, device picker, settings panel and messages, and the names
a screen reader reads. Its words live in one catalogue, so a language can be added again later (the viewer's README
says how); the View menu then offers a Language section, and the viewer's root element carries the language as its
`lang`.

What the server says is shown as it wrote it, in English: a setting's and a settings section's description, why
something was refused, a recording's notes, what an agent says it is doing.

Each language is one file of typed messages in the package's source; [the package's README](../../viewer/README.md#languages)
says how to add one.

## Theming

Custom properties pass into the shadow root. Each has a default, for the viewer's light and dark themes alike.

| Property | Styles |
|---|---|
| `--simtrail-accent`, `--simtrail-on-accent` | Active controls, and text on them |
| `--simtrail-cursor`, `--simtrail-cursor-text` | The agent's pointer, its label, its rings and the pill that names it, and text on them; the accent when unset. A scope's `agent.cursor_color` wins over both, with white or near-black text chosen to read on it |
| `--simtrail-surface`, `--simtrail-surface-sunken`, `--simtrail-border` | The bar, the stage behind the screen, and edges |
| `--simtrail-raised` | The toolbar and the menus over the stage |
| `--simtrail-device`, `--simtrail-device-edge` | The device's body, and its band and buttons |
| `--simtrail-text`, `--simtrail-text-muted` | Text |
| `--simtrail-success`, `--simtrail-warning`, `--simtrail-danger` | The device's state |
| `--simtrail-screen-text` | The boxes around text read from the screen's pixels, while `perception.ocr_overlay` is on |
| `--simtrail-radius`, `--simtrail-radius-full` | Corners |
| `--simtrail-space-1` to `--simtrail-space-7` | Spacing, 2px to 24px |
| `--simtrail-font`, `--simtrail-font-size` | Type |

Filled controls -- a primary button, the selected settings tab, a switch that is on, a menu row under the pointer --
draw `--simtrail-accent` a shade deeper, so white text on it reads at WCAG AA in both themes; outlines, the scale and
pressed icons use it as it is.

For anything more, style its parts: `simtrail::part(bar)`, `::part(stage)` and `::part(screen)`, and -- since the
device's frame -- `::part(device)` and `::part(toolbar)`.

## The function

```ts
import { createHttpTransport, createViewer } from '@soflution/simtrail'

const view = createViewer(document.querySelector('#simulator')!, {
  transport: createHttpTransport({ baseUrl: 'http://127.0.0.1:7466', scope: 'demo', token: () => viewerToken }),
  placement: 'page',
  onState: (state) => console.log(state.device?.state, state.viewOnly),
})
view.setActive(true)
```

`createViewer(host, options)` draws into an element or a shadow root and answers a handle.

| Option | Meaning |
|---|---|
| `transport` | How it reaches its server (required) |
| `placement` | `page`, `dock` or `window` |
| `onPlace(next)` | Offer moving between a dock and a window |
| `pageHref` | Offer opening the viewer on a page of its own |
| `onClose()` | Offer closing it |
| `onState(state)` | Told whenever the device, the connector's offer or the connection changes |
| `reducedMotion()` | Whether the agent's cursor jumps instead of gliding; the system setting when absent |
| `canDecodeH264()` | Whether to ask for H.264; WebCodecs in a secure page when absent |
| `icon(name)` | Draws the viewer's icons; Lucide's, inline, when absent |
| `frames` | Told about each picture of the screen -- `received()`, `decoded(ms)`, `drawn()`, `dropped(count)`, each optional -- to measure how smoothly it draws; nothing of the picture itself is passed |
| `device` | One of the scope's devices, by UDID, to show instead of its own, told to the transport's `use`; it follows the scope's own when absent, or with a transport that has no `use` |
| `onDevice(udid)` | Told when a person picks what the view shows: a UDID, or `null` to follow the scope's own again -- to keep it in a page's address |
| `theme` | `system`, `light` or `dark`: the viewer's own colours; what a person last picked when absent, else the system's |
| `deviceFrame` | Whether the device's body is drawn around its screen; what a person last picked when absent, else drawn |
| `lang` | The language the viewer speaks: `en` (or a tag of it), or `auto` for the browser's own; a language it does not speak is English |
| `onLang(lang)` | Told the language spoken, by its tag, as the viewer starts and whenever it changes -- to set a page's own `lang` |

| Handle | Does |
|---|---|
| `el` | The viewer's root element, which a host may move between containers without reconnecting |
| `device`, `hello`, `encoding` | The device, what the server offered, and the encoding in use |
| `connected()` | Whether the screen socket is open |
| `setActive(on)` | Connect while active; let the screen go while not |
| `setPlacement(placement)`, `focus()` | Change where it is shown; focus the screen for keys |
| `setLang(lang)` | Speak another language, as the `lang` option, without reconnecting; `null` for what a person last picked, else the browser's |
| `destroy()` | Close the socket and remove the viewer |

A picture is drawn on the next animation frame, one per frame (`PAINT_QUEUE_MAX`, 2): pictures come over the socket
in bursts, and two drawn within one display frame showed only the second. A third waiting drops the oldest, so the
screen is never more than two frames behind.

## Transports

`createHttpTransport(options)` talks to a Simtrail daemon, or to any host that mounts Simtrail's routers:

| Option | Meaning |
|---|---|
| `scope` | The scope (required) |
| `baseUrl` | The server; the page's origin when empty |
| `token()` | The bearer token for each request, asked for every time so it can change; none when absent |
| `prefix` | Where the scope routes are mounted: `/api/v1/scopes` on the daemon |
| `fetch`, `origin` | A `fetch` of your own, and the origin a relative `baseUrl` resolves against |
| `device` | One of the scope's devices, by UDID, that its calls are about instead of the scope's own (`?udid=`), until `use` says otherwise |

A refusal rejects with a `TransportError` carrying the server's message and status.

A host with its own API client passes an object of this shape instead:

```ts
interface SimtrailTransport {
  status(): Promise<ScopeStatus>
  start(): Promise<Started>                 // brings the device up and mints a screen socket ticket
  stop(shutdown: boolean): Promise<boolean>
  devices(): Promise<DeviceChoice[]>
  choose(udid: string): Promise<void>      // makes this device the scope's own
  socketUrl(ticket: string): string
  use?(udid: string | null): void | Promise<void>  // optional: show this device from now on, or the scope's own
}
```

`use` is what lets a view show a device of its own: after it, every call is about that device -- the HTTP transport
adds `?udid=` to the scope's routes -- so the next `start` mints a ticket for its screen. A transport without it shows
the scope's own device, and its picker's rows pick the scope's own device (`choose`), as before 3.9.

## Encodings and view-only

On connecting, the server says what it offers and the viewer answers with what it decodes: H.264 first where WebCodecs
can decode it in a secure page (HTTPS, `http://127.0.0.1` or `http://localhost`) and it has not failed on this page,
then JPEG. A connector that cannot touch the screen makes the viewer a mirror: it says so, offers no buttons it cannot
press, and sends no input.
