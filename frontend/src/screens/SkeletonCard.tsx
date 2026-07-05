import { prefersReducedMotion } from '../data/motion'

/**
 * A card-shaped placeholder shown the instant a search is submitted (NNG:
 * skeleton screens over spinners/text — a structured wait feels shorter than a
 * bare "loading" line, and layout doesn't jump when real cards land since the
 * silhouette already occupies the same shape). Purely decorative: `aria-hidden`,
 * because the sr-only status line Home renders alongside the stack already
 * carries the loading state to assistive tech (WCAG 4.1.3).
 */
export function SkeletonCard() {
  const shimmer = prefersReducedMotion() ? '' : ' skeleton-shimmer'
  const line = (modifier: string) => `skeleton-line skeleton-line--${modifier}${shimmer}`

  return (
    <div className="card skeleton-card" aria-hidden="true">
      <div className="card-tap">
        <div className={line('verdict')} />
        <div className="card-id">
          <div className={line('name')} />
          <div className={line('area')} />
        </div>
        <div className="decision">
          <div className={line('decision')} />
          <div className={line('decision')} />
        </div>
        <div className={`skeleton-glyph${shimmer}`} />
        <div className={line('condition')} />
        <div className="card-foot">
          <div className={line('foot')} />
        </div>
      </div>
    </div>
  )
}
