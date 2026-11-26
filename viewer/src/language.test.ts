// SPDX-License-Identifier: Apache-2.0
/**
 * The viewer in a person's language: which one it speaks, changing it where it stands, and keeping the choice.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FakeSocket } from '../test-support/fake-socket'
import { settingsView } from '../test-support/settings'
import { DEVICE, HELLO, VIEW_ONLY, flush, live, said, setup, socket } from '../test-support/viewer-harness'
import { defineRocketwrightElement, ELEMENT_NAME, RocketwrightElement } from './element'
import type { Recording, RecordingState, TouchSetup } from './protocol.generated'
import type { RocketwrightTransport } from './transport'

// The viewer ships English alone; French is added here so changing the language where it stands stays tested.
vi.mock('./locales', async (real) => (await import('../test-support/locale-fr')).withFrench(real))

const UNDER_WAY: RecordingState = { id: 'r1', since_ms: 0, by: 'person', max_ms: 300000 }
const KEPT: Recording = {
  id: 'r1', device: 'Test iPhone', started_at: '2026-09-29T00:45:15Z', duration_ms: 10_800, notes: ['kept as recorded'],
  files: [{ name: 'r1.mp4', path: '/r/r1.mp4', format: 'mp4', bytes: 4_300_000, width: 900, height: 1952 }],
  capture: null,
}
const OFFER: TouchSetup = {
  state: 'offer', message: '', team: 'TESTTEAM01', team_from: 'mac', log: null,
} as unknown as TouchSetup

const kept = () => JSON.parse(localStorage.getItem('rocketwright.viewer') ?? '{}') as Record<string, unknown>

function choose(el: HTMLElement, menu: string, item: string): void {
  el.querySelector<HTMLButtonElement>(`[data-smv-menu="${menu}"]`)!.click()
  el.querySelector<HTMLElement>(`[data-smv-menu-panel="${menu}"] [data-smv-item="${item}"]`)!.click()
}

const titles = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>('[data-smv-menu]')].map((menu) => menu.textContent)

beforeEach(() => {
  FakeSocket.reset()
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 1206, height: 2622, close: vi.fn() })))
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ drawImage: vi.fn() })) as never
})

afterEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('the language the viewer speaks', () => {
  it('is English where the browser reads English, and French where it reads French', () => {
    expect(titles(setup().view.el)).toEqual(['Edit', 'Device', 'View'])
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['fr-FR', 'fr', 'en'])
    const { view, $ } = setup()
    expect(titles(view.el)).toEqual(['Édition', 'Appareil', 'Présentation'])
    expect(view.el.lang).toBe('fr')
    expect($('[data-smv-name]').textContent).toBe('Simulateur iOS')
    expect($('[data-smv-state]').textContent).toBe('Arrêté')
    expect($<HTMLElement>('[data-smv="home"]').title).toBe('Accueil')
    expect($('[data-smv="lock"]').getAttribute('aria-label')).toBe('Verrouiller')
    expect($<HTMLElement>('[data-smv="screenshot"]').title).toBe('Enregistrer une capture d’écran')
    expect($<HTMLElement>('[data-smv="settings"]').title).toBe('Réglages')
    expect($('[data-smv-canvas]').getAttribute('aria-label')).toBe('Écran du simulateur iOS')
    expect($('.smv-tools').getAttribute('aria-label')).toBe('Commandes de l’appareil')
    expect($('[data-smv="devices"] .smv-sr').textContent).toBe('Choisir un appareil\u00a0: ')
  })

  it('is the one a host asks for, before a person\'s last pick, before the browser\'s', () => {
    localStorage.setItem('rocketwright.viewer', JSON.stringify({ lang: 'fr' }))
    expect(titles(setup().view.el)[0]).toBe('Édition')
    expect(titles(setup({ lang: 'en' }).view.el)[0]).toBe('Edit')
    expect(titles(setup({ lang: 'auto' }).view.el)[0]).toBe('Edit')
    // A language the viewer does not speak is as good as none asked for.
    expect(titles(setup({ lang: 'de' }).view.el)[0]).toBe('Édition')
    localStorage.setItem('rocketwright.viewer', JSON.stringify({ lang: 'klingon' }))
    expect(titles(setup().view.el)[0]).toBe('Edit')
    expect(titles(setup({ lang: 'fr-CA' }).view.el)[0]).toBe('Édition')
  })

  it('is picked in View > Language, each language under its own name, and kept for next time', async () => {
    const onLang = vi.fn()
    const { view, $ } = await live({ onLang })
    expect(onLang.mock.calls).toEqual([['en']])
    $<HTMLButtonElement>('[data-smv-menu="view"]').click()
    const panel = $<HTMLElement>('[data-smv-menu-panel="view"]')
    const languages = [...panel.querySelectorAll<HTMLElement>('[data-smv-item^="lang-"]')]
    expect(panel.querySelector('.smv-picker-group')!.textContent).toBe('Language')
    expect(panel.querySelector('.smv-picker-group')!.nextElementSibling).toBe(languages[0])
    expect(languages.map((row) => [row.textContent, row.getAttribute('role'), row.getAttribute('aria-checked')])).toEqual([
      ['Automatic', 'menuitemradio', 'true'], ['English', 'menuitemradio', 'false'], ['Français', 'menuitemradio', 'false'],
    ])
    languages[2].click()
    expect(view.el.lang).toBe('fr')
    expect(onLang).toHaveBeenLastCalledWith('fr')
    expect(kept().lang).toBe('fr')
    expect(titles(view.el)).toEqual(['Édition', 'Appareil', 'Présentation'])
    // The menu is drawn in French as it opens again, its languages still under their own names.
    $<HTMLButtonElement>('[data-smv-menu="view"]').click()
    expect(panel.getAttribute('aria-label')).toBe('Présentation')
    expect(panel.querySelector('.smv-picker-group')!.textContent).toBe('Langue')
    expect([...panel.querySelectorAll<HTMLElement>('[data-smv-item] span')].map((row) => row.textContent)).toEqual([
      'Zoom avant', 'Zoom arrière', 'Adapter à la fenêtre', 'Taille réelle', 'Afficher le cadre de l’appareil',
      'Suivre le système', 'Clair', 'Sombre', 'Automatique', 'English', 'Français',
    ])
    expect(panel.querySelector('[data-smv-item="lang-fr"]')!.getAttribute('aria-checked')).toBe('true')
    panel.querySelector<HTMLElement>('[data-smv-item="lang-auto"]')!.click()
    expect([view.el.lang, kept().lang, onLang.mock.calls.length]).toEqual(['en', 'auto', 3])
    // The next viewer on this browser starts where this one was left.
    choose(view.el, 'view', 'lang-fr')
    const next = setup()
    expect([next.view.el.lang, titles(next.view.el)[2]]).toEqual(['fr', 'Présentation'])
  })

  it('changes where the viewer stands: the bar, the toolbar, the menus, the device, without reconnecting', async () => {
    const { view, $, transport } = await live()
    $<HTMLButtonElement>('[data-smv="zoom-actual"]').click()
    const side = $<HTMLElement>('[data-smv-side="lock"]')
    expect([side.title, $<HTMLElement>('[data-smv="stop"]').title]).toEqual(['Side button', 'Let the simulator go'])
    $<HTMLButtonElement>('[data-smv="appearance"]').click()
    expect($<HTMLElement>('[data-smv="appearance"]').title).toBe('Light appearance')
    const sockets = FakeSocket.instances.length

    view.setLang('fr')
    expect($<HTMLElement>('[data-smv="appearance"]').title).toBe('Apparence claire')
    expect($('[data-smv="appearance"]').getAttribute('aria-label')).toBe('Apparence claire')
    expect([side.title, side.getAttribute('aria-label')]).toEqual(['Bouton latéral', 'Bouton latéral'])
    expect($<HTMLElement>('[data-smv="stop"]').title).toBe('Libérer le simulateur')
    expect($<HTMLElement>('[data-smv="place"]').title).toBe('Détacher dans une fenêtre')
    expect($<HTMLElement>('[data-smv-page]').title).toBe('Ouvrir dans une page à part')
    expect($<HTMLElement>('[data-smv="devices"]').title).toBe('Choisir un appareil')
    expect($('[data-smv="devices"]').hasAttribute('aria-label')).toBe(false)
    expect($('[data-smv-state]').textContent).toBe('Prêt')
    expect($('[data-smv-name]').textContent).toBe('iPhone 17 Pro · iOS 26.5')
    const level = $<HTMLElement>('[data-smv-zoom-level]')
    expect([level.textContent, level.title]).toEqual(['100\u202f%', 'Zoom 100\u202f%'])
    expect([$('[data-smv="zoom-actual"]').textContent, $<HTMLElement>('[data-smv="zoom-actual"]').title])
      .toEqual(['100\u202f%', 'Taille réelle'])
    expect($('.smv-zoom').getAttribute('aria-label')).toBe('Zoom')
    // Nothing was asked of the server, and the screen is the one it was.
    expect([FakeSocket.instances.length, transport.start.mock.calls.length, view.connected()]).toEqual([sockets, 1, true])

    $<HTMLButtonElement>('[data-smv="stop"]').click()
    expect(said(view)).toBe('Le simulateur est libéré\u202f; son appareil reste en marche pour la prochaine fois.Démarrer le simulateur')
    expect($('[data-smv-state]').textContent).toBe('Arrêté')
    // What is said of no screen is said again, with its way on.
    view.setLang('en')
    expect(said(view)).toBe('The simulator is let go; its device keeps running for next time.Start the simulator')
    expect([$('[data-smv-state]').textContent, $<HTMLElement>('[data-smv="stop"]').title]).toEqual(['Stopped', 'Let the simulator go'])
    // Asked for nothing, it goes back to a person's pick, else the browser's.
    localStorage.setItem('rocketwright.viewer', JSON.stringify({ lang: 'fr' }))
    view.setLang(null)
    expect(view.el.lang).toBe('fr')
    view.setLang('tlh')
    expect(view.el.lang).toBe('fr')
    localStorage.clear()
    view.setLang(null)
    expect(view.el.lang).toBe('en')
  })

  it('says a device that starts, stalls, fails and reconnects in French, as it happens', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
    const { view, $ } = setup({ lang: 'fr' })
    view.setActive(true)
    await flush()
    expect(said(view)).toBe('Démarrage de iPhone 17 Pro… 2\u00a0s')
    vi.advanceTimersByTime(1000)
    expect(said(view)).toBe('Démarrage de iPhone 17 Pro… 3\u00a0s')
    // The count goes on in the language picked while it runs.
    view.setLang('en')
    expect(said(view)).toBe('Starting iPhone 17 Pro… 3s')
    vi.advanceTimersByTime(1000)
    expect(said(view)).toBe('Starting iPhone 17 Pro… 4s')
    view.setLang('fr')
    socket().open()
    socket().message(HELLO)
    socket().message({ type: 'status', ...DEVICE, state: 'stalled', reason: null })
    expect([said(view), $('[data-smv-state]').textContent]).toEqual(['Le simulateur ne répond plus. Reconnexion…', 'Reconnexion'])
    socket().message({ type: 'status', ...DEVICE, state: 'failed', reason: null })
    expect(said(view)).toBe('Le simulateur n’a pas pu démarrer.Réessayer')
    // A reason the server gives is said as it gave it.
    socket().message({ type: 'status', ...DEVICE, state: 'failed', reason: 'CoreSimulator is not answering' })
    expect(said(view)).toBe('CoreSimulator is not answeringRéessayer')
    socket().message({ type: 'status', ...DEVICE, state: 'stopped' })
    expect(said(view)).toBe('Le simulateur est arrêté.Démarrer le simulateur')
    socket().message({ type: 'status', ...DEVICE, state: 'ready' })
    socket().end(1006, '')
    expect(said(view)).toBe('La connexion au simulateur a pris fin. Reconnexion…')
    view.setLang('en')
    expect(said(view)).toBe('The connection to the simulator ended. Reconnecting…')
  })

  it('says who is using the device, what a mirror cannot do and what is being read, in French', async () => {
    const { view, $ } = await live({ lang: 'fr' }, { ...HELLO, connector: 'simctl', capabilities: VIEW_ONLY })
    const mode = $<HTMLElement>('[data-smv-mode]')
    expect([mode.textContent, mode.title]).toEqual(['Affichage seul', 'Le connecteur simctl affiche l’écran mais ne peut pas le toucher.'])
    socket().message({ type: 'status', ...DEVICE, busy: 'installing', app_hierarchy: { name: 'Notes', bundle_id: 'dev.notes', sdk_version: '1.2' } })
    expect($('[data-smv-badge]').textContent).toBe('Occupé\u00a0: installing')
    expect($<HTMLElement>('[data-smv-app]').title).toBe('Notes (dev.notes) partage sa hiérarchie de vues via le SDK 1.2 de Rocketwright')
    socket().message({
      type: 'agent', id: 'a1', phase: 'working', agent: { key: 'k', title: 'Claude Code' }, activity: '', color: '', park_after_ms: 30000,
    })
    const badge = $<HTMLElement>('[data-smv-badge]')
    expect([badge.textContent, badge.title]).toEqual(['Claude Code utilise cet appareil', 'Claude Code utilise cet appareil'])
    view.setLang('en')
    expect([badge.textContent, mode.textContent]).toEqual(['Claude Code is using this device', 'View only'])
    expect($<HTMLElement>('[data-smv-app]').title).toContain('shares its view hierarchy')
  })

  it('closes a menu drawn in the old language, and draws the picker in the new one', async () => {
    const devices = vi.fn(async () => [
      { udid: 'U1', name: 'iPhone 17 Pro', runtime: 'iOS 26.5', state: 'Booted', created: true, kind: 'simulator',
        connection: null, detail: null, usable: true, agents: [{ key: 'k', title: 'Claude Code' }] },
      { udid: 'P1', name: 'Test iPhone', runtime: 'iOS 26.3', state: 'Connected', created: false, kind: 'physical',
        connection: 'usb', detail: null, usable: true },
      { udid: 'A1', name: 'Pixel 9', runtime: 'Android 16', state: 'Booted', created: false, kind: 'android',
        connection: null, detail: null, usable: true },
      { udid: 'A2', name: 'Pixel 8', runtime: 'API 36', state: 'Shutdown', created: false, kind: 'android',
        connection: null, detail: "its system image is not installed: install it in Android Studio's SDK Manager",
        detail_code: 'system_image_missing', usable: false },
      { udid: 'P2', name: 'Old iPad', runtime: 'iPadOS 18', state: 'Disconnected', created: false, kind: 'physical',
        connection: null, detail: 'Not connected', detail_code: 'not_connected', usable: false },
      { udid: 'M1', name: 'Notes', runtime: 'macOS 26', state: 'Running', created: false, kind: 'mac',
        connection: null, detail: null, usable: true },
    ])
    const { view, $ } = await live({ transport: { devices, use: vi.fn() } })
    const picker = $<HTMLElement>('[data-smv-picker]')
    $<HTMLButtonElement>('[data-smv="devices"]').click()
    expect(picker.textContent).toBe('Looking for devices…')
    await flush()
    expect(picker.hidden).toBe(false)
    view.setLang('fr')
    expect(picker.hidden).toBe(true)
    $<HTMLButtonElement>('[data-smv="devices"]').click()
    expect(picker.textContent).toBe('Recherche d’appareils…')
    await flush()
    expect([...picker.querySelectorAll('.smv-picker-group')].map((group) => group.textContent))
      .toEqual(['Afficher dans cet onglet', 'iOS 26.5', 'iPhone et iPad', 'Android', 'Apps macOS'])
    expect([...picker.querySelectorAll('[data-smv-udid] .smv-choice-about')].map((row) => row.textContent)).toEqual([
      'iOS 26.5 · utilisé par Claude Code', 'iOS 26.3 · USB', 'iPadOS 18 · Non connecté', 'Android 16 · Émulateur',
      'API 36 · Émulateur · Image système non installée\u00a0: installez-la dans le SDK Manager d’Android Studio',
      'macOS 26',
    ])
    expect([...picker.querySelectorAll('[role="menuitem"]')].map((row) => row.textContent)).toEqual(['Utiliser pour le projet', 'Éteindre cet appareil'])
    $<HTMLButtonElement>('[data-smv="devices"]').click()
    devices.mockRejectedValueOnce(new Error(''))
    $<HTMLButtonElement>('[data-smv="devices"]').click()
    await flush()
    expect(picker.textContent).toBe('Impossible de lister les appareils.')
  })

  it('says a note again where it stands when it is the viewer\'s own, and leaves the server\'s words alone', async () => {
    const calls = {
      startRecording: vi.fn(async () => UNDER_WAY), stopRecording: vi.fn(async () => KEPT), recordingFile: vi.fn(),
      changeDevice: vi.fn(async () => 'contrast: on'), touch: vi.fn(async () => OFFER), setUpTouch: vi.fn(async () => OFFER),
    }
    const { view, $ } = await live({ transport: calls as Partial<RocketwrightTransport> })
    const note = $<HTMLElement>('[data-smv-note]')
    const record = $<HTMLButtonElement>('[data-smv="record"]')
    const size = $<HTMLButtonElement>('[data-smv="record-size"]')
    // Nothing shown yet: nothing to say again.
    view.setLang('fr')
    expect(note.hidden).toBe(true)
    expect([record.title, size.title]).toEqual(['Enregistrer l’écran', 'Taille de l’enregistrement\u00a0: Taille d’origine'])
    size.click()
    const sizes = $<HTMLElement>('[data-smv-record-size]')
    expect(sizes.getAttribute('aria-label')).toBe('Taille de l’enregistrement')
    expect(sizes.textContent).toContain('Pour une pull requestMP4, 450\u00a0px de large')
    view.setLang('en')
    // An open menu follows.
    expect(sizes.textContent).toContain('For a pull requestMP4, 450 wide')
    sizes.querySelector<HTMLElement>('[data-smv-size="both"]')!.click()
    view.setLang('fr')
    expect(record.title).toBe('Enregistrer l’écran, avec une copie pour une pull request')

    record.click()
    await flush()
    expect([record.title, $('[data-smv-rec]').textContent]).toEqual(['Arrêter l’enregistrement (lancé par person)', 'REC 0:00'])
    record.click()
    await flush()
    expect([...note.querySelectorAll('p')].map((line) => line.textContent)).toEqual([
      'Enregistrement de Test iPhone\u00a0: 0:10.', 'kept as recorded',
      'Aucune copie pour une pull request n’a été conservée\u00a0: ce serveur n’en produit pas.',
    ])
    expect(note.querySelector('[data-smv-save]')!.textContent).toBe('Enregistrer en MP4 · 900×1952 · 4,3\u00a0Mo')
    expect(note.querySelector<HTMLElement>('[data-smv-note-close]')!.title).toBe('Fermer')
    view.setLang('en')
    expect(note.querySelector('p')!.textContent).toBe('Recorded 0:10 of Test iPhone.')
    expect(note.querySelector('[data-smv-save]')!.textContent).toBe('Save MP4 · 900×1952 · 4.3 MB')
    expect(note.querySelector<HTMLElement>('[data-smv-note-close]')!.title).toBe('Close')

    // The Display menu, open, is drawn again; what the device answered is the server's.
    view.setLang('fr')
    const display = $<HTMLElement>('[data-smv-display]')
    $<HTMLButtonElement>('[data-smv="display"]').click()
    expect(display.getAttribute('aria-label')).toBe('Affichage')
    expect(display.textContent).toBe('Barre d’état de démonstrationTexte plus grandTexte plus petitAugmenter le contrasteTexte\u00a0: grand')
    view.setLang('en')
    expect(display.textContent).toBe('Demo status barLarger textSmaller textIncrease contrastText: large')
    display.querySelector<HTMLElement>('[data-smv-display="contrast"]')!.click()
    await flush()
    view.setLang('fr')
    expect(note.querySelector('p')!.textContent).toBe('contrast: on')
    calls.changeDevice.mockRejectedValueOnce(new Error(''))
    display.querySelector<HTMLElement>('[data-smv-display="contrast"]')!.click()
    await flush()
    expect(note.querySelector('p')!.textContent).toBe('L’appareil n’a pas changé.')
    // A note closed stays closed.
    note.querySelector<HTMLElement>('[data-smv-note-close]')!.click()
    view.setLang('en')
    expect(note.hidden).toBe(true)
  })

  it('sets touch up in French', async () => {
    const calls = { touch: vi.fn(async () => OFFER), setUpTouch: vi.fn(async () => { throw new Error('') }) }
    const phone = { ...DEVICE, kind: 'physical' as const, connection: 'usb' as const }
    const { view, $ } = setup({ lang: 'fr', transport: calls as Partial<RocketwrightTransport> })
    view.setActive(true)
    await flush()
    socket().open()
    socket().message({ ...HELLO, connector: 'devicectl', capabilities: VIEW_ONLY })
    socket().message({ type: 'status', ...phone })
    expect($('[data-smv-kind]').textContent).toBe('Appareil réel · USB')
    const mode = $<HTMLButtonElement>('[data-smv-mode]')
    expect(mode.textContent).toBe('Configurer le toucher')
    mode.click()
    await flush()
    const note = $<HTMLElement>('[data-smv-note]')
    expect(note.textContent).toBe('Le toucher est en cours de configuration.Signé par l’équipe TESTTEAM01\u00a0: la seule équipe de ce Mac.Configurer le toucher')
    view.setLang('en')
    expect(note.textContent).toBe('Touch is being set up.Signed by team TESTTEAM01: the only team on this Mac.Set up touch')
    view.setLang('fr')
    note.querySelector<HTMLElement>('[data-smv-touch="set-up"]')!.click()
    await flush()
    expect(note.textContent).toBe('Impossible de configurer le toucher.')
    expect($<HTMLElement>('[data-smv="stop"]').title).toBe('Libérer l’appareil')
  })

  it('changes the settings panel where it stands, a half-made change kept', async () => {
    const settings = vi.fn(async () => settingsView({
      sections: [
        { id: '', title: 'General', doc: 'Whether devices are brought up at all.' },
        { id: 'stream', title: 'Stream', doc: 'How the screen is sent to a viewer.' },
        { id: 'server', title: 'Server', doc: 'Where the daemon listens.' },
        { id: 'plugins', title: 'Plug-ins', doc: 'What others add.' },
      ],
    }))
    const { view, $ } = await live({ transport: { settings, changeSettings: vi.fn() } })
    $<HTMLButtonElement>('[data-smv="settings"]').click()
    const panel = $<HTMLElement>('[data-smv-settings]')
    expect(panel.textContent).toBe('Loading settings…')
    view.setLang('fr')
    expect(panel.textContent).toBe('Chargement des réglages…')
    await flush()
    const tabs = () => [...panel.querySelectorAll('[role="tab"]')].map((tab) => tab.textContent)
    // A section the viewer knows is called in French; one it does not, and every description, as the server wrote it.
    expect(tabs()).toEqual(['Général', 'Flux', 'Serveur', 'Plug-ins'])
    expect(panel.querySelector('.smv-pane-doc')!.textContent).toBe('Whether devices are brought up at all.')
    expect(panel.querySelector('.smv-settings-title')!.textContent).toBe('Réglages')
    expect(panel.querySelector('[role="tablist"]')!.getAttribute('aria-label')).toBe('Sections des réglages')
    const enabled = panel.querySelector<HTMLInputElement>('[data-smv-setting="enabled"] input')!
    enabled.click()
    const save = panel.querySelector<HTMLButtonElement>('.smv-button-primary')!
    expect([save.textContent, save.disabled]).toEqual(['Enregistrer', false])
    expect([...panel.querySelectorAll('.smv-target')].map((target) => target.textContent)).toEqual([' Ce projet', ' Tous les projets'])

    view.setLang('en')
    expect(tabs()).toEqual(['General', 'Stream', 'Server', 'Plug-ins'])
    expect(panel.querySelector<HTMLInputElement>('[data-smv-setting="enabled"] input')).toBe(enabled)
    expect([enabled.checked, save.textContent, save.disabled]).toEqual([false, 'Save', false])
    expect([...panel.querySelectorAll('[data-smv-setting="stream.fps"] .smv-chip, [data-smv-setting="stream.fps"] .smv-link')]
      .map((chip) => chip.textContent)).toEqual(['from this project', 'Reset'])
    view.setLang('fr')
    expect([...panel.querySelectorAll('[data-smv-setting="stream.fps"] .smv-chip, [data-smv-setting="stream.fps"] .smv-link')]
      .map((chip) => chip.textContent)).toEqual(['depuis ce projet', 'Réinitialiser'])
    expect([...panel.querySelectorAll('[data-smv-setting="server.port"] .smv-chip')].map((chip) => chip.textContent))
      .toEqual(['valeur par défaut', 's’applique après un redémarrage', 'tout le daemon', 'à confirmer dans le terminal'])
    expect(panel.querySelector('[data-smv-setting="stream.quality"] .smv-chip')!.textContent).toBe('depuis ROCKETWRIGHT_STREAM_QUALITY')
    expect(panel.querySelector<HTMLElement>('.smv-settings-head .smv-icon')!.title).toBe('Fermer les réglages')
  })

  it('says why settings could not be read or saved: the server\'s reason, else its own', async () => {
    const refusal = Object.assign(new Error('refused'), {
      body: { detail: 'Type the code shown at the terminal.', errors: [], confirmation: { summary: 'server.port → 7500' } },
    })
    const changeSettings = vi.fn()
      .mockRejectedValueOnce(refusal).mockRejectedValueOnce(new Error('')).mockRejectedValueOnce(new Error('The daemon is away.'))
    const settings = vi.fn(async () => settingsView())
    const { view, $ } = await live({ lang: 'fr', transport: { settings, changeSettings } })
    $<HTMLButtonElement>('[data-smv="settings"]').click()
    await flush()
    const panel = $<HTMLElement>('[data-smv-settings]')
    const status = () => panel.querySelector('.smv-settings-status')!.textContent
    const save = () => panel.querySelector<HTMLButtonElement>('.smv-button-primary')!
    panel.querySelector<HTMLInputElement>('[data-smv-setting="enabled"] input')!.click()
    save().click()
    expect(status()).toBe('Enregistrement…')
    await flush()
    expect(status()).toBe('En attente du code pour\u00a0: server.port → 7500')
    expect(panel.querySelector('.smv-confirm .smv-button')!.textContent).toBe('Confirmer')
    expect(panel.querySelector('.smv-confirm input')!.getAttribute('aria-label')).toBe('Code de confirmation')
    view.setLang('en')
    expect(status()).toBe('Waiting for the code for: server.port → 7500')
    view.setLang('fr')
    save().click()
    await flush()
    expect(status()).toBe('Impossible d’enregistrer les réglages.')
    save().click()
    await flush()
    // The server's own words are left as they are, whatever the language.
    expect(status()).toBe('The daemon is away.')
    view.setLang('en')
    expect(status()).toBe('The daemon is away.')
    view.setLang('fr')
    $<HTMLButtonElement>('[data-smv="settings"]').click()
    settings.mockRejectedValueOnce(new Error('')).mockRejectedValueOnce(new Error('No such scope.'))
    $<HTMLButtonElement>('[data-smv="settings"]').click()
    await flush()
    expect(panel.textContent).toBe('Impossible de lire les réglages.')
    $<HTMLButtonElement>('[data-smv="settings"]').click()
    $<HTMLButtonElement>('[data-smv="settings"]').click()
    await flush()
    expect(panel.textContent).toBe('No such scope.')
  })
})

describe('<rocket-wright lang>', () => {
  const transport = () => ({
    status: vi.fn(), start: vi.fn(async () => ({ device: null, ticket: 'tk' })), stop: vi.fn(async () => true),
    devices: vi.fn(async () => []), choose: vi.fn(), socketUrl: vi.fn(() => 'ws://host/screen'),
  }) as unknown as RocketwrightTransport

  it('speaks the language its attribute names, and changes it without starting afresh', async () => {
    defineRocketwrightElement()
    expect(RocketwrightElement.observedAttributes).toContain('lang')
    const el = document.createElement(ELEMENT_NAME) as RocketwrightElement
    el.setAttribute('lang', 'fr')
    el.transport = transport()
    document.body.appendChild(el)
    await flush()
    const view = el.view!
    expect([view.el.lang, titles(view.el)[0]]).toEqual(['fr', 'Édition'])
    el.setAttribute('lang', 'en')
    expect([el.view, view.el.lang, titles(view.el)[0]]).toEqual([view, 'en', 'Edit'])
    // Without it, the viewer speaks what a person last picked.
    localStorage.setItem('rocketwright.viewer', JSON.stringify({ lang: 'fr' }))
    el.removeAttribute('lang')
    expect([el.view, view.el.lang]).toEqual([view, 'fr'])
    el.remove()
    // Set while it is not on the page, it is read as the element comes back.
    el.setAttribute('lang', 'en')
    document.body.appendChild(el)
    expect(el.view!.el.lang).toBe('en')
  })
})
