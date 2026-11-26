// SPDX-License-Identifier: Apache-2.0
/**
 * What the viewer offers around the device, beside the device's own controls (`viewer-controls.ts`): the zoom, the
 * device's frame shown or not, screenshots, the viewer's theme and language, and the Edit, Device and View menus with
 * their shortcuts (`menu-bar.ts`).
 *
 * A menu row that stands for a button the viewer already shows -- Home, Lock, Settings -- runs that button, and is
 * offered exactly while the button is: what a device or a transport cannot do is never in a menu either.
 */
import type { DeviceView, Zoom } from './device-view'
import type { I18n, LocaleChoice, PlainKey } from './i18n'
import { LOCALES, type Locale } from './locales'
import { createMenuBar, type MenuBar, type MenuEntry, type MenuItem, type Shortcut } from './menu-bar'
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
  /** The viewer's language: what the menus are said in, and what View > Language changes. */
  i18n: I18n
  /** The clipboard to copy screenshots to; the page's own when absent. */
  clipboard?: ClipboardLike | null
}

export interface Chrome {
  /** A picture of the screen has been drawn: there is something to capture. */
  drawn(): void
  /** The zoom changed: say how large the device is drawn. */
  paintZoom(): void
  /** The language changed: say the menus' titles and the zoom again. */
  relabel(): void
  destroy(): void
}

export function createChrome(options: ChromeOptions): Chrome {
  const { el, view, i18n } = options
  const { t } = i18n
  const q = <T extends Element>(selector: string) => el.querySelector<T>(selector)!
  const level = q<HTMLElement>('[data-smv-zoom-level]')
  const fitButton = q<HTMLButtonElement>('[data-smv="zoom-fit"]')
  const actualButton = q<HTMLButtonElement>('[data-smv="zoom-actual"]')
  const shotButton = q<HTMLButtonElement>('[data-smv="screenshot"]')
  let theme = options.theme
  let hasPicture = false
  const shots = createScreenshots({
    canvas: options.canvas, device: options.device, say: options.tell, clipboard: options.clipboard, t,
  })

  function applyTheme(next: Theme): void {
    theme = next
    if (next === 'system') delete el.dataset.theme
    else el.dataset.theme = next
  }
  applyTheme(theme)

  /** Draw the device so large, and keep the choice for next time. */
  function zoom(next: Zoom): void {
    view.setZoom(next)
    keepPreferences({ zoom: view.zoom })
    paintZoom()
  }

  /** Say how large the device is drawn -- and, asked for its actual size in a room too small, that it is smaller. */
  function paintZoom(): void {
    const scale = view.scale
    const percent = scale === null ? '' : t('percent', { n: Math.round(scale * 100) })
    level.textContent = percent
    level.dataset.reduced = String(view.reduced)
    if (view.reduced) {
      const why = document.createElement('span')
      why.className = 'smv-zoom-why'
      why.textContent = t('zoom.fitted')
      level.append(why)
    }
    const said = t(view.reduced ? 'zoom.reduced' : 'zoom.level', { percent })
    level.title = said
    level.setAttribute('aria-label', said)
    fitButton.setAttribute('aria-pressed', String(view.zoom === 'fit'))
    actualButton.setAttribute('aria-pressed', String(view.zoom === 'actual'))
  }

  /** A row running a button the viewer shows, offered while it is. */
  function proxy(action: string, label: PlainKey | (() => string), shortcut?: Shortcut): MenuItem {
    const target = () => el.querySelector<HTMLButtonElement>(`[data-smv="${action}"]`)!
    return {
      id: action, label: typeof label === 'function' ? label : () => t(label), shortcut,
      available: () => !target().hidden && !target().disabled,
      run: () => target().click(),
    }
  }
  const titleOf = (action: string) => () => q<HTMLElement>(`[data-smv="${action}"]`).title
  const themeRow = (value: Theme): MenuItem => ({
    id: `theme-${value}`, label: () => t(`theme.${value}`), kind: 'radio', checked: () => theme === value,
    run: () => {
      applyTheme(value)
      keepPreferences({ theme: value })
    },
  })
  /** A language to read the viewer in: the browser's own, or one the viewer speaks, called as it calls itself. */
  const languageRow = (value: LocaleChoice): MenuItem => ({
    id: `lang-${value}`, kind: 'radio', checked: () => i18n.choice === value,
    label: () => (value === 'auto' ? t('language.auto') : LOCALES[value]['language.name']),
    run: () => {
      i18n.set(value)
      keepPreferences({ lang: value })
    },
  })
  const locales = Object.keys(LOCALES) as Locale[]
  // A choice of one is no choice: the section shows once the viewer speaks two languages.
  const languages: MenuEntry[] = locales.length < 2 ? [] : [
    { ...languageRow('auto'), group: () => t('language.heading') },
    ...locales.map(languageRow),
  ]

  const menus: MenuBar = createMenuBar({
    root: el, bar: q('[data-smv-menus]'), host: options.stage, layers: options.layers,
    // A macOS app has shortcuts of its own: Command-S is its Save, not a screenshot.
    shortcuts: () => options.device()?.kind !== 'mac',
    menus: [
      {
        id: 'edit', label: () => t('menu.edit'), items: [
          proxy('screenshot', 'menu.saveScreenshot', { key: 's' }),
          {
            id: 'copy-screenshot', label: () => t('menu.copyScreenshot'), shortcut: { key: 'c', ctrl: true },
            available: () => shots.canCopy && hasPicture, run: () => void shots.copy(),
          },
        ],
      },
      {
        id: 'device', label: () => t('menu.device'), items: [
          proxy('home', 'button.home', { key: 'h', shift: true }),
          proxy('lock', 'button.lock', { key: 'l' }),
          proxy('rotate-left', 'rotate.left', { key: 'arrowleft' }),
          proxy('rotate-right', 'rotate.right', { key: 'arrowright' }),
          proxy('back', 'button.back'),
          proxy('app_switch', 'button.app_switch'),
          proxy('volume_up', 'button.volume_up'),
          proxy('volume_down', 'button.volume_down'),
          'separator',
          { ...proxy('appearance', 'appearance.dark', { key: 'a', shift: true }), kind: 'check',
            checked: () => q('[data-smv="appearance"]').getAttribute('aria-pressed') === 'true' },
          proxy('display', 'menu.display'),
          proxy('record', titleOf('record')),
          'separator',
          proxy('devices', 'menu.chooseDevice'),
          proxy('settings', 'menu.settings', { key: ',' }),
          proxy('stop', titleOf('stop')),
        ],
      },
      {
        id: 'view', label: () => t('menu.view'), items: [
          { id: 'zoom-in', label: () => t('zoom.in'), shortcut: { key: '+' }, run: () => q<HTMLElement>('[data-smv="zoom-in"]').click() },
          { id: 'zoom-out', label: () => t('zoom.out'), shortcut: { key: '-' }, run: () => q<HTMLElement>('[data-smv="zoom-out"]').click() },
          { id: 'zoom-fit', label: () => t('zoom.fit'), shortcut: { key: '0' }, kind: 'check',
            checked: () => view.zoom === 'fit', run: () => zoom('fit') },
          { id: 'zoom-actual', label: () => t('zoom.actual'), shortcut: { key: '1' }, kind: 'check',
            checked: () => view.zoom === 'actual', run: () => zoom('actual') },
          'separator',
          {
            id: 'frame', label: () => t('menu.frame'), kind: 'check', checked: () => view.framed,
            available: () => view.family !== 'bare',
            run: () => {
              view.setFramed(!view.framed)
              keepPreferences({ framed: view.framed })
              paintZoom()
            },
          },
          'separator',
          themeRow('system'),
          themeRow('light'),
          themeRow('dark'),
          'separator',
          ...languages,
        ],
      },
    ],
  })

  const onClick = (event: Event) => {
    const action = (event.target as HTMLElement).closest<HTMLElement>('[data-smv]')?.dataset.smv
    if (action === 'zoom-in' || action === 'zoom-out') {
      view.zoomBy(action === 'zoom-in' ? 1 : -1)
      keepPreferences({ zoom: view.zoom })
      paintZoom()
    } else if (action === 'zoom-fit') {
      zoom('fit')
    } else if (action === 'zoom-actual') {
      zoom('actual')
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
    relabel() {
      menus.relabel()
      paintZoom()
    },
    destroy() {
      el.removeEventListener('click', onClick)
      menus.destroy()
    },
  }
}
