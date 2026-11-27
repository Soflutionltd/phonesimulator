// SPDX-License-Identifier: Apache-2.0
/**
 * The viewer's language: English, whatever a browser, a host or a past pick asks for, with no Language menu while it
 * speaks no other.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FakeSocket } from '../test-support/fake-socket'
import { flush, live, setup } from '../test-support/viewer-harness'
import { definePhoneSimulatorElement, ELEMENT_NAME, PhoneSimulatorElement } from './element'
import type { PhoneSimulatorTransport } from './transport'

const titles = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>('[data-smv-menu]')].map((menu) => menu.textContent)

beforeEach(() => {
  FakeSocket.reset()
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 1206, height: 2622, close: vi.fn() })))
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ drawImage: vi.fn() })) as never
})

afterEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('the language the viewer speaks', () => {
  it('is English where the browser reads another language', () => {
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['fr-FR', 'fr', 'de'])
    const { view, $ } = setup()
    expect(titles(view.el)).toEqual(['Edit', 'Device', 'View'])
    expect(view.el.lang).toBe('en')
    expect($('[data-smv-state]').textContent).toBe('Stopped')
    expect($<HTMLElement>('[data-smv="settings"]').title).toBe('Settings')
  })

  it('is English whatever a host or a past pick asks for', () => {
    localStorage.setItem('phonesimulator.viewer', JSON.stringify({ lang: 'fr' }))
    expect(titles(setup().view.el)[0]).toBe('Edit')
    expect(titles(setup({ lang: 'fr-CA' }).view.el)[0]).toBe('Edit')
    expect(titles(setup({ lang: 'auto' }).view.el)[0]).toBe('Edit')
  })

  it('offers no Language section in the View menu while it speaks one language', async () => {
    const onLang = vi.fn()
    const { $ } = await live({ onLang })
    expect(onLang.mock.calls).toEqual([['en']])
    $<HTMLButtonElement>('[data-smv-menu="view"]').click()
    const panel = $<HTMLElement>('[data-smv-menu-panel="view"]')
    expect(panel.querySelectorAll('[data-smv-item^="lang-"]')).toHaveLength(0)
    expect([...panel.querySelectorAll('.smv-picker-group')].map((group) => group.textContent)).not.toContain('Language')
  })
})

describe('<phone-simulator lang>', () => {
  const transport = () => ({
    status: vi.fn(), start: vi.fn(async () => ({ device: null, ticket: 'tk' })), stop: vi.fn(async () => true),
    devices: vi.fn(async () => []), choose: vi.fn(), socketUrl: vi.fn(() => 'ws://host/screen'),
  }) as unknown as PhoneSimulatorTransport

  it('is still observed, and a language the viewer does not speak leaves it in English', async () => {
    definePhoneSimulatorElement()
    expect(PhoneSimulatorElement.observedAttributes).toContain('lang')
    const el = document.createElement(ELEMENT_NAME) as PhoneSimulatorElement
    el.setAttribute('lang', 'fr')
    el.transport = transport()
    document.body.appendChild(el)
    await flush()
    const view = el.view!
    expect([view.el.lang, titles(view.el)[0]]).toEqual(['en', 'Edit'])
    el.setAttribute('lang', 'en')
    expect([el.view, view.el.lang]).toEqual([view, 'en'])
  })
})
