// SPDX-License-Identifier: Apache-2.0
/**
 * What the viewer offers around the device, beside the device's own controls (`viewer-controls.ts`): the zoom, the
 * device's frame shown or not, screenshots, the viewer's theme, and the Edit, Device and View menus with their
 * shortcuts (`menu-bar.ts`).
 *
 * A menu row that stands for a button the viewer already shows -- Home, Lock, Settings -- runs that button, and is
 * offered exactly while the button is: what a device or a transport cannot do is never in a menu either.
 */
import type { DeviceView, Zoom } from './device-view'
import { createMenuBar, type MenuBar, type MenuItem, type Shortcut } from './menu-bar'
import type { Layers } from './popover'
import { keepPreferences, type Theme } from './preferences'
import type { Device } from './protocol.generated'
import { createScreenshots } from './screenshot'
import type { ClipboardLike } from './screenshot'

export interface ChromeOptions {
  /** The viewer's root. */
  el: HTMLElement
  /** Where menus open. */
  stage: HTMLElement
  canvas: HTMLCanvasElement
  view: DeviceView
  layers: Layers
  device(): Device | null
  /** Say something over the screen. */
  tell(message: string): void
  theme: Theme
  /** The clipboard to copy screenshots to; the page's own when absent. */
  clipboard?: ClipboardLike | null
}

export interface Chrome {
  /** A picture of the screen has been drawn: there is something to capture. */
  drawn(): void
  /** The zoom changed: say how large the device is drawn. */
  paintZoom(): void
  destroy(): void
}

export function createChrome(options: ChromeOptions): Chrome {
  const { el, view } = options
  const q = <T extends Element>(selector: string) => el.querySelector<T>(selector)!
  const level = q<HTMLElement>('[data-smv-zoom-level]')
  const fitButton = q<HTMLButtonElement>('[data-smv="zoom-fit"]')
  const actualButton = q<HTMLButtonElement>('[data-smv="zoom-actual"]')
  const shotButton = q<HTMLButtonElement>('[data-smv="screenshot"]')
  let theme = options.theme
  let hasPicture = false
  const shots = createScreenshots({ canvas: options.canvas, device: options.device, say: options.tell, clipboard: options.clipboard })

  function applyTheme(next: Theme): void {
    theme = next
    if (next === 'system') delete el.dataset.theme
    else el.dataset.theme = next
  }
  applyTheme(theme)

  function zoom(next: Zoom): void {
    view.setZoom(next)
    paintZoom()
  }

  function paintZoom(): void {
    const scale = view.scale
    level.textContent = scale === null ? '' : `${Math.round(scale * 100)}%`
    fitButton.setAttribute('aria-pressed', String(view.zoom === 'fit'))
    actualButton.setAttribute('aria-pressed', String(view.zoom === 1))
  }

  /** A row running a button the viewer shows, offered while it is. */
  function proxy(action: string, label: string | (() => string), shortcut?: Shortcut): MenuItem {
    const target = () => el.querySelector<HTMLButtonElement>(`[data-smv="${action}"]`)!
    return {
      id: action, label, shortcut,
      available: () => !target().hidden && !target().disabled,
      run: () => target().click(),
    }
  }
  const titleOf = (action: string) => () => q<HTMLElement>(`[data-smv="${action}"]`).title
  const themeRow = (value: Theme, label: string): MenuItem => ({
    id: `theme-${value}`, label, kind: 'radio', checked: () => theme === value,
    run: () => {
      applyTheme(value)
      keepPreferences({ theme: value })
    },
  })

  const menus: MenuBar = createMenuBar({
    root: el, bar: q('[data-smv-menus]'), host: options.stage, layers: options.layers,
    // A macOS app has shortcuts of its own: Command-S is its Save, not a screenshot.
    shortcuts: () => options.device()?.kind !== 'mac',
    menus: [
      {
        id: 'edit', label: 'Edit', items: [
          proxy('screenshot', 'Save screenshot', { key: 's' }),
          {
            id: 'copy-screenshot', label: 'Copy screenshot', shortcut: { key: 'c', ctrl: true },
            available: () => shots.canCopy && hasPicture, run: () => void shots.copy(),
          },
        ],
      },
      {
        id: 'device', label: 'Device', items: [
          proxy('home', 'Home', { key: 'h', shift: true }),
          proxy('lock', 'Lock', { key: 'l' }),
          proxy('back', 'Back'),
          proxy('app_switch', 'Recent apps'),
          proxy('volume_up', 'Volume up'),
          proxy('volume_down', 'Volume down'),
          'separator',
          { ...proxy('appearance', 'Dark appearance', { key: 'a', shift: true }), kind: 'check',
            checked: () => q('[data-smv="appearance"]').getAttribute('aria-pressed') === 'true' },
          proxy('display', 'Display…'),
          proxy('record', titleOf('record')),
          'separator',
          proxy('devices', 'Choose a device…'),
          proxy('settings', 'Settings…', { key: ',' }),
          proxy('stop', titleOf('stop')),
        ],
      },
      {
        id: 'view', label: 'View', items: [
          { id: 'zoom-in', label: 'Zoom in', shortcut: { key: '+' }, run: () => q<HTMLElement>('[data-smv="zoom-in"]').click() },
          { id: 'zoom-out', label: 'Zoom out', shortcut: { key: '-' }, run: () => q<HTMLElement>('[data-smv="zoom-out"]').click() },
          { id: 'zoom-fit', label: 'Fit to window', shortcut: { key: '0' }, kind: 'check',
            checked: () => view.zoom === 'fit', run: () => zoom('fit') },
          { id: 'zoom-actual', label: 'Actual size', shortcut: { key: '1' }, kind: 'check',
            checked: () => view.zoom === 1, run: () => zoom(1) },
          'separator',
          {
            id: 'frame', label: 'Show device frame', kind: 'check', checked: () => view.framed,
            available: () => view.family !== 'bare',
            run: () => {
              view.setFramed(!view.framed)
              keepPreferences({ framed: view.framed })
              paintZoom()
            },
          },
          'separator',
          themeRow('system', 'Match the system'),
          themeRow('light', 'Light'),
          themeRow('dark', 'Dark'),
        ],
      },
    ],
  })

  const onClick = (event: Event) => {
    const action = (event.target as HTMLElement).closest<HTMLElement>('[data-smv]')?.dataset.smv
    if (action === 'zoom-in' || action === 'zoom-out') {
      view.zoomBy(action === 'zoom-in' ? 1 : -1)
      paintZoom()
    } else if (action === 'zoom-fit') {
      zoom('fit')
    } else if (action === 'zoom-actual') {
      zoom(1)
    } else if (action === 'screenshot') {
      void shots.save()
    }
  }
  el.addEventListener('click', onClick)

  return {
    drawn() {
      if (hasPicture) return
      hasPicture = true
      shotButton.disabled = false
    },
    paintZoom,
    destroy() {
      el.removeEventListener('click', onClick)
      menus.destroy()
    },
  }
}
