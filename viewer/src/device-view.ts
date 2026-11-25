// SPDX-License-Identifier: Apache-2.0
/**
 * The device as the stage shows it: its frame drawn around its screen (`device-frame.ts`), at a zoom a person picks --
 * fitted to the room, or so many CSS pixels a point -- and scrolled when it is larger than the room. The device is
 * drawn turned as it stands (`turns`), its whole box turned about its centre.
 *
 * The screen's box -- the canvas and what is drawn over it -- is always exactly the device's screen shape at that
 * zoom, so the screen's own measuring (`screen-canvas.ts`) and the agent's pointer (`agent-cursor.ts`) need nothing of
 * the frame. The buttons on the frame's edges press the device's own buttons, where the device has them and its
 * connector can press them; the others are drawn only.
 */
import { familyOf, fitScale, frameGeometry, stepZoom, type FrameFamily, type Margins, type Shape } from './device-frame'
import type { Device, PanelButton, Size } from './protocol.generated'

/** Fitted to the room, or so many CSS pixels a point. */
export type Zoom = 'fit' | number

/** Room kept around the device: the toolbar floats below it. */
export const MARGINS: Margins = { side: 16, top: 16, bottom: 72 }

export interface DeviceViewOptions {
  /** The room the device is drawn in, scrolled when the device is larger. */
  viewport: HTMLElement
  /** The device's box, frame and all. */
  device: HTMLElement
  /** The screen's box: the canvas and what is drawn over it. */
  screen: HTMLElement
  /** The screen's size in its own points. */
  units(): Size
  /** Whether this device button can be pressed now. */
  pressable(button: PanelButton): boolean
  press(button: PanelButton): void
  /** Draw the device's body around its screen; true when absent. */
  framed?: boolean
  zoom?: Zoom
  margins?: Margins
  /** How many quarter turns clockwise the device is drawn at; upright when absent. */
  turns?(): number
  /** Told after each layout: the scale may have changed. */
  onLayout?(): void
}

export interface DeviceView {
  /** CSS pixels a point the screen is drawn at; null until the room and the screen have a size. */
  readonly scale: number | null
  readonly zoom: Zoom
  readonly framed: boolean
  readonly family: FrameFamily
  setDevice(device: Pick<Device, 'kind' | 'name'> | null): void
  setFramed(on: boolean): void
  setZoom(zoom: Zoom): void
  /** One zoom step larger or smaller than the scale drawn now. */
  zoomBy(by: 1 | -1): void
  /** Measure the room and the screen again and draw the device to fit. */
  layout(): void
  destroy(): void
}

const px = (value: number) => `${value}px`

function place(el: HTMLElement, shape: Shape | (Omit<Shape, 'radius'> & { radius?: number })): void {
  el.style.left = px(shape.x)
  el.style.top = px(shape.y)
  el.style.width = px(shape.w)
  el.style.height = px(shape.h)
  if (shape.radius !== undefined) el.style.borderRadius = px(shape.radius)
}

export function createDeviceView(options: DeviceViewOptions): DeviceView {
  const { viewport, device, screen } = options
  const margins = options.margins ?? MARGINS
  let family: FrameFamily = familyOf(null)
  let framed = options.framed ?? true
  let zoom: Zoom = options.zoom ?? 'fit'
  let scale: number | null = null
  /** What the drawn parts were made for: they are made again only when it changes, so a focused button keeps focus. */
  let made = ''
  const body = document.createElement('div')
  body.className = 'smv-body'
  body.setAttribute('aria-hidden', 'true')
  const cutout = document.createElement('div')
  cutout.className = 'smv-cutout'
  cutout.setAttribute('aria-hidden', 'true')
  let parts: HTMLElement[] = []

  viewport.style.padding = `${margins.top}px ${margins.side}px ${margins.bottom}px`

  function part(label: string, press: PanelButton | undefined, className: string): HTMLElement {
    if (press && options.pressable(press)) {
      const button = document.createElement('button')
      button.type = 'button'
      button.className = className
      button.dataset.smvSide = press
      button.title = label
      button.setAttribute('aria-label', label)
      button.addEventListener('click', () => options.press(press))
      return button
    }
    const span = document.createElement('span')
    span.className = className
    span.setAttribute('aria-hidden', 'true')
    return span
  }

  function layout(): void {
    const units = options.units()
    if (units.w <= 0 || units.h <= 0) return
    const turns = (((options.turns?.() ?? 0) % 4) + 4) % 4
    const sideways = turns % 2 === 1
    const upright = frameGeometry(family, units, 1, framed).box
    const natural = sideways ? { w: upright.h, h: upright.w } : upright
    const room = { w: viewport.clientWidth, h: viewport.clientHeight }
    const next = zoom === 'fit' ? fitScale(room, natural, margins) : zoom
    if (next === null) return
    scale = next
    const geometry = frameGeometry(family, units, scale, framed)
    device.dataset.family = family
    device.dataset.framed = String(framed && geometry.body !== null)
    device.dataset.turns = String(turns)
    device.toggleAttribute('data-landscape', geometry.landscape)
    device.style.width = px(geometry.box.w)
    device.style.height = px(geometry.box.h)
    // Turned about its centre, and its margins make the room it takes the turned box's: the stage centres that.
    const across = sideways ? (geometry.box.h - geometry.box.w) / 2 : 0
    device.style.transform = turns ? `rotate(${turns * 90}deg)` : ''
    device.style.margin = sideways ? `${px(-across)} ${px(across)}` : ''
    place(screen, geometry.screen)

    const pressable = geometry.sides.map((side) => side.press && options.pressable(side.press))
    const homePressable = geometry.home !== null && options.pressable('home')
    const signature = JSON.stringify([family, framed, geometry.landscape, pressable, homePressable])
    if (signature !== made) {
      made = signature
      for (const old of parts) old.remove()
      parts = geometry.sides.map((side) => part(side.label, side.press, 'smv-side'))
      if (geometry.home) parts.push(part('Home button', 'home', 'smv-home-button'))
      // The side buttons sit under the body's edge, and the screen and what is over it above the body.
      device.prepend(...parts.filter((el) => el.classList.contains('smv-side')), body)
      device.append(cutout, ...parts.filter((el) => el.classList.contains('smv-home-button')))
    }
    body.hidden = geometry.body === null
    if (geometry.body) place(body, geometry.body)
    cutout.hidden = geometry.cutout === null
    if (geometry.cutout) {
      cutout.dataset.kind = geometry.cutout.kind
      place(cutout, geometry.cutout)
    }
    geometry.sides.forEach((side, index) => place(parts[index], side))
    if (geometry.home) place(parts[parts.length - 1], geometry.home)
    options.onLayout?.()
  }

  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(() => layout()) : null
  observer?.observe(viewport)

  return {
    get scale() {
      return scale
    },
    get zoom() {
      return zoom
    },
    get framed() {
      return framed
    },
    get family() {
      return family
    },
    setDevice(next) {
      family = familyOf(next)
      layout()
    },
    setFramed(on) {
      framed = on
      layout()
    },
    setZoom(next) {
      zoom = next
      layout()
    },
    zoomBy(by) {
      if (scale === null) return
      zoom = stepZoom(scale, by)
      layout()
    },
    layout,
    destroy() {
      observer?.disconnect()
    },
  }
}
