// SPDX-License-Identifier: Apache-2.0
/**
 * The viewer's menus -- Edit, Device and View -- and their keyboard shortcuts, as the iOS Simulator has them: Shift-
 * Command-H for Home, Command-S for a screenshot, Command-plus and Command-minus to zoom.
 *
 * A menu lists only what can be done now: each row asks whether it is available as the menu opens, so a row never
 * stands for something the device or the transport cannot do. Most rows run a button the viewer already shows, and are
 * offered exactly while that button is. A shortcut runs its row as a click would, only while the row is available, and
 * only while the viewer says shortcuts are its own: a macOS app gets Command-S itself.
 *
 * What a menu says may be asked for each time it is shown (a function), so that it follows the viewer's language:
 * rows are drawn as their menu opens, and `relabel` says the titles again.
 *
 * Each menu is a popover (`popover.ts`): Escape closes it and gives focus back to its title, the arrow keys walk it.
 */
import { escapeHTML } from './escape'
import { resolve, type Said } from './i18n'
import { createPopover, type Layers, type Popover } from './popover'

export interface Shortcut {
  /** `KeyboardEvent.key`, lower case; `+` also answers `=`, and `-` also `_`. */
  key: string
  shift?: boolean
  /** Control as well as Command. */
  ctrl?: boolean
}

export interface MenuItem {
  id: string
  /** What the row says; read as the menu opens when it depends on how things stand. */
  label: Said
  /** What the set of rows this one starts is called -- Language -- said in a line above it. */
  group?: Said
  shortcut?: Shortcut
  /** A switch, or one of a set; a plain row when absent. */
  kind?: 'check' | 'radio'
  checked?(): boolean
  /** Whether the row can be done now; always when absent. */
  available?(): boolean
  run(): void
}

export type MenuEntry = MenuItem | 'separator'

export interface MenuSpec {
  id: string
  label: Said
  items: MenuEntry[]
}

export interface MenuBarOptions {
  /** The viewer's root: keys anywhere inside it reach the shortcuts and an open menu. */
  root: HTMLElement
  /** Where the menus' titles go. */
  bar: HTMLElement
  /** Where the menus' panels open: over the stage. */
  host: HTMLElement
  layers: Layers
  menus: MenuSpec[]
  /** Whether the viewer's shortcuts are its own now, rather than the device's. */
  shortcuts?(): boolean
}

export interface MenuBar {
  /** Close whichever menu is open. */
  close(): void
  /** The language changed: say the menus' titles again, and close an open menu, drawn in the old one. */
  relabel(): void
  destroy(): void
}

/** A shortcut as a Mac menu writes it: ⌃⇧⌘H. */
/** Keys a menu writes as a sign: the arrows. */
const SIGNS: Record<string, string> = { arrowleft: '←', arrowright: '→', arrowup: '↑', arrowdown: '↓' }

export function shortcutLabel(shortcut: Shortcut): string {
  const key = shortcut.key === '-' ? '−' : SIGNS[shortcut.key]
    ?? (shortcut.key.length === 1 ? shortcut.key.toUpperCase() : shortcut.key)
  return `${shortcut.ctrl ? '⌃' : ''}${shortcut.shift ? '⇧' : ''}⌘${key}`
}

const ALIASES: Record<string, string> = { '=': '+', _: '-' }

/** Whether a key press is this shortcut: Command, with Shift and Control exactly as it asks, and never Option. */
export function matches(event: KeyboardEvent, shortcut: Shortcut): boolean {
  if (!event.metaKey || event.altKey) return false
  if (event.ctrlKey !== Boolean(shortcut.ctrl)) return false
  const key = event.key.toLowerCase()
  const named = ALIASES[key] ?? key
  // Shift is how a keyboard types +: it is not asked of a shortcut that is +.
  if (shortcut.key !== '+' && event.shiftKey !== Boolean(shortcut.shift)) return false
  return named === shortcut.key
}

const isItem = (entry: MenuEntry): entry is MenuItem => entry !== 'separator'
const availableNow = (item: MenuItem) => item.available?.() ?? true

/** The rows to show now: those available, with no separator first, last or twice. */
export function visibleEntries(entries: MenuEntry[]): MenuEntry[] {
  const shown = entries.filter((entry) => !isItem(entry) || availableNow(entry))
  return shown.filter((entry, index) =>
    isItem(entry) || (index > 0 && isItem(shown[index - 1]) && shown.slice(index + 1).some(isItem)))
}

function rowMarkup(item: MenuItem): string {
  const role = item.kind === 'check' ? 'menuitemcheckbox' : item.kind === 'radio' ? 'menuitemradio' : 'menuitem'
  const checked = item.kind ? ` aria-checked="${Boolean(item.checked?.())}"` : ''
  const keys = item.shortcut
    ? `<kbd aria-hidden="true">${escapeHTML(shortcutLabel(item.shortcut))}</kbd>` : ''
  const shortcut = item.shortcut ? ` aria-keyshortcuts="${keysFor(item.shortcut)}"` : ''
  const group = item.group === undefined ? ''
    : `<p class="smv-picker-group" role="presentation">${escapeHTML(resolve(item.group))}</p>`
  return `${group}<button type="button" role="${role}"${checked}${shortcut} data-smv-item="${escapeHTML(item.id)}">`
    + `<span>${escapeHTML(resolve(item.label))}</span>${keys}</button>`
}

/** A shortcut as `aria-keyshortcuts` names it: Meta+Shift+H. */
function keysFor(shortcut: Shortcut): string {
  const arrow = /^arrow(left|right|up|down)$/.exec(shortcut.key)
  const key = shortcut.key === '+' ? 'Plus' : shortcut.key === '-' ? 'Minus'
    : arrow ? `Arrow${arrow[1][0].toUpperCase()}${arrow[1].slice(1)}` : shortcut.key.toUpperCase()
  return ['Meta', shortcut.ctrl ? 'Control' : '', shortcut.shift ? 'Shift' : '', key].filter(Boolean).join('+')
}

export function createMenuBar(options: MenuBarOptions): MenuBar {
  const { root, bar, host, layers } = options
  const doc = root.ownerDocument
  const opened: Array<{ spec: MenuSpec; popover: Popover; toggle: HTMLButtonElement; panel: HTMLElement }> = []

  for (const spec of options.menus) {
    const toggle = doc.createElement('button')
    toggle.type = 'button'
    toggle.className = 'smv-menu'
    toggle.dataset.smvMenu = spec.id
    toggle.setAttribute('aria-haspopup', 'menu')
    toggle.setAttribute('aria-expanded', 'false')
    const panel = doc.createElement('div')
    panel.className = 'smv-picker smv-menu-panel'
    panel.setAttribute('role', 'menu')
    panel.dataset.smvMenuPanel = spec.id
    panel.hidden = true
    bar.appendChild(toggle)
    host.appendChild(panel)
    const popover = createPopover({ root, toggle, panel, layers, onClose: () => { panel.innerHTML = '' } })
    const menu = { spec, popover, toggle, panel }
    opened.push(menu)

    toggle.addEventListener('click', () => {
      if (popover.isOpen) return popover.close('toggle')
      panel.innerHTML = visibleEntries(spec.items)
        .map((entry) => isItem(entry) ? rowMarkup(entry) : '<hr role="separator">').join('')
      popover.open()
      // Under its title: the panel is placed in the stage, which starts where the bar ends.
      const left = toggle.getBoundingClientRect().left - host.getBoundingClientRect().left
      panel.style.left = `${Math.max(4, left)}px`
      popover.focusItem('first')
    })
    panel.addEventListener('click', (event) => {
      const row = (event.target as HTMLElement).closest<HTMLElement>('[data-smv-item]')
      const item = row && spec.items.filter(isItem).find((candidate) => candidate.id === row.dataset.smvItem)
      if (!item) return
      popover.close('api')
      if (availableNow(item)) item.run()
    })
  }

  function onKey(event: KeyboardEvent): void {
    if (!event.metaKey || (options.shortcuts && !options.shortcuts())) return
    const target = event.target as HTMLElement | null
    if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return
    for (const { spec } of opened) {
      const item = spec.items.filter(isItem).find((candidate) => candidate.shortcut && matches(event, candidate.shortcut))
      if (!item || !availableNow(item)) continue
      event.preventDefault()
      event.stopPropagation()
      close()
      item.run()
      return
    }
  }

  function close(): void {
    for (const { popover } of opened) popover.close('api')
  }

  function relabel(): void {
    close()
    for (const { spec, toggle, panel } of opened) {
      toggle.textContent = resolve(spec.label)
      panel.setAttribute('aria-label', toggle.textContent)
    }
  }

  root.addEventListener('keydown', onKey, true)
  relabel()

  return {
    close,
    relabel,
    destroy() {
      root.removeEventListener('keydown', onKey, true)
      for (const { popover, toggle, panel } of opened) {
        popover.destroy()
        toggle.remove()
        panel.remove()
      }
    },
  }
}
