import type { ReactNode } from 'react'

import type { SystemBannerModel } from '../../design/contracts'
import { tierGlyphs } from '../../screens/glyphs'
import { Icon } from '../Icon'
import { Text } from '../Text'
import * as styles from './SystemBanner.css'

/** The sr-only lead-in per tier — the same "cue beyond colour" convention `Signal` already
 *  establishes (design-system-v0.1 §4.3): colour is never the only signal of severity. */
const TIER_LABEL: Record<SystemBannerModel['tier'], string> = {
  unknown: 'Notice',
  headsUp: 'Heads up',
  blocked: 'Blocked',
}

export type SystemBannerProps = SystemBannerModel & {
  /**
   * An optional detail line rendered below the message, always in muted
   * ink regardless of tier (states-gallery.html §6 — "Trails, distances and
   * terrain still work…"). Not part of the frozen `SystemBannerModel`
   * (which carries one conclusion-first sentence); this is additive for
   * callers that want the fuller two-line outage/degraded treatment.
   */
  secondary?: ReactNode
  className?: string
}

/**
 * SystemBanner — regional-alert / live-outage / personalization-degraded
 * (design-system-v0.2.md II.B). Calm, one sentence, constructive (Law 6);
 * tiered colour like every other signal surface, but `clear` is never valid
 * here (`SystemBannerModel.tier` already excludes it — a banner only exists
 * to disclose something). `unknown` renders gray and un-alarmed, never red
 * (Law 7) — a source being down is not an error and not the user's problem.
 */
export function SystemBanner({ kind, tier, message, secondary, className }: SystemBannerProps) {
  const Glyph = tierGlyphs[tier]
  const cls = [styles.base, styles.tier[tier], className].filter(Boolean).join(' ')
  return (
    <div className={cls} role="status" data-banner-kind={kind}>
      <div className={`${styles.row} ${styles.rowTier[tier]}`}>
        <Icon glyph={Glyph} label={TIER_LABEL[tier]} className={styles.icon} />
        <Text role="bodySm" as="p" className={styles.message}>
          {message}
        </Text>
      </div>
      {secondary ? (
        <Text role="caption" as="p" className={styles.secondary}>
          {secondary}
        </Text>
      ) : null}
    </div>
  )
}
