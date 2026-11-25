// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest'

import { english } from './i18n'
import { familyOf, fitScale, frameGeometry, stepZoom, ZOOM_MAX, ZOOM_MIN, type FrameFamily } from './device-frame'

const PHONE = { w: 402, h: 874 }
const named = (name: string, kind: 'simulator' | 'physical' | 'android' | 'mac' = 'simulator') => familyOf({ name, kind })

describe('familyOf', () => {
  it('draws each device as the shape it has', () => {
    expect(named('iPhone 17 Pro')).toBe('island')
    expect(named('iPhone 15')).toBe('island')
    expect(named('iPhone 14 Pro Max')).toBe('island')
    expect(named('iPhone Air')).toBe('island')
    expect(named('iPhone 14')).toBe('notch')
    expect(named('iPhone 14 Plus')).toBe('notch')
    expect(named('iPhone 13 mini')).toBe('notch')
    expect(named('iPhone XS')).toBe('notch')
    expect(named('iPhone 16e')).toBe('notch')
    expect(named('iPhone SE (3rd generation)')).toBe('home')
    expect(named('iPhone 8 Plus')).toBe('home')
    expect(named('iPad Pro 13-inch (M5)')).toBe('tablet')
    expect(named('iPad (10th generation)')).toBe('tablet')
    expect(named('iPad (9th generation)')).toBe('tablet_home')
    expect(named('iPad mini (5th generation)')).toBe('tablet_home')
    expect(named('iPad Air (3rd generation)')).toBe('tablet_home')
    expect(named('iPad mini (A17 Pro)')).toBe('tablet')
    expect(named('Pixel 9', 'android')).toBe('android')
    expect(named('TextEdit', 'mac')).toBe('bare')
  })

  it('draws a device it does not know by name as a current iPhone', () => {
    expect(named("Someone's phone", 'physical')).toBe('island')
    expect(familyOf(null)).toBe('island')
  })
})

describe('frameGeometry', () => {
  const families: FrameFamily[] = ['island', 'notch', 'home', 'tablet', 'tablet_home', 'android', 'bare']

  it('keeps the screen exactly the device screen shape, at the scale asked, whatever the frame', () => {
    for (const family of families) {
      for (const scale of [0.5, 1, 1.75]) {
        const { screen, box } = frameGeometry(family, PHONE, scale)
        expect(screen.w).toBeCloseTo(PHONE.w * scale)
        expect(screen.h).toBeCloseTo(PHONE.h * scale)
        // Inside the box drawn.
        expect(screen.x).toBeGreaterThanOrEqual(0)
        expect(screen.y + screen.h).toBeLessThanOrEqual(box.h + 1e-9)
      }
    }
  })

  it('draws an iPhone with its island over the top of its screen, and buttons out of its edges', () => {
    const geometry = frameGeometry('island', PHONE, 1)
    const { body, screen, cutout, sides, box } = geometry
    expect(body).not.toBeNull()
    expect(cutout?.kind).toBe('island')
    // Centred, inside the screen's top.
    expect(cutout!.x + cutout!.w / 2).toBeCloseTo(screen.x + screen.w / 2)
    expect(cutout!.y).toBeGreaterThan(screen.y)
    expect(cutout!.radius).toBeCloseTo(cutout!.h / 2)
    // The body is round-cornered beyond the screen's corners, which are rounded too.
    expect(body!.radius).toBeGreaterThan(screen.radius)
    expect(screen.radius).toBeGreaterThan(0)
    // Each side button stands out of the body by its own depth, on the side it belongs to.
    const left = sides.filter((side) => side.x < body!.x)
    const right = sides.filter((side) => side.x + side.w > body!.x + body!.w)
    expect(left.map((side) => english(side.label))).toEqual(['Action button', 'Volume up', 'Volume down'])
    expect(right.map((side) => side.press)).toEqual(['lock'])
    expect(left[0].press).toBeUndefined()
    expect(box.w).toBeCloseTo(body!.w + 2 * body!.x)
    expect(geometry.home).toBeNull()
    expect(geometry.landscape).toBe(false)
  })

  it('draws a notch at the screen top, a Home button under an older screen, and a camera hole on Android', () => {
    const notch = frameGeometry('notch', PHONE, 1)
    expect(notch.cutout).toMatchObject({ kind: 'notch', y: notch.screen.y })
    const home = frameGeometry('home', { w: 375, h: 667 }, 1)
    expect(home.cutout).toBeNull()
    expect(home.screen.radius).toBe(0)
    expect(home.home!.y).toBeGreaterThan(home.screen.y + home.screen.h)
    expect(home.home!.x + home.home!.w / 2).toBeCloseTo(home.screen.x + home.screen.w / 2)
    const android = frameGeometry('android', { w: 412, h: 915 }, 1)
    expect(android.cutout).toMatchObject({ kind: 'punch' })
    expect(android.sides.map((side) => side.press)).toEqual(['volume_up', 'volume_down', 'lock'])
    const tablet = frameGeometry('tablet', { w: 820, h: 1180 }, 1)
    // The top button lies along the top edge, out of it.
    expect(tablet.sides[0]).toMatchObject({ y: 0, press: 'lock' })
    expect(english(tablet.sides[0].label)).toBe('Top button')
    expect(tablet.sides[0].w).toBeGreaterThan(tablet.sides[0].h)
    expect(frameGeometry('tablet_home', { w: 768, h: 1024 }, 1).home).not.toBeNull()
  })

  it('draws the screen alone for a macOS app, and without its body when asked, keeping the screen shape', () => {
    const mac = frameGeometry('bare', { w: 1280, h: 800 }, 1)
    expect([mac.body, mac.cutout, mac.home, mac.sides]).toEqual([null, null, null, []])
    expect(mac.screen).toMatchObject({ x: 0, y: 0 })
    const bare = frameGeometry('island', PHONE, 2, false)
    expect(bare.body).toBeNull()
    expect(bare.sides).toEqual([])
    expect(bare.box).toEqual({ w: PHONE.w * 2, h: PHONE.h * 2 })
    expect(bare.screen).toMatchObject({ x: 0, y: 0, w: PHONE.w * 2, h: PHONE.h * 2 })
    // The device's own screen keeps its corners and its island.
    expect(bare.screen.radius).toBeGreaterThan(0)
    expect(bare.cutout?.kind).toBe('island')
    expect(frameGeometry('home', PHONE, 1, false).home).toBeNull()
  })

  it('lays a screen wider than tall on its side, top to the left', () => {
    const upright = frameGeometry('island', PHONE, 1)
    const turned = frameGeometry('island', { w: PHONE.h, h: PHONE.w }, 1)
    expect(turned.landscape).toBe(true)
    expect(turned.box).toEqual({ w: upright.box.h, h: upright.box.w })
    expect(turned.screen.w).toBeCloseTo(PHONE.h)
    expect(turned.screen.h).toBeCloseTo(PHONE.w)
    // The island, at the device's top, is now at its left, centred top to bottom.
    expect(turned.cutout!.x).toBeLessThan(turned.screen.x + 60)
    expect(turned.cutout!.y + turned.cutout!.h / 2).toBeCloseTo(turned.screen.y + turned.screen.h / 2)
    expect(turned.cutout!.h).toBeCloseTo(upright.cutout!.w)
    // Turned to the left, the right edge is the top one and the left edge the bottom one.
    const side = turned.sides.find((button) => button.press === 'lock')!
    expect(side.y).toBeCloseTo(0)
    expect(side.w).toBeGreaterThan(side.h)
    const volume = turned.sides.find((button) => button.press === 'volume_up')!
    expect(volume.y + volume.h).toBeCloseTo(turned.box.h)
  })
})

describe('zoom', () => {
  it('steps through the zoom steps, and stops at either end', () => {
    expect(stepZoom(1, 1)).toBe(1.25)
    expect(stepZoom(1, -1)).toBe(0.75)
    expect(stepZoom(0.8, 1)).toBe(1)
    expect(stepZoom(0.8, -1)).toBe(0.75)
    expect(stepZoom(ZOOM_MAX, 1)).toBe(ZOOM_MAX)
    expect(stepZoom(ZOOM_MIN, -1)).toBe(ZOOM_MIN)
    expect(stepZoom(10, -1)).toBe(ZOOM_MAX)
  })

  it('fits the device whole inside the room, its margins kept', () => {
    const margins = { side: 10, top: 20, bottom: 80 }
    expect(fitScale({ w: 1000, h: 500 }, { w: 400, h: 800 }, margins)).toBeCloseTo(0.5)
    expect(fitScale({ w: 220, h: 2000 }, { w: 400, h: 800 }, margins)).toBeCloseTo(0.5)
    expect(fitScale({ w: 0, h: 500 }, { w: 400, h: 800 }, margins)).toBeNull()
    expect(fitScale({ w: 500, h: 500 }, { w: 0, h: 0 }, margins)).toBeNull()
    // A room too small for any device still draws one, tiny.
    expect(fitScale({ w: 10, h: 10 }, { w: 400, h: 800 }, margins)).toBe(0.05)
  })
})
