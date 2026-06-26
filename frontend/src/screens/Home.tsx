import { originLabels, partyLabels, whenLabels } from '../data/labels'
import { useFeed, useRecentEpisodes } from '../data/PlannerProvider'
import { widenFrame } from '../data/widen'
import type { FeedVM, SetAside } from '../data/vm'
import type { TuningState } from '../types'
import { RecommendationCard } from './RecommendationCard'

/** The calm frame setter and primary tuning entry (v0.3 §2/C5). */
function contextSentence(tuning: TuningState, anonymous: boolean): string {
  if (anonymous) return `${whenLabels[tuning.when]} · Shenandoah`
  return `${whenLabels[tuning.when]} · from ${originLabels[tuning.origin]} · ${partyLabels[tuning.party]}`
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
  const { status, feed, error, reload } = useFeed({ tuning })
  const { episodes } = useRecentEpisodes()
  // The post-hike nod FINDS the user on Home (R4) — a single pending hike, not a
  // Trips tab to navigate to. Quiet, dismissible by simply not tapping it.
  const pending = episodes.find((e) => !e.outcome)

  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="wordmark">Curation</span>
        {anonymous ? <span className="topbar-mode">Browsing</span> : null}
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

      {status === 'loading' ? <p className="state-note">Reading conditions…</p> : null}

      {status === 'error' ? (
        <div className="state-block">
          <p className="state-note">{error?.message ?? 'Something went wrong.'}</p>
          <button className="text-action" type="button" onClick={reload}>
            Try again
          </button>
        </div>
      ) : null}

      {status === 'empty' ? <EmptyState tuning={tuning} onApplyTuning={onApplyTuning} /> : null}

      {(status === 'ready' || status === 'empty') && feed ? (
        <section className="stack">
          {feed.cards.length > 0 ? (
            <p className="stack-meta">
              {feed.cards.length === 1 ? '1 option' : `${feed.cards.length} options`} · Shenandoah
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

function EmptyState({
  tuning,
  onApplyTuning,
}: {
  tuning: TuningState
  onApplyTuning: (next: TuningState) => void
}) {
  return (
    <div className="state-block">
      <p className="state-note">Nothing holds under this frame right now.</p>
      <WidenAction tuning={tuning} onApplyTuning={onApplyTuning} />
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
