/**
 * The reveal animation.
 *
 * It exists because the ANSWER cannot be streamed: the graph's compliance
 * gate is fail-closed, so text emitted as the model produced it could be
 * retracted after the user had already read it. Real progress streams
 * separately as stage events; this only paces text that is already approved.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTypewriter } from './useTypewriter'

const LONG = 'x'.repeat(3000)

function matchMedia(reduced: boolean) {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: reduced }))
}

describe('useTypewriter', () => {
  beforeEach(() => {
    matchMedia(false)
    let now = 0
    vi.stubGlobal('performance', { now: () => now })
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      now += 100
      return setTimeout(() => cb(now), 0) as unknown as number
    })
    vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('starts empty and ends with the whole text', async () => {
    const { result } = renderHook(() => useTypewriter('Merhaba dünya', true))
    expect(result.current).toBe('')
    await act(() => new Promise((r) => setTimeout(r, 60)))
    expect(result.current).toBe('Merhaba dünya')
  })

  it('reveals the text progressively rather than in one jump', async () => {
    // Frames are driven by hand: the point of the test is the INTERMEDIATE
    // state, which a timing-based assertion would race against.
    const pending: FrameRequestCallback[] = []
    let clock = 0
    vi.stubGlobal('performance', { now: () => clock })
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      pending.push(cb)
      return pending.length
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())

    const text = 'a'.repeat(200)
    const { result } = renderHook(() => useTypewriter(text, true))
    expect(result.current).toBe('')

    // One frame at 100ms: 900 chars/s => 90 of 200 characters.
    clock = 100
    await act(async () => { pending.shift()?.(clock) })
    expect(result.current.length).toBeGreaterThan(0)
    expect(result.current.length).toBeLessThan(text.length)

    clock = 1000
    await act(async () => { pending.shift()?.(clock) })
    expect(result.current).toBe(text)
  })

  it('shows everything at once when disabled', () => {
    const { result } = renderHook(() => useTypewriter('Merhaba', false))
    expect(result.current).toBe('Merhaba')
  })

  it('respects prefers-reduced-motion', () => {
    matchMedia(true)
    const { result } = renderHook(() => useTypewriter('Merhaba', true))
    expect(result.current).toBe('Merhaba')
  })

  it('does not animate a very long answer', () => {
    // Typing out a forty-row price table is a performance, not information.
    const { result } = renderHook(() => useTypewriter(LONG, true))
    expect(result.current).toBe(LONG)
  })

  it('survives a missing matchMedia', () => {
    vi.stubGlobal('matchMedia', undefined)
    const { result } = renderHook(() => useTypewriter('Merhaba', false))
    expect(result.current).toBe('Merhaba')
  })

  it('cancels its frame on unmount', () => {
    const cancel = vi.fn()
    vi.stubGlobal('cancelAnimationFrame', cancel)
    const { unmount } = renderHook(() => useTypewriter('Merhaba dünya', true))
    unmount()
    expect(cancel).toHaveBeenCalled()
  })
})
