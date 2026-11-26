// SPDX-License-Identifier: Apache-2.0
/**
 * The settings panel: every setting a scope has, one tab per section of config.toml, changed and saved a tab at a time.
 *
 * Everything shown comes from the server's `SettingsView` -- the sections, each setting's rule, where its value comes
 * from, when a change takes effect -- so a setting added to Rocketwright appears here without the viewer changing. A save
 * sends the tab's changed values as one `SettingsChange`, for this project or every project; the server checks all of
 * it and answers either the settings as they now are, or why not, which is shown on each setting it names. A change to a
 * sensitive setting comes back asking for the code `rocketwright settings confirm` shows at the terminal, and is sent
 * again with it.
 *
 * What the server says -- a section's and a setting's description, a notice, why a change was refused -- is shown as it
 * wrote it, in English; a section's title is said in the viewer's language when the viewer knows the section. Everything
 * else is written with its message's key on it (`i18n.ts`), so the panel changes language as it stands, a half-made
 * change kept.
 *
 * It is a dialog over the screen (`popover.ts`): Escape closes it, and while it is open nothing typed reaches the
 * device. A press outside does not close it, so a half-made change is not lost to a stray click.
 */
import { english, isMessageKey, label, name, say, sayPlain, type Translate } from './i18n'
import type { IconRenderer } from './icons'
import { createPopover, type Layers } from './popover'
import type { SettingsChange, SettingsRefusal, SettingsTarget, SettingsView } from './protocol.generated'
import { renderField, type Field } from './settings-fields'
import type { RocketwrightTransport } from './transport'

export type SettingsTransport = Required<Pick<RocketwrightTransport, 'settings' | 'changeSettings'>>

export interface SettingsPanelOptions {
  root: HTMLElement
  toggle: HTMLElement
  panel: HTMLElement
  transport: SettingsTransport
  layers: Layers
  icon: IconRenderer
  /** Says the panel's messages; in English when absent. */
  t?: Translate
}

export interface SettingsPanel {
  readonly isOpen: boolean
  /** Open the panel, reading the settings afresh, or close it. */
  toggle(): Promise<void>
  /** Open the panel at a section's tab -- `real_devices`, say -- or go to that tab when it is open. */
  show(section: string): Promise<void>
  close(): void
  destroy(): void
}

/** A refusal's body, when the server said more than a message. */
function refusalOf(error: unknown): SettingsRefusal | null {
  const body = (error as { body?: unknown }).body
  return body && typeof body === 'object' && Array.isArray((body as SettingsRefusal).errors)
    ? body as SettingsRefusal : null
}

let panels = 0

export function createSettingsPanel(options: SettingsPanelOptions): SettingsPanel {
  const { panel, transport, icon } = options
  const t = options.t ?? english
  panels += 1
  const uid = `smv-settings-${panels}`
  let view: SettingsView | null = null
  let active = ''
  let target: SettingsTarget = 'scope'
  let waiting: SettingsChange | null = null
  let fields = new Map<string, Field>()
  /** The rendered panel's parts; set while it shows settings. */
  let refs: {
    tabs: HTMLButtonElement[]; panes: HTMLElement[]; save: HTMLButtonElement; status: HTMLElement
    targets: HTMLElement; confirm: HTMLElement; confirmText: HTMLElement; code: HTMLInputElement
  } | null = null

  const popover = createPopover({
    root: options.root, toggle: options.toggle, panel, layers: options.layers, menu: false, outside: false,
    onClose: () => {
      panel.replaceChildren()
      view = null
      refs = null
      waiting = null
    },
  })

  const make = <K extends keyof HTMLElementTagNameMap>(tag: K, className: string, text?: string) => {
    const node = document.createElement(tag)
    node.className = className
    if (text !== undefined) node.textContent = text
    return node
  }

  const inSection = (id: string) => [...fields.values()].filter((field) => field.entry.section === id)
  const wholeDaemon = (id: string) => inSection(id).every((field) => field.entry.reach === 'global')
  const editable = () => view!.access !== 'read'

  function refresh(): void {
    const dirty = inSection(active).some((field) => field.dirty())
    refs!.save.disabled = !editable() || !dirty
    refs!.targets.hidden = !editable() || wholeDaemon(active)
  }

  function select(id: string, focus = false): void {
    active = id
    view!.sections.forEach((section, index) => {
      const chosen = section.id === id
      const tab = refs!.tabs[index]
      tab.setAttribute('aria-selected', String(chosen))
      tab.tabIndex = chosen ? 0 : -1
      refs!.panes[index].hidden = !chosen
      if (chosen && focus) tab.focus()
    })
    refresh()
  }

  function onTabKey(event: KeyboardEvent): void {
    const ids = view!.sections.map((section) => section.id)
    const at = ids.indexOf(active)
    const next: Record<string, number> = {
      ArrowRight: (at + 1) % ids.length, ArrowLeft: (at - 1 + ids.length) % ids.length, Home: 0, End: ids.length - 1,
    }
    if (!(event.key in next)) return
    event.preventDefault()
    select(ids[next[event.key]], true)
  }

  function render(next: SettingsView): void {
    view = next
    if (!next.sections.some((section) => section.id === active)) active = next.sections[0]?.id ?? ''
    fields = new Map()

    const header = make('div', 'smv-settings-head')
    const title = make('h2', 'smv-settings-title')
    say(title, t, 'settings.title')
    title.id = `${uid}-title`
    const close = make('button', 'smv-icon')
    close.type = 'button'
    name(close, t, 'settings.close')
    close.innerHTML = icon('close')
    close.addEventListener('click', () => popover.close('api'))
    // The project's name, with its id on hover: what a person reads, and what a command names.
    const scope = make('span', 'smv-settings-scope', next.label || next.scope)
    scope.title = next.scope
    header.append(title, scope, close)

    const tablist = make('div', 'smv-tabs')
    tablist.setAttribute('role', 'tablist')
    label(tablist, t, 'settings.sections')
    tablist.addEventListener('keydown', onTabKey)
    const tabs: HTMLButtonElement[] = []
    const panes: HTMLElement[] = []
    next.sections.forEach((section, index) => {
      const tab = make('button', 'smv-tab', section.title)
      // A section this viewer knows is called by its own message; one it does not, as the server calls it.
      const known = `section.${section.id || 'general'}`
      if (isMessageKey(known)) say(tab, t, known as 'section.general')
      tab.type = 'button'
      tab.id = `${uid}-tab-${index}`
      tab.setAttribute('role', 'tab')
      tab.setAttribute('aria-controls', `${uid}-pane-${index}`)
      tab.addEventListener('click', () => select(section.id))
      tabs.push(tab)
      const pane = make('div', 'smv-pane')
      pane.id = `${uid}-pane-${index}`
      pane.setAttribute('role', 'tabpanel')
      pane.setAttribute('aria-labelledby', tab.id)
      pane.append(make('p', 'smv-pane-doc', section.doc))
      for (const entry of next.settings.filter((setting) => setting.section === section.id)) {
        const field = renderField(entry, { editable: next.access !== 'read', onInput: refresh, onReset: reset, t })
        fields.set(entry.path, field)
        pane.append(field.el)
      }
      panes.push(pane)
    })
    tablist.append(...tabs)

    const footer = make('div', 'smv-settings-foot')
    const targets = make('div', 'smv-targets')
    targets.setAttribute('role', 'radiogroup')
    label(targets, t, 'settings.saveFor')
    for (const value of ['scope', 'all'] as const) {
      const choice = make('label', 'smv-target')
      const text = make('span', '')
      say(text, t, `settings.target.${value}`)
      const radio = make('input', '')
      radio.type = 'radio'
      radio.name = `${uid}-target`
      radio.value = value
      radio.checked = target === value
      radio.addEventListener('change', () => {
        target = value
      })
      choice.append(radio, ' ', text)
      targets.append(choice)
    }
    const confirm = make('div', 'smv-confirm')
    confirm.hidden = true
    const confirmText = make('p', 'smv-confirm-text')
    const code = make('input', 'smv-input')
    code.type = 'text'
    code.autocomplete = 'one-time-code'
    code.spellcheck = false
    label(code, t, 'settings.code')
    code.placeholder = 'ABCD-EFGH'
    const confirmButton = make('button', 'smv-button')
    say(confirmButton, t, 'settings.confirm')
    confirmButton.type = 'button'
    confirmButton.addEventListener('click', () => {
      // Shown only while a change waits for its code.
      void send({ ...waiting!, confirmation: code.value.trim() })
    })
    confirm.append(confirmText, code, confirmButton)
    const status = make('p', 'smv-settings-status')
    status.setAttribute('role', 'status')
    status.setAttribute('aria-live', 'polite')
    const save = make('button', 'smv-button smv-button-primary')
    say(save, t, 'settings.save')
    save.type = 'button'
    save.addEventListener('click', () => void saveTab())
    footer.append(targets, confirm, status, save)

    const children: HTMLElement[] = [header]
    if (next.notice) children.push(make('p', 'smv-settings-notice', next.notice))
    children.push(tablist, ...panes, footer)
    panel.replaceChildren(...children)
    panel.setAttribute('aria-labelledby', title.id)
    refs = { tabs, panes, save, status, targets, confirm, confirmText, code }
    select(active)
  }

  async function send(change: SettingsChange): Promise<void> {
    for (const field of fields.values()) field.setError(null)
    say(refs!.status, t, 'settings.saving')
    refs!.save.disabled = true
    let next: SettingsView
    try {
      next = await transport.changeSettings(change)
    } catch (error) {
      // Closed while it was saving: there is nothing left to show why.
      if (!popover.isOpen) return
      refuse(change, error)
      return
    }
    if (!popover.isOpen) return
    waiting = null
    render(next)
    say(refs!.status, t, 'settings.saved')
    // What had focus -- Save, a field's Reset -- was drawn again: keep focus in the panel, or Escape is heard nowhere.
    focusTab()
  }

  function focusTab(): void {
    refs!.tabs.find((tab) => tab.tabIndex === 0)?.focus()
  }

  function refuse(change: SettingsChange, error: unknown): void {
    const parts = refs!
    const refusal = refusalOf(error)
    if (refusal?.confirmation) {
      waiting = { ...change, confirmation: null }
      parts.confirm.hidden = false
      parts.confirmText.textContent = refusal.detail
      parts.code.value = ''
      parts.code.focus()
      say(parts.status, t, 'settings.waiting', { summary: refusal.confirmation.summary })
    } else {
      for (const problem of refusal?.errors ?? []) fields.get(problem.path)?.setError(problem.message)
      const why = refusal?.detail ?? (error as Error).message
      if (why) sayPlain(parts.status, why)
      else say(parts.status, t, 'settings.saveFailed')
    }
    refresh()
  }

  /** The tab's changed values, as one change. Save is offered only once a value has changed. */
  async function saveTab(): Promise<void> {
    const changed = inSection(active).filter((field) => field.dirty())
    await send({
      target: wholeDaemon(active) ? 'all' : target,
      set: changed.map((field) => ({ path: field.entry.path, value: field.value() })),
      unset: [],
      confirmation: null,
    })
  }

  function reset(path: string): void {
    // Put back where the value came from: this project's table, or the whole file.
    const where: SettingsTarget = fields.get(path)!.entry.origin.layer === 'scope' ? 'scope' : 'all'
    void send({ target: where, set: [], unset: [path], confirmation: null })
  }

  async function open(): Promise<void> {
    popover.open()
    const loading = make('p', 'smv-settings-status')
    say(loading, t, 'settings.loading')
    loading.setAttribute('role', 'status')
    panel.replaceChildren(loading)
    try {
      const next = await transport.settings()
      if (!popover.isOpen) return
      render(next)
      focusTab()
    } catch (error) {
      if (!popover.isOpen) return
      const why = (error as Error).message
      if (why) sayPlain(loading, why)
      else say(loading, t, 'settings.readFailed')
    }
  }

  return {
    get isOpen() {
      return popover.isOpen
    },
    toggle: () => (popover.isOpen ? Promise.resolve(popover.close('toggle')) : open()),
    show(section) {
      if (!popover.isOpen) {
        active = section
        return open()
      }
      if (view?.sections.some((known) => known.id === section)) select(section, true)
      return Promise.resolve()
    },
    close: () => popover.close('api'),
    destroy: () => popover.destroy(),
  }
}
