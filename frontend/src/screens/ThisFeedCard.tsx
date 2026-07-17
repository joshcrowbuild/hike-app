import {
  ChevronDown,
  ChevronRight,
  CloudRain,
  Footprints,
  RotateCw,
  Sun,
  Thermometer,
  Wind,
} from 'lucide-react'
import { useEffect, useState } from 'react'

import { Icon, Text } from '../components'
import { srOnly } from '../design/a11y.css'
import type { ConditionChipModel } from '../design/contracts'
import type { ForecastDayVM, RegionConditionsVM } from '../data/vm'
import * as chipStyles from './ConditionChip.css'
import { ConditionChip } from './ConditionChip'
import type { PanelKey } from './Tuning'
import * as styles from './ThisFeedCard.css'

export interface ThisFeedCardProps {
  /** From — the origin's own label ("Front Royal" / "Your location"). */
  originLabel: string
  /** When — the humanised time label ("Weekend morning"). */
  when: string
  /** Party / Effort labels — omitted for anonymous viewers (world facets only). */
  party?: string
  effort?: string
  anonymous: boolean
  /** Opens the existing PanelSheet for a facet (the tuning overlay). */
  onOpenFacet: (key: PanelKey) => void
  /** Area conditions temporally aligned to the trip's day (§5). */
  regionConditions?: RegionConditionsVM | null
  /** Region-shared current readings (`feedCurrentChips`) for the right-now zone. */
  currentChips: ConditionChipModel[]
  /** Phase 2 in flight — render skeleton chips, never a fabricated reading. */
  conditionsPending: boolean
  /** The one on-demand refetch (Q10). */
  onRefresh: () => void
}

const PENDING_CHIP: ConditionChipModel = { kind: 'weather', valueText: '', state: 'pending', tier: 'clear' }

/** A small forecast reading chip (temp / precip / short) — not a coverage chip,
 *  so it reuses the strip's visual box without the kind/state machinery. */
function ForecastChip({ glyph: Glyph, label, value }: { glyph: typeof Sun; label: string; value: string }) {
  return (
    <span className={chipStyles.chip}>
      <Glyph size={13} className={chipStyles.glyph} aria-hidden="true" focusable={false} />
      <span className={srOnly}>{label}: </span>
      <span className={chipStyles.value}>{value}</span>
    </span>
  )
}

export function ThisFeedCard({
  originLabel,
  when,
  party,
  effort,
  anonymous,
  onOpenFacet,
  regionConditions,
  currentChips,
  conditionsPending,
  onRefresh,
}: ThisFeedCardProps) {
  const forecast = regionConditions?.forecast ?? null
  const recentPrecip = regionConditions?.recentPrecip ?? null
  const mud = regionConditions?.mud ?? null

  // The day toggle is pure client state — all days arrive in one payload, so
  // switching never refetches (S2 AC-2.1). Re-seed only when a NEW forecast
  // (new target) lands.
  const [selectedKey, setSelectedKey] = useState<string | undefined>(forecast?.targetKey)
  useEffect(() => {
    setSelectedKey(forecast?.targetKey)
  }, [forecast?.targetKey])

  const days = forecast?.days ?? []
  const selectedDay: ForecastDayVM | undefined =
    days.find((d) => d.key === selectedKey) ?? days.find((d) => d.key === forecast?.targetKey) ?? days[0]

  const targetDay = days.find((d) => d.key === forecast?.targetKey)
  const targetIsFuture = !!forecast && forecast.targetKey !== 'today'

  const [recentOpen, setRecentOpen] = useState(false)

  // `null` is a DISCLOSED outage (phase 2 answered "unavailable") and must
  // still render the zone with its unavailable line — only `undefined` (an
  // older backend that never emits region conditions) hides it (review fix,
  // S2 AC-2.3).
  const showForecastZone = conditionsPending || regionConditions !== undefined
  const showRightNow = conditionsPending || currentChips.length > 0

  return (
    <section className={styles.card} aria-label="This feed">
      <div className={styles.header}>
        <Text role="overline" as="p" className={styles.overline}>
          This feed
        </Text>
      </div>

      {/* S1 — the facet stack (type scale = hierarchy; all slate, all tappable). */}
      <div className={styles.facets}>
        <span className={styles.facetLabel}>From</span>
        <button type="button" className={styles.fromButton} onClick={() => onOpenFacet('origin')}>
          {originLabel}
          <ChevronRight size={18} className={styles.caret} aria-hidden="true" focusable={false} />
        </button>
        <div>
          <button type="button" className={styles.whenButton} onClick={() => onOpenFacet('when')}>
            {when}
            <ChevronRight size={14} className={styles.caret} aria-hidden="true" focusable={false} />
          </button>
        </div>
        {!anonymous ? (
          <div className={styles.minorRow}>
            {party ? (
              <button type="button" className={styles.chipButton} onClick={() => onOpenFacet('party')}>
                {party}
                <ChevronDown size={13} className={styles.caret} aria-hidden="true" focusable={false} />
              </button>
            ) : null}
            {effort ? (
              <button type="button" className={styles.chipButton} onClick={() => onOpenFacet('effort')}>
                {effort}
                <ChevronDown size={13} className={styles.caret} aria-hidden="true" focusable={false} />
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* S2 — forecast zone + day toggle. */}
      {showForecastZone ? (
        <div className={styles.zone}>
          <div className={styles.zoneHead}>
            <span className={styles.zoneLabel}>
              {selectedDay ? (
                <>
                  <span className={styles.zoneLead}>
                    {selectedDay.key === 'today' ? 'Today' : `${selectedDay.label} forecast`}
                  </span>
                  <span className={selectedDay.key === 'today' ? styles.currentTag : styles.forecastTag}>
                    {selectedDay.key === 'today' ? 'now' : 'forecast'}
                  </span>
                </>
              ) : (
                <span className={styles.zoneLead}>Forecast</span>
              )}
            </span>
            {days.length > 1 ? (
              <div className={styles.dayToggle} role="group" aria-label="Forecast day">
                {days.map((d) => (
                  <button
                    key={d.key}
                    type="button"
                    className={styles.dayButton}
                    aria-pressed={d.key === selectedDay?.key}
                    onClick={() => setSelectedKey(d.key)}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          {forecast && selectedDay ? (
            <div className={styles.chips}>
              {selectedDay.highF != null ? (
                <ForecastChip glyph={Thermometer} label="High temperature" value={`${selectedDay.highF}°F`} />
              ) : null}
              {selectedDay.precipPct != null ? (
                <ForecastChip glyph={CloudRain} label="Chance of rain" value={`${selectedDay.precipPct}%`} />
              ) : null}
              {selectedDay.short ? <ForecastChip glyph={Wind} label="Conditions" value={selectedDay.short} /> : null}
            </div>
          ) : conditionsPending ? (
            <div className={styles.chips}>
              <ConditionChip model={PENDING_CHIP} />
              <ConditionChip model={PENDING_CHIP} />
            </div>
          ) : (
            <p className={styles.degradedLine}>Forecast unavailable right now</p>
          )}

          {/* S4 — Past 3 days reveal + the hedged mud read (only when data exists). */}
          {recentPrecip ? (
            <>
              <button
                type="button"
                className={styles.recentToggle}
                aria-expanded={recentOpen}
                aria-controls="this-feed-recent"
                onClick={() => setRecentOpen((v) => !v)}
              >
                {recentOpen ? (
                  <ChevronDown size={12} aria-hidden="true" focusable={false} />
                ) : (
                  <ChevronRight size={12} aria-hidden="true" focusable={false} />
                )}
                Past 3 days
              </button>
              {/* The id'd region always exists so aria-controls never dangles;
                  only its CONTENTS are conditional (a11y review fix). */}
              <div id="this-feed-recent">
                {recentOpen ? (
                  <>
                  <div className={styles.recentBox}>
                    <p className={styles.recentHead}>Rain, last 3 days</p>
                    <div className={styles.days}>
                      {recentPrecip.days.map((d) => {
                        // Three-way honesty: a number is a reading, 0 is a
                        // CONFIRMED dry day, null is a station gap — disclosed
                        // as "—", never dressed as dry (S3 AC-3.1 per-day).
                        const missing = d.amountIn == null
                        const wet = !missing && d.amountIn! > 0
                        const RainGlyph = wet ? CloudRain : Sun
                        return (
                          <div key={d.label} className={styles.day}>
                            <span className={styles.dayLabel}>{d.label}</span>
                            <RainGlyph size={15} className={wet ? styles.dayGlyph.wet : styles.dayGlyph.dry} aria-hidden="true" focusable={false} />
                            <span className={wet ? styles.dayAmount.wet : styles.dayAmount.dry}>
                              {missing ? '—' : wet ? `${d.amountIn}"` : 'dry'}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                  {mud ? (
                    <div className={styles.mud}>
                      <Footprints size={16} className={styles.mudGlyph} aria-hidden="true" focusable={false} />
                      <span className={styles.mudText}>
                        <span className={styles.mudStatement}>{mud.statement}</span>
                        <span className={styles.mudTag}>inferred</span>
                        <span className={styles.mudEvidence}>
                          {mud.evidence} · from {mud.source}
                        </span>
                      </span>
                    </div>
                  ) : null}
                  </>
                ) : null}
              </div>
            </>
          ) : null}
        </div>
      ) : null}

      {/* S3 — right-now zone. */}
      {showRightNow ? (
        <div className={styles.zone}>
          <div className={styles.zoneHead}>
            <span className={styles.zoneLabel}>
              <span className={styles.zoneLead}>Right now</span>
              {targetIsFuture && targetDay ? (
                <span className={styles.caveat}>· may change by {targetDay.label}</span>
              ) : null}
            </span>
            <span className={styles.headActions}>
              <button type="button" className={styles.refresh} onClick={onRefresh}>
                <RotateCw size={12} aria-hidden="true" focusable={false} />
                Refresh
                <span className={srOnly}> current conditions</span>
              </button>
              <span className={styles.currentTag}>current</span>
            </span>
          </div>
          <div className={styles.chips}>
            {currentChips.length > 0
              ? currentChips.map((chip, i) => <ConditionChip key={`${chip.kind}-${i}`} model={chip} />)
              : conditionsPending
                ? [0, 1, 2].map((i) => <ConditionChip key={i} model={PENDING_CHIP} />)
                : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}
