// SPDX-License-Identifier: Apache-2.0
/**
 * Nothing a person reads is written straight into the viewer's source: it is a message in `locales/`, said through
 * `i18n.ts`. This reads every source file for text that looks said (`test-support/visible-text.ts`) and fails on any
 * that is not listed below, with why it may stay.
 */
import { describe, expect, it } from 'vitest'

import { isProse, proseIn, readable } from '../test-support/visible-text'

const SOURCES: Record<string, string> = {
  ...import.meta.glob<string>('./*.ts', { query: '?raw', import: 'default', eager: true }),
  ...import.meta.glob<string>('../standalone/*.ts', { query: '?raw', import: 'default', eager: true }),
}

/** Text that is in the source on purpose, by file: each is a name or a word for a program, not for a person. */
const ALLOWED: Record<string, string[]> = {
  // A key's name, as `KeyboardEvent.key` and `aria-keyshortcuts` spell it.
  './menu-bar.ts': ['Plus', 'Minus', 'Arrow', 'Meta', 'Control', 'Shift'],
  './popover.ts': ['Escape', 'Tab'],
  // An HTTP authorization scheme's name.
  './http-transport.ts': ['Bearer'],
  // How the server's own note of a recording still being rendered begins: read, never shown.
  './recording-control.ts': ['still being rendered'],
  // Why a picture or a start was given up, for the code that asked: caught there, and shown to nobody.
  './screen-canvas.ts': ['a frame that does not decode'],
  './viewer-stream.ts': ['the simulator view was closed'],
}

const scanned = Object.entries(SOURCES)
  .filter(([path]) => !path.endsWith('.test.ts') && !path.endsWith('protocol.generated.ts'))

describe('text a person reads', () => {
  it('is told from markup, selectors and names', () => {
    expect(readable('<button type="button" class="smv-icon a" title="Close" aria-label="Close settings">\u0001</button>'))
      .toEqual(['Close', 'Close settings'])
    expect(readable('<p class="smv-picker-note">Looking for devices…</p>')).toEqual(['Looking for devices…'])
    expect(['Close', 'Looking for devices…', 'Thinking…', 'used by', "the project's own team", 'à la une'].map(isProse))
      .toEqual([true, true, true, true, true, true])
    expect(['close', 'smv-button smv-button-primary', '[data-smv], [data-smv-udid]', 'zoom.level', 'image/png', 'USB',
      'Bearer', 'HTTP', '· SDK', '100%', 'aria-label'].map(isProse))
      .toEqual([false, false, false, false, false, false, true, false, false, false, false])
  })

  it('is found wherever it is written: in a call, in markup, in a template, joined with +', () => {
    const source = [
      "close.title = 'Close settings'",
      "const save = make('button', 'smv-button smv-button-primary', 'Save')",
      'el.innerHTML = `<p class="note">${escapeHTML(text)}</p><button title="Try again">${icon}</button>`',
      "const row = '<button type=\"button\" role=\"menuitem\"' + ` data-id=\"${id}\">Follow the project</button>`",
      'status.textContent = `Waiting for the code for: ${summary}`',
      "say(node, t, 'settings.saved')",
      "import { say } from './i18n'",
      "type Placement = 'dock' | 'window'",
    ].join('\n')
    expect(proseIn('sample.ts', source))
      .toEqual(['Close settings', 'Save', 'Try again', 'Follow the project', 'Waiting for the code for:'])
  })

  it.each(scanned)('is not written into %s', (path, source) => {
    const allowed = ALLOWED[path] ?? []
    expect(proseIn(path, source).filter((text) => !allowed.includes(text))).toEqual([])
  })

  it('is read in every source file, and nothing is allowed that is no longer there', () => {
    expect(scanned.length).toBeGreaterThan(30)
    for (const [path, texts] of Object.entries(ALLOWED)) {
      const there = proseIn(path, SOURCES[path])
      expect(texts.filter((text) => !there.includes(text)), path).toEqual([])
    }
  })
})
