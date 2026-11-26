// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  choiceOf, createI18n, detectLocale, english, hint, isMessageKey, label, labelAttrs, localeOf, localize, name, nameAttrs,
  resolve, said, say, sayAttr, sayPlain, tip, translator,
} from './i18n'
import { DEFAULT_LOCALE, LOCALES, type MessageKey, type Messages } from './locales'

// Read as any catalogue, so the checks below hold a language added later -- none but English is spoken today.
const CATALOGUES: Record<string, Messages> = LOCALES
const KEYS = Object.keys(LOCALES.en) as MessageKey[]
const OTHERS = Object.keys(CATALOGUES).filter((locale) => locale !== 'en')
const named = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort()
const FILES = Object.keys(import.meta.glob('./locales/*.ts')).map((path) => path.replace(/^.*\/|\.ts$/g, ''))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the catalogues', () => {
  it('are one file a language, every one of them offered', () => {
    expect(FILES.filter((file) => file !== 'index').sort()).toEqual(Object.keys(LOCALES).sort())
    expect(DEFAULT_LOCALE).toBe('en')
    for (const locale of Object.keys(LOCALES)) expect(locale).toMatch(/^[a-z]{2,3}$/)
  })

  it.each(OTHERS)('%s says everything English says, and nothing else', (locale) => {
    const keys = Object.keys(CATALOGUES[locale])
    expect(KEYS.filter((key) => !keys.includes(key))).toEqual([])
    expect(keys.filter((key) => !KEYS.includes(key as MessageKey))).toEqual([])
  })

  it.each(OTHERS)('%s takes the values English takes, message by message, and leaves none empty', (locale) => {
    const odd = KEYS.filter((key) => named(CATALOGUES[locale][key]).join() !== named(LOCALES.en[key]).join())
    expect(odd).toEqual([])
    expect(KEYS.filter((key) => CATALOGUES[locale][key].trim() === '')).toEqual([])
    // What is said before or after a value keeps its room: a message that begins or ends with a space still does.
    const spaced = (text: string) => [/^\s/.test(text), /\s$/.test(text)].join()
    expect(KEYS.filter((key) => spaced(CATALOGUES[locale][key]) !== spaced(LOCALES.en[key]))).toEqual([])
  })

  it('speaks English alone, called by its own name', () => {
    expect(Object.keys(LOCALES)).toEqual(['en'])
    expect(LOCALES.en['language.name']).toBe('English')
  })

})

describe('saying a message', () => {
  it('puts each value where its name is, in the language asked for as it is asked', () => {
    const t = translator(() => 'en')
    expect(t('close')).toBe('Close')
    expect(t('zoom.reduced', { percent: '67%' })).toBe('Actual size, reduced to 67% to fit the window')
    expect(t('status.booting', { name: 'iPhone', seconds: 4 })).toBe('Starting iPhone… 4s')
    expect(english('close')).toBe('Close')
  })

  it('knows a message from any other text, and something asked for from something said', () => {
    expect([isMessageKey('close'), isMessageKey('section.plugins'), isMessageKey('toString')]).toEqual([true, false, false])
    expect([resolve('as it is'), resolve(() => 'asked for')]).toEqual(['as it is', 'asked for'])
  })
})

describe('the language', () => {
  it('is a tag\'s primary language when the viewer speaks it', () => {
    expect(['en', 'EN-us', ' en-GB ', 'fr', 'fr-FR', 'de', 'english', '', null, undefined].map(localeOf))
      .toEqual(['en', 'en', 'en', null, null, null, null, null, null, null])
    expect(['auto', ' AUTO ', 'en-AU', 'en', 'fr', 4, null, undefined].map(choiceOf))
      .toEqual(['auto', 'auto', 'en', 'en', null, null, null, null])
  })

  it('is the first of a person\'s languages the viewer speaks, else English', () => {
    expect(detectLocale(['fr-FR', 'en'])).toBe('en')
    expect(detectLocale(['en-US', 'fr'])).toBe('en')
    expect(detectLocale(['de-DE', 'fr-BE'])).toBe('en')
    expect(detectLocale(['de', 'ja'])).toBe('en')
    expect(detectLocale([])).toBe('en')
  })

  it('is read from the browser: its languages, else its language, else none', () => {
    // jsdom's own.
    expect(detectLocale()).toBe('en')
    vi.stubGlobal('navigator', { languages: ['fr-FR', 'en-GB'], language: 'fr-FR' })
    expect(detectLocale()).toBe('en')
    vi.stubGlobal('navigator', { languages: [], language: 'en-CA' })
    expect(detectLocale()).toBe('en')
    vi.stubGlobal('navigator', { language: 'fr' })
    expect(detectLocale()).toBe('en')
    vi.stubGlobal('navigator', {})
    expect(detectLocale()).toBe('en')
    vi.stubGlobal('navigator', undefined)
    expect(detectLocale()).toBe('en')
  })

  it('keeps what was asked for, telling those listening only when what is spoken changes', () => {
    const i18n = createI18n('auto', ['fr-FR'])
    const heard = vi.fn()
    const stop = i18n.onChange(heard)
    expect([i18n.locale, i18n.choice, i18n.t('close')]).toEqual(['en', 'auto', 'Close'])
    // English asked for by name is still English: the choice is kept, and nobody is told.
    i18n.set('en')
    expect([i18n.locale, i18n.choice, heard.mock.calls.length]).toEqual(['en', 'en', 0])
    i18n.set('auto')
    expect([i18n.locale, i18n.choice, heard.mock.calls.length]).toEqual(['en', 'auto', 0])
    stop()
    // Asked for nothing, it is the browser's -- here jsdom's English.
    expect([createI18n().locale, createI18n().choice]).toEqual(['en', 'auto'])
  })
})

describe('text that stays on the page', () => {
  it('is written with its key, and said again where it stands', () => {
    const t = translator(() => 'en')
    const root = document.createElement('div')
    const [text, button, group, field, link, server] = ['p', 'button', 'div', 'textarea', 'a', 'p']
      .map((tag) => root.appendChild(document.createElement(tag)))
    say(text, t, 'settings.waiting', { summary: 'server.port | {a}' })
    name(button, t, 'record.stop', { by: 'Claude' })
    label(group, t, 'zoom.group')
    hint(field, t, 'field.originsHint')
    tip(link, t, 'field.resetTitle', { path: 'stream.fps' })
    say(server, t, 'settings.saved')
    sayPlain(server, 'The server said no.')
    expect(text.textContent).toBe('Waiting for the code for: server.port | {a}')
    expect([button.title, button.getAttribute('aria-label')]).toEqual(Array(2).fill('Stop recording (started by Claude)'))
    expect([group.getAttribute('aria-label'), group.title]).toEqual(['Zoom', ''])
    expect(field.getAttribute('placeholder')).toBe('http://localhost:3000 — one per line')
    expect([link.title, link.hasAttribute('aria-label')]).toEqual(['Put stream.fps back to what applies without it', false])

    // Said again from the keys left on the elements, whatever was written over them since.
    for (const node of [text, group]) node.textContent = ''
    button.title = ''
    field.setAttribute('placeholder', '')
    link.title = ''
    localize(root, t)
    expect(text.textContent).toBe('Waiting for the code for: server.port | {a}')
    expect([button.title, button.getAttribute('aria-label')]).toEqual(Array(2).fill('Stop recording (started by Claude)'))
    expect(group.getAttribute('aria-label')).toBe('Zoom')
    expect(field.getAttribute('placeholder')).toBe('http://localhost:3000 — one per line')
    expect(link.title).toBe('Put stream.fps back to what applies without it')
    // What a server said is nobody's to translate.
    expect(server.textContent).toBe('The server said no.')

    // The same key said again with another value replaces the first.
    name(button, t, 'record.full')
    localize(root, t)
    expect(button.title).toBe('Record the screen')
  })

  it('is written the same in markup, made safe', () => {
    const host = document.createElement('div')
    host.innerHTML = `<button${nameAttrs(english, 'settings.close')}></button><div${labelAttrs(english, 'tools.label')}></div>`
      + `<span${sayAttr('close')}>${said(english, 'close')}</span>`
    const [button, bar, text] = [...host.children] as HTMLElement[]
    expect([button.title, button.getAttribute('aria-label')]).toEqual(Array(2).fill('Close settings'))
    expect([bar.getAttribute('aria-label'), text.textContent]).toEqual(['Device controls', 'Close'])
    text.textContent = ''
    localize(host, english)
    expect([button.title, button.getAttribute('aria-label'), bar.getAttribute('aria-label'), text.textContent])
      .toEqual(['Close settings', 'Close settings', 'Device controls', 'Close'])
    const quoted = translator(() => 'en')
    expect(nameAttrs(quoted, 'touch.signed.project' as 'close')).toContain('project&#39;s')
  })
})
