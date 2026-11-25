// SPDX-License-Identifier: Apache-2.0
/**
 * A screenshot of the device's screen as the viewer shows it: the last picture drawn, at the device's own pixels, as a
 * PNG -- saved as a file, or copied to the clipboard. It is taken from the viewer's canvas, so it needs nothing of the
 * server and works on any device the viewer shows.
 */
import type { Device } from './protocol.generated'

export interface ClipboardLike {
  write(items: ClipboardItem[]): Promise<void>
}

/** The screen's last picture as a PNG; null while nothing has been drawn. */
export function screenPng(canvas: HTMLCanvasElement): Promise<Blob | null> {
  if (canvas.width === 0 || canvas.height === 0) return Promise.resolve(null)
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
}

const two = (value: number) => String(value).padStart(2, '0')

/** A screenshot's file name, as the iOS Simulator names its own: the device and when, never a path. */
export function screenshotName(device: Pick<Device, 'name'> | null, at: Date): string {
  const name = (device?.name ?? 'Device').replace(/[\\/:*?"<>|]+/g, '-').trim() || 'Device'
  const day = `${at.getFullYear()}-${two(at.getMonth() + 1)}-${two(at.getDate())}`
  const time = `${two(at.getHours())}.${two(at.getMinutes())}.${two(at.getSeconds())}`
  return `Screenshot - ${name} - ${day} at ${time}.png`
}

/** The clipboard, where this page may write a picture to it; null where it may not. */
export function imageClipboard(nav: Navigator = navigator): ClipboardLike | null {
  const clipboard = nav.clipboard as Partial<Clipboard> | undefined
  return typeof clipboard?.write === 'function' && typeof ClipboardItem === 'function' ? (clipboard as ClipboardLike) : null
}

export interface ScreenshotOptions {
  canvas: HTMLCanvasElement
  device(): Pick<Device, 'name'> | null
  /** Say what happened, over the screen. */
  say(message: string): void
  clipboard?: ClipboardLike | null
  now?(): Date
}

export interface Screenshots {
  /** Whether the screenshot can be copied here. */
  readonly canCopy: boolean
  save(): Promise<void>
  copy(): Promise<void>
}

const NOTHING = 'There is no screen to capture yet.'

export function createScreenshots(options: ScreenshotOptions): Screenshots {
  const clipboard = options.clipboard === undefined ? imageClipboard() : options.clipboard
  const now = options.now ?? (() => new Date())

  return {
    canCopy: clipboard !== null,
    async save() {
      const png = await screenPng(options.canvas)
      if (!png) return options.say(NOTHING)
      const name = screenshotName(options.device(), now())
      const url = URL.createObjectURL(png)
      const link = options.canvas.ownerDocument.createElement('a')
      link.href = url
      link.download = name
      link.click()
      // Revoked once the download has had its chance to start.
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      options.say(`Screenshot saved as ${name}.`)
    },
    async copy() {
      if (!clipboard) return options.say('This page cannot copy a picture to the clipboard.')
      const png = await screenPng(options.canvas)
      if (!png) return options.say(NOTHING)
      try {
        await clipboard.write([new ClipboardItem({ 'image/png': png })])
        options.say('Screenshot copied.')
      } catch (error) {
        options.say(`The screenshot could not be copied: ${(error as Error).message || 'the clipboard refused it'}.`)
      }
    },
  }
}
