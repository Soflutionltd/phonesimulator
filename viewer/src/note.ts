// SPDX-License-Identifier: Apache-2.0
/**
 * A note over the screen: what a person's action did, or why not -- a recording kept, a display change refused. It
 * stays until it is closed with its own button or replaced by the next, and is read out as it changes.
 */
import { escapeHTML } from './escape'
import { english, resolve, type Said, type Translate } from './i18n'
import type { IconRenderer } from './icons'

export interface Note {
  /** Show markup the caller made safe; `sayText` for plain text. Either may be asked for each time it is shown, so
   * that a note still showing follows the language. */
  show(markup: Said): void
  sayText(text: Said): void
  hide(): void
  /** The language changed: say again what is showing. */
  relabel(): void
  destroy(): void
}

export function createNote(el: HTMLElement, icon: IconRenderer, t: Translate = english): Note {
  el.setAttribute('role', 'status')
  let shown: Said | null = null

  function show(markup: Said): void {
    shown = markup
    const close = escapeHTML(t('close'))
    el.innerHTML = `${resolve(markup)}<button type="button" class="smv-icon smv-note-close" data-smv-note-close`
      + ` title="${close}" aria-label="${close}">${icon('close')}</button>`
    el.hidden = false
  }

  const onClick = (event: Event) => {
    if ((event.target as HTMLElement).closest('[data-smv-note-close]')) el.hidden = true
  }
  el.addEventListener('click', onClick)

  return {
    show,
    sayText: (text) => show(() => `<p>${escapeHTML(resolve(text))}</p>`),
    hide: () => {
      el.hidden = true
    },
    relabel: () => {
      if (shown !== null && !el.hidden) show(shown)
    },
    destroy: () => el.removeEventListener('click', onClick),
  }
}
