// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FakeSocket } from '../test-support/fake-socket'
import { DEVICE, HELLO, VIEW_ONLY, flush, frame, live, socket } from '../test-support/viewer-harness'
import { TAG_JPEG, type Device } from './protocol.generated'

const ANDROID: Device = {
  ...DEVICE, kind: 'android', name: 'Pixel 9', connection: null,
  buttons: ['back', 'home', 'app_switch', 'lock', 'volume_up', 'volume_down'],
}

const key = (init: KeyboardEventInit & { key: string }) => new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init })

beforeEach(() => {
  FakeSocket.reset()
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('requestAnimationFrame', (paint: FrameRequestCallback) => { paint(0); return 1 })
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

/** Open a menu and say which rows it shows. */
function rows(el: HTMLElement, menu: string): string[] {
  el.querySelector<HTMLButtonElement>(`[data-smv-menu="${menu}"]`)!.click()
  const shown = [...el.querySelectorAll<HTMLElement>(`[data-smv-menu-panel="${menu}"] [data-smv-item]`)]
    .map((row) => row.querySelector('span')!.textContent!)
  el.querySelector<HTMLButtonElement>(`[data-smv-menu="${menu}"]`)!.click()
  return shown
}

function choose(el: HTMLElement, menu: string, item: string): void {
  el.querySelector<HTMLButtonElement>(`[data-smv-menu="${menu}"]`)!.click()
  el.querySelector<HTMLElement>(`[data-smv-menu-panel="${menu}"] [data-smv-item="${item}"]`)!.click()
}

describe('the viewer around the device', () => {
  it('draws the device in its frame, with the screen as the canvas and the stage parts a host styles', async () => {
    const { $ } = await live()
    const device = $<HTMLElement>('[data-smv-device]')
    expect(device.getAttribute('part')).toBe('device')
    expect(device.contains($('[data-smv-canvas]'))).toBe(true)
    expect($('.smv-tools').getAttribute('part')).toBe('toolbar')
    expect($('[data-smv="devices"]').contains($('[data-smv-name]'))).toBe(true)
    expect($('[data-smv-name]').textContent).toBe('iPhone 17 Pro · iOS 26.5')
    // Laid out once there is a scale to draw at: actual size, here, where the room has no size.
    $<HTMLButtonElement>('[data-smv="zoom-actual"]').click()
    expect(device.querySelector('.smv-body')).not.toBeNull()
  })

  it('keeps the device name on a picker that cannot change it', async () => {
    const { $, view } = await live({}, { ...HELLO, capabilities: VIEW_ONLY.filter((capability) => capability !== 'device_list') })
    const devices = $<HTMLButtonElement>('[data-smv="devices"]')
    expect([devices.hidden, devices.disabled]).toEqual([false, true])
    expect(rows(view.el, 'device')).not.toContain('Choose a device…')
  })

  it('zooms by steps, to actual size and back to fitting, and says how large', async () => {
    const { $, view } = await live()
    const level = $<HTMLElement>('[data-smv-zoom-level]')
    const actual = $<HTMLButtonElement>('[data-smv="zoom-actual"]')
    const fit = $<HTMLButtonElement>('[data-smv="zoom-fit"]')
    // At its actual size from the start, as Simulator.app's Point Accurate: the room has no size to be too small.
    expect([level.textContent, actual.getAttribute('aria-pressed')]).toEqual(['100%', 'true'])
    // The room has no size here: nothing to fit to yet, so it stays as it was drawn.
    fit.click()
    expect([level.textContent, fit.getAttribute('aria-pressed')]).toEqual(['100%', 'true'])
    actual.click()
    expect([level.textContent, actual.getAttribute('aria-pressed'), fit.getAttribute('aria-pressed')]).toEqual(['100%', 'true', 'false'])
    expect($<HTMLElement>('[data-smv-screen]').style.width).toBe('402px')
    $<HTMLButtonElement>('[data-smv="zoom-in"]').click()
    expect([level.textContent, actual.getAttribute('aria-pressed')]).toEqual(['125%', 'false'])
    $<HTMLButtonElement>('[data-smv="zoom-out"]').click()
    $<HTMLButtonElement>('[data-smv="zoom-out"]').click()
    expect(level.textContent).toBe('75%')
    fit.click()
    expect(fit.getAttribute('aria-pressed')).toBe('true')
    // From the View menu, and its shortcuts.
    choose(view.el, 'view', 'zoom-actual')
    expect(level.textContent).toBe('100%')
    $('[data-smv-canvas]').dispatchEvent(key({ key: '=', metaKey: true }))
    expect(level.textContent).toBe('125%')
    $('[data-smv-canvas]').dispatchEvent(key({ key: '-', metaKey: true }))
    expect(level.textContent).toBe('100%')
    $('[data-smv-canvas]').dispatchEvent(key({ key: '0', metaKey: true }))
    expect(fit.getAttribute('aria-pressed')).toBe('true')
    expect(rows(view.el, 'view').slice(0, 4)).toEqual(['Zoom in', 'Zoom out', 'Fit to window', 'Actual size'])
  })

  it('shrinks its actual size to fit a room too small, says so, and keeps the zoom picked for next time', async () => {
    const { $, canvas } = await live()
    const viewport = $<HTMLElement>('[data-smv-viewport]')
    Object.defineProperty(viewport, 'clientWidth', { configurable: true, get: () => 420 })
    Object.defineProperty(viewport, 'clientHeight', { configurable: true, get: () => 600 })
    const level = $<HTMLElement>('[data-smv-zoom-level]')
    canvas.dispatchEvent(key({ key: '1', metaKey: true }))
    expect(level.dataset.reduced).toBe('true')
    expect(level.textContent).toMatch(/^\d+% · fitted$/)
    expect(level.getAttribute('aria-label')).toMatch(/^Actual size, reduced to \d+% to fit the window$/)
    expect($('[data-smv="zoom-actual"]').getAttribute('aria-pressed')).toBe('true')
    expect(JSON.parse(localStorage.getItem('simtrail.viewer')!).zoom).toBe('actual')
    canvas.dispatchEvent(key({ key: '0', metaKey: true }))
    expect([level.dataset.reduced, $('[data-smv="zoom-fit"]').getAttribute('aria-pressed')]).toEqual(['false', 'true'])
    document.body.innerHTML = ''
    // The next viewer starts where the person left it.
    const again = await live()
    expect(again.$('[data-smv="zoom-fit"]').getAttribute('aria-pressed')).toBe('true')
    // Fitted to a room that has no size yet: no scale to say.
    again.$<HTMLButtonElement>('[data-smv="zoom-fit"]').click()
    expect(again.$('[data-smv-zoom-level]').textContent).toBe('')
  })

  it('offers a screenshot once a picture is drawn, and saves it from its button, the Edit menu or Command-S', async () => {
    const created = vi.fn(() => 'blob:shot')
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }))
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const { $, canvas, view } = await live()
    canvas.toBlob = (callback: BlobCallback) => callback(new Blob(['png'], { type: 'image/png' }))
    const shot = $<HTMLButtonElement>('[data-smv="screenshot"]')
    expect(shot.disabled).toBe(true)
    expect(rows(view.el, 'edit')).toEqual([])
    socket().message(frame(TAG_JPEG, 5))
    await flush()
    expect(shot.disabled).toBe(false)
    shot.click()
    await flush()
    expect($('[data-smv-note]').textContent).toMatch(/^Screenshot saved as Screenshot - iPhone 17 Pro - .+\.png\.$/)
    choose(view.el, 'edit', 'screenshot')
    canvas.dispatchEvent(key({ key: 's', metaKey: true }))
    await flush()
    expect(created).toHaveBeenCalledTimes(3)
    // A second picture changes nothing: the device is not laid out again for the same size.
    socket().message(frame(TAG_JPEG, 5))
    await flush()
    expect(rows(view.el, 'edit')).toEqual(['Save screenshot'])
  })

  it('copies a screenshot where the page can put a picture on the clipboard', async () => {
    const write = vi.fn(async () => undefined)
    vi.stubGlobal('ClipboardItem', class { constructor(readonly items: unknown) {} })
    vi.stubGlobal('navigator', { ...navigator, clipboard: { write } })
    const { $, canvas, view } = await live()
    canvas.toBlob = (callback: BlobCallback) => callback(new Blob(['png'], { type: 'image/png' }))
    socket().message(frame(TAG_JPEG, 5))
    await flush()
    expect(rows(view.el, 'edit')).toEqual(['Save screenshot', 'Copy screenshot'])
    canvas.dispatchEvent(key({ key: 'c', metaKey: true, ctrlKey: true }))
    await flush()
    expect(write).toHaveBeenCalledOnce()
    expect($('[data-smv-note]').textContent).toBe('Screenshot copied.')
  })

  it('presses the device from the Device menu and its shortcuts, offering only the buttons the device has', async () => {
    const { $, canvas, view } = await live()
    expect(rows(view.el, 'device')).toEqual([
      'Home', 'Lock', 'Rotate left', 'Rotate right', 'Dark appearance', 'Choose a device…', 'Let the simulator go',
    ])
    canvas.dispatchEvent(key({ key: 'H', metaKey: true, shiftKey: true }))
    canvas.dispatchEvent(key({ key: 'l', metaKey: true }))
    canvas.dispatchEvent(key({ key: 'A', metaKey: true, shiftKey: true }))
    canvas.dispatchEvent(key({ key: 'ArrowLeft', metaKey: true }))
    canvas.dispatchEvent(key({ key: 'ArrowRight', metaKey: true }))
    choose(view.el, 'device', 'home')
    expect(socket().sent).toEqual([
      { type: 'button', name: 'home' }, { type: 'button', name: 'lock' }, { type: 'appearance', mode: 'dark' },
      { type: 'rotate', direction: 'left' }, { type: 'rotate', direction: 'right' }, { type: 'button', name: 'home' },
    ])
    // Their shortcuts are written as Simulator.app writes them.
    $<HTMLButtonElement>('[data-smv-menu="device"]').click()
    expect($('[data-smv-item="rotate-left"] kbd').textContent).toBe('⌘←')
    expect($('[data-smv-item="rotate-right"]').getAttribute('aria-keyshortcuts')).toBe('Meta+ArrowRight')
    $<HTMLButtonElement>('[data-smv-menu="device"]').click()
    // The appearance row says how the device is.
    $<HTMLButtonElement>('[data-smv-menu="device"]').click()
    expect($('[data-smv-item="appearance"]').getAttribute('aria-checked')).toBe('true')
  })

  it('presses an Android device from its frame and offers its own buttons in the Device menu', async () => {
    const { $, view } = await live()
    socket().message({ type: 'status', ...ANDROID })
    $<HTMLButtonElement>('[data-smv="zoom-actual"]').click()
    expect(rows(view.el, 'device').slice(0, 6)).toEqual(['Home', 'Lock', 'Back', 'Recent apps', 'Volume up', 'Volume down'])
    $<HTMLButtonElement>('[data-smv-device] [data-smv-side="volume_up"]').click()
    expect(socket().sent).toEqual([{ type: 'button', name: 'volume_up' }])
    expect($<HTMLElement>('[data-smv-device]').dataset.family).toBe('android')
  })

  it('leaves Command-keys to a macOS app, whose window is shown without a frame', async () => {
    const { canvas, view } = await live({}, { ...HELLO, capabilities: [...HELLO.capabilities, 'input_pointer'] })
    socket().message({ type: 'status', ...DEVICE, kind: 'mac', name: 'Sample', runtime: 'macOS', buttons: [] })
    canvas.dispatchEvent(key({ key: 's', metaKey: true }))
    expect(socket().sent).toEqual([{ type: 'chord', chord: 'cmd+s' }])
    expect(rows(view.el, 'view')).not.toContain('Show device frame')
  })

  it('shows the frame or not, and the theme picked, and keeps both for next time', async () => {
    const first = await live()
    const root = first.view.el
    first.$<HTMLButtonElement>('[data-smv="zoom-actual"]').click()
    expect(root.dataset.theme).toBeUndefined()
    choose(root, 'view', 'frame')
    expect(first.$<HTMLElement>('[data-smv-device]').dataset.framed).toBe('false')
    choose(root, 'view', 'theme-dark')
    expect(root.dataset.theme).toBe('dark')
    first.$<HTMLButtonElement>('[data-smv-menu="view"]').click()
    expect(first.$('[data-smv-item="theme-dark"]').getAttribute('aria-checked')).toBe('true')
    expect(first.$('[data-smv-item="frame"]').getAttribute('aria-checked')).toBe('false')
    first.view.destroy()

    const again = await live()
    again.$<HTMLButtonElement>('[data-smv="zoom-actual"]').click()
    expect(again.view.el.dataset.theme).toBe('dark')
    expect(again.$<HTMLElement>('[data-smv-device]').dataset.framed).toBe('false')
    choose(again.view.el, 'view', 'theme-system')
    expect(again.view.el.dataset.theme).toBeUndefined()
    again.view.destroy()

    // A page's own choice wins over what was kept.
    const told = await live({ theme: 'light', deviceFrame: true })
    told.$<HTMLButtonElement>('[data-smv="zoom-actual"]').click()
    expect(told.view.el.dataset.theme).toBe('light')
    expect(told.$<HTMLElement>('[data-smv-device]').dataset.framed).toBe('true')
  })
})
