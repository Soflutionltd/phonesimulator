// SPDX-License-Identifier: Apache-2.0
/**
 * The viewer's controls. The bar holds the device picker -- the device's name on it --, where the view is placed,
 * letting the device go, and closing; the menus and the zoom beside them are `viewer-chrome.ts`'s. The toolbar under
 * the device holds the device's buttons -- Home and Lock, and an Android device's Back, Recents and volume --, Rotate
 * Left and Rotate Right where the device can be turned from here, a
 * screenshot, recording and how big it is kept (`recording-control.ts`), the appearance, and how the device looks for
 * a demo (`display-menu.ts`). A button the
 * device cannot press is not offered once the server has said what it can do, nor one the transport has no call for.
 *
 * The picker is a menu (`popover.ts`): Escape closes it and gives focus back to its button, and the arrow keys walk its
 * rows. It lists this Mac's simulators, the iPhones and iPads connected to it, then the Android emulators and phones --
 * each with how it is connected, what stands in its way, and which agents work on it. Through a transport that can
 * show any of the scope's devices (`use`), a row shows that device in this view alone -- the scope's own device and
 * its agents stay where they are -- and the picker also offers to make the device shown the scope's own (Use for the
 * project, `choose`), and, in a view showing a device of its own, to follow the scope's own again. Through any other
 * transport a row picks the scope's own device, as it always did. Settings open in a panel of their own
 * (`settings-panel.ts`), offered only by a transport that reads settings. The badge beside the name says what would let
 * the device be touched, or touched quickly: a real device's and an Android device's is Set up touch
 * (`touch-setup.ts`), and a simulator's opens the settings where its connector is chosen.
 */
import { androidReach, buttonsOf, connectionLabel, detailLabel, deviceNoun, isReal } from './device-kind'
import { createDisplayMenu, type DisplayMenu } from './display-menu'
import { escapeHTML } from './escape'
import { english, labelAttrs, name, nameAttrs, said, sayAttr, type PlainKey, type Translate } from './i18n'
import type { IconName, IconRenderer } from './icons'
import { createNote } from './note'
import { createPopover, type Layers } from './popover'
import { createRecordingControl, type RecordingControl } from './recording-control'
import { createSettingsPanel, type SettingsPanel } from './settings-panel'
import { createTouchSetup, type TouchSetupControl } from './touch-setup'
import type { Capability, Device, DeviceChoice, PanelButton, ServerHello } from './protocol.generated'
import type { StatusView } from './status-view'
import type { RocketwrightTransport } from './transport'
import type { ViewerInput } from './viewer-input'
import type { ViewerStream } from './viewer-stream'

export type Placement = 'dock' | 'window' | 'page'

/** The buttons that need the connector to be able to do something. */
const NEEDS: ReadonlyArray<[action: string, capability: Capability]> = [['appearance', 'appearance']]

/** The device's own buttons the toolbar offers, in its order; each is called by its `button.…` message. */
export const BAR_BUTTONS: ReadonlyArray<PanelButton & IconName> = [
  'back', 'home', 'app_switch', 'lock', 'volume_down', 'volume_up',
]
const PRESSED = new Set<string>(BAR_BUTTONS)

type ButtonMaker = (action: string, shape: IconName, title: PlainKey, extra?: string, className?: string) => string

const iconButtons = (icon: IconRenderer, t: Translate): ButtonMaker => (action, shape, title, extra = '', className = '') =>
  `<button type="button" class="smv-icon${className ? ` ${className}` : ''}" data-smv="${action}"${nameAttrs(t, title)}${extra}>`
  + `${icon(shape)}</button>`

/** The bar above the stage: the device and how it stands, the menus, the zoom, and the view's own controls. */
export function barMarkup(icon: IconRenderer, t: Translate): string {
  const button = iconButtons(icon, t)
  return `<div class="smv-bar" part="bar">
      <div class="smv-bar-device">
        <button type="button" class="smv-select" data-smv="devices" title="${said(t, 'devices.choose')}"
          data-i18n-title="devices.choose" aria-haspopup="menu" aria-expanded="false"><span
          class="smv-sr"${sayAttr('devices.chooseSr')}>${said(t, 'devices.chooseSr')}</span><span class="smv-name"
          data-smv-name>${said(t, 'device.unnamed')}</span><span class="smv-chevron">${icon('chevron')}</span></button>
        <span class="smv-state" data-smv-state data-state="stopped">${said(t, 'state.stopped')}</span>
        <span class="smv-kind" data-smv-kind hidden></span>
        <button type="button" class="smv-mode" data-smv="mode" data-smv-mode hidden>${said(t, 'mode.viewOnly')}</button>
        <span class="smv-app" data-smv-app hidden></span>
        <span class="smv-rec" data-smv-rec hidden></span>
      </div>
      <div class="smv-menus" data-smv-menus></div>
      <span class="smv-spacer"></span>
      <div class="smv-zoom" role="group"${labelAttrs(t, 'zoom.group')}>
        ${button('zoom-out', 'minus', 'zoom.out')}
        <span class="smv-zoom-level" data-smv-zoom-level></span>
        ${button('zoom-in', 'plus', 'zoom.in')}
        ${button('zoom-fit', 'fit', 'zoom.fit', ' aria-pressed="true"')}
        <button type="button" class="smv-icon smv-actual" data-smv="zoom-actual"${nameAttrs(t, 'zoom.actual')}
          aria-pressed="false"${sayAttr('zoom.actualMark')}>${said(t, 'zoom.actualMark')}</button>
      </div>
      <div class="smv-window">
        ${button('settings', 'settings', 'settings.title', ' aria-haspopup="dialog" aria-expanded="false" hidden')}
        ${button('place', 'undock', 'place.undock')}
        <a class="smv-icon" data-smv-page target="_blank" rel="noopener"${nameAttrs(t, 'page.open')}>${icon('page')}</a>
        ${button('stop', 'power', 'stop.simulator')}
        ${button('close', 'close', 'close')}
      </div>
    </div>`
}

/** The toolbar floating under the device: its buttons, a screenshot, recording, and how it looks. */
export function toolsMarkup(icon: IconRenderer, t: Translate): string {
  const button = iconButtons(icon, t)
  // Home and Lock until the device says which it has: what a viewer of an older server always showed.
  const pressed = BAR_BUTTONS.map((pressable) =>
    button(pressable, pressable, `button.${pressable}`, pressable === 'home' || pressable === 'lock' ? '' : ' hidden', 'smv-press'))
    .join('\n      ')
  // Named by its control (`recording-control.ts`) once there is one, and never shown without.
  return `<div class="smv-tools" role="toolbar"${labelAttrs(t, 'tools.label')} part="toolbar">
      ${pressed}
      ${button('rotate-left', 'rotate_left', 'rotate.left', ' hidden')}
      ${button('rotate-right', 'rotate_right', 'rotate.right', ' hidden')}
      <span class="smv-tools-gap" aria-hidden="true"></span>
      ${button('screenshot', 'camera', 'screenshot.save', ' disabled')}
      ${button('record', 'record', 'record.full', ' aria-pressed="false" hidden')}
      <button type="button" class="smv-icon smv-size" data-smv="record-size" aria-haspopup="menu" aria-expanded="false"
         hidden></button>
      ${button('appearance', 'moon', 'appearance.dark', ' aria-pressed="false"')}
      ${button('display', 'contrast', 'display.title', ' aria-haspopup="menu" aria-expanded="false" hidden')}
    </div>`
}

export interface ControlsOptions {
  el: HTMLElement
  picker: HTMLElement
  /** The Display menu's panel. */
  display: HTMLElement
  /** The recording size menu's panel. */
  recordSize: HTMLElement
  /** The note over the screen. */
  note: HTMLElement
  /** Where the settings panel is drawn. */
  settingsPanel: HTMLElement
  transport: RocketwrightTransport
  stream: ViewerStream
  status: StatusView
  input: ViewerInput
  icon: IconRenderer
  /** Says the viewer's messages in the language it speaks now. */
  t: Translate
  layers: Layers
  placement(): Placement
  onPlace?(next: 'dock' | 'window'): void
  pageHref?: string
  onClose?(): void
  /** The device this view shows instead of the scope's own, by UDID, as the view was made; null to follow its own. */
  device?: string | null
  /** Told when a person picks what this view shows: a device's UDID, or null to follow the scope's own again. */
  onDevice?(udid: string | null): void
}

/** What a view that can show any of the scope's devices tells its picker. */
export interface TabChoice {
  /** The device the view shows instead of the scope's own, or null while it follows the scope's own. */
  pinned: string | null
  /** The scope's own device, as the server last said; null when it did not say. */
  own: string | null
}

export interface Controls {
  paintPlacement(): void
  applyHello(hello: ServerHello | null): void
  /** How the device stands: what it is, whether it is dark, and whether it is being recorded. */
  applyDevice(device: Device | null): void
  /** Say something over the screen without taking it away: input the device did not take. */
  tell(message: string): void
  /** The language changed: say again what the controls say outside the markup `localize` reads. */
  relabel(): void
  destroy(): void
}

/** How a device the picker lists reaches this Mac: a real device by cable or network, an emulator on it. */
function reached(choice: DeviceChoice, t: Translate): string {
  if (choice.kind === 'physical') return connectionLabel(choice.connection, t)
  if (choice.kind === 'android') return androidReach(choice.connection, t)
  return ''
}

/** Which agents work on a device the picker lists; an older server does not say. */
function workedOn(choice: DeviceChoice, t: Translate): string {
  const titles = (choice.agents ?? []).map((agent) => agent.title)
  return titles.length ? t('picker.usedBy', { agents: titles.join(', ') }) : ''
}

/** What a row says beside a device's name: what it runs, how it is reached, what stands in its way and who works on
 * it -- each once: a device not connected is not said to be so twice. */
function choiceAbout(choice: DeviceChoice, t: Translate = english): string {
  const how = reached(choice, t)
  const detail = detailLabel(choice, t)
  return [choice.runtime, how, detail === how ? '' : detail, workedOn(choice, t)].filter(Boolean).join(' · ')
}

/** A device the picker lists, grouped by kind: simulators first. Its name and what is said of it each keep to one
 * line, cut short where the row ends; the whole of it is the row's tooltip. */
function choiceRow(choice: DeviceChoice, current: string | undefined, t: Translate): string {
  const usable = choice.usable !== false
  const about = choiceAbout(choice, t)
  const tip = about ? ` title="${escapeHTML(`${choice.name} · ${about}`)}"` : ''
  return `<button type="button" role="menuitemradio" aria-checked="${choice.udid === current}"`
    + `${usable ? '' : ' aria-disabled="true"'}${tip} data-smv-udid="${escapeHTML(choice.udid)}">`
    + `<span class="smv-choice-name">${escapeHTML(choice.name)}</span>`
    + `<span class="smv-choice-about">${escapeHTML(about)}</span></button>`
}

/** What a view that can show any of the scope's devices offers beside its rows: making the device it shows the scope's
 * own, and -- showing one of its own -- following the scope's own again. */
function tabMarkup(tab: TabChoice, current: Device | null, t: Translate): string {
  const own = current !== null && current.udid !== tab.own
    ? '<button type="button" role="menuitem" data-smv="use-for-project"'
      + ` data-smv-device="${escapeHTML(current.udid)}">${said(t, 'picker.useForProject')}</button>` : ''
  const follow = tab.pinned !== null
    ? `<button type="button" role="menuitem" data-smv="follow">${said(t, 'picker.follow')}</button>` : ''
  return own + follow
}

export function pickerMarkup(
  choices: DeviceChoice[], current: Device | null, tab?: TabChoice, t: Translate = english,
): string {
  // Simulators -- an older server says no kind -- are headed by their runtime, "iOS 26.5"; the rest by their kind.
  const simulators = choices.filter((choice) => choice.kind !== 'physical' && choice.kind !== 'android' && choice.kind !== 'mac')
  const groups: Array<[label: string, rows: DeviceChoice[]]> = [
    ...[...new Set(simulators.map((choice) => choice.runtime))]
      .map((runtime): [string, DeviceChoice[]] => [runtime, simulators.filter((choice) => choice.runtime === runtime)]),
    [t('picker.physical'), choices.filter((choice) => choice.kind === 'physical')],
    [t('picker.android'), choices.filter((choice) => choice.kind === 'android')],
    [t('picker.mac'), choices.filter((choice) => choice.kind === 'mac')],
  ]
  const group = (text: string) => `<p class="smv-picker-group" role="presentation">${escapeHTML(text)}</p>`
  const listed = groups.filter(([, rows]) => rows.length)
  const body = listed.map(([label, rows]) =>
    (listed.length > 1 ? group(label) : '')
    + rows.map((choice) => choiceRow(choice, current?.udid, t)).join('')).join('')
  // A real device -- an iPhone, an Android phone -- is never shut down: it is only let go.
  const shutdown = isReal(current)
    ? '' : `<button type="button" role="menuitem" data-smv="shutdown">${said(t, 'picker.shutdown')}</button>`
  const heading = tab && body ? group(t('picker.inTab')) : ''
  return heading + (body || `<p class="smv-picker-note">${said(t, 'picker.none')}</p>`)
    + (tab ? tabMarkup(tab, current, t) : '') + shutdown
}

export function createControls(options: ControlsOptions): Controls {
  const { el, picker, transport, stream, status, input, icon, layers, t } = options
  const q = <T extends Element>(selector: string) => el.querySelector<T>(selector)!
  const note = createNote(options.note, icon, t)
  const recordButton = q<HTMLButtonElement>('[data-smv="record"]')
  const { startRecording, stopRecording, recordingFile, recordings, changeDevice } = transport
  // Bound, since a host's transport may be an object whose methods use `this`.
  const recording: RecordingControl | null = startRecording && stopRecording && recordingFile
    ? createRecordingControl({
      button: recordButton, clock: q('[data-smv-rec]'), noteEl: options.note, note, icon, t, root: el, layers,
      sizeToggle: q('[data-smv="record-size"]'), sizePanel: options.recordSize,
      transport: {
        startRecording: startRecording.bind(transport),
        stopRecording: stopRecording.bind(transport),
        recordingFile: recordingFile.bind(transport),
        recordings: recordings?.bind(transport),
      },
    })
    : null
  const display: DisplayMenu | null = changeDevice
    ? createDisplayMenu({
      root: el, toggle: q('[data-smv="display"]'), panel: options.display, layers, note, t,
      changeDevice: changeDevice.bind(transport),
    })
    : null
  let hello: ServerHello | null = null
  const placeButton = q<HTMLButtonElement>('[data-smv="place"]')
  const pageLink = q<HTMLAnchorElement>('[data-smv-page]')
  const closeButton = q<HTMLButtonElement>('[data-smv="close"]')
  const appearanceButton = q<HTMLButtonElement>('[data-smv="appearance"]')
  const devicesButton = q<HTMLButtonElement>('[data-smv="devices"]')
  const settingsButton = q<HTMLButtonElement>('[data-smv="settings"]')
  let dark = false
  // Bound, since a host's transport may be an object whose methods use `this`.
  const use = transport.use?.bind(transport)
  /** The device this view shows instead of the scope's own: only through a transport that can show one. */
  let pinned: string | null = use ? options.device ?? null : null
  /** The scope's own device, as the server last said. */
  let own: string | null = null

  const menu = createPopover({
    root: el, toggle: devicesButton, panel: picker, layers, onClose: () => { picker.innerHTML = '' },
  })

  const closePicker = () => menu.close('toggle')

  const { settings: readSettings, changeSettings } = transport
  const settings: SettingsPanel | null = readSettings && changeSettings
    ? createSettingsPanel({
      root: el, toggle: settingsButton, panel: options.settingsPanel, layers, icon, t,
      // Bound, since a host's transport may be an object whose methods use `this`.
      transport: { settings: readSettings.bind(transport), changeSettings: changeSettings.bind(transport) },
    })
    : null
  settingsButton.hidden = settings === null

  const { touch, setUpTouch } = transport
  const touchSetup: TouchSetupControl | null = touch && setUpTouch
    ? createTouchSetup({
      noteEl: options.note, note, t,
      transport: { touch: touch.bind(transport), setUpTouch: setUpTouch.bind(transport) },
      openSettings: settings
        ? () => void settings.show(stream.device?.kind === 'android' ? 'android' : 'real_devices') : undefined,
    })
    : null

  async function togglePicker(): Promise<void> {
    if (menu.isOpen) return closePicker()
    menu.open()
    picker.innerHTML = `<p class="smv-picker-note">${said(t, 'picker.looking')}</p>`
    let choices: DeviceChoice[]
    try {
      const listing = transport.devices()
      // Which device is the scope's own, for a view that can show another: an older server does not say.
      const standing = use ? transport.status().catch(() => null) : null
      choices = await listing
      own = (await standing)?.default_udid ?? null
    } catch (err) {
      if (menu.isOpen) {
        const message = (err as Error).message || t('picker.failed')
        picker.innerHTML = `<p class="smv-picker-note">${escapeHTML(message)}</p>`
      }
      return
    }
    if (!menu.isOpen) return
    picker.innerHTML = pickerMarkup(choices, stream.device, use ? { pinned, own } : undefined, t)
    menu.focusItem('checked')
  }

  /** Show this device in this view alone, or -- with null -- the scope's own again: the scope's own device and its
   * agents stay where they are. A view already on that device's screen only changes where it comes back to. */
  async function show(udid: string | null): Promise<void> {
    const here = stream.device?.udid
    if (udid !== null && udid === pinned && udid === here) return
    pinned = udid
    await use!(udid)
    options.onDevice?.(udid)
    if (udid !== null ? udid === here : own !== null && own === here) return
    stream.close()
    status.say(() => t('status.switching'))
    await stream.connect()
  }

  /** Make the device this view shows the scope's own: the views following the scope's own come to it, and its agents
   * working on the old one with them. This view then follows the scope's own, which this device now is. */
  async function useForProject(udid: string): Promise<void> {
    closePicker()
    try {
      await transport.choose(udid)
    } catch (err) {
      note.sayText(() => (err as Error).message || t('device.unusable'))
      return
    }
    own = udid
    if (pinned !== null) await show(null)
  }

  async function pick(row: HTMLElement): Promise<void> {
    if (row.getAttribute('aria-disabled') === 'true') return
    const udid = row.dataset.smvUdid!
    closePicker()
    if (use) return show(udid)
    if (udid === stream.device?.udid) return
    try {
      await transport.choose(udid)
    } catch (err) {
      // The device in use is still in use: its screen stays, and the note says why the other could not be.
      note.sayText(() => (err as Error).message || t('device.unusable'))
      return
    }
    stream.close()
    status.say(() => t('status.switching'))
    await stream.connect()
  }

  function letGo(shutdown: boolean): void {
    closePicker()
    input.flushTyped()
    const noun = deviceNoun(stream.device)
    stream.end(() => t(shutdown ? 'letGo.shutdown'
      : noun === 'device' ? 'letGo.device' : noun === 'emulator' ? 'letGo.emulator' : 'letGo.simulator'), 'start')
    void transport.stop(shutdown).catch(() => undefined)
  }

  function paintAppearance(): void {
    appearanceButton.setAttribute('aria-pressed', String(dark))
    name(appearanceButton, t, dark ? 'appearance.light' : 'appearance.dark')
    appearanceButton.innerHTML = icon(dark ? 'sun' : 'moon')
  }

  function paintPlacement(): void {
    const placement = options.placement()
    el.dataset.placement = placement
    const undock = placement === 'dock'
    placeButton.hidden = placement === 'page' || !options.onPlace
    name(placeButton, t, undock ? 'place.undock' : 'place.dock')
    placeButton.innerHTML = icon(undock ? 'undock' : 'dock')
    pageLink.hidden = placement === 'page' || !options.pageHref
    pageLink.setAttribute('href', options.pageHref ?? '')
    closeButton.hidden = !options.onClose
  }

  el.addEventListener('click', (event) => {
    const target = (event.target as HTMLElement).closest<HTMLElement>('[data-smv], [data-smv-udid]')
    if (!target) return
    if (target.dataset.smvUdid !== undefined) {
      void pick(target)
      return
    }
    const action = target.dataset.smv
    if (action !== undefined && PRESSED.has(action)) {
      stream.send({ type: 'button', name: action as PanelButton })
    } else if (action === 'rotate-left' || action === 'rotate-right') {
      stream.send({ type: 'rotate', direction: action === 'rotate-left' ? 'left' : 'right' })
    } else if (action === 'appearance') {
      if (stream.send({ type: 'appearance', mode: dark ? 'light' : 'dark' })) {
        dark = !dark
        paintAppearance()
      }
    } else if (action === 'devices') {
      settings?.close()
      void togglePicker()
    } else if (action === 'settings') {
      closePicker()
      void settings?.toggle()
    } else if (action === 'mode') {
      closePicker()
      const kind = stream.device?.kind
      if (kind !== undefined && kind !== 'simulator' && touchSetup) void touchSetup.open()
      // Where what would let the device be touched is set.
      else void settings?.show(kind === 'physical' ? 'real_devices' : kind === 'android' ? 'android' : 'connectors')
    } else if (action === 'use-for-project') {
      void useForProject(target.dataset.smvDevice!)
    } else if (action === 'follow') {
      closePicker()
      void show(null)
    } else if (action === 'shutdown' || action === 'stop') {
      letGo(action === 'shutdown')
    } else if (action === 'place') {
      options.onPlace?.(options.placement() === 'dock' ? 'window' : 'dock')
    } else if (action === 'start') {
      stream.restart()
    } else if (action === 'close') {
      options.onClose?.()
    }
  })

  /** The device's buttons it can press: those it has, while its connector can press any. */
  function paintButtons(device: Device | null): void {
    const pressable = hello === null || hello.capabilities.includes('input_button')
    const has = buttonsOf(device)
    for (const button of BAR_BUTTONS) q<HTMLButtonElement>(`[data-smv="${button}"]`).hidden = !pressable || !has.includes(button)
  }

  /** Rotate Left and Rotate Right, offered where the server can turn the device: a simulator through its native
   * connector. A real device is turned in the hand, and a macOS app's window does not turn. */
  function paintRotate(device: Device | null): void {
    const turnable = hello !== null && hello.capabilities.includes('rotate')
      && device !== null && (device.kind ?? 'simulator') === 'simulator'
    for (const action of ['rotate-left', 'rotate-right']) q<HTMLButtonElement>(`[data-smv="${action}"]`).hidden = !turnable
  }

  /** A simulator's motion is not the viewer's to reduce; any other device's is. */
  const reducesMotion = (device: Device | null) => device !== null && device.kind !== 'simulator'

  return {
    paintPlacement,
    applyHello(next) {
      hello = next
      for (const [action, capability] of NEEDS) {
        q<HTMLButtonElement>(`[data-smv="${action}"]`).hidden = next !== null && !next.capabilities.includes(capability)
      }
      // The device's name is on the picker's button: a device that cannot be changed keeps its name, on a button
      // that does nothing.
      devicesButton.hidden = false
      devicesButton.disabled = next !== null && !next.capabilities.includes('device_list')
      paintButtons(stream.device)
      paintRotate(stream.device)
      recording?.offer(next !== null && next.capabilities.includes('record'))
      display?.offer(next?.capabilities ?? [], reducesMotion(stream.device))
    },
    applyDevice(device) {
      // The device says whether it is dark -- after a reconnect, a switch, or another viewer's or an agent's change.
      // An older server does not, and the button keeps what this viewer last set.
      const appearance = device?.appearance
      if (appearance === 'dark' || appearance === 'light') {
        dark = appearance === 'dark'
        paintAppearance()
      }
      const stop = q<HTMLButtonElement>('[data-smv="stop"]')
      name(stop, t, `stop.${deviceNoun(device)}`)
      paintButtons(device)
      paintRotate(device)
      recording?.applyDevice(device)
      display?.offer(hello?.capabilities ?? [], reducesMotion(device))
    },
    tell: (message) => note.sayText(message),
    relabel() {
      // A menu open in the old language is closed rather than said again: it is drawn afresh as it opens.
      closePicker()
      note.relabel()
      recording?.relabel()
      display?.relabel()
    },
    destroy() {
      menu.destroy()
      settings?.destroy()
      recording?.destroy()
      display?.destroy()
      touchSetup?.destroy()
      note.destroy()
    },
  }
}
