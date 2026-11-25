// SPDX-License-Identifier: Apache-2.0
/**
 * The device drawn around its screen: a body, its side buttons, and what sits over the top of the screen -- an iPhone's
 * Dynamic Island or notch, an Android phone's camera hole -- or a Home button below it. Drawn by the viewer with CSS
 * boxes, never from a picture of the device.
 *
 * Everything here is measured in the screen's own points and as shares of its width held upright, then scaled to CSS
 * pixels: the screen inside the frame is always exactly the device's screen shape, so a point on it is still a point
 * on the device (`screen-canvas.ts` measures against the screen box alone). A screen wider than tall is drawn with the
 * device on its side, its top to the left.
 */
import type { PlainKey } from './i18n'
import type { Device, PanelButton, Size } from './protocol.generated'
import type { Rect } from './screen-canvas'

/** The shapes of device the viewer draws. `bare` is the screen alone: a macOS app's window. */
export type FrameFamily = 'island' | 'notch' | 'home' | 'tablet' | 'tablet_home' | 'android' | 'bare'

/** A button on the device's edge: where along that edge it sits and how long it is, as shares of the edge, and the
 * device button it presses, where it is one a person can press from here. */
interface SideSpec {
  edge: 'left' | 'right' | 'top'
  at: number
  length: number
  /** The message that names it. */
  label: PlainKey
  press?: PanelButton
}

interface FamilySpec {
  /** The body around the screen, as shares of the screen's upright width. */
  side: number
  top: number
  bottom: number
  /** The screen's corners and the body's, as shares of the screen's upright width. */
  screenRadius: number
  bodyRadius: number
  cutout: 'island' | 'notch' | 'punch' | null
  /** A Home button's diameter, as a share of the screen's upright width; 0 for none. */
  home: number
  sides: readonly SideSpec[]
}

const VOLUME_UP = 'button.volume_up'
const VOLUME_DOWN = 'button.volume_down'
const SIDE = 'frame.side'

const SPECS: Record<FrameFamily, FamilySpec> = {
  island: {
    side: 0.045, top: 0.045, bottom: 0.045, screenRadius: 0.145, bodyRadius: 0.19, cutout: 'island', home: 0,
    sides: [
      { edge: 'left', at: 0.185, length: 0.05, label: 'frame.action' },
      { edge: 'left', at: 0.265, length: 0.095, label: VOLUME_UP, press: 'volume_up' },
      { edge: 'left', at: 0.375, length: 0.095, label: VOLUME_DOWN, press: 'volume_down' },
      { edge: 'right', at: 0.28, length: 0.15, label: SIDE, press: 'lock' },
    ],
  },
  notch: {
    side: 0.045, top: 0.045, bottom: 0.045, screenRadius: 0.12, bodyRadius: 0.165, cutout: 'notch', home: 0,
    sides: [
      { edge: 'left', at: 0.17, length: 0.04, label: 'frame.ring' },
      { edge: 'left', at: 0.25, length: 0.085, label: VOLUME_UP, press: 'volume_up' },
      { edge: 'left', at: 0.35, length: 0.085, label: VOLUME_DOWN, press: 'volume_down' },
      { edge: 'right', at: 0.27, length: 0.14, label: SIDE, press: 'lock' },
    ],
  },
  home: {
    side: 0.075, top: 0.29, bottom: 0.29, screenRadius: 0, bodyRadius: 0.16, cutout: null, home: 0.17,
    sides: [
      { edge: 'left', at: 0.12, length: 0.035, label: 'frame.ring' },
      { edge: 'left', at: 0.19, length: 0.06, label: VOLUME_UP, press: 'volume_up' },
      { edge: 'left', at: 0.27, length: 0.06, label: VOLUME_DOWN, press: 'volume_down' },
      { edge: 'right', at: 0.19, length: 0.075, label: SIDE, press: 'lock' },
    ],
  },
  tablet: {
    side: 0.03, top: 0.03, bottom: 0.03, screenRadius: 0.024, bodyRadius: 0.054, cutout: null, home: 0,
    sides: [
      { edge: 'top', at: 0.8, length: 0.07, label: 'frame.top', press: 'lock' },
      { edge: 'right', at: 0.1, length: 0.06, label: VOLUME_UP, press: 'volume_up' },
      { edge: 'right', at: 0.18, length: 0.06, label: VOLUME_DOWN, press: 'volume_down' },
    ],
  },
  tablet_home: {
    side: 0.07, top: 0.13, bottom: 0.13, screenRadius: 0, bodyRadius: 0.07, cutout: null, home: 0.065,
    sides: [
      { edge: 'top', at: 0.83, length: 0.07, label: 'frame.top', press: 'lock' },
      { edge: 'right', at: 0.12, length: 0.055, label: VOLUME_UP, press: 'volume_up' },
      { edge: 'right', at: 0.19, length: 0.055, label: VOLUME_DOWN, press: 'volume_down' },
    ],
  },
  android: {
    side: 0.035, top: 0.035, bottom: 0.035, screenRadius: 0.075, bodyRadius: 0.11, cutout: 'punch', home: 0,
    sides: [
      { edge: 'right', at: 0.17, length: 0.07, label: VOLUME_UP, press: 'volume_up' },
      { edge: 'right', at: 0.245, length: 0.07, label: VOLUME_DOWN, press: 'volume_down' },
      { edge: 'right', at: 0.36, length: 0.08, label: 'frame.power', press: 'lock' },
    ],
  },
  bare: { side: 0, top: 0, bottom: 0, screenRadius: 0, bodyRadius: 0, cutout: null, home: 0, sides: [] },
}

/** How far a side button stands out of the body, as a share of the screen's upright width. */
const BUTTON_DEPTH = 0.012

/** The shape of device a device is drawn as, from what it is and its name. A device the viewer does not know by name
 * is drawn as a current one of its kind. */
export function familyOf(device: Pick<Device, 'kind' | 'name'> | null): FrameFamily {
  if (device?.kind === 'mac') return 'bare'
  if (device?.kind === 'android') return 'android'
  const name = device?.name ?? ''
  if (/iPad/i.test(name)) {
    const generation = /iPad \((\d+)(?:st|nd|rd|th) generation\)/i.exec(name)
    const homeButton = (generation !== null && Number(generation[1]) <= 9)
      || /iPad (mini|Air) \((?:[1-5])(?:st|nd|rd|th) generation\)/i.test(name)
    return homeButton ? 'tablet_home' : 'tablet'
  }
  if (/iPhone (SE|[5-8])\b/i.test(name)) return 'home'
  if (/iPhone X/i.test(name) || /iPhone 16e/i.test(name)) return 'notch'
  const model = /iPhone (\d+)/i.exec(name)
  if (model) {
    const number = Number(model[1])
    if (number <= 13 || (number === 14 && !/Pro/i.test(name))) return 'notch'
  }
  return 'island'
}

export interface Shape extends Rect {
  radius: number
}

export interface SideButton extends Rect {
  /** The message that names it. */
  label: PlainKey
  press?: PanelButton
}

export interface FrameGeometry {
  family: FrameFamily
  /** The screen is wider than tall, and the device is drawn on its side. */
  landscape: boolean
  /** Everything drawn, side buttons included, in CSS pixels. */
  box: Size
  /** The device's body; null when only the screen is drawn. */
  body: Shape | null
  screen: Shape
  /** What sits over the top of the screen. */
  cutout: (Shape & { kind: 'island' | 'notch' | 'punch' }) | null
  /** A Home button below the screen. */
  home: Shape | null
  sides: SideButton[]
}

/** Turn a box laid out upright in a `width` wide box onto its side, the device's top to the left. */
function turn<T extends Rect>(rect: T, width: number): T {
  return { ...rect, x: rect.y, y: width - rect.x - rect.w, w: rect.h, h: rect.w }
}

function scaled<T extends Rect>(rect: T, scale: number, keys: ReadonlyArray<keyof T> = []): T {
  const out = { ...rect, x: rect.x * scale, y: rect.y * scale, w: rect.w * scale, h: rect.h * scale }
  for (const key of keys) (out as Record<keyof T, unknown>)[key] = (rect[key] as number) * scale
  return out
}

/**
 * Where everything is drawn for a screen of `units` points shown at `scale` CSS pixels a point. Without the body
 * (`body: false`) the screen keeps its corners and what sits over it, as the device's own screen has them.
 */
export function frameGeometry(family: FrameFamily, units: Size, scale: number, body = true): FrameGeometry {
  const spec = SPECS[family]
  const landscape = units.w > units.h
  const pw = landscape ? units.h : units.w
  const ph = landscape ? units.w : units.h
  const drawn = body && family !== 'bare'
  const side = drawn ? spec.side * pw : 0
  const top = drawn ? spec.top * pw : 0
  const bottom = drawn ? spec.bottom * pw : 0
  const depth = drawn ? BUTTON_DEPTH * pw : 0
  const bw = pw + 2 * side
  const bh = ph + top + bottom
  const width = bw + 2 * depth
  const height = bh + 2 * depth
  const screen: Shape = { x: depth + side, y: depth + top, w: pw, h: ph, radius: spec.screenRadius * pw }
  const bodyShape: Shape | null = drawn ? { x: depth, y: depth, w: bw, h: bh, radius: spec.bodyRadius * pw } : null
  let cutout: FrameGeometry['cutout'] = null
  if (spec.cutout === 'island') {
    const w = 0.31 * pw
    const h = 0.092 * pw
    cutout = { kind: 'island', x: screen.x + (pw - w) / 2, y: screen.y + 0.028 * pw, w, h, radius: h / 2 }
  } else if (spec.cutout === 'notch') {
    const w = 0.53 * pw
    cutout = { kind: 'notch', x: screen.x + (pw - w) / 2, y: screen.y, w, h: 0.075 * pw, radius: 0.05 * pw }
  } else if (spec.cutout === 'punch') {
    const d = 0.033 * pw
    cutout = { kind: 'punch', x: screen.x + (pw - d) / 2, y: screen.y + 0.03 * pw, w: d, h: d, radius: d / 2 }
  }
  const homeSize = spec.home * pw
  const home: Shape | null = drawn && homeSize > 0
    ? { x: depth + (bw - homeSize) / 2, y: screen.y + ph + (bottom - homeSize) / 2, w: homeSize, h: homeSize, radius: homeSize / 2 }
    : null
  const sides: SideButton[] = drawn ? spec.sides.map(({ edge, at, length, label, press }) => {
    const rect = edge === 'top'
      ? { x: depth + at * bw, y: 0, w: length * bw, h: 2 * depth }
      : { x: edge === 'left' ? 0 : bw, y: depth + at * bh, w: 2 * depth, h: length * bh }
    return press ? { ...rect, label, press } : { ...rect, label }
  }) : []

  const place = <T extends Rect>(rect: T, keys: ReadonlyArray<keyof T> = []) =>
    scaled(landscape ? turn(rect, width) : rect, scale, keys)
  return {
    family,
    landscape,
    box: landscape ? { w: height * scale, h: width * scale } : { w: width * scale, h: height * scale },
    body: bodyShape && place(bodyShape, ['radius']),
    screen: place(screen, ['radius']),
    cutout: cutout && place(cutout, ['radius']),
    home: home && place(home, ['radius']),
    sides: sides.map((button) => place(button)),
  }
}

/** The zoom steps a person walks with Zoom in and Zoom out, as CSS pixels a point. */
export const ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 1, 1.25, 1.5, 2, 3] as const
export const ZOOM_MIN = ZOOM_STEPS[0]
export const ZOOM_MAX = ZOOM_STEPS[ZOOM_STEPS.length - 1]

/** The next zoom step from `scale` -- larger or smaller -- and the last one when there is none further. */
export function stepZoom(scale: number, by: 1 | -1): number {
  if (by > 0) return ZOOM_STEPS.find((step) => step > scale + 0.001) ?? ZOOM_MAX
  return [...ZOOM_STEPS].reverse().find((step) => step < scale - 0.001) ?? ZOOM_MIN
}

/** Room kept clear around the device: at its sides, above it, and below it for the toolbar that floats there. */
export interface Margins {
  side: number
  top: number
  bottom: number
}

/** The scale at which a device `natural` points large fits whole in `room`, inside `margins`; null while the room has
 * no size to fit into. */
export function fitScale(room: Size, natural: Size, margins: Margins): number | null {
  const w = room.w - 2 * margins.side
  const h = room.h - margins.top - margins.bottom
  if (room.w <= 0 || room.h <= 0 || natural.w <= 0 || natural.h <= 0) return null
  return Math.max(0.05, Math.min(w / natural.w, h / natural.h))
}
