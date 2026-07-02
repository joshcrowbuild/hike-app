import { originLabels, partyLabels, regionLabels, whenLabels } from '../data/labels'
import { useFeed, useRecentEpisodes } from '../data/PlannerProvider'
import { widenFrame } from '../data/widen'
import type { FeedVM, HeldBackVM, SetAside } from '../data/vm'
import type { TuningState } from '../types'
import { RecommendationCard } from './RecommendationCard'
import { SkeletonCard } from './SkeletonCard'

/** Home shows peers, not a full page of results (v0.3 §2: "≤3 peers") — the
 *  skeleton mirrors that count so the placeholder shape matches what actually
 *  lands. */
const SKELETON_COUNT = 3

/** The calm frame setter and primary tuning entry (v0.3 §2/C5). Anonymous still
 *  picks an origin (R7 world-browse), so the region tag must track it too — never
 *  the Shenandoah pilot region regardless of what's actually selected. */
function contextSentence(tuning: TuningState, anonymous: boolean): string {
  const region = tuning.originCoords ? 'Near you' : regionLabels[tuning.origin]
  const origin = tuning.originCoords ? 'your location' : originLabels[tuning.origin]
  if (anonymous) return `${whenLabels[tuning.when]} · ${region}`
  return `${whenLabels[tuning.when]} · from ${origin} · ${partyLabels[tuning.party]}`
}

export interface HomeProps {
  tuning: TuningState
  anonymous: boolean
  onOpenTuning: () => void
  onOpenTrail: (id: string) => void
  onOpenOutcome: (episodeId: string) => void
  onApplyTuning: (next: TuningState) => void
}

export function Home({
  tuning,
  anonymous,
  onOpenTuning,
  onOpenTrail,
  onOpenOutcome,
  onApplyTuning,
}: HomeProps) {
  const { status, feed, error, slow, reload } = useFeed({ tuning })
  const { episodes } = useRecentEpisodes()
  // The post-hike nod FINDS the user on Home (R4) — a single pending hike, not a
  // Trips tab to navigate to. Quiet, dismissible by simply not tapping it.
  const pending = episodes.find((e) => !e.outcome)

  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="wordmark">Curation</span>
        {anonymous ? (
          <span className="topbar-mode" role="status" aria-label="Browsing anonymously — not signed in">
            Browsing
          </span>
        ) : null}
      </header>

      {pending ? (
        <button className="pending-nod" type="button" onClick={() => onOpenOutcome(pending.id)}>
          <span className="pending-nod-text">You hiked {pending.trailName}</span>
          <span className="pending-nod-cue">How was it? →</span>
        </button>
      ) : null}

      <section className="frame">
        <button className="context" type="button" onClick={onOpenTuning}>
          <span className="context-text">{contextSentence(tuning, anonymous)}</span>
          <span className="context-adjust">Adjust</span>
        </button>
      </section>

      {feed?.dataSource === 'mock' ? (
        <p className="sample-strip" role="note">
          Sample data — the layout and behaviour are real; the conditions aren’t live yet.
        </p>
      ) : null}

      {feed ? <ReadinessLine feed={feed} /> : null}

      {status === 'loading' ? (
        <>
          {/* A skeleton card silhouette renders instantly (NNG: structured wait
              beats a bare "loading" line). A slow request is almost always the
              free-tier API cold-starting; that gets a visible, calmer note
              layered on top rather than replacing the structure. Either way
              role="status" reaches screen readers too (WCAG 4.1.3). Below the
              slow mark the same copy stays, sr-only — assistive tech still
              hears that a request is in flight even though sighted users get
              the skeleton instead. */}
          <p className={slow ? 'state-note' : 'sr-only'} role="status">
            {slow ? 'Waking the server — this can take up to a minute…' : 'Reading conditions…'}
          </p>
          <div className="card-stack" aria-hidden="true">
            {Array.from({ length: SKELETON_COUNT }, (_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        </>
      ) : null}

      {status === 'error' ? (
        <div className="state-block">
          <p className="state-note">{error?.message ?? 'Couldn’t load trails right now.'}</p>
          <button className="text-action" type="button" onClick={reload}>
            Try again
          </button>
        </div>
      ) : null}

      {status === 'empty' ? (
        <EmptyState tuning={tuning} onApplyTuning={onApplyTuning} onOpenTuning={onOpenTuning} />
      ) : null}

      {(status === 'ready' || status === 'empty') && feed ? (
        <section className="stack">
          {feed.cards.length > 0 ? (
            <p className="stack-meta">
              {feed.cards.length === 1 ? '1 option' : `${feed.cards.length} options`} ·{' '}
              {tuning.originCoords ? 'Near you' : regionLabels[tuning.origin]}
            </p>
          ) : null}

          <div className="card-stack">
            {feed.cards.map((card) => (
              <RecommendationCard key={card.id} card={card} onOpen={() => onOpenTrail(card.id)} />
            ))}
          </div>

          {feed.cards.length === 1 ? (
            <SparseNote tuning={tuning} onApplyTuning={onApplyTuning} />
          ) : null}

          {feed.setAside.length > 0 ? (
            <SetAsideList items={feed.setAside} onOpenTrail={onOpenTrail} />
          ) : null}

          {feed.heldBack.length > 0 ? <HeldBackNote items={feed.heldBack} /> : null}

          {feed.notices.map((notice) => (
            <p key={notice} className="frame-note">
              {notice}
            </p>
          ))}
        </section>
      ) : null}
    </div>
  )
}

/** Readiness disclosure (R2): effect-first; fails open and says so. Never a number. */
function ReadinessLine({ feed }: { feed: FeedVM }) {
  if (!feed.readiness.on) return null
  if (feed.readiness.state === 'open') {
    return <p className="readiness-line">{feed.readiness.staleReason}</p>
  }
  return <p className="readiness-line">{feed.readiness.rationale}</p>
}

function WidenAction({
  tuning,
  onApplyTuning,
}: {
  tuning: TuningState
  onApplyTuning: (next: TuningState) => void
}) {
  const widen = widenFrame(tuning)
  if (!widen) return null
  return (
    <button className="text-action" type="button" onClick={() => onApplyTuning(widen.next)}>
      {widen.label}
    </button>
  )
}

/** Honest + never a dead end (NNG error guidance: say what happened, and what
 *  to do about it). `widenFrame` is the preferred one-tap fix; once the frame
 *  is already at its widest, "Adjust search" reopens Tuning instead of leaving
 *  the note with no action at all. */
function EmptyState({
  tuning,
  onApplyTuning,
  onOpenTuning,
}: {
  tuning: TuningState
  onApplyTuning: (next: TuningState) => void
  onOpenTuning: () => void
}) {
  const widen = widenFrame(tuning)
  return (
    <div className="state-block">
      <p className="state-note">Nothing holds under this frame right now.</p>
      {widen ? (
        <button className="text-action" type="button" onClick={() => onApplyTuning(widen.next)}>
          {widen.label}
        </button>
      ) : (
        <button className="text-action" type="button" onClick={onOpenTuning}>
          Adjust search
        </button>
      )}
    </div>
  )
}

/** Sparse (1 option) is a confident outcome, never an apology (v0.3 §7). */
function SparseNote({
  tuning,
  onApplyTuning,
}: {
  tuning: TuningState
  onApplyTuning: (next: TuningState) => void
}) {
  return (
    <div className="sparse-block">
      <p className="sparse-note">One option really holds under this frame.</p>
      <WidenAction tuning={tuning} onApplyTuning={onApplyTuning} />
    </div>
  )
}

/**
 * Guardrail-held trails (Epic 018 S5): a quiet feed-level disclosure so nothing
 * the engine held back silently vanishes (Rule #1). These are the UNVERIFIABLE
 * class — a required condition no source could confirm — so there is no card to
 * restore; the note carries the cause(s), source-stamped by the backend. A
 * verified hazard never lands here: it stays in the feed wearing its warning.
 */
function HeldBackNote({ items }: { items: HeldBackVM[] }) {
  const causes = [...new Set(items.flatMap((t) => t.reasons.map((r) => r.text)))]
  const count = items.length === 1 ? '1 trail held back' : `${items.length} trails held back`
  return (
    <p className="frame-note held-back-note" role="note">
      {count} — {causes.join(' · ')}
    </p>
  )
}

/** Constraint-excluded options, disclosed and inspectable — never silent (R6). */
function SetAsideList({
  items,
  onOpenTrail,
}: {
  items: SetAside[]
  onOpenTrail: (id: string) => void
}) {
  return (
    <div className="set-aside">
      {items.map((item) => (
        <p key={item.id} className="set-aside-row">
          <span className="set-aside-text">
            {item.name} set aside — {item.reason}
          </span>
          <button className="text-action" type="button" onClick={() => onOpenTrail(item.id)}>
            Show anyway
          </button>
        </p>
      ))}
    </div>
  )
}
