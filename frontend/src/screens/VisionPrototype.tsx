import React from 'react';
import { vars } from '../design/theme.css';
import { ConditionStates } from './ConditionStates';
import { WarningBlock, DecisionFacts } from './cardParts';
import type { CardVM, ConditionStatusVM, WarningVM, GeoPosition } from '../data/vm';
import { Signal } from '../components';

// -----------------------------------------------------------------------------
// Mock Data Utilities
// -----------------------------------------------------------------------------
const MOCK_GEO: GeoPosition = { lat: 38.6, lon: -78.3 };
function createMockCard(
  id: string,
  name: string,
  distanceMi: number,
  ascentFeet: number,
  durationMinutes: number,
  warnings: WarningVM[],
  conditions: ConditionStatusVM[]
): CardVM {
  return {
    id,
    name,
    distanceMi,
    conditionLines: [],
    warnings,
    conditions,
    enrichment: { provenance: 'mock' },
    geo: {
      geometry: { type: 'LineString', coordinates: [[MOCK_GEO.lon, MOCK_GEO.lat]] },
      trailhead: MOCK_GEO,
      quality: 'confident',
      elevationProfile: {
        samples: [],
        totalGainMeters: ascentFeet / 3.28084,
        totalLossMeters: 0,
        maxGradePercent: 10,
        source: 'USGS 3DEP',
        resolutionMeters: 10,
        estimatedDurationMin: durationMinutes,
      }
    }
  };
}

// -----------------------------------------------------------------------------
// The Call (Hero Card)
// -----------------------------------------------------------------------------
type ConfidenceMode = 'confident' | 'hedged' | 'flagged' | 'pending';

export function HeroCard({ 
  card, 
  confidenceMode, 
  headline 
}: { 
  card: CardVM, 
  confidenceMode: ConfidenceMode, 
  headline: string 
}) {
  const isPending = confidenceMode === 'pending';
  
  return (
    <article
      style={{
        backgroundColor: vars.surface.raised,
        borderRadius: vars.radius.md,
        padding: vars.space[4],
        border: confidenceMode === 'flagged' ? `1px solid ${vars.signal.caution.bg}` : `1px solid ${vars.border.hairline}`,
        display: 'flex',
        flexDirection: 'column',
        gap: vars.space[3],
        marginBottom: vars.space[6],
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: vars.space[1] }}>
        <h2 style={{ 
          fontFamily: vars.font.family.sans, 
          fontSize: vars.size.title, 
          fontWeight: vars.font.weight.semibold,
          color: vars.text.primary,
          margin: 0,
        }}>
          {card.name}
        </h2>
        
        {isPending ? (
          <div style={{ color: vars.text.muted, fontFamily: vars.font.family.sans, fontSize: vars.size.body }}>
            Checking current conditions...
          </div>
        ) : (
          <div style={{ display: 'flex', gap: vars.space[2], alignItems: 'center' }}>
            <span style={{ 
              fontFamily: vars.font.family.sans, 
              fontSize: vars.size.body, 
              color: confidenceMode === 'confident' ? vars.text.primary : (confidenceMode === 'flagged' ? vars.signal.caution.fg : vars.text.secondary),
              fontWeight: confidenceMode === 'confident' ? vars.font.weight.medium : vars.font.weight.regular,
            }}>
              {headline}
            </span>
          </div>
        )}
      </div>

      <DecisionFacts card={card} className="decision-facts-row" />
      <style>{`
        .decision-facts-row {
          display: flex;
          gap: var(--space-4);
          font-family: var(--font-family-mono);
          font-size: var(--size-label);
          color: var(--text-primary);
          padding-top: var(--space-2);
          padding-bottom: var(--space-2);
          border-top: 1px solid var(--border-faint);
          border-bottom: 1px solid var(--border-faint);
        }
        .decision-facts-row .decision-item {
          display: flex;
          flex-direction: column;
        }
        .decision-facts-row .decision-label {
          color: var(--text-muted);
          margin-bottom: var(--space-1);
        }
      `}</style>

      {/* Honest scaled terrain glyph mock */}
      <svg width="100%" height="80" viewBox="0 0 300 80" preserveAspectRatio="none" style={{ marginTop: vars.space[2] }}>
        <path 
          d="M0,70 L50,65 L100,50 L150,20 L200,35 L250,60 L300,70" 
          fill="none" 
          stroke={vars.stroke.path} 
          strokeWidth="2"
        />
        <path 
          d="M0,70 L50,65 L100,50 L150,20 L200,35 L250,60 L300,70 L300,80 L0,80 Z" 
          fill={vars.border.faint} 
        />
      </svg>

      {/* §41 Warning Block */}
      {!isPending && card.warnings.length > 0 && (
        <div style={{ marginTop: vars.space[2] }}>
          <WarningBlock warnings={card.warnings} />
        </div>
      )}

      {/* Compact Conditions Block */}
      {!isPending && card.conditions && card.conditions.length > 0 && (
        <div style={{ marginTop: vars.space[2], paddingTop: vars.space[2], borderTop: `1px solid ${vars.border.hairline}` }}>
          <ConditionStates conditions={card.conditions} compact={true} />
        </div>
      )}
    </article>
  );
}

// -----------------------------------------------------------------------------
// The Context Ribbon
// -----------------------------------------------------------------------------
export function ContextSentence({ empty = false }: { empty?: boolean }) {
  if (empty) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: vars.space[2],
        paddingBottom: vars.space[4],
        marginBottom: vars.space[4],
      }}>
        <div style={{
          fontFamily: vars.font.family.mono,
          fontSize: vars.size.label,
          color: vars.text.muted,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
        }}>
          Search Area
        </div>
        <div style={{ color: vars.text.primary, fontFamily: vars.font.family.sans, fontSize: vars.size.body }}>
          We don't have verified data for that region yet.
        </div>
      </div>
    );
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: vars.space[2],
      paddingBottom: vars.space[4],
      marginBottom: vars.space[4],
    }}>
      <div style={{
        fontFamily: vars.font.family.mono,
        fontSize: vars.size.label,
        color: vars.text.muted,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
      }}>
        Shenandoah · Saturday Morning
      </div>
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: vars.space[1],
        fontFamily: vars.font.family.sans,
        fontSize: vars.size.body,
      }}>
        <div style={{ display: 'flex', gap: vars.space[2], color: vars.text.primary }}>
          <span aria-hidden="true">✓</span>
          <span>Mostly Cloudy 61°F · NWS</span>
        </div>
        <div style={{ display: 'flex', gap: vars.space[2], color: vars.text.secondary }}>
          <span aria-hidden="true" style={{ color: vars.text.muted }}>–</span>
          <span>Air quality couldn't be verified right now</span>
        </div>
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------------
// Alternative Option (Compact Card)
// -----------------------------------------------------------------------------
export function AlternativeOption({ name, distance, verdict }: { name: string, distance: string, verdict: 'GO' | 'NO' }) {
  return (
    <button style={{
      display: 'flex',
      width: '100%',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: `${vars.space[3]} ${vars.space[4]}`,
      backgroundColor: vars.surface.canvas,
      border: `1px solid ${vars.border.hairline}`,
      borderRadius: vars.radius.md,
      marginBottom: vars.space[2],
      cursor: 'pointer',
      textAlign: 'left'
    }}>
      <div style={{ display: 'flex', gap: vars.space[2], alignItems: 'baseline' }}>
        <span style={{ 
          fontFamily: vars.font.family.sans, 
          fontSize: vars.size.emphasis, 
          color: vars.text.primary 
        }}>
          {name}
        </span>
        <span style={{ 
          fontFamily: vars.font.family.mono, 
          fontSize: vars.size.label, 
          color: vars.text.muted 
        }}>
          {distance}
        </span>
      </div>
      <div style={{
        fontFamily: vars.font.family.mono,
        fontSize: vars.size.dataMicro,
        padding: `${vars.space[1]} ${vars.space[2]}`,
        backgroundColor: verdict === 'GO' ? vars.surface.raised : vars.signal.caution.bg,
        color: verdict === 'GO' ? vars.text.primary : vars.signal.caution.fg,
        borderRadius: vars.radius.sm,
        border: verdict === 'NO' ? `1px solid ${vars.signal.caution.fg}` : `1px solid ${vars.border.hairline}`,
      }}>
        {verdict}
      </div>
    </button>
  );
}

// -----------------------------------------------------------------------------
// Assembled Mobile View
// -----------------------------------------------------------------------------
export function MobileHomePrototype({ 
  card, 
  confidenceMode = 'confident', 
  headline = 'Good to go — nothing flagged across 6 checks',
  empty = false 
}: { 
  card?: CardVM, 
  confidenceMode?: ConfidenceMode, 
  headline?: string,
  empty?: boolean
}) {
  return (
    <div style={{
      backgroundColor: vars.surface.canvas,
      minHeight: '100vh',
      padding: vars.space[4],
      maxWidth: '432px',
      margin: '0 auto',
      outline: `1px solid ${vars.border.hairline}`,
    }}>
      <header style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginBottom: vars.space[6],
        fontFamily: vars.font.family.mono,
        fontSize: vars.size.label,
      }}>
        <h1 style={{ margin: 0, fontSize: 'inherit', color: vars.text.primary }}>CURATION</h1>
        <button style={{ 
          background: 'none', 
          border: 'none', 
          color: vars.text.muted, 
          fontFamily: 'inherit',
          fontSize: 'inherit',
          cursor: 'pointer'
        }}>
          SIGN IN
        </button>
      </header>

      <ContextSentence empty={empty} />
      
      {!empty && card && (
        <>
          <HeroCard card={card} confidenceMode={confidenceMode} headline={headline} />
          <div style={{ marginTop: vars.space[6] }}>
            <h3 style={{
              fontFamily: vars.font.family.mono,
              fontSize: vars.size.label,
              color: vars.text.muted,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: vars.space[3],
            }}>
              Other Options
            </h3>
            <AlternativeOption name="Hammock Hills" distance="3.3 mi" verdict="GO" />
            <AlternativeOption name="Virginia Capital" distance="0.7 mi" verdict="NO" />
          </div>
        </>
      )}
    </div>
  );
}

// -----------------------------------------------------------------------------
// Assembled Desktop View
// -----------------------------------------------------------------------------
export function DesktopHomePrototype({ 
  card, 
  confidenceMode = 'confident', 
  headline = 'Good to go — nothing flagged across 6 checks' 
}: { 
  card?: CardVM, 
  confidenceMode?: ConfidenceMode, 
  headline?: string 
}) {
  return (
    <div style={{
      backgroundColor: vars.surface.canvas,
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <header style={{
        display: 'flex',
        justifyContent: 'space-between',
        padding: `${vars.space[4]} ${vars.space[6]}`,
        fontFamily: vars.font.family.mono,
        fontSize: vars.size.label,
        borderBottom: `1px solid ${vars.border.hairline}`,
      }}>
        <h1 style={{ margin: 0, fontSize: 'inherit', color: vars.text.primary }}>ADVENTURE PLANNER</h1>
        <button style={{ 
          background: 'none', 
          border: 'none', 
          color: vars.text.muted, 
          fontFamily: 'inherit',
          fontSize: 'inherit',
          cursor: 'pointer'
        }}>
          SIGN IN
        </button>
      </header>
      
      <div style={{ display: 'flex', flex: 1 }}>
        <div style={{ 
          flex: '0 0 60%', 
          backgroundColor: '#e6e4de', 
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: vars.text.muted,
          fontFamily: vars.font.family.sans,
        }}>
          [ Topographic Map Rendered Here ]
        </div>
        
        <div style={{ 
          flex: '0 0 40%', 
          padding: vars.space[6],
          overflowY: 'auto',
          borderLeft: `1px solid ${vars.border.hairline}`
        }}>
          <ContextSentence />
          {card && <HeroCard card={card} confidenceMode={confidenceMode} headline={headline} />}
          <div style={{ marginTop: vars.space[6] }}>
            <h3 style={{
              fontFamily: vars.font.family.mono,
              fontSize: vars.size.label,
              color: vars.text.muted,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: vars.space[3],
            }}>
              Other Options
            </h3>
            <AlternativeOption name="Hammock Hills" distance="3.3 mi" verdict="GO" />
            <AlternativeOption name="Virginia Capital" distance="0.7 mi" verdict="NO" />
          </div>
        </div>
      </div>
    </div>
  );
}

export { createMockCard };
