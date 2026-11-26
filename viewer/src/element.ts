// SPDX-License-Identifier: Apache-2.0
/**
 * `<rocket-wright>`: the viewer as a custom element, for a page that would rather write markup than script.
 *
 *     <rocket-wright server="http://127.0.0.1:7466" scope="demo" token="…" placement="page"></rocket-wright>
 *
 * `device` names one of the scope's devices, by UDID, to show instead of its own; without it the element follows the
 * scope's own device. A person's Show in this tab and Follow the project set and remove it, and say so with a
 * `rocketwright:device` event.
 *
 * `lang` is the language the viewer speaks -- `fr`, `en`, or `auto` for the browser's own -- changed without starting
 * afresh; without it the viewer speaks what a person last picked in its View menu, else the browser's.
 *
 * It draws in an open shadow root with its own styles, themed by `--rocketwright-*` custom properties and styled further
 * through `::part(bar)`, `::part(stage)` and `::part(screen)`. `token` is a viewer token -- what an embed ticket is
 * spent for -- or absent where the page's own cookie or origin lets it in; a host with its own API client sets the
 * `transport` property instead. It tells the page what happens with `rocketwright:state`, `rocketwright:place`,
 * `rocketwright:device` and `rocketwright:close` events.
 */
import { createHttpTransport } from './http-transport'
import type { RocketwrightTransport } from './transport'
import { createViewer, type Placement, type ViewHandle } from './viewer'

export const ELEMENT_NAME = 'rocket-wright'
const PLACEMENTS: readonly Placement[] = ['dock', 'window', 'page']

const placementOf = (value: string | null): Placement =>
  PLACEMENTS.includes(value as Placement) ? (value as Placement) : 'page'

export class RocketwrightElement extends HTMLElement {
  static readonly observedAttributes = ['server', 'scope', 'token', 'placement', 'device', 'lang']

  #view: ViewHandle | null = null
  #transport: RocketwrightTransport | null = null
  /** The device a person picked, being written to `device`: already shown, so not drawn again. */
  #picked = false

  constructor() {
    super()
    this.attachShadow({ mode: 'open' })
  }

  get view(): ViewHandle | null {
    return this.#view
  }

  get transport(): RocketwrightTransport | null {
    return this.#transport
  }

  set transport(value: RocketwrightTransport | null) {
    this.#transport = value
    if (this.isConnected) this.#render()
  }

  connectedCallback(): void {
    this.#render()
  }

  disconnectedCallback(): void {
    this.#view?.destroy()
    this.#view = null
  }

  attributeChangedCallback(name: string, previous: string | null, value: string | null): void {
    if (previous === value || !this.isConnected || this.#picked) return
    if (name === 'placement' && this.#view) this.#view.setPlacement(placementOf(value))
    else if (name === 'lang' && this.#view) this.#view.setLang(value)
    else this.#render()
  }

  #tell(type: string, detail?: unknown): void {
    this.dispatchEvent(new CustomEvent(`rocketwright:${type}`, { detail, bubbles: true, composed: true }))
  }

  #render(): void {
    this.#view?.destroy()
    this.#view = null
    const scope = this.getAttribute('scope')
    const token = this.getAttribute('token')
    const device = this.getAttribute('device') || null
    const transport = this.#transport
      ?? (scope ? createHttpTransport({ baseUrl: this.getAttribute('server') ?? '', scope, token: () => token }) : null)
    if (!transport) return
    const placement = placementOf(this.getAttribute('placement'))
    this.#view = createViewer(this.shadowRoot!, {
      transport,
      placement,
      device,
      lang: this.getAttribute('lang') ?? undefined,
      onPlace: placement === 'page' ? undefined : (next) => this.#tell('place', { placement: next }),
      onClose: () => this.#tell('close'),
      onState: (state) => this.#tell('state', state),
      onDevice: (udid) => {
        this.#picked = true
        if (udid) this.setAttribute('device', udid)
        else this.removeAttribute('device')
        this.#picked = false
        this.#tell('device', { udid })
      },
    })
    this.#view.setActive(true)
  }
}

/** Define `<rocket-wright>` -- or another name -- once; a name already taken is left alone. */
export function defineRocketwrightElement(name: string = ELEMENT_NAME, registry: CustomElementRegistry = customElements): void {
  if (!registry.get(name)) registry.define(name, class extends RocketwrightElement {})
}
