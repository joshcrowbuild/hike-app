import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const STORAGE_KEY = 'adventure-planner:saved-trail-ids'

beforeEach(() => {
  localStorage.clear()
  vi.resetModules()
})

describe('savedTrails (client-side bookmark list, no backend/auth)', () => {
  it('starts with nothing saved when storage is empty', async () => {
    const { isTrailSaved } = await import('./savedTrails')
    expect(isTrailSaved('stony-man')).toBe(false)
  })

  it('toggles a trail saved and back to unsaved', async () => {
    const { isTrailSaved, toggleTrailSaved } = await import('./savedTrails')
    toggleTrailSaved('stony-man')
    expect(isTrailSaved('stony-man')).toBe(true)
    toggleTrailSaved('stony-man')
    expect(isTrailSaved('stony-man')).toBe(false)
  })

  it('setTrailSaved sets the state explicitly, idempotently', async () => {
    const { isTrailSaved, setTrailSaved } = await import('./savedTrails')
    setTrailSaved('old-rag', true)
    setTrailSaved('old-rag', true)
    expect(isTrailSaved('old-rag')).toBe(true)
    setTrailSaved('old-rag', false)
    expect(isTrailSaved('old-rag')).toBe(false)
  })

  it('persists a saved trail across a simulated reload (fresh module reads localStorage)', async () => {
    const first = await import('./savedTrails')
    first.setTrailSaved('old-rag', true)
    expect(localStorage.getItem(STORAGE_KEY)).toContain('old-rag')

    vi.resetModules()
    const second = await import('./savedTrails')
    expect(second.isTrailSaved('old-rag')).toBe(true)
  })

  it('degrades to empty on corrupt storage instead of throwing', async () => {
    localStorage.setItem(STORAGE_KEY, 'not valid json')
    const { isTrailSaved } = await import('./savedTrails')
    expect(isTrailSaved('anything')).toBe(false)
  })

  it('ignores non-string entries in a foreign/corrupt array', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(['stony-man', 42, null]))
    const { isTrailSaved } = await import('./savedTrails')
    expect(isTrailSaved('stony-man')).toBe(true)
  })
})

describe('useIsTrailSaved / useSavedTrailIds (reactive across components)', () => {
  it('re-renders a subscriber when the trail is toggled from outside the hook', async () => {
    const { useIsTrailSaved, toggleTrailSaved } = await import('./savedTrails')
    const { result } = renderHook(() => useIsTrailSaved('stony-man'))
    expect(result.current).toBe(false)
    act(() => toggleTrailSaved('stony-man'))
    expect(result.current).toBe(true)
    act(() => toggleTrailSaved('stony-man'))
    expect(result.current).toBe(false)
  })

  it('useSavedTrailIds reflects the full saved set', async () => {
    const { useSavedTrailIds, toggleTrailSaved } = await import('./savedTrails')
    const { result } = renderHook(() => useSavedTrailIds())
    expect(result.current.size).toBe(0)
    act(() => {
      toggleTrailSaved('stony-man')
      toggleTrailSaved('old-rag')
    })
    expect(result.current.has('stony-man')).toBe(true)
    expect(result.current.has('old-rag')).toBe(true)
    expect(result.current.size).toBe(2)
  })
})
