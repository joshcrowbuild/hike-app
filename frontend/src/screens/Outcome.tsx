import { useEffect, useRef, useState } from 'react'

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
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  // Hard re-entrancy guard: a ref blocks a same-tick second tap synchronously,
  // before the busy state can re-render (prevents a double write).
  const inFlight = useRef(false)
  const doneRef = useRef<HTMLButtonElement>(null)

  // Pre-fill the Ruby toggle from the planned party (R12): the common case is
  // zero extra taps; you only correct it on the exception.
  const rubyDefault = (episode?.companions ?? []).some((c) => c.name === 'Ruby')
  const ruby = rubyAlong ?? rubyDefault

  // Move focus to the acknowledgment so it isn't dropped to <body> (WCAG 2.4.3);
  // the ack region announces itself via role="status" (WCAG 4.1.3).
  useEffect(() => {
    if (submitted) doneRef.current?.focus()
  }, [submitted])

  const submit = async (rating: 1 | 2 | 3 | null, skipped: boolean): Promise<boolean> => {
    if (inFlight.current || submitted) return false
    inFlight.current = true
    setBusy(true)
    setFailed(false)
    const companions: EpisodeVM['companions'] = ruby ? [{ kind: 'dependent', name: 'Ruby' }] : []
    try {
      await client.recordOutcome(episodeId, { overall: rating, skipped }, companions, scope)
      setSubmitted(true)
      return true
    } catch {
      // Source-or-silence: never claim it saved if it didn't. Keep the form live.
      setFailed(true)
      setOverall(null)
      return false
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  const onFace = (value: 1 | 2 | 3) => {
    setOverall(value)
    void submit(value, false)
  }

  // Skip is first-class: it writes Outcome{skipped:true} (data, not a nag) then
  // leaves (outcome-card-ux §1.7).
  const onSkip = () => {
    void submit(null, true).then((ok) => {
      if (ok) onDone()
    })
  }

  const showForm = status === 'ready' && episode && !submitted

  return (
    <div className="app-shell">
      <header className="detail-top">
        {showForm ? (
          <button className="back" type="button" onClick={onSkip} disabled={busy}>
            Skip
          </button>
        ) : (
          <button className="back" type="button" onClick={onDone}>
            Done
          </button>
        )}
        <span className="screen-title">After the hike</span>
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
          <section className="outcome" role="status">
            <p className="outcome-ack">Noted.</p>
            <button ref={doneRef} className="text-action" type="button" onClick={onDone}>
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

            <div className="faces" role="radiogroup" aria-label="How was it?">
              <p className="faces-legend" id="faces-legend">
                How was it?
              </p>
              <div className="faces-row">
                {FACES.map((face) => (
                  <button
                    key={face.value}
                    type="button"
                    role="radio"
                    aria-checked={overall === face.value}
                    aria-label={face.label}
                    disabled={busy}
                    className={overall === face.value ? 'face face--on' : 'face'}
                    onClick={() => onFace(face.value)}
                  >
                    <span aria-hidden="true">{face.glyph}</span>
                  </button>
                ))}
              </div>
            </div>

            {failed ? (
              <p className="state-note" role="alert">
                Couldn’t save that just now — tap a face to try again.
              </p>
            ) : null}

            <Toggle label="Was Ruby with you?" isSelected={ruby} onChange={(on) => setRubyAlong(on)} />
          </section>
        )
      ) : null}
    </div>
  )
}
