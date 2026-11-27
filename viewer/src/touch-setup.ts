// SPDX-License-Identifier: Apache-2.0
/**
 * Set up touch: a real device that cannot be touched yet is set up once by a person, from the note over the screen.
 *
 * The server says how it stands (`TouchSetup`): what is in the way, and what a person can do about it -- set it up,
 * try again, or open the settings where WebDriverAgent and the signing team are. Setting up builds WebDriverAgent on
 * the Mac, which takes a minute or two the first time; the note follows it until it is done, and the screen socket
 * restarts with a device that can be touched.
 */
import { escapeHTML } from './escape'
import { english, type Translate } from './i18n'
import type { Note } from './note'
import type { TouchSetup } from './protocol.generated'
import type { PhoneSimulatorTransport } from './transport'

const POLL_MS = 3000

export type TouchTransport = Required<Pick<PhoneSimulatorTransport, 'touch' | 'setUpTouch'>>

export interface TouchSetupOptions {
  /** The note's element, where the setup's buttons are. */
  noteEl: HTMLElement
  note: Note
  transport: TouchTransport
  /** Says the setup's messages; in English when absent. */
  t?: Translate
  /** Open the settings where WebDriverAgent and its team are set; absent where no settings are offered. */
  openSettings?(): void
}

export interface TouchSetupControl {
  /** Say how touching the device stands, with what a person can do about it. */
  open(): Promise<void>
  destroy(): void
}

/** How touching the device stands, as the note shows it, with a button for what a person can do next. */
export function touchMarkup(setup: TouchSetup, settings: boolean, t: Translate = english): string {
  const button = (action: string, label: string) =>
    `<button type="button" class="smv-btn" data-smv-touch="${action}">${escapeHTML(label)}</button>`
  const message = setup.state === 'ready' ? t('touch.ready')
    : setup.state === 'not_needed' ? t('touch.notNeeded')
      : setup.message || t('touch.pending')
  const team = setup.team && setup.team_from
    // The message is the viewer's own; the team's name is the server's, and is the part made safe.
    ? `<p>${t(`touch.signed.${setup.team_from}`, { team: escapeHTML(setup.team) })}</p>` : ''
  const next = setup.state === 'offer' ? button('set-up', t('mode.setUpTouch'))
    : setup.state === 'failed' ? button('set-up', t('retry'))
      : (setup.state === 'needs_team' || setup.state === 'off') && settings ? button('settings', t('touch.openSettings'))
        : ''
  return `<div class="smv-touch" data-smv-touch-note data-state="${setup.state}"><p>${escapeHTML(message)}</p>`
    + `${team}${next}</div>`
}

export function createTouchSetup(options: TouchSetupOptions): TouchSetupControl {
  const { noteEl, note, transport } = options
  const t = options.t ?? english
  let timer: number | null = null

  function stopFollowing(): void {
    if (timer !== null) window.clearTimeout(timer)
    timer = null
  }

  /** Whether the note still shows the setup, rather than something since. */
  const showing = () => !noteEl.hidden && noteEl.querySelector('[data-smv-touch-note]') !== null

  function show(setup: TouchSetup): void {
    note.show(() => touchMarkup(setup, options.openSettings !== undefined, t))
    stopFollowing()
    if (setup.state === 'building' || setup.state === 'starting') {
      timer = window.setTimeout(() => void follow(), POLL_MS)
    }
  }

  async function ask(call: () => Promise<TouchSetup>): Promise<void> {
    try {
      show(await call())
    } catch (error) {
      stopFollowing()
      note.sayText(() => (error as Error).message || t('touch.failed'))
    }
  }

  async function follow(): Promise<void> {
    timer = null
    if (showing()) await ask(() => transport.touch())
  }

  const onNote = (event: Event) => {
    const target = (event.target as HTMLElement).closest<HTMLElement>('[data-smv-touch]')
    if (!target) return
    if (target.dataset.smvTouch === 'settings') {
      note.hide()
      options.openSettings?.()
    } else {
      void ask(() => transport.setUpTouch())
    }
  }
  noteEl.addEventListener('click', onNote)

  return {
    open: () => ask(() => transport.touch()),
    destroy() {
      stopFollowing()
      noteEl.removeEventListener('click', onNote)
    },
  }
}
