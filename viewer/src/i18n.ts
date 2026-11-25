// SPDX-License-Identifier: Apache-2.0
/**
 * The viewer's language: which one a person reads, and every message said in it.
 *
 * Messages live in `locales/`, one file per language, English the reference. `t('zoom.level', { percent })` says one:
 * TypeScript knows every key and the values each message takes, so a key that does not exist or a value left out does
 * not compile. The language is the one asked for (`lang`, or View > Language) when the viewer speaks it, else the
 * first of the browser's languages it speaks, else English.
 *
 * It changes without the page reloading. Text that stays on the page is written through `say`, `tip`, `label` and
 * `hint`, which leave its key on the element (`data-i18n…`); `localize` says them all again in the new language. What
 * is drawn afresh each time it shows -- a menu, a note -- simply asks `t` again.
 */
import { escapeHTML } from './escape'
import { DEFAULT_LOCALE, LOCALES, type Locale, type MessageKey } from './locales'
import type { en } from './locales/en'

export type { Locale, MessageKey } from './locales'

/** A language, or the browser's own. */
export type LocaleChoice = Locale | 'auto'

type Named<S> = S extends `${string}{${infer Name}}${infer Rest}` ? Name | Named<Rest> : never
/** The values a message takes: none, or one for each `{name}` in its English. */
export type Vars<K extends MessageKey> = [Named<(typeof en)[K]>] extends [never]
  ? [] : [vars: Record<Named<(typeof en)[K]>, string | number>]

export type Translate = <K extends MessageKey>(key: K, ...vars: Vars<K>) => string

/** Something to say: as it stands, or asked for each time it is shown, so that it follows the language. */
export type Said = string | (() => string)

export const resolve = (said: Said): string => (typeof said === 'function' ? said() : said)

const fill = (text: string, vars: Record<string, string | number> | undefined): string =>
  vars ? text.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name])) : text

/** Says messages in whichever language `locale` answers as each is asked for. */
export function translator(locale: () => Locale): Translate {
  return (key, ...vars) => fill(LOCALES[locale()][key], vars[0])
}

export const english: Translate = translator(() => DEFAULT_LOCALE)

export const isMessageKey = (key: string): key is MessageKey => Object.hasOwn(LOCALES[DEFAULT_LOCALE], key)

/** The language of a BCP 47 tag the viewer speaks -- `fr-CA` is French -- or null. */
export function localeOf(tag: string | null | undefined): Locale | null {
  const primary = (tag ?? '').trim().toLowerCase().split(/[-_]/)[0]
  return Object.hasOwn(LOCALES, primary) ? (primary as Locale) : null
}

/** A choice as kept or asked for: `auto`, or a tag of a language the viewer speaks; null for anything else. */
export function choiceOf(value: unknown): LocaleChoice | null {
  if (typeof value !== 'string') return null
  return value.trim().toLowerCase() === 'auto' ? 'auto' : localeOf(value)
}

/** The browser's languages, most wanted first; none where it does not say. */
function browserLanguages(): readonly string[] {
  const nav = globalThis.navigator as Partial<Navigator> | undefined
  return nav?.languages?.length ? nav.languages : nav?.language ? [nav.language] : []
}

/** The first of a person's languages the viewer speaks, else English. */
export function detectLocale(languages: readonly string[] = browserLanguages()): Locale {
  for (const tag of languages) {
    const locale = localeOf(tag)
    if (locale) return locale
  }
  return DEFAULT_LOCALE
}

export interface I18n {
  /** The language spoken now. */
  readonly locale: Locale
  /** What was asked for: a language, or the browser's own. */
  readonly choice: LocaleChoice
  readonly t: Translate
  /** Speak another language from now on; those listening are told when what is spoken changes. */
  set(choice: LocaleChoice): void
  /** Be told when the language spoken changes; answers how to stop being told. */
  onChange(listener: (locale: Locale) => void): () => void
}

export function createI18n(initial: LocaleChoice = 'auto', languages?: readonly string[]): I18n {
  const spoken = (asked: LocaleChoice) => (asked === 'auto' ? detectLocale(languages) : asked)
  let choice = initial
  let locale = spoken(choice)
  const listeners = new Set<(locale: Locale) => void>()
  return {
    get locale() {
      return locale
    },
    get choice() {
      return choice
    },
    t: translator(() => locale),
    set(next) {
      choice = next
      const now = spoken(next)
      if (now === locale) return
      locale = now
      for (const listener of [...listeners]) listener(locale)
    },
    onChange(listener) {
      listeners.add(listener)
      return () => void listeners.delete(listener)
    },
  }
}

// -- text that stays on the page --------------------------------------------------------------------------------------

/** Where an element's message is said: its text, its tooltip, its accessible name, its placeholder. */
const SLOTS = {
  i18n: (node: HTMLElement, text: string) => { node.textContent = text },
  i18nTitle: (node: HTMLElement, text: string) => { node.title = text },
  i18nLabel: (node: HTMLElement, text: string) => node.setAttribute('aria-label', text),
  i18nHint: (node: HTMLElement, text: string) => node.setAttribute('placeholder', text),
} as const
type Slot = keyof typeof SLOTS
const ATTRIBUTES: Record<Slot, string> = {
  i18n: 'data-i18n', i18nTitle: 'data-i18n-title', i18nLabel: 'data-i18n-label', i18nHint: 'data-i18n-hint',
}

function write<K extends MessageKey>(slot: Slot, node: HTMLElement, t: Translate, key: K, vars: Vars<K>): void {
  node.dataset[slot] = vars.length ? `${key}|${JSON.stringify(vars[0])}` : key
  SLOTS[slot](node, t(key, ...vars))
}

/** Set an element's text to a message, and leave its key on it for `localize`. */
export function say<K extends MessageKey>(node: HTMLElement, t: Translate, key: K, ...vars: Vars<K>): void {
  write('i18n', node, t, key, vars)
}

/** Set an element's text to something that is no message -- what a server said -- so `localize` leaves it alone. */
export function sayPlain(node: HTMLElement, text: string): void {
  delete node.dataset.i18n
  node.textContent = text
}

/** An element's tooltip alone: for one whose content already names it. */
export function tip<K extends MessageKey>(node: HTMLElement, t: Translate, key: K, ...vars: Vars<K>): void {
  write('i18nTitle', node, t, key, vars)
}

/** An element's accessible name alone. */
export function label<K extends MessageKey>(node: HTMLElement, t: Translate, key: K, ...vars: Vars<K>): void {
  write('i18nLabel', node, t, key, vars)
}

/** An element's tooltip and its accessible name: what an icon button is called. */
export function name<K extends MessageKey>(node: HTMLElement, t: Translate, key: K, ...vars: Vars<K>): void {
  write('i18nTitle', node, t, key, vars)
  write('i18nLabel', node, t, key, vars)
}

/** A field's placeholder. */
export function hint<K extends MessageKey>(node: HTMLElement, t: Translate, key: K, ...vars: Vars<K>): void {
  write('i18nHint', node, t, key, vars)
}

/** A message that takes no values. */
export type PlainKey = { [K in MessageKey]: Vars<K> extends [] ? K : never }[MessageKey]

/** The same in markup, for a message that takes no values: the attributes of an element named by one... */
export function nameAttrs(t: Translate, key: PlainKey): string {
  const text = escapeHTML(t(key))
  return ` title="${text}" aria-label="${text}" data-i18n-title="${key}" data-i18n-label="${key}"`
}

/** ...of one given an accessible name alone... */
export function labelAttrs(t: Translate, key: PlainKey): string {
  return ` aria-label="${escapeHTML(t(key))}" data-i18n-label="${key}"`
}

/** ...and an element's `data-i18n` attribute and text: `<span${sayAttr('close')}>${said(t, 'close')}</span>`. */
export const sayAttr = (key: PlainKey): string => ` data-i18n="${key}"`
export const said = (t: Translate, key: PlainKey): string => escapeHTML(t(key))

/** Say again, in `t`'s language, every message left on the elements under `root`. */
export function localize(root: ParentNode, t: Translate): void {
  for (const slot of Object.keys(SLOTS) as Slot[]) {
    for (const node of root.querySelectorAll<HTMLElement>(`[${ATTRIBUTES[slot]}]`)) {
      const [key, vars] = node.dataset[slot]!.split(/\|(.*)/s)
      // Written by `write` or by this viewer's own markup: a key that exists, with the values it takes.
      const text = (t as (key: string, vars?: unknown) => string)(key, vars ? JSON.parse(vars) : undefined)
      SLOTS[slot](node, text)
    }
  }
}
