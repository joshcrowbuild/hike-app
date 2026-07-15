import React from 'react'
import ReactDOM from 'react-dom/client'

import App from './App'
import { AuthProvider, useAuth } from './data/auth/AuthProvider'
import { Gallery } from './Gallery'
import { PlannerProvider } from './data/PlannerProvider'
import { BootShell } from './screens/BootShell'
import './design/tokens.css'
import './styles.css'

const params = new URLSearchParams(window.location.search)

// `?gallery` is the trunk's component-gallery dev surface; it is provider-free.
const isGallery = params.has('gallery')

/**
 * The viewer scope is now a real product axis driven by managed auth (Epic 043):
 * anonymous until a Supabase session lands, then the signed-in overlay keyed by the
 * verified `sub` — the SAME ScopeContext shape. Anonymous browsing is never gated
 * on the session check (AuthProvider mounts anonymous and upgrades in place).
 */
function AuthedApp() {
  const { scope } = useAuth()
  return (
    <PlannerProvider scope={scope} fallback={<BootShell />}>
      <App />
    </PlannerProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isGallery ? (
      <Gallery />
    ) : (
      <AuthProvider>
        <AuthedApp />
      </AuthProvider>
    )}
  </React.StrictMode>,
)
