import { useState } from 'react'

import { Toggle } from '../components'
import { useEpisode, usePlannerClient } from '../data/PlannerProvider'
import type { EpisodeVM } from '../data/vm'

const FACES: Array<{ value: 1 | 2 | 3; glyph: string; label: string }> = [
  { value: 3, glyph: '🙂', label: 'Good' },
  { value: 2, glyph: '😐', label: 'Okay' },
  { value: 1, glyph: '😞', label: 'Rough' },
]

export interface OutcomeProps {
  episodeId: string
  onDone: () => void
}

/**
 * The post-hike outcome card (outcome-card-ux §1). Measured facts are shown as
 * already-known and never re-asked; the only required input is one tap on a
 * face. There is NO delta question — the backend generates no real prediction,
 * so we ship none rather than fabricate one (R3). Skip is first-class and writes
 * data, never nags (§1.7). Measured facts are sample data, disclosed as such.
 */
export function Outcome({ episodeId, onDone }: OutcomeProps) {
  const { status, episode } = useEpisode(episodeId)
  const { client, scope } = usePlannerClient()
  const [overall, setOverall] = useState<1 | 2 | 3 | null>(null)
  const [rubyAlong, setRubyAlong] = useState<boolean | null>(null)
  const [submitted, setSubmitted] = useState(false)

  // Pre-fill the Ruby toggle from the planned party (R12): the common case is
  // zero extra taps; you only correct it on the exception.
  const rubyDefault = (episode?.companions ?? []).some((c) => c.name === 'Ruby')
  const ruby = rubyAlong ?? rubyDefault

  const submit = async (rating: 1 | 2 | 3 | null, skipped: boolean) => {
    const companions: EpisodeVM['companions'] = ruby ? [{ kind: 'dependent', name: 'Ruby' }] : []
    await client.recordOutcome(episodeId, { overall: rating, skipped }, companions, scope)
    setSubmitted(true)
  }

  const onFace = (value: 1 | 2 | 3) => {
    setOverall(value)
    void submit(value, false)
  }

  // Skip is first-class: it writes Outcome{skipped:true} (data, not a nag) then
  // leaves (outcome-card-ux §1.7).
  const onSkip = async () => {
    await submit(null, true)
    onDone()
  }

  return (
    <div className="app-shell">
      <header className="detail-top">
        {status === 'ready' && !submitted ? (
          <button className="back" type="button" onClick={onSkip}>
            Skip
          </button>
        ) : (
          <button className="back" type="button" onClick={onDone}>
            Done
          </button>
        )}
        <span className="wordmark">After the hike</span>
      </header>

      {status === 'loading' ? <p className="state-note">Loading…</p> : null}

      {status === 'notfound' ? (
        <div className="state-block">
          <p className="state-note">Sign in to log your hikes and keep what we learn.</p>
          <button className="text-action" type="button" onClick={onDone}>
            Back to the feed
          </button>
        </div>
      ) : null}

      {status === 'ready' && episode ? (
        submitted ? (
          <section className="outcome">
            <p className="outcome-ack">Noted.</p>
            <button className="text-action" type="button" onClick={onDone}>
              Done
            </button>
          </section>
        ) : (
          <section className="outcome">
            <p className="sample-strip" role="note">
              Sample hike — these measured facts stand in for your watch until it’s connected.
            </p>

            <div className="outcome-head">
              <h1 className="outcome-name">You hiked {episode.trailName}</h1>
              <p className="outcome-facts">
                {episode.when} · {episode.distanceMiles.toFixed(1)} mi ·{' '}
                {episode.ascentFeet.toLocaleString()} ft up
              </p>
            </div>

            <div className="measured">
              <p className="measured-label">Measured</p>
              <p className="measured-value">{episode.movingTime}</p>
              {episode.paceNote ? <p className="measured-note">{episode.paceNote}</p> : null}
            </div>

            <fieldset className="faces">
              <legend className="faces-legend">How was it?</legend>
              {FACES.map((face) => (
                <button
                  key={face.value}
                  type="button"
                  className={overall === face.value ? 'face face--on' : 'face'}
                  aria-pressed={overall === face.value}
                  aria-label={face.label}
                  onClick={() => onFace(face.value)}
                >
                  <span aria-hidden="true">{face.glyph}</span>
                </button>
              ))}
            </fieldset>

            <Toggle
              label="Was Ruby with you?"
              isSelected={ruby}
              onChange={(on) => setRubyAlong(on)}
            />
          </section>
        )
      ) : null}
    </div>
  )
}
