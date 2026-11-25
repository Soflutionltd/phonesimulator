// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest'

import { keepPreferences, readPreferences } from './preferences'

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('preferences', () => {
  it('starts from nothing, and keeps what a person picks, one change at a time', () => {
    expect(readPreferences()).toEqual({ theme: null, framed: null, zoom: null, lang: null })
    keepPreferences({ theme: 'dark' })
    keepPreferences({ framed: false })
    expect(readPreferences()).toEqual({ theme: 'dark', framed: false, zoom: null, lang: null })
    keepPreferences({ zoom: 'fit' })
    expect(readPreferences().zoom).toBe('fit')
    keepPreferences({ zoom: 1.5 })
    expect(readPreferences()).toEqual({ theme: 'dark', framed: false, zoom: 1.5, lang: null })
  })

  it('ignores what it does not recognise', () => {
    localStorage.setItem('simtrail.viewer', JSON.stringify({ theme: 'sepia', framed: 'yes', zoom: 40 }))
    expect(readPreferences()).toEqual({ theme: null, framed: null, zoom: null, lang: null })
    localStorage.setItem('simtrail.viewer', '{not json')
    expect(readPreferences()).toEqual({ theme: null, framed: null, zoom: null, lang: null })
  })

  it('starts from the defaults where the browser keeps nothing, or refuses', () => {
    vi.stubGlobal('localStorage', undefined)
    keepPreferences({ theme: 'light' })
    expect(readPreferences()).toEqual({ theme: null, framed: null, zoom: null, lang: null })
    vi.unstubAllGlobals()
    vi.spyOn(globalThis, 'localStorage', 'get').mockImplementation(() => { throw new Error('denied') })
    expect(readPreferences()).toEqual({ theme: null, framed: null, zoom: null, lang: null })
    vi.restoreAllMocks()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    expect(() => keepPreferences({ framed: true })).not.toThrow()
  })
})
