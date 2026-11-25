// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest'

import { frameGeometry } from './device-frame'
import { createDeviceView, MARGINS, type DeviceViewOptions } from './device-view'
import type { PanelButton } from './protocol.generated'
import { framePoint } from './screen-canvas'

const UNITS = { w: 402, h: 874 }

function rig(overrides: Partial<DeviceViewOptions> = {}, room = { w: 800, h: 1100 }) {
  const viewport = document.createElement('div')
  const device = document.createElement('div')
  const screen = document.createElement('div')
  device.appendChild(screen)
  viewport.appendChild(device)
  document.body.appendChild(viewport)
  Object.defineProperty(viewport, 'clientWidth', { configurable: true, get: () => room.w })
  Object.defineProperty(viewport, 'clientHeight', { configurable: true, get: () => room.h })
  const press = vi.fn()
  const view = createDeviceView({
    viewport, device, screen, units: () => UNITS, pressable: () => true, press, ...overrides,
  })
  view.setDevice({ kind: 'simulator', name: 'iPhone 17 Pro' })
  return { viewport, device, screen, view, press, room }
}

const sizeOf = (el: HTMLElement) => ({
  x: parseFloat(el.style.left), y: parseFloat(el.style.top), w: parseFloat(el.style.width), h: parseFloat(el.style.height),
})

afterEach(() => {
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

describe('createDeviceView', () => {
  it('fits the device, frame and all, inside the room and its margins, and keeps room for the toolbar', () => {
    const { viewport, device, screen, view } = rig({ zoom: 'fit' })
    const natural = frameGeometry('island', UNITS, 1).box
    const scale = Math.min((800 - 2 * MARGINS.side) / natural.w, (1100 - MARGINS.top - MARGINS.bottom) / natural.h)
    expect(view.scale).toBeCloseTo(scale)
    expect(view.zoom).toBe('fit')
    expect(parseFloat(device.style.height)).toBeCloseTo(natural.h * scale, 1)
    expect(viewport.style.padding).toBe(`${MARGINS.top}px ${MARGINS.side}px ${MARGINS.bottom}px`)
    expect(device.dataset).toMatchObject({ family: 'island', framed: 'true' })
    // The screen's box keeps the device's screen shape.
    const box = sizeOf(screen)
    expect(box.w / box.h).toBeCloseTo(UNITS.w / UNITS.h, 3)
    expect(screen.style.borderRadius).not.toBe('')
    expect(device.querySelector<HTMLElement>('.smv-cutout')!.dataset.kind).toBe('island')
    expect(device.querySelector<HTMLElement>('.smv-body')!.hidden).toBe(false)
  })

  it('maps a point on the screen to the same device point at any zoom, framed or not', () => {
    const { screen, view } = rig()
    for (const [zoom, framed] of [['fit', true], [1, true], [2, true], [0.5, false], ['fit', false]] as const) {
      view.setFramed(framed)
      view.setZoom(zoom)
      // Where the screen's box lies on the page: the device's own left and top, plus the screen's inside it.
      const box = sizeOf(screen)
      const page = { left: 100 + box.x, top: 50 + box.y, width: box.w, height: box.h }
      const corner = framePoint({ clientX: page.left, clientY: page.top }, page, UNITS, 'contain')
      const far = framePoint({ clientX: page.left + box.w, clientY: page.top + box.h }, page, UNITS, 'contain')
      const mid = framePoint({ clientX: page.left + box.w * 0.25, clientY: page.top + box.h * 0.75 }, page, UNITS, 'contain')
      expect([corner.x, corner.y, corner.inside]).toEqual([0, 0, true])
      expect(far.x).toBeCloseTo(UNITS.w, 1)
      expect(far.y).toBeCloseTo(UNITS.h, 1)
      expect(mid.nx).toBeCloseTo(0.25, 3)
      expect(mid.ny).toBeCloseTo(0.75, 3)
      // A point on the frame, left of the screen, is not on the device's screen.
      expect(framePoint({ clientX: page.left - 4, clientY: page.top + 10 }, page, UNITS, 'contain').inside).toBe(false)
    }
  })

  it('zooms by steps from what it shows, to a scale asked, and back to fitting', () => {
    const onLayout = vi.fn()
    const { view, screen } = rig({ onLayout })
    view.setZoom(1)
    expect(view.scale).toBe(1)
    expect(sizeOf(screen).w).toBeCloseTo(UNITS.w)
    view.zoomBy(1)
    expect([view.zoom, view.scale]).toEqual([1.25, 1.25])
    view.zoomBy(-1)
    view.zoomBy(-1)
    expect(view.scale).toBe(0.75)
    view.setZoom('fit')
    expect(view.zoom).toBe('fit')
    expect(onLayout).toHaveBeenCalled()
  })

  it('draws the device at its actual size by default, a point a CSS pixel, as Point Accurate in Simulator.app', () => {
    const { screen, view } = rig({}, { w: 1600, h: 1400 })
    expect([view.zoom, view.scale, view.reduced]).toEqual(['actual', 1, false])
    expect(sizeOf(screen).w).toBeCloseTo(402)
    expect(sizeOf(screen).h).toBeCloseTo(874)
  })

  it('draws its actual size smaller in a room too small for it, and says it is reduced', () => {
    const { view } = rig({}, { w: 600, h: 700 })
    const natural = frameGeometry('island', UNITS, 1).box
    const fitted = Math.min((600 - 2 * MARGINS.side) / natural.w, (700 - MARGINS.top - MARGINS.bottom) / natural.h)
    expect(view.zoom).toBe('actual')
    expect(view.scale).toBeCloseTo(fitted)
    expect(view.reduced).toBe(true)
    view.setZoom('fit')
    expect(view.reduced).toBe(false)
  })

  it('draws the device turned as it stands, taking the room of its turned box, and fits that box', () => {
    let turns = 1
    const { device, view } = rig({ turns: () => turns, zoom: 'fit' }, { w: 1100, h: 800 })
    const natural = frameGeometry('island', UNITS, 1).box
    const fitted = Math.min((1100 - 2 * MARGINS.side) / natural.h, (800 - MARGINS.top - MARGINS.bottom) / natural.w)
    expect(view.scale).toBeCloseTo(fitted)
    expect(device.style.transform).toBe('rotate(90deg)')
    expect(device.dataset.turns).toBe('1')
    const w = parseFloat(device.style.width)
    const h = parseFloat(device.style.height)
    // Its margins give it the turned box's room: wider than tall.
    expect(device.style.margin).toBe(`${-(h - w) / 2}px ${(h - w) / 2}px`)
    turns = 2
    view.layout()
    expect([device.style.transform, device.style.margin]).toEqual(['rotate(180deg)', ''])
    turns = 0
    view.layout()
    expect([device.style.transform, device.dataset.turns]).toEqual(['', '0'])
  })

  it('lays nothing out before the room or the screen has a size', () => {
    const empty = rig({ zoom: 'fit' }, { w: 0, h: 0 })
    expect(empty.view.scale).toBeNull()
    empty.view.zoomBy(1)
    expect(empty.view.zoom).toBe('fit')
    // Its actual size needs no room to be measured: it is only made smaller in a room that has a size.
    expect(rig({}, { w: 0, h: 0 }).view.scale).toBe(1)
    const unsized = rig({ units: () => ({ w: 0, h: 0 }) })
    expect(unsized.view.scale).toBeNull()
    expect(unsized.device.style.width).toBe('')
  })

  it('makes the buttons on its edges press the device, only those it can press, and draws the others', () => {
    let pressable = new Set<PanelButton>(['lock'])
    const { device, press, view } = rig({ pressable: (button) => pressable.has(button) })
    const buttons = [...device.querySelectorAll<HTMLButtonElement>('button.smv-side')]
    expect(buttons.map((button) => [button.dataset.smvSide, button.getAttribute('aria-label')])).toEqual([['lock', 'Side button']])
    expect(device.querySelectorAll('span.smv-side[aria-hidden="true"]').length).toBe(3)
    buttons[0].click()
    expect(press).toHaveBeenCalledWith('lock')
    // Laid out again as it was: the same button, so focus on it stays.
    view.layout()
    expect(device.querySelector('button.smv-side')).toBe(buttons[0])
    pressable = new Set(['lock', 'volume_up', 'volume_down'])
    view.layout()
    expect(device.querySelectorAll('button.smv-side').length).toBe(3)
  })

  it('draws a Home button that presses Home, under an older iPhone screen', () => {
    const { device, press, view } = rig()
    view.setDevice({ kind: 'simulator', name: 'iPhone SE (3rd generation)' })
    expect(view.family).toBe('home')
    const home = device.querySelector<HTMLButtonElement>('button.smv-home-button')!
    expect(home.getAttribute('aria-label')).toBe('Home button')
    home.click()
    expect(press).toHaveBeenCalledWith('home')
    expect(device.querySelector<HTMLElement>('.smv-cutout')!.hidden).toBe(true)
  })

  it('draws the screen alone without its frame, and a macOS app always so', () => {
    const { device, view } = rig()
    view.setFramed(false)
    expect(view.framed).toBe(false)
    expect(device.dataset.framed).toBe('false')
    expect(device.querySelector<HTMLElement>('.smv-body')!.hidden).toBe(true)
    expect(device.querySelectorAll('.smv-side').length).toBe(0)
    view.setFramed(true)
    view.setDevice({ kind: 'mac', name: 'TextEdit' })
    expect(device.dataset).toMatchObject({ family: 'bare', framed: 'false' })
  })

  it('draws a screen wider than tall on its side', () => {
    const { device } = rig({ units: () => ({ w: 874, h: 402 }) })
    expect(device.hasAttribute('data-landscape')).toBe(true)
    expect(parseFloat(device.style.width)).toBeGreaterThan(parseFloat(device.style.height))
  })

  it('fits again whenever the room changes size, and stops watching once destroyed', () => {
    const observers: Array<{ callback: () => void; disconnect: ReturnType<typeof vi.fn> }> = []
    vi.stubGlobal('ResizeObserver', class {
      callback: () => void
      disconnect = vi.fn()
      constructor(callback: () => void) {
        this.callback = callback
        observers.push(this)
      }
      observe() {}
    })
    const { view, room } = rig()
    const before = view.scale!
    room.w = 400
    observers[0].callback()
    expect(view.scale!).toBeLessThan(before)
    view.destroy()
    expect(observers[0].disconnect).toHaveBeenCalled()
  })
})
