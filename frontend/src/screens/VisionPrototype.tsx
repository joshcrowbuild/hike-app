import React from 'react';
import { vars } from '../design/theme.css';

// -----------------------------------------------------------------------------
// The Call (Hero Card)
// -----------------------------------------------------------------------------
export function HeroCard() {
  return (
    <article
      style={{
        backgroundColor: vars.surface.raised,
        borderRadius: vars.radius.md,
        padding: vars.space[4],
        border: `1px solid ${vars.border.hairline}`,
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
          Fox Hollow Trail
        </h2>
        <div style={{ display: 'flex', gap: vars.space[2], alignItems: 'center' }}>
          <span style={{ 
            fontFamily: vars.font.family.sans, 
            fontSize: vars.size.body, 
            color: vars.text.primary,
            fontWeight: vars.font.weight.medium,
          }}>
            Good to go
          </span>
          <span style={{ color: vars.text.muted }}>—</span>
          <span style={{ 
            fontFamily: vars.font.family.sans, 
            fontSize: vars.size.body, 
            color: vars.text.secondary 
          }}>
            nothing flagged across 6 checks
          </span>
        </div>
      </div>

      <div style={{ 
        display: 'flex', 
        gap: vars.space[4], 
        fontFamily: vars.font.family.mono, 
        fontSize: vars.size.label,
        color: vars.text.primary,
        paddingTop: vars.space[2],
        paddingBottom: vars.space[2],
        borderTop: `1px solid ${vars.border.faint}`,
        borderBottom: `1px solid ${vars.border.faint}`,
      }}>
        <span>3.0 mi</span>
        <span>↑ 278 ft</span>
        <span>~35 min</span>
      </div>

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
    </article>
  );
}

// -----------------------------------------------------------------------------
// The Context Ribbon
// -----------------------------------------------------------------------------
export function ContextRibbon() {
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
          <span>Air quality couldn't be verified</span>
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
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: `${vars.space[3]} ${vars.space[4]}`,
      backgroundColor: vars.surface.canvas,
      border: `1px solid ${vars.border.hairline}`,
      borderRadius: vars.radius.md,
      marginBottom: vars.space[2],
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
    </div>
  );
}

// -----------------------------------------------------------------------------
// Assembled Mobile View
// -----------------------------------------------------------------------------
export function MobileHomePrototype() {
  return (
    <div style={{
      backgroundColor: vars.surface.canvas,
      minHeight: '100vh',
      padding: vars.space[4],
      maxWidth: '432px',
      margin: '0 auto',
      outline: `1px solid ${vars.border.hairline}`, // Just for storybook framing
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

      <ContextRibbon />
      <HeroCard />
      
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
  );
}

// -----------------------------------------------------------------------------
// Assembled Desktop View
// -----------------------------------------------------------------------------
export function DesktopHomePrototype() {
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
        {/* Map Area (60%) */}
        <div style={{ 
          flex: '0 0 60%', 
          backgroundColor: '#e6e4de', // Mock map background color matching paper tone
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: vars.text.muted,
          fontFamily: vars.font.family.sans,
        }}>
          [ Topographic Map Rendered Here ]
        </div>
        
        {/* Decision Panel (40%) */}
        <div style={{ 
          flex: '0 0 40%', 
          padding: vars.space[6],
          overflowY: 'auto',
          borderLeft: `1px solid ${vars.border.hairline}`
        }}>
          <ContextRibbon />
          <HeroCard />
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
