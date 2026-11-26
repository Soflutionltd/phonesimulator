// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FakeSocket } from '../test-support/fake-socket'
import { DEVICE, live, socket } from '../test-support/viewer-harness'

beforeEach(() => {
  FakeSocket.reset()
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 1206, height: 2622, close: vi.fn() })))
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ drawImage: vi.fn() })) as never
})

afterEach(() => {
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('a device other projects share', () => {
  it('says so in the bar and names the others on hover, never this project', async () => {
    const { $ } = await live({ project: 'Notes' })
    const chip = $<HTMLElement>('[data-smv-shared]')
    socket().message({ type: 'status', ...DEVICE })
    expect(chip.hidden).toBe(true)
    socket().message({ type: 'status', ...DEVICE, projects: ['Courly', 'Notes', 'Notes · ios'] })
    expect(chip.hidden).toBe(false)
    expect(chip.textContent).toBe('Shared · 3 projects')
    expect(chip.title).toBe('Also open in: Courly, Notes · ios')
    socket().message({ type: 'status', ...DEVICE, projects: ['Notes'] })
    expect(chip.hidden).toBe(true)
    expect(chip.title).toBe('')
  })

  it('names every project when the view does not know its own', async () => {
    const { $ } = await live()
    socket().message({ type: 'status', ...DEVICE, projects: ['<b>Courly</b>', 'Notes'] })
    const chip = $<HTMLElement>('[data-smv-shared]')
    expect(chip.title).toBe('Also open in: <b>Courly</b>, Notes')
    expect(chip.querySelector('b')).toBeNull()
  })
})
