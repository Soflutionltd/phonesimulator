// SPDX-License-Identifier: Apache-2.0
/**
 * What a person chose for how the viewer looks -- its theme, whether the device's frame is drawn -- kept in this
 * browser for next time. Only those: nothing about a device or a scope. A browser that keeps nothing (a private
 * window, storage turned off) simply starts from the defaults each time.
 */

export type Theme = 'system' | 'light' | 'dark'
export const THEMES: readonly Theme[] = ['system', 'light', 'dark']

export interface Preferences {
  theme: Theme | null
  framed: boolean | null
}

const KEY = 'simtrail.viewer'

/** The storage to keep them in; null where the page may not read it. */
function store(): Storage | null {
  try {
    return globalThis.localStorage ?? null
  } catch {
    return null
  }
}

export function readPreferences(): Preferences {
  try {
    const kept = JSON.parse(store()?.getItem(KEY) ?? '{}') as Record<string, unknown>
    return {
      theme: THEMES.includes(kept.theme as Theme) ? (kept.theme as Theme) : null,
      framed: typeof kept.framed === 'boolean' ? kept.framed : null,
    }
  } catch {
    return { theme: null, framed: null }
  }
}

export function keepPreferences(change: Partial<Preferences>): void {
  try {
    store()?.setItem(KEY, JSON.stringify({ ...readPreferences(), ...change }))
  } catch {
    // Not kept: the choice still holds for this page.
  }
}
