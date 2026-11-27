// SPDX-License-Identifier: Apache-2.0
/**
 * A device's iOS Simulator: its live screen, a person's touches and keys, and what an agent is doing on it.
 *
 * `createViewer` draws into any element and talks to its server through a transport (`createHttpTransport`, or a
 * host's own). The screen is a real device's, frame by frame over a ticketed socket (`viewer-stream.ts`), drawn keeping
 * the device's shape (`screen-canvas.ts`). Nothing a person does reaches the device but the protocol's short list of
 * input (`viewer-input.ts`). What an agent does arrives on the same socket before it happens, and is drawn over the
 * screen (`agent-cursor.ts`): a pointer of the viewer's own, never the machine's. So is the text read from the screen's
 * pixels, outlined under that pointer (`text-overlay.ts`).
 *
 * The same view can dock beside a page, fill a window, or have a page of its own; a host moves its element between
 * those without the socket noticing, so a device is never reconnected to be moved.
 */
import { createAgentCursor } from './agent-cursor'
import { createDeviceView } from './device-view'
import { quarterTurns } from './orientation'
import { buttonsOf } from './device-kind'
import { canDecodeH264 } from './h264-stream'
import { choiceOf, createI18n, labelAttrs, localize, type Translate } from './i18n'
import { lucideSvg, type IconRenderer } from './icons'
import { createLayers } from './popover'
import { readPreferences, type Theme } from './preferences'
import type { Capability, Device, Encoding, ServerHello } from './protocol.generated'
import { createScreenCanvas, fitRect, type FrameObserver } from './screen-canvas'
import { createStatusView } from './status-view'
import { adoptStyles } from './styles'
import { createTextOverlay } from './text-overlay'
import type { PhoneSimulatorTransport } from './transport'
import { createChrome } from './viewer-chrome'
import { barMarkup, createControls, toolsMarkup, type Placement } from './viewer-controls'
import { attachInput } from './viewer-input'
import { createViewerStream } from './viewer-stream'

export type { Placement } from './viewer-controls'
export type { Theme } from './preferences'

export interface ViewerState {
  device: Device | null
  connector: string | null
  capabilities: readonly Capability[]
  /** The connector can show the screen but not touch it. */
  viewOnly: boolean
  connected: boolean
}

export interface ViewerOptions {
  transport: PhoneSimulatorTransport
  /** Where the view is shown; `page` when not given. */
  placement?: Placement
  /** Move the view between a dock and a window; not offered when absent, nor on a page. */
  onPlace?(next: 'dock' | 'window'): void
  /** Where the view has a page of its own; not offered when absent, nor on that page. */
  pageHref?: string
  onClose?(): void
  /** Whether the agent's pointer jumps rather than glides; the system setting when absent. */
  reducedMotion?(): boolean
  /** Whether this page can decode H.264 itself; WebCodecs in a secure page when absent. */
  canDecodeH264?(): boolean
  /** Draws the viewer's icons; Lucide's, inline, when absent. The agent's pointer is PhoneSimulator's own drawing. */
  icon?: IconRenderer
  /** Told whenever the device, what the server offers, or the connection changes. */
  onState?(state: ViewerState): void
  /**
   * Told about each picture of the screen -- received, decoded, drawn, or thrown away before it was drawn -- for a
   * host measuring how smoothly it draws. Nothing of the picture itself is passed.
   */
  frames?: FrameObserver
  /** Show this one of the scope's devices, by UDID, instead of its own -- a view of its own device, told to the
   * transport (`use`) -- and come back to it after a restart. Absent, or through a transport that cannot show one, the
   * view follows the scope's own device. */
  device?: string | null
  /** What this view's project is called: the others sharing its device are named beside it, not it. */
  project?: string | null
  /** Told when a person picks what this view shows: a device's UDID, or null to follow the scope's own again -- for a
   * page to keep it in its address. */
  onDevice?(udid: string | null): void
  /** The viewer's own colours: the system's light or dark (`system`), or one of them. What a person last picked in
   * the View menu when absent, else the system's. */
  theme?: Theme
  /** Draw the device's body -- its edges, buttons, Dynamic Island or notch -- around its screen. What a person last
   * picked in the View menu when absent, else drawn. */
  deviceFrame?: boolean
  /** The language the viewer speaks: a BCP 47 tag of one it does -- `en`, `fr`, `fr-CA` -- or `auto` for the first of
   * the browser's languages it speaks, else English. What a person last picked in the View menu when absent or not
   * spoken, else `auto`. */
  lang?: string
  /** Told the language the viewer speaks, by its tag (`en`, `fr`), as it starts and whenever it changes -- for a page
   * to set its own `lang`. */
  onLang?(lang: string): void
}

export interface ViewHandle {
  readonly el: HTMLElement
  readonly device: Device | null
  readonly hello: ServerHello | null
  /** How frames come on this connection, once the server has said. */
  readonly encoding: Encoding | null
  connected(): boolean
  /** Connect while active; let the device's screen go while not. */
  setActive(on: boolean): void
  setPlacement(placement: Placement): void
  /** Speak another language, without reconnecting: as `ViewerOptions.lang`, and with null what a person last picked
   * in the View menu, else the browser's. */
  setLang(lang: string | null): void
  focus(): void
  destroy(): void
}

const stageMarkup = (tools: string, t: Translate) => `
    <div class="smv-stage" data-smv-stage part="stage">
      <div class="smv-viewport" data-smv-viewport>
        <div class="smv-device" data-smv-device part="device">
          <div class="smv-screen" data-smv-screen>
            <canvas class="smv-canvas" data-smv-canvas tabindex="0"${labelAttrs(t, 'screen.label')} part="screen"></canvas>
            <div class="smv-overlay" data-smv-overlay></div>
          </div>
        </div>
      </div>
      ${tools}
      <div class="smv-badge" data-smv-badge hidden></div>
      <div class="smv-empty" data-smv-empty hidden></div>
      <div class="smv-picker" data-smv-picker role="menu" hidden></div>
      <div class="smv-picker" data-smv-display role="menu"${labelAttrs(t, 'display.title')} hidden></div>
      <div class="smv-picker" data-smv-record-size role="menu"${labelAttrs(t, 'recordSize.menu')} hidden></div>
      <div class="smv-note" data-smv-note hidden></div>
      <div class="smv-settings" data-smv-settings role="dialog" hidden></div>
    </div>`

export function createViewer(host: HTMLElement | ShadowRoot, options: ViewerOptions): ViewHandle {
  const icon = options.icon ?? lucideSvg
  const el = document.createElement('div')
  el.className = 'smv'
  // Before anything is asked of the server: every call is then about that device.
  if (options.device) void options.transport.use?.(options.device)
  const kept = readPreferences()
  /** What is asked of the language when a host asks nothing: a person's last pick, else the browser's. */
  const keptLang = () => readPreferences().lang ?? 'auto'
  const i18n = createI18n(choiceOf(options.lang) ?? kept.lang ?? 'auto')
  const { t } = i18n
  el.lang = i18n.locale
  el.innerHTML = barMarkup(icon, t) + stageMarkup(toolsMarkup(icon, t), t)
  host.appendChild(el)
  adoptStyles(el)

  const q = <T extends Element>(selector: string) => el.querySelector<T>(selector)!
  const canvas = q<HTMLCanvasElement>('[data-smv-canvas]')
  const overlay = q<HTMLElement>('[data-smv-overlay]')
  let active = false
  let destroyed = false
  let placement: Placement = options.placement ?? 'page'

  /** The last screen size laid out: the device is drawn again only when it changes. */
  let laidOut = ''
  /** How many quarter turns clockwise the device is drawn at: as the server last said it stands. */
  const turns = () => quarterTurns(stream.device?.orientation)
  const screen = createScreenCanvas(canvas, {
    fit: 'contain', frames: options.frames, turns,
    onFrame: (frame) => {
      chrome.drawn()
      const size = `${frame.w}x${frame.h}`
      if (size === laidOut) return
      laidOut = size
      deviceView.layout()
    },
  })
  const status = createStatusView({
    canvas, empty: q('[data-smv-empty]'), badge: q('[data-smv-badge]'), name: q('[data-smv-name]'),
    kind: q('[data-smv-kind]'), shared: q('[data-smv-shared]'), state: q('[data-smv-state]'),
    mode: q('[data-smv-mode]'), app: q('[data-smv-app]'),
  }, t, options.project ?? '')
  /** The screen's shape: the device's points once it says, the canvas's until then. */
  const unitsOf = () => stream.device?.screen?.points ?? { w: canvas.width, h: canvas.height }
  /** Where the device's screen is drawn inside the overlay. */
  const frameBox = () => {
    const box = overlay.getBoundingClientRect()
    // Drawn on its side, the overlay's box on the page is its own turned: its width is its height.
    const sideways = turns() % 2 === 1
    return fitRect({ w: sideways ? box.height : box.width, h: sideways ? box.width : box.height }, unitsOf())
  }
  // Made before the agent's pointer, so the pointer is drawn over the boxes.
  const text = createTextOverlay(overlay, {
    frameBox, pointer: { target: canvas, at: (event) => screen.point(event) }, t,
  })
  const cursor = createAgentCursor(overlay, {
    frameBox, t,
    reducedMotion: options.reducedMotion,
    onActive: (on, title, activity, color) => status.setAgent(on ? title : null, activity, color),
  })
  const stream = createViewerStream({
    transport: options.transport, screen, cursor, text, status, t, unitsOf, frames: options.frames,
    canDecodeH264: options.canDecodeH264 ?? (() => canDecodeH264()),
    wanted: () => active && !destroyed,
    onHello: (hello) => {
      status.setMode(hello)
      controls.applyHello(hello)
      deviceView.layout()
    },
    onChange: () => {
      controls.applyDevice(stream.device)
      deviceView.setDevice(stream.device)
      const hello = stream.hello
      options.onState?.({
        device: stream.device, connector: hello?.connector ?? null, capabilities: hello?.capabilities ?? [],
        viewOnly: hello !== null && !hello.capabilities.includes('input_touch'), connected: stream.open,
      })
    },
    onEnd: () => input.releaseFinger(),
    onInputRefused: (reason) => controls.tell(reason),
  })
  /** Menus open over the screen; while one is, the screen's input holds back. */
  const layers = createLayers()
  const deviceView = createDeviceView({
    viewport: q('[data-smv-viewport]'), device: q('[data-smv-device]'), screen: q('[data-smv-screen]'),
    units: unitsOf, framed: options.deviceFrame ?? kept.framed ?? true, zoom: kept.zoom ?? 'actual', turns,
    pressable: (button) => stream.allows('input_button') && buttonsOf(stream.device).includes(button),
    press: (button) => void stream.send({ type: 'button', name: button }),
    // Laid out only once the chrome below is made: the first layout is asked for after it.
    onLayout: () => chrome.paintZoom(),
    t,
  })
  const input = attachInput({
    canvas, screen, send: (message) => stream.send(message), allows: stream.allows, blocked: () => layers.open,
    onUnsent: () => controls.tell(t('input.unsent')),
  })
  const controls = createControls({
    el, picker: q('[data-smv-picker]'), display: q('[data-smv-display]'), recordSize: q('[data-smv-record-size]'),
    note: q('[data-smv-note]'), settingsPanel: q('[data-smv-settings]'), transport: options.transport, stream,
    status, input, icon, t, layers,
    placement: () => placement, onPlace: options.onPlace, pageHref: options.pageHref, onClose: options.onClose,
    device: options.device, onDevice: options.onDevice,
  })
  controls.paintPlacement()
  const chrome = createChrome({
    el, stage: q('[data-smv-stage]'), canvas, view: deviceView, layers, device: () => stream.device,
    tell: (message) => controls.tell(message), theme: options.theme ?? kept.theme ?? 'system', i18n,
  })
  deviceView.layout()
  // The language changed -- in the View menu, or by the host: everything said is said again, as it stands.
  const unlisten = i18n.onChange((locale) => {
    el.lang = locale
    localize(el, t)
    status.relabel()
    cursor.relabel()
    controls.relabel()
    chrome.relabel()
    options.onLang?.(locale)
  })
  options.onLang?.(i18n.locale)

  return {
    el,
    get device() {
      return stream.device
    },
    get hello() {
      return stream.hello
    },
    get encoding() {
      return stream.encoding
    },
    connected: () => stream.open,
    setActive(on) {
      if (on === active) return
      active = on
      if (on) {
        void stream.connect()
      } else {
        input.flushTyped()
        stream.close()
        status.stopBootTimer()
        stream.cancelReconnect()
      }
    },
    setPlacement(next) {
      placement = next
      controls.paintPlacement()
    },
    setLang: (lang) => i18n.set(choiceOf(lang) ?? keptLang()),
    focus: () => canvas.focus(),
    destroy() {
      destroyed = true
      unlisten()
      status.stopBootTimer()
      stream.cancelReconnect()
      input.destroy()
      controls.destroy()
      chrome.destroy()
      deviceView.destroy()
      cursor.destroy()
      text.destroy()
      screen.destroy()
      stream.close()
      el.remove()
    },
  }
}
