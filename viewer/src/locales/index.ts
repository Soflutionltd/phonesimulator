// SPDX-License-Identifier: Apache-2.0
/**
 * The languages the viewer speaks, each by its BCP 47 primary subtag.
 *
 * To add one: write `<tag>.ts` beside this file -- a `Messages` object, so TypeScript names every key it lacks or
 * invents, with its own name under `language.name` -- and add it to `LOCALES`. Nothing else changes: the View menu
 * lists it (its Language section shows once there are two), `navigator.languages` and `lang` pick it, and the tests
 * hold it to English's keys and placeholders.
 */
import { en, type Messages } from './en'

export type { MessageKey, Messages } from './en'

export const LOCALES = { en } as const satisfies Record<string, Messages>

export type Locale = keyof typeof LOCALES

/** What is spoken where nothing else is asked for or understood. */
export const DEFAULT_LOCALE: Locale = 'en'
