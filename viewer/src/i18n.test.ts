// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  choiceOf, createI18n, detectLocale, english, hint, isMessageKey, label, labelAttrs, localeOf, localize, name, nameAttrs,
  resolve, said, say, sayAttr, sayPlain, tip, translator,
} from './i18n'
import { DEFAULT_LOCALE, LOCALES, type Locale, type MessageKey } from './locales'

const FILES = Object.keys(import.meta.glob('./locales/*.ts')).map((path) => path.replace(/^.*\/|\.ts$/g, ''))
const KEYS = Object.keys(LOCALES.en) as MessageKey[]
const OTHERS = (Object.keys(LOCALES) as Locale[]).filter((locale) => locale !== 'en')
const named = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort()

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
    const keys = Object.keys(LOCALES[locale])
    expect(KEYS.filter((key) => !keys.includes(key))).toEqual([])
    expect(keys.filter((key) => !KEYS.includes(key as MessageKey))).toEqual([])
  })

  it.each(OTHERS)('%s takes the values English takes, message by message, and leaves none empty', (locale) => {
    const odd = KEYS.filter((key) => named(LOCALES[locale][key]).join() !== named(LOCALES.en[key]).join())
    expect(odd).toEqual([])
    expect(KEYS.filter((key) => LOCALES[locale][key].trim() === '')).toEqual([])
    // What is said before or after a value keeps its room: a message that begins or ends with a space still does.
    const spaced = (text: string) => [/^\s/.test(text), /\s$/.test(text)].join()
    expect(KEYS.filter((key) => spaced(LOCALES[locale][key]) !== spaced(LOCALES.en[key]))).toEqual([])
  })

  it('calls each language by its own name', () => {
    expect([LOCALES.en['language.name'], LOCALES.fr['language.name']]).toEqual(['English', 'Français'])
  })

  it('writes French as French is set: no-break spaces before double punctuation, ’ for the apostrophe', () => {
    for (const key of KEYS) {
      // An address and a command are written as they are typed.
      const text = LOCALES.fr[key].replace(/https?:\/\/\S+/g, '').replace(/`[^`]*`/g, '')
      expect(text, key).not.toMatch(/'/)
      expect(text, key).not.toMatch(/[—–]/)
      expect(text, key).not.toMatch(/[^\u00a0]:/)
      expect(text, key).not.toMatch(/[^\u202f][;!?%]/)
      expect(text, key).not.toMatch(/\.\.\./)
    }
  })
})

describe('saying a message', () => {
  it('puts each value where its name is, in the language asked for as it is asked', () => {
    let locale: Locale = 'en'
    const t = translator(() => locale)
    expect(t('close')).toBe('Close')
    expect(t('zoom.reduced', { percent: '67%' })).toBe('Actual size, reduced to 67% to fit the window')
    expect(t('status.booting', { name: 'iPhone', seconds: 4 })).toBe('Starting iPhone… 4s')
    locale = 'fr'
    expect(t('close')).toBe('Fermer')
    expect(t('status.booting', { name: 'iPhone', seconds: 4 })).toBe('Démarrage de iPhone… 4\u00a0s')
    expect(t('percent', { n: 67 })).toBe('67\u202f%')
    expect(english('close')).toBe('Close')
  })

  it('knows a message from any other text, and something asked for from something said', () => {
    expect([isMessageKey('close'), isMessageKey('section.plugins'), isMessageKey('toString')]).toEqual([true, false, false])
    expect([resolve('as it is'), resolve(() => 'asked for')]).toEqual(['as it is', 'asked for'])
  })
})

describe('the language', () => {
  it('is a tag\'s primary language when the viewer speaks it', () => {
    expect(['fr', 'fr-FR', 'FR_ca', ' en-GB ', 'de', 'french', '', null, undefined].map(localeOf))
      .toEqual(['fr', 'fr', 'fr', 'en', null, null, null, null, null])
    expect(['auto', ' AUTO ', 'fr-CH', 'en', 'de', 4, null, undefined].map(choiceOf))
      .toEqual(['auto', 'auto', 'fr', 'en', null, null, null, null])
  })

  it('is the first of a person\'s languages the viewer speaks, else English', () => {
    expect(detectLocale(['fr-FR', 'en'])).toBe('fr')
    expect(detectLocale(['en-US', 'fr'])).toBe('en')
    expect(detectLocale(['de-DE', 'fr-BE', 'en'])).toBe('fr')
    expect(detectLocale(['de', 'ja'])).toBe('en')
    expect(detectLocale([])).toBe('en')
  })

  it('is read from the browser: its languages, else its language, else none', () => {
    // jsdom's own.
    expect(detectLocale()).toBe('en')
    vi.stubGlobal('navigator', { languages: ['fr-FR', 'fr', 'en'], language: 'fr-FR' })
    expect(detectLocale()).toBe('fr')
    vi.stubGlobal('navigator', { languages: [], language: 'fr-CA' })
    expect(detectLocale()).toBe('fr')
    vi.stubGlobal('navigator', { language: 'fr' })
    expect(detectLocale()).toBe('fr')
    vi.stubGlobal('navigator', {})
    expect(detectLocale()).toBe('en')
    vi.stubGlobal('navigator', undefined)
    expect(detectLocale()).toBe('en')
  })

  it('changes when asked, telling those listening only when what is spoken changes', () => {
    const i18n = createI18n('auto', ['fr-FR'])
    const heard = vi.fn()
    const stop = i18n.onChange(heard)
    expect([i18n.locale, i18n.choice, i18n.t('close')]).toEqual(['fr', 'auto', 'Fermer'])
    // French asked for by name is still French: the choice is kept, and nobody is told.
    i18n.set('fr')
    expect([i18n.locale, i18n.choice, heard.mock.calls.length]).toEqual(['fr', 'fr', 0])
    i18n.set('en')
    expect([i18n.locale, i18n.choice, i18n.t('close')]).toEqual(['en', 'en', 'Close'])
    expect(heard).toHaveBeenLastCalledWith('en')
    i18n.set('auto')
    expect(heard).toHaveBeenLastCalledWith('fr')
    stop()
    i18n.set('en')
    expect(heard).toHaveBeenCalledTimes(2)
    // Asked for nothing, it is the browser's -- here jsdom's English.
    expect([createI18n().locale, createI18n().choice]).toEqual(['en', 'auto'])
  })
})

describe('text that stays on the page', () => {
  it('is written with its key, and said again in another language where it stands', () => {
    let locale: Locale = 'en'
    const t = translator(() => locale)
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

    locale = 'fr'
    localize(root, t)
    expect(text.textContent).toBe('En attente du code pour\u00a0: server.port | {a}')
    expect([button.title, button.getAttribute('aria-label')]).toEqual(Array(2).fill('Arrêter l’enregistrement (lancé par Claude)'))
    expect(group.getAttribute('aria-label')).toBe('Zoom')
    expect(field.getAttribute('placeholder')).toBe('http://localhost:3000 (une par ligne)')
    expect(link.title).toBe('Rétablir pour stream.fps la valeur qui s’applique sans ce réglage')
    // What a server said is nobody's to translate.
    expect(server.textContent).toBe('The server said no.')

    // The same key said again with another value replaces the first.
    name(button, t, 'record.full')
    locale = 'en'
    localize(root, t)
    expect(button.title).toBe('Record the screen')
  })

  it('is written the same in markup, made safe', () => {
    const t = translator(() => 'fr')
    const host = document.createElement('div')
    host.innerHTML = `<button${nameAttrs(t, 'settings.close')}></button><div${labelAttrs(t, 'tools.label')}></div>`
      + `<span${sayAttr('close')}>${said(t, 'close')}</span>`
    const [button, bar, text] = [...host.children] as HTMLElement[]
    expect([button.title, button.getAttribute('aria-label')]).toEqual(Array(2).fill('Fermer les réglages'))
    expect([bar.getAttribute('aria-label'), text.textContent]).toEqual(['Commandes de l’appareil', 'Fermer'])
    localize(host, english)
    expect([button.title, button.getAttribute('aria-label'), bar.getAttribute('aria-label'), text.textContent])
      .toEqual(['Close settings', 'Close settings', 'Device controls', 'Close'])
    const quoted = translator(() => 'en')
    expect(nameAttrs(quoted, 'touch.signed.project' as 'close')).toContain('project&#39;s')
  })
})
