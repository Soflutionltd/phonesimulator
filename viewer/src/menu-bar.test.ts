// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createMenuBar, matches, shortcutLabel, visibleEntries, type MenuEntry, type MenuItem } from './menu-bar'
import { createLayers } from './popover'

const key = (init: KeyboardEventInit & { key: string }) => new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init })

function rig(items: MenuEntry[], shortcuts?: () => boolean) {
  const root = document.createElement('div')
  const bar = document.createElement('div')
  const host = document.createElement('div')
  root.append(bar, host)
  document.body.appendChild(root)
  const layers = createLayers()
  const menus = createMenuBar({ root, bar, host, layers, shortcuts, menus: [{ id: 'device', label: 'Device', items }] })
  const toggle = bar.querySelector<HTMLButtonElement>('[data-smv-menu="device"]')!
  const panel = host.querySelector<HTMLElement>('[data-smv-menu-panel="device"]')!
  return { root, bar, host, layers, menus, toggle, panel }
}

const item = (id: string, extra: Partial<MenuItem> = {}): MenuItem => ({ id, label: id, run: vi.fn(), ...extra })

afterEach(() => {
  document.body.innerHTML = ''
})

describe('shortcuts', () => {
  it('writes them as a Mac menu does', () => {
    expect(shortcutLabel({ key: 'h', shift: true })).toBe('⇧⌘H')
    expect(shortcutLabel({ key: 'c', ctrl: true })).toBe('⌃⌘C')
    expect(shortcutLabel({ key: '-' })).toBe('⌘−')
    expect(shortcutLabel({ key: '+' })).toBe('⌘+')
    expect(shortcutLabel({ key: 'Enter' })).toBe('⌘Enter')
  })

  it('matches Command with Shift and Control exactly as asked, and never Option', () => {
    expect(matches(key({ key: 'H', metaKey: true, shiftKey: true }), { key: 'h', shift: true })).toBe(true)
    expect(matches(key({ key: 'h', metaKey: true }), { key: 'h', shift: true })).toBe(false)
    expect(matches(key({ key: 'h', shiftKey: true }), { key: 'h', shift: true })).toBe(false)
    expect(matches(key({ key: 's', metaKey: true, altKey: true }), { key: 's' })).toBe(false)
    expect(matches(key({ key: 'c', metaKey: true, ctrlKey: true }), { key: 'c', ctrl: true })).toBe(true)
    expect(matches(key({ key: 'c', metaKey: true }), { key: 'c', ctrl: true })).toBe(false)
    // + is typed with Shift, or as = on its own key.
    expect(matches(key({ key: '+', metaKey: true, shiftKey: true }), { key: '+' })).toBe(true)
    expect(matches(key({ key: '=', metaKey: true }), { key: '+' })).toBe(true)
    expect(matches(key({ key: '-', metaKey: true }), { key: '-' })).toBe(true)
    expect(matches(key({ key: 'x', metaKey: true }), { key: '-' })).toBe(false)
  })
})

describe('visibleEntries', () => {
  it('shows the rows available now, with no separator first, last or twice', () => {
    const on = item('on')
    const off = item('off', { available: () => false })
    const ids = (entries: MenuEntry[]) => visibleEntries(entries).map((entry) => entry === 'separator' ? '-' : entry.id)
    expect(ids(['separator', on, 'separator', off, 'separator', on, 'separator', 'separator'])).toEqual(['on', '-', 'on'])
    expect(ids([on, 'separator', off])).toEqual(['on'])
    expect(ids([off])).toEqual([])
  })
})

describe('createMenuBar', () => {
  it('opens a menu of what can be done now, runs a row as it closes, and walks it with the keys', () => {
    const home = item('home', { shortcut: { key: 'h', shift: true } })
    const dark = item('dark', { kind: 'check', checked: () => true, label: () => 'Dark appearance' })
    const theme = item('theme', { kind: 'radio', checked: () => false })
    const gone = item('gone', { available: () => false })
    const { toggle, panel, layers } = rig([home, 'separator', dark, theme, gone])
    expect([toggle.textContent, toggle.getAttribute('aria-haspopup'), panel.getAttribute('role')]).toEqual(['Device', 'menu', 'menu'])
    toggle.click()
    expect([panel.hidden, toggle.getAttribute('aria-expanded'), layers.open]).toEqual([false, 'true', true])
    const rows = [...panel.querySelectorAll<HTMLButtonElement>('[data-smv-item]')]
    expect(rows.map((row) => [row.dataset.smvItem, row.getAttribute('role'), row.getAttribute('aria-checked')])).toEqual([
      ['home', 'menuitem', null], ['dark', 'menuitemcheckbox', 'true'], ['theme', 'menuitemradio', 'false'],
    ])
    expect(rows[0].querySelector('kbd')!.textContent).toBe('⇧⌘H')
    expect(rows[0].getAttribute('aria-keyshortcuts')).toBe('Meta+Shift+H')
    expect(rows[1].textContent).toBe('Dark appearance')
    expect(panel.querySelector('hr[role="separator"]')).not.toBeNull()
    expect(panel.ownerDocument.activeElement).toBe(rows[0])
    rows[1].click()
    expect(dark.run).toHaveBeenCalled()
    expect([panel.hidden, panel.innerHTML, layers.open]).toEqual([true, '', false])
    // Its title closes it too.
    toggle.click()
    toggle.click()
    expect(panel.hidden).toBe(true)
  })

  it('does nothing for a press between rows, or for a row no longer available', () => {
    let available = true
    const row = item('row', { available: () => available })
    const { toggle, panel } = rig([row, 'separator', item('other')])
    toggle.click()
    panel.querySelector('hr')!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(panel.hidden).toBe(false)
    available = false
    panel.querySelector<HTMLElement>('[data-smv-item="row"]')!.click()
    expect(row.run).not.toHaveBeenCalled()
  })

  it('runs a row from its shortcut anywhere in the viewer, only while it is available and the shortcuts are its own', () => {
    let available = true
    let own = true
    const home = item('home', { shortcut: { key: 'h', shift: true }, available: () => available })
    const lock = item('lock', { shortcut: { key: 'l' } })
    const { root, toggle, panel } = rig([home, lock], () => own)
    const target = document.createElement('canvas')
    root.appendChild(target)
    const heard = vi.fn()
    target.addEventListener('keydown', heard)
    toggle.click()
    const press = key({ key: 'H', metaKey: true, shiftKey: true })
    target.dispatchEvent(press)
    expect([home.run, press.defaultPrevented, heard.mock.calls.length, panel.hidden]).toEqual([home.run, true, 0, true])
    expect(home.run).toHaveBeenCalledTimes(1)
    available = false
    target.dispatchEvent(key({ key: 'h', metaKey: true, shiftKey: true }))
    expect(home.run).toHaveBeenCalledTimes(1)
    // The device's own, then: the key goes on to the screen.
    own = false
    target.dispatchEvent(key({ key: 'l', metaKey: true }))
    expect(lock.run).not.toHaveBeenCalled()
    own = true
    target.dispatchEvent(key({ key: 'l' }))
    target.dispatchEvent(key({ key: 'q', metaKey: true }))
    expect(lock.run).not.toHaveBeenCalled()
    expect(heard).toHaveBeenCalledTimes(4)
    // A field being typed in keeps its keys.
    const field = document.createElement('input')
    root.appendChild(field)
    field.dispatchEvent(key({ key: 'l', metaKey: true }))
    expect(lock.run).not.toHaveBeenCalled()
    target.dispatchEvent(key({ key: 'l', metaKey: true }))
    expect(lock.run).toHaveBeenCalledTimes(1)
  })

  it('takes its shortcuts always when not told otherwise, and leaves nothing behind once destroyed', () => {
    const lock = item('lock', { shortcut: { key: 'l' } })
    const { root, bar, host, menus } = rig([lock])
    root.dispatchEvent(key({ key: 'l', metaKey: true }))
    expect(lock.run).toHaveBeenCalledTimes(1)
    menus.close()
    menus.destroy()
    root.dispatchEvent(key({ key: 'l', metaKey: true }))
    expect(lock.run).toHaveBeenCalledTimes(1)
    expect([bar.children.length, host.children.length]).toEqual([0, 0])
  })
})
