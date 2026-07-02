/**
 * Chooses the viewer scope the app boots with (H1 fix). The non-anonymous
 * scope can only authenticate if `VITE_DEV_VIEWER_SECRET` was baked into this
 * build — sending it without a secret just 403s at `_authorize_viewer`
 * (api/app.py), and shipping the secret into a public bundle is exactly the
 * hole H1 closed. So: no secret at build time → always anonymous, regardless
 * of `?anon`. A secret only exists in dev/local builds (Rule #10).
 */
import { ANON_SCOPE, type ScopeContext } from './api'

const JOSH: ScopeContext = { viewerId: 'josh', grantedIds: [] }

export function resolveScope(params: URLSearchParams, devSecret: string | undefined): ScopeContext {
  if (!devSecret) return ANON_SCOPE
  return params.has('anon') ? ANON_SCOPE : JOSH
}
