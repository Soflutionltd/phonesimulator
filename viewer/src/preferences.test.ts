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
    expect(readPreferences()).toEqual({ theme: null, framed: null })
    keepPreferences({ theme: 'dark' })
    keepPreferences({ framed: false })
    expect(readPreferences()).toEqual({ theme: 'dark', framed: false })
  })

  it('ignores what it does not recognise', () => {
    localStorage.setItem('simtrail.viewer', JSON.stringify({ theme: 'sepia', framed: 'yes' }))
    expect(readPreferences()).toEqual({ theme: null, framed: null })
    localStorage.setItem('simtrail.viewer', '{not json')
    expect(readPreferences()).toEqual({ theme: null, framed: null })
  })

  it('starts from the defaults where the browser keeps nothing, or refuses', () => {
    vi.stubGlobal('localStorage', undefined)
    keepPreferences({ theme: 'light' })
    expect(readPreferences()).toEqual({ theme: null, framed: null })
    vi.unstubAllGlobals()
    vi.spyOn(globalThis, 'localStorage', 'get').mockImplementation(() => { throw new Error('denied') })
    expect(readPreferences()).toEqual({ theme: null, framed: null })
    vi.restoreAllMocks()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    expect(() => keepPreferences({ framed: true })).not.toThrow()
  })
})
