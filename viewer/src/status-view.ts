// SPDX-License-Identifier: Apache-2.0
/**
 * What the viewer says about the device: its name, whether it is a real device or an Android one and how it is
 * connected, the state pill, what an agent is doing or the device is busy with, whether the mirror can only show the
 * screen -- or, on an Android device without scrcpy, show it only a few times a second -- which app in front shares its
 * view hierarchy through Simtrail's debug SDK, and -- when there is no screen to show -- why, with a way on.
 */
import { textOn } from './agent-cursor'
import { deviceNoun, isReal, kindChip } from './device-kind'
import { escapeHTML } from './escape'
import { resolve, type Said, type Translate } from './i18n'
import { DEVICE_STATES, type Device, type DeviceState, type ServerHello } from './protocol.generated'

const BOOT_TICK_MS = 1000

export type Offer = 'start' | 'retry'

/** Text as a sentence, so another can follow it: ending as it does, or with a full stop. A server's reasons -- a close
 * code's, a device's -- may end either way. */
export function sentence(text: string): string {
  const trimmed = text.trim()
  return /[.!?…]$/.test(trimmed) ? trimmed : `${trimmed}.`
}

export interface StatusParts {
  canvas: HTMLCanvasElement
  empty: HTMLElement
  badge: HTMLElement
  name: HTMLElement
  /** The chip that says a device is a real one or an Android one, and how it is connected. */
  kind: HTMLElement
  state: HTMLElement
  mode: HTMLElement
  app: HTMLElement
}

export interface StatusView {
  /** Show why there is no screen -- with a way on, when there is one -- or, given null, the screen. A message asked
   * for each time it is shown follows the language. */
  say(message: Said | null, offer?: Offer): void
  showState(state: DeviceState): void
  applyDevice(device: Device | null): void
  /** An agent is using the device, by this title, doing this -- '' when it says nothing more -- and drawn in this colour
   * ('' for the viewer's own, `--simtrail-cursor`); null when none is. The pill is that colour too. */
  setAgent(title: string | null, activity?: string, color?: string): void
  /** What the server said it offers: a mirror whose connector cannot touch the screen says so. */
  setMode(hello: ServerHello | null): void
  stopBootTimer(): void
  /** The language changed: say again everything said here. */
  relabel(): void
}

/** A device's state from the screen socket, checked -- or null for anything that is not one. */
export function readDevice(message: Record<string, unknown>): Device | null {
  const valid = typeof message.udid === 'string' && typeof message.name === 'string'
    && (DEVICE_STATES as readonly unknown[]).includes(message.state)
  return valid ? (message as unknown as Device) : null
}

export function createStatusView(parts: StatusParts, t: Translate): StatusView {
  let device: Device | null = null
  /** The state the pill shows, and what the empty screen says, as last asked: said again when the language changes. */
  let state: DeviceState = 'stopped'
  let told: { message: Said | null, offer?: Offer } = { message: null }
  let hello: ServerHello | null = null
  let agent: string | null = null
  let doing = ''
  let hue = ''
  const activity = document.createElement('span')
  activity.className = 'smv-agent-activity'
  let bootTimer: number | null = null

  /** Who is using the device and what it is doing now -- or that it is, until it says -- else what it is busy with. The
   * agent's name is kept whole in the pill's tooltip, however the pill is cut to fit. */
  function paintBadge(): void {
    const using = agent ? t('agent.using', { agent }) : ''
    const busy = device?.busy ? t('device.busy', { what: device.busy }) : ''
    if (agent) {
      activity.textContent = doing ? ` · ${doing}` : t('agent.usingSuffix')
      parts.badge.replaceChildren(agent, activity)
    } else {
      parts.badge.textContent = busy
    }
    parts.badge.title = using
    parts.badge.hidden = !agent && !busy
    // The agent's pill is the colour of its pointer; what the device is busy with keeps the accent.
    parts.badge.classList.toggle('is-agent', agent !== null)
    if (agent !== null && hue) {
      parts.badge.style.setProperty('--ac-color', hue)
      parts.badge.style.setProperty('--ac-text', textOn(hue))
    } else {
      parts.badge.style.removeProperty('--ac-color')
      parts.badge.style.removeProperty('--ac-text')
    }
  }

  /** The app sharing its view hierarchy, by the name the app gives: always set as text, never as markup. */
  function paintApp(): void {
    const shared = device?.app_hierarchy ?? null
    const said = shared
      ? t('app.shares', { name: shared.name, bundle: shared.bundle_id, version: shared.sdk_version })
      : ''
    parts.app.hidden = shared === null
    parts.app.textContent = shared ? `${shared.name} · SDK` : ''
    parts.app.title = said
    if (shared) parts.app.setAttribute('aria-label', said)
    else parts.app.removeAttribute('aria-label')
  }

  /** What starting says: a real device is not started, only shown again. */
  const startLabel = () => t(isReal(device) ? 'start.real' : `start.${deviceNoun(device)}`)

  function say(message: Said | null, offer?: Offer): void {
    told = { message, offer }
    parts.empty.hidden = message === null
    parts.canvas.hidden = message !== null
    const way = escapeHTML(offer === 'start' ? startLabel() : t('retry'))
    parts.empty.innerHTML = message === null ? ''
      : `<p>${escapeHTML(resolve(message))}</p>`
        + (offer ? `<button type="button" class="smv-btn" data-smv="start">${way}</button>` : '')
  }

  function stopBootTimer(): void {
    if (bootTimer !== null) window.clearInterval(bootTimer)
    bootTimer = null
  }

  function showState(next: DeviceState): void {
    state = next
    parts.state.dataset.state = next
    parts.state.textContent = t(`state.${next}`)
  }

  /** The device's name and what it is: what the bar says of it whatever its state. */
  function paintDevice(): void {
    parts.name.textContent = device ? `${device.name} · ${device.runtime}` : t('device.unnamed')
    paintMode()
    const chip = kindChip(device, t)
    parts.kind.hidden = !chip
    parts.kind.textContent = chip
    paintBadge()
    paintApp()
  }

  function applyDevice(next: Device | null): void {
    device = next
    stopBootTimer()
    paintDevice()
    const noun = deviceNoun(next)
    showState(next?.state ?? 'stopped')
    if (!next) return
    if (next.state === 'ready') {
      say(null)
    } else if (next.state === 'booting') {
      const began = Date.now() - next.since_ms
      const starting = () =>
        t('status.booting', { name: next.name, seconds: Math.round((Date.now() - began) / 1000) })
      say(starting)
      bootTimer = window.setInterval(() => say(starting), BOOT_TICK_MS)
    } else if (next.state === 'stalled') {
      say(() => t('status.reconnecting', { why: sentence(next.reason || t(`status.unanswering.${noun}`)) }))
    } else if (next.state === 'failed') {
      say(() => next.reason || t(`status.failed.${noun}`), 'retry')
    } else {
      say(() => t(`status.stopped.${noun}`), 'start')
    }
  }

  /** A mirror that cannot touch says so; a real device's offers what would let it be touched -- and an Android
   * device shown through adb alone, what would show it live. */
  function paintMode(): void {
    const viewOnly = hello !== null && !hello.capabilities.includes('input_touch')
    const slow = hello !== null && device?.kind === 'android' && !hello.capabilities.includes('stream_h264')
    parts.mode.hidden = !viewOnly && !slow
    parts.mode.textContent = t(slow || (viewOnly && device?.kind === 'physical') ? 'mode.setUpTouch' : 'mode.viewOnly')
    parts.mode.title = hello && viewOnly
      ? hello.fallback_reason ?? t('mode.viewOnlyWhy', { connector: hello.connector })
      : slow ? t('mode.slowWhy') : ''
  }

  function setMode(next: ServerHello | null): void {
    hello = next
    paintMode()
  }

  return {
    say,
    showState,
    applyDevice,
    setAgent(title, activity = '', color = '') {
      agent = title
      doing = title === null ? '' : activity
      hue = title === null ? '' : color
      paintBadge()
    },
    setMode,
    stopBootTimer,
    relabel() {
      showState(state)
      paintDevice()
      say(told.message, told.offer)
    },
  }
}
