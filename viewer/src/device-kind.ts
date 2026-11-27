// SPDX-License-Identifier: Apache-2.0
/**
 * What a device is, as the viewer says it: a simulator, an Android emulator, or a real device -- an iPhone or iPad, or
 * an Android phone. A real device is never started or shut down by PhoneSimulator, only shown and let go; a simulator and an
 * emulator run on this Mac, and are.
 */
import { english, isMessageKey, type PlainKey, type Translate } from './i18n'
import type { Connection, Device, DeviceChoice, PanelButton } from './protocol.generated'

type Described = Pick<Device | DeviceChoice, 'kind' | 'connection'>

/** The buttons a device can press when its server does not say: Home and Lock, as the toolbar always had. */
export const DEFAULT_BUTTONS: readonly PanelButton[] = ['home', 'lock']

/** Whether a device is a real one, in a person's hand: an iPhone or iPad, or an Android phone. */
export function isReal(device: Described | null | undefined): boolean {
  return device?.kind === 'physical' || (device?.kind === 'android' && device.connection !== null)
}

/** How the viewer calls a device in a sentence: "the simulator", "the emulator", "the device". */
export function deviceNoun(device: Described | null | undefined): 'simulator' | 'emulator' | 'device' | 'app' {
  if (device?.kind === 'mac') return 'app'
  if (isReal(device)) return 'device'
  return device?.kind === 'android' ? 'emulator' : 'simulator'
}

/** How a real device reaches this Mac, as a person reads it. */
export function connectionLabel(connection: Connection | null, t: Translate = english): string {
  return t(connection === 'usb' ? 'connection.usb' : connection ? 'connection.wifi' : 'connection.none')
}

/** How an Android device reaches this Mac: a phone as it is connected, an emulator as one. */
export function androidReach(connection: Connection | null, t: Translate): string {
  return connection ? connectionLabel(connection, t) : t('connection.emulator')
}

/** What a person should know of a device before picking it: in the viewer's language when the server names it -- its
 * message is `detail.<name>` --, as the server says it otherwise: a name this viewer does not know, or an older server,
 * which names none. Null when nothing. */
export function detailLabel(choice: Pick<DeviceChoice, 'detail' | 'detail_code'>, t: Translate = english): string | null {
  const key = `detail.${choice.detail_code}`
  return choice.detail_code && isMessageKey(key) ? t(key as PlainKey) : choice.detail || null
}

/** The chip beside a device's name: what it is, when it is not a simulator, and how it is connected. */
export function kindChip(device: Described | null | undefined, t: Translate = english): string {
  if (device?.kind === 'mac') return t('chip.mac')
  if (device?.kind === 'physical') return t('chip.real', { how: connectionLabel(device.connection, t) })
  if (device?.kind === 'android') return t('chip.android', { how: androidReach(device.connection, t) })
  return ''
}

/** The buttons a device can press now: what its server says, else Home and Lock. */
export function buttonsOf(device: Device | null | undefined): readonly PanelButton[] {
  return device?.kind === 'mac' ? [] : device?.buttons ?? DEFAULT_BUTTONS
}
