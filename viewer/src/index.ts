// SPDX-License-Identifier: Apache-2.0
/** `@soflution/phonesimulator`: the PhoneSimulator viewer, as a function, a custom element, and the protocol's types. */
export { createViewer } from './viewer'
export type { Placement, ViewerOptions, ViewerState, ViewHandle } from './viewer'
export { createHttpTransport, TransportError } from './http-transport'
export type { HttpTransportOptions } from './http-transport'
export type { PhoneSimulatorTransport } from './transport'
export { definePhoneSimulatorElement, ELEMENT_NAME, PhoneSimulatorElement } from './element'
export { ICON_NAMES, lucideSvg } from './icons'
export type { IconName, IconRenderer } from './icons'
export { VIEWER_CSS } from './styles'
export { PAINT_QUEUE_MAX } from './screen-canvas'
export type { FrameObserver } from './screen-canvas'
export * from './protocol.generated'
