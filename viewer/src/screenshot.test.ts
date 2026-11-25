// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createScreenshots, imageClipboard, screenPng, screenshotName } from './screenshot'

const AT = new Date(2026, 10, 25, 9, 5, 7)

function drawn(width = 402, height = 874): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  canvas.toBlob = (callback: BlobCallback, type?: string) => callback(new Blob(['png'], { type }))
  return canvas
}

class FakeItem {
  constructor(readonly items: Record<string, Blob>) {}
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('screenshots', () => {
  it('names a screenshot after the device and when, as a file name and never a path', () => {
    expect(screenshotName({ name: 'iPhone 17 Pro' }, AT)).toBe('Screenshot - iPhone 17 Pro - 2026-11-25 at 09.05.07.png')
    expect(screenshotName({ name: '../a/b:c' }, AT)).toBe('Screenshot - ..-a-b-c - 2026-11-25 at 09.05.07.png')
    expect(screenshotName({ name: ' / ' }, AT)).toBe('Screenshot - - - 2026-11-25 at 09.05.07.png')
    expect(screenshotName({ name: '' }, AT)).toBe('Screenshot - Device - 2026-11-25 at 09.05.07.png')
    expect(screenshotName(null, AT)).toBe('Screenshot - Device - 2026-11-25 at 09.05.07.png')
  })

  it('takes the last picture as a PNG, and nothing before one is drawn', async () => {
    expect(await screenPng(drawn(0, 0))).toBeNull()
    const png = await screenPng(drawn())
    expect(png?.type).toBe('image/png')
  })

  it('finds a clipboard that takes pictures, and none where the page has none', () => {
    const write = vi.fn()
    expect(imageClipboard({ clipboard: { write } } as unknown as Navigator)).toBeNull()
    vi.stubGlobal('ClipboardItem', FakeItem)
    expect(imageClipboard({ clipboard: { write } } as unknown as Navigator)).not.toBeNull()
    expect(imageClipboard({} as Navigator)).toBeNull()
    expect(imageClipboard()).toBeNull()
  })

  it('saves the screenshot as a download, says so, and lets its address go after', async () => {
    vi.useFakeTimers()
    const say = vi.fn()
    const create = vi.fn(() => 'blob:shot')
    const revoke = vi.fn()
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }))
    const clicked: HTMLAnchorElement[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { clicked.push(this) })
    const shots = createScreenshots({ canvas: drawn(), device: () => ({ name: 'iPhone 17 Pro' }), say, now: () => AT, clipboard: null })
    expect(shots.canCopy).toBe(false)
    await shots.save()
    expect([clicked[0].download, clicked[0].href]).toEqual(['Screenshot - iPhone 17 Pro - 2026-11-25 at 09.05.07.png', 'blob:shot'])
    expect(say).toHaveBeenCalledWith('Screenshot saved as Screenshot - iPhone 17 Pro - 2026-11-25 at 09.05.07.png.')
    vi.advanceTimersByTime(1000)
    expect(revoke).toHaveBeenCalledWith('blob:shot')
  })

  it('says there is nothing to capture before a picture is drawn', async () => {
    const say = vi.fn()
    const shots = createScreenshots({ canvas: drawn(0, 0), device: () => null, say, clipboard: { write: vi.fn() } })
    await shots.save()
    await shots.copy()
    expect(say.mock.calls).toEqual([['There is no screen to capture yet.'], ['There is no screen to capture yet.']])
  })

  it('copies the screenshot as a PNG, and says why when it could not', async () => {
    vi.stubGlobal('ClipboardItem', FakeItem)
    const say = vi.fn()
    const write = vi.fn(async () => undefined)
    const shots = createScreenshots({ canvas: drawn(), device: () => null, say, clipboard: { write } })
    expect(shots.canCopy).toBe(true)
    await shots.copy()
    const [[items]] = write.mock.calls as unknown as Array<[FakeItem[]]>
    expect(Object.keys(items[0].items)).toEqual(['image/png'])
    expect(say).toHaveBeenLastCalledWith('Screenshot copied.')
    write.mockRejectedValueOnce(new Error('Document is not focused'))
    await shots.copy()
    expect(say).toHaveBeenLastCalledWith('The screenshot could not be copied: Document is not focused.')
    write.mockRejectedValueOnce(new Error(''))
    await shots.copy()
    expect(say).toHaveBeenLastCalledWith('The screenshot could not be copied: the clipboard refused it.')
    await createScreenshots({ canvas: drawn(), device: () => null, say, clipboard: null }).copy()
    expect(say).toHaveBeenLastCalledWith('This page cannot copy a picture to the clipboard.')
  })

  it('uses the page clipboard when none is given', () => {
    expect(createScreenshots({ canvas: drawn(), device: () => null, say: vi.fn() }).canCopy).toBe(false)
  })
})
