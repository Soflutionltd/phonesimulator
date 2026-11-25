// SPDX-License-Identifier: Apache-2.0
/**
 * Which way the device is turned, and a pointer on a screen drawn turned brought back onto the device's own screen.
 *
 * A device's screen does not turn: its frames stay portrait, an app turned drawn sideways in them. So the viewer draws
 * the whole device turned -- as Simulator.app does after Device > Rotate -- and a touch on it is turned back before it
 * is measured, so it lands on the point of the portrait screen under the finger.
 */
import type { Orientation } from './protocol.generated'

/** The four ways, a quarter clockwise each from the one before: Rotate Right walks them forwards. */
export const TURNS: readonly Orientation[] = ['portrait', 'landscape_left', 'portrait_upside_down', 'landscape_right']

/** How many quarter turns clockwise the device is drawn at; an older server says nothing, read as upright. */
export function quarterTurns(orientation: Orientation | null | undefined): number {
  const at = TURNS.indexOf(orientation ?? 'portrait')
  return at < 0 ? 0 : at
}

/** A point on the page, as it lies on an element drawn `turns` quarters clockwise about its centre: in the element's
 * own unturned box, which is `size` large and whose turned bounding box on the page is `rect`. */
export function unturned(
  client: { clientX: number; clientY: number },
  rect: { left: number; top: number; width: number; height: number },
  size: { w: number; h: number },
  turns: number,
): { clientX: number; clientY: number; box: { left: number; top: number; width: number; height: number } } {
  const box = { left: -size.w / 2, top: -size.h / 2, width: size.w, height: size.h }
  const dx = client.clientX - (rect.left + rect.width / 2)
  const dy = client.clientY - (rect.top + rect.height / 2)
  const quarter = ((turns % 4) + 4) % 4
  // CSS turns clockwise with y down: a turn of a quarter takes (x, y) to (-y, x). Undone here.
  const [x, y] = quarter === 1 ? [dy, -dx] : quarter === 2 ? [-dx, -dy] : quarter === 3 ? [-dy, dx] : [dx, dy]
  return { clientX: x, clientY: y, box }
}
