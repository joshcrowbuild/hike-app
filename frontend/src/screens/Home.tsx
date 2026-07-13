import { useMemo, useState, type ReactNode } from 'react'
import { ToggleButton } from 'react-aria-components'

import { partyLabels, whenLabels } from '../data/labels'
import { splitFeedWarnings } from '../data/feedWarnings'
import { prefersReducedMotion } from '../data/motion'
import { useFeed, useRecentEpisodes, type LoadingStage } from '../data/PlannerProvider'
import { useOrigins, type OriginOption } from '../data/regionsCatalog'
import { resolveRegionLabel } from '../data/resolveRegion'
import { useSavedTrailIds } from '../data/savedTrails'
import { widenFrame } from '../data/widen'
import type { CardVM, FeedVM, HeldBackVM, SetAside } from '../data/vm'
import type { TuningState } from '../types'
import { WarningBlock } from './cardParts'
import { RecommendationCard } from './RecommendationCard'
import { SkeletonCard } from './SkeletonCard'

/** The honest progress ladder for a still-loading request (D4 — perceived
 *  performance). Never a frozen line past NNG's ~10s attention threshold: the
 *  copy keeps changing as the wait stretches, without pretending to know a
 *  cause it can't confirm until the wait is long enough to make one likely. */
const LOADING_COPY: Record<LoadingStage, string> = {
  initial: 'Reading conditions…',
  reassure: 'Still checking conditions…',
  coldstart: 'Waking the server — this can take up to a minute…',
}

/** A short, staggered per-card delay so real cards settle in one after another
 *  instead of popping in as one flat block — a calmer "arriving" feel than an
 *  instant swap, without reflowing anything (opacity/transform only, so no
 *  layout shift). Skipped under reduced motion; capped so a long feed doesn't
 *  make the tail of the stack wait noticeably longer than the top. */
const REVEAL_STAGGER_MS = 45
const REVEAL_STAGGER_MAX_MS = 270

/** `undefined` under reduced motion — callers skip the reveal class entirely
 *  rather than just zeroing the delay, so no animation fires at all. */
function revealDelay(index: number): number | undefined {
  if (prefersReducedMotion()) return undefined
  return Math.min(index * REVEAL_STAGGER_MS, REVEAL_STAGGER_MAX_MS)
}

/** Home shows peers, not a full page of results (v0.3 §2: "≤3 peers") — the
 *  skeleton mirrors that count so the placeholder shape matches what actually
 *  lands. */
const SKELETON_COUNT = 3

/** A stable empty array so `useMemo` below doesn't recompute every render
 *  while there's no feed yet (a fresh `[]` literal would never memoize). */
const EMPTY_CARDS: CardVM[] = []

/** The calm frame setter and primary tuning entry (v0.3 §2/C5). Anonymous still
 *  picks an origin (R7 world-browse) — the sentence names it plainly rather
 *  than leaving the region tag below to speak for it alone (report #3). The
 *  region itself is derived from the SERVED cards, never the picker's
 *  assumption — see `resolveRegionLabel`. */
function contextSentence(
  tuning: TuningState,
  anonymous: boolean,
  cards: CardVM[],
  origins: OriginOption[],
): string {
  const region = resolveRegionLabel(cards, tuning, origins)
  const origin = tuning.originCoords
    ? 'your location'
    : (origins.find((o) => o.key === tuning.origin)?.label ?? '')
  if (anonymous) return `${whenLabels[tuning.when]} · ${region} · from ${origin}`
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
  const { status, feed, error, loadingStage, reload, stale, revalidating, staleAsOf, revalidateError } = useFeed({
    tuning,
  })
  const { episodes } = useRecentEpisodes()
  const { origins } = useOrigins()
  // The post-hike nod FINDS the user on Home (R4) — a single pending hike, not a
  // Trips tab to navigate to. Quiet, dismissible by simply not tapping it.
  const pending = episodes.find((e) => !e.outcome)
  const cards = feed?.cards ?? EMPTY_CARDS
  // Hoist any region-wide alert duplicated across most cards to one feed-level
  // banner (report #1) — the red wall was pushing distance off-screen on every
  // card. Rendering-only: cards are never rewritten (F1) — the card component
  // suppresses the shared warning BLOCK but its verdict and accessible name
  // keep deriving from the full CardVM, exactly as Detail does, so the two
  // surfaces can never disagree on the verdict.
  const { banner, sharedTexts } = useMemo(() => splitFeedWarnings(cards), [cards])

  // Client-side bookmark list (localStorage, no backend/auth) — a view filter
  // over THIS frame's served cards, never a second data source. Feed-level
  // disclosures (banner/notices/setAside/heldBack) stay about the frame as a
  // whole and keep showing regardless of the filter.
  const savedIds = useSavedTrailIds()
  const [savedOnly, setSavedOnly] = useState(false)
  const shown = savedOnly ? cards.filter((c) => savedIds.has(c.id)) : cards

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
          <span className="context-text">{contextSentence(tuning, anonymous, cards, origins)}</span>
          <span className="context-adjust">Adjust</span>
        </button>
      </section>

      {feed?.dataSource === 'mock' ? (
        <p className="sample-strip" role="note">
          Sample data — the layout and behaviour are real; the conditions aren’t live yet.
        </p>
      ) : null}

      {feed ? <ReadinessLine feed={feed} /> : null}

      {/* aria-busy stays tied to status==='loading' only — a stale-painted
          feed (Epic 039 S3) is usable, perceivable content, not a busy wait;
          the "still checking" signal is carried by the polite status line
          above the card stack instead. */}
      <div aria-busy={status === 'loading'}>
        {status === 'loading' ? (
          <>
            {/* A skeleton card silhouette renders instantly (NNG: structured wait
                beats a bare "loading" line). The status line keeps changing as
                the wait stretches past NNG's ~10s attention mark, never sitting
                frozen on one line — and is always rendered visibly, not just to
                assistive tech (role=status also reaches AT, WCAG 4.1.3), so a
                long wait never silently sits on a bare skeleton (report #4). */}
            <p className="state-note" role="status">
              {LOADING_COPY[loadingStage]}
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
            {/* Stale-while-revalidate disclosure (Epic 039 S3): a repainted
                last-visit feed is perceivable content, not a busy wait — the
                "loading" aria-busy above stays tied to status==='loading'
                only, and this polite status line carries the "still
                checking" signal instead. Neither line duplicates a live fact:
                the only age shown is `staleAsOf`, the honest fetch-time
                stamp — every card's own condition is already silenced to
                `stale-degraded` (toStalePaint), never repainted as current. */}
            {stale && revalidating ? (
              <p className="state-note" role="status" aria-live="polite">
                Showing your last visit ({staleAsOf}) — checking current conditions…
              </p>
            ) : null}
            {stale && revalidateError ? (
              <div className="state-block">
                <p className="state-note" role="status">
                  Couldn’t refresh — showing your last visit. Conditions may have changed.
                </p>
                <button className="text-action" type="button" onClick={reload}>
                  Try again
                </button>
              </div>
            ) : null}

            {feed.cards.length > 0 || savedIds.size > 0 ? (
              <div className="stack-controls">
                <ToggleButton className="action-chip" isSelected={savedOnly} onChange={setSavedOnly}>
                  {savedOnly ? 'Show all' : savedIds.size > 0 ? `Saved (${savedIds.size})` : 'Saved'}
                </ToggleButton>
              </div>
            ) : null}

            {shown.length > 0 ? (
              <p className="stack-meta">
                {savedOnly
                  ? shown.length === 1
                    ? '1 saved'
                    : `${shown.length} saved`
                  : feed.cards.length === 1
                    ? '1 option'
                    : `${feed.cards.length} options`}{' '}
                · {resolveRegionLabel(cards, tuning, origins)}
              </p>
            ) : null}

            {banner.length > 0 ? (
              <div className="feed-alert-banner">
                <WarningBlock warnings={banner} label="Regional alert" />
              </div>
            ) : null}

            {shown.length > 0 ? (
              <div className="card-stack">
                {shown.map((card, i) => {
                  const delay = revealDelay(i)
                  return (
                    <div
                      key={card.id}
                      className={delay != null ? 'card-reveal' : undefined}
                      style={delay != null ? { animationDelay: `${delay}ms` } : undefined}
                    >
                      <RecommendationCard
                        card={card}
                        onOpen={() => onOpenTrail(card.id)}
                        hoistedWarningTexts={sharedTexts}
                      />
                    </div>
                  )
                })}
              </div>
            ) : savedOnly ? (
              <SavedEmptyState anySaved={savedIds.size > 0} />
            ) : null}

            <HousekeepingGroup
              feed={feed}
              savedOnly={savedOnly}
              tuning={tuning}
              onApplyTuning={onApplyTuning}
              onOpenTrail={onOpenTrail}
            />
          </section>
        ) : null}
      </div>
    </div>
  )
}

/**
 * Honest empty state for the Saved filter (never a bare blank, mirroring
 * `EmptyState`/`SavedEmptyState`'s siblings below): distinguishes "you've
 * never saved anything" from "you have saved trails, just none in this
 * frame" — the two read very differently and the copy says which is true.
 */
function SavedEmptyState({ anySaved }: { anySaved: boolean }) {
  return (
    <div className="state-block">
      <p className="state-note">
        {anySaved ? 'None of your saved trails are in this frame.' : 'No saved trails yet.'}
      </p>
    </div>
  )
}

/**
 * Shared recessive-disclosure shell for the housekeeping tier (Epic 025):
 * one step down from the safety banner (the sole accent-hue element), one
 * step up from the sample-strip build note. Native `<details>`/`<summary>`
 * gives a keyboard-operable, self-announcing expand control for free — open
 * by default so nothing here is hidden un-inspectably (AC-25.1.2).
 */
function Housekeeping({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="housekeeping" open>
      <summary className="housekeeping-summary">{summary}</summary>
      <div className="housekeeping-body">{children}</div>
    </details>
  )
}

/** Readiness disclosure (R2): effect-first; fails open and says so. Never a
 *  number. Housekeeping-tier (Epic 025) — recessive + collapsible. */
function ReadinessLine({ feed }: { feed: FeedVM }) {
  if (!feed.readiness.on) return null
  const text = feed.readiness.state === 'open' ? feed.readiness.staleReason : feed.readiness.rationale
  return (
    <Housekeeping summary="About this list">
      <p className="readiness-line">{text}</p>
    </Housekeeping>
  )
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

/**
 * The housekeeping tier (Epic 025): set-aside / held-back / sparse / generic
 * notices, grouped into one recessive, collapsible disclosure so they read as
 * a quiet aside beneath the results — never at the same weight as the safety
 * banner above them. Nothing here is new: same components, same source data,
 * just given a shared shell instead of rendering as separate loose lines.
 */
function HousekeepingGroup({
  feed,
  savedOnly,
  tuning,
  onApplyTuning,
  onOpenTrail,
}: {
  feed: FeedVM
  savedOnly: boolean
  tuning: TuningState
  onApplyTuning: (next: TuningState) => void
  onOpenTrail: (id: string) => void
}) {
  const showSparse = !savedOnly && feed.cards.length === 1
  const hasAny = showSparse || feed.setAside.length > 0 || feed.heldBack.length > 0 || feed.notices.length > 0
  if (!hasAny) return null
  return (
    <Housekeeping summary="More about this frame">
      {showSparse ? <SparseNote tuning={tuning} onApplyTuning={onApplyTuning} /> : null}
      {feed.setAside.length > 0 ? <SetAsideList items={feed.setAside} onOpenTrail={onOpenTrail} /> : null}
      {feed.heldBack.length > 0 ? <HeldBackNote items={feed.heldBack} /> : null}
      {feed.notices.map((notice) => (
        <p key={notice} className="frame-note">
          {notice}
        </p>
      ))}
    </Housekeeping>
  )
}
