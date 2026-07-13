import { LOADING_COPY, useLoadingStage } from '../data/loadingStages'
import { SKELETON_COUNT, SkeletonCard } from './SkeletonCard'

/**
 * The first-paint shell (craft review H1). Rendered by the provider gate while
 * `/regions` resolves — which, on a Render cold start, is exactly the
 * multi-second-to-minute window where reassurance matters most. It draws the
 * same chrome Home draws anyway (topbar + wordmark + skeleton stack) so the
 * gate-to-app swap never reads as a second, different loading screen, and it
 * runs the shared staged copy ladder driven by elapsed time — so the only long
 * wait a first-time user ever hits is a designed one, never a bare unstyled
 * "Loading…" string.
 */
export function BootShell() {
  const stage = useLoadingStage()
  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="wordmark">Curation</span>
      </header>
      {/* Visible AND role=status (WCAG 4.1.3) — the wait is announced once to
          assistive tech and keeps updating for sighted users as it stretches. */}
      <p className="state-note" role="status">
        {LOADING_COPY[stage]}
      </p>
      <div className="card-stack" aria-hidden="true">
        {Array.from({ length: SKELETON_COUNT }, (_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    </div>
  )
}
