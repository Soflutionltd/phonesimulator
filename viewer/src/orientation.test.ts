// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FakeSocket } from '../test-support/fake-socket'
import { DEVICE, HELLO, live, socket } from '../test-support/viewer-harness'
import { TURNS, quarterTurns, unturned } from './orientation'
import { createScreenCanvas, framePoint } from './screen-canvas'

beforeEach(() => {
  FakeSocket.reset()
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('requestAnimationFrame', (paint: FrameRequestCallback) => { paint(0); return 1 })
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ drawImage: vi.fn() })) as never
})

afterEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/** A 100 by 200 screen drawn turned: its bounding box on the page, at (0, 0). */
const SIZE = { w: 100, h: 200 }
const box = (turns: number) => turns % 2 ? { left: 0, top: 0, width: 200, height: 100 } : { left: 0, top: 0, width: 100, height: 200 }
/** Where a point of the screen, as shares of it, lands on the page once the screen is turned. */
function onPage(nx: number, ny: number, turns: number): { clientX: number; clientY: number } {
  const [x, y] = [nx * SIZE.w - SIZE.w / 2, ny * SIZE.h - SIZE.h / 2]
  const [dx, dy] = turns === 1 ? [-y, x] : turns === 2 ? [-x, -y] : turns === 3 ? [y, -x] : [x, y]
  const rect = box(turns)
  return { clientX: rect.width / 2 + dx, clientY: rect.height / 2 + dy }
}

describe('orientation', () => {
  it('counts quarter turns clockwise, and reads an orientation an older server does not send as upright', () => {
    expect(TURNS.map(quarterTurns)).toEqual([0, 1, 2, 3])
    expect(quarterTurns(undefined)).toBe(0)
    expect(quarterTurns(null)).toBe(0)
    // A way a newer server names that this viewer does not know: drawn upright rather than guessed.
    expect(quarterTurns('face_up' as never)).toBe(0)
  })

  it('turns a pointer on a turned screen back onto the same point of the portrait screen, whichever way', () => {
    for (const turns of [0, 1, 2, 3]) {
      for (const [nx, ny] of [[0.1, 0.2], [0.9, 0.05], [0.5, 0.5], [0.25, 0.75]]) {
        const back = unturned(onPage(nx, ny, turns), box(turns), SIZE, turns)
        const point = framePoint(back, back.box, SIZE, 'contain')
        expect(point.nx).toBeCloseTo(nx, 6)
        expect(point.ny).toBeCloseTo(ny, 6)
        expect(point.inside).toBe(true)
      }
    }
  })

  it('measures a pointer on the canvas against the screen as it is turned', () => {
    let turns = 1
    const canvas = document.createElement('canvas')
    canvas.width = 100
    canvas.height = 200
    Object.defineProperty(canvas, 'offsetWidth', { get: () => 100 })
    Object.defineProperty(canvas, 'offsetHeight', { get: () => 200 })
    canvas.getBoundingClientRect = () => ({ ...box(turns), right: 0, bottom: 0, x: 0, y: 0, toJSON: () => null })
    const screen = createScreenCanvas(canvas, { turns: () => turns })
    // The screen's top left corner, turned a quarter clockwise, is at the page's top right.
    const corner = screen.point({ clientX: 199, clientY: 1 })
    expect([corner.nx, corner.ny]).toEqual([0.01, 0.005])
    turns = 0
    expect(screen.point({ clientX: 50, clientY: 100 }).nx).toBe(0.5)
  })
})

describe('turning the device from the viewer', () => {
  it('offers Rotate left and Rotate right where the server can turn a simulator, and sends them', async () => {
    const { $ } = await live()
    const left = $<HTMLButtonElement>('[data-smv="rotate-left"]')
    const right = $<HTMLButtonElement>('[data-smv="rotate-right"]')
    expect([left.hidden, right.hidden]).toEqual([false, false])
    left.click()
    right.click()
    expect(socket().sent).toEqual([{ type: 'rotate', direction: 'left' }, { type: 'rotate', direction: 'right' }])
    socket().message({ type: 'status', ...DEVICE, kind: 'physical', connection: 'usb' })
    expect(left.hidden).toBe(true)
  })

  it('offers neither through a connector that cannot turn the device', async () => {
    const { $ } = await live({}, { ...HELLO, capabilities: HELLO.capabilities.filter((each) => each !== 'rotate') })
    expect($<HTMLButtonElement>('[data-smv="rotate-left"]').hidden).toBe(true)
  })

  it('draws the device turned as the server says it stands', async () => {
    const { $ } = await live()
    // At a zoom that needs no room to be measured.
    $<HTMLButtonElement>('[data-smv="zoom-actual"]').click()
    const device = $<HTMLElement>('[data-smv-device]')
    expect(device.style.transform).toBe('')
    socket().message({ type: 'status', ...DEVICE, orientation: 'landscape_right' })
    expect([device.style.transform, device.dataset.turns]).toEqual(['rotate(270deg)', '3'])
    socket().message({ type: 'status', ...DEVICE, orientation: 'portrait' })
    expect(device.style.transform).toBe('')
  })

  it('draws the agent on the screen where it acts, on a device drawn on its side too', async () => {
    const { $ } = await live()
    // On its side, the overlay's box on the page is its own turned: 874 wide, 402 tall.
    $<HTMLElement>('[data-smv-overlay]').getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 874, height: 402, right: 874, bottom: 402, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect
    socket().message({ type: 'status', ...DEVICE, orientation: 'landscape_left' })
    socket().message({
      type: 'agent', id: 'a1', phase: 'intent', agent: { key: 'k', title: 'Claude Code' },
      gesture: { kind: 'tap', duration_ms: 80, points: [[0.25, 0.75]] }, label: '', caption: '', lead_ms: 0,
      pointer: true,
    })
    // In the screen's own points, as the overlay turns with the device.
    expect($<HTMLElement>('[data-ac-pointer]').style.transform).toBe('translate(100.5px, 655.5px)')
  })
})
