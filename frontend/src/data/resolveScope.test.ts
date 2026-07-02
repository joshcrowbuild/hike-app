import { describe, expect, it } from 'vitest'
import { resolveScope } from './resolveScope'
import { ANON_SCOPE } from './api'

describe('resolveScope (H1: no bundled secret => anonymous-only)', () => {
  it('is anonymous with no dev secret, even without ?anon', () => {
    expect(resolveScope(new URLSearchParams(), undefined)).toEqual(ANON_SCOPE)
  })

  it('is anonymous with no dev secret, even when secret is the empty string', () => {
    expect(resolveScope(new URLSearchParams(), '')).toEqual(ANON_SCOPE)
  })

  it('is anonymous with a dev secret when ?anon is set', () => {
    expect(resolveScope(new URLSearchParams('anon'), 'dev-secret-value')).toEqual(ANON_SCOPE)
  })

  it('is the non-anonymous viewer only when a dev secret is present and ?anon is absent', () => {
    expect(resolveScope(new URLSearchParams(), 'dev-secret-value')).toEqual({
      viewerId: 'josh',
      grantedIds: [],
    })
  })
})
