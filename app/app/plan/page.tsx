export default function PlanPage() {
  return (
    <div className="p-4 space-y-3 max-w-[480px] mx-auto pb-8">

      <div className="pt-3">
        <h1 className="font-play uppercase tracking-[0.25em] text-brand-white text-sm">System Rules</h1>
      </div>

      <div className="brand-card p-4 space-y-3">
        <h2 className="section-label">Confidence Thresholds</h2>
        <div className="space-y-0.5">
          {[
            ['LOW',      '< 15',   '60'],
            ['NORMAL',   '15–20',  '60'],
            ['ELEVATED', '20–30',  '65'],
            ['HIGH',     '> 30',   '72'],
          ].map(([regime, range, score]) => (
            <div key={regime} className="flex items-center py-2 border-b border-brand-cyan/8 last:border-0 gap-3">
              <span className="font-space text-[10px] tracking-widest text-brand-white/55 w-20 shrink-0">{regime}</span>
              <span className="font-space text-[10px] text-brand-white/30 tracking-wider flex-1">{range}</span>
              <span className="font-orbitron text-xs text-brand-cyan">{score}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="brand-card p-4 space-y-3">
        <h2 className="section-label">After-Tax Minimums (30%)</h2>
        <div className="space-y-0.5">
          {[
            ['INTRADAY (0–1D)',      '+3%'],
            ['SHORT-TERM (4–30D)',   '+5%'],
            ['MEDIUM-TERM (30–90D)', '+7%'],
          ].map(([tf, min]) => (
            <div key={tf} className="flex items-center py-2 border-b border-brand-cyan/8 last:border-0 gap-3">
              <span className="font-space text-[9px] tracking-wider text-brand-white/45 flex-1">{tf}</span>
              <span className="font-orbitron text-xs text-brand-cyan">{min}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="brand-card p-4 space-y-3">
        <h2 className="section-label">Risk Hard Rules</h2>
        <ul className="space-y-2.5">
          {[
            'Max 2 new positions / day',
            'Max 20% equity deployed per session',
            'Agentic account only (cash, T+1 settlement)',
            'Stop loss: 7% below entry · 5% in elevated VIX',
            'No trades when macro_go = false',
            'Autonomous auto-execute — AI executes when confidence threshold passes',
          ].map((rule, i) => (
            <li key={i} className="flex gap-3 items-start">
              <span className="text-brand-magenta/55 font-mono text-[10px] mt-px shrink-0">■</span>
              <span className="font-inter text-[11px] text-brand-white/60 leading-relaxed">{rule}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="brand-card p-4 space-y-3">
        <h2 className="section-label">Trailing Stop Ladder</h2>
        <ul className="space-y-2.5">
          {[
            ['+15%', 'Move stop to breakeven'],
            ['+25%', 'Trail 10% below peak'],
            ['+35%', 'Trail 8% below peak'],
          ].map(([trigger, action]) => (
            <li key={trigger} className="flex gap-3 items-center">
              <span className="font-orbitron text-[11px] text-brand-cyan w-10 shrink-0">{trigger}</span>
              <span className="font-inter text-[11px] text-brand-white/55">{action}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="brand-card p-4 space-y-3">
        <h2 className="section-label">Exit Triggers</h2>
        <ul className="space-y-2.5">
          {[
            'Stop loss hit',
            'Price target reached → review whether to hold',
            'Timeframe expired',
            'Original thesis invalidated',
            'Trailing stop triggered',
            'Sector rotation turns against position',
            'Manual exit',
          ].map((trigger, i) => (
            <li key={i} className="flex gap-3 items-start">
              <span className="font-orbitron text-[9px] text-brand-cyan/35 mt-px shrink-0 w-4">{i + 1}</span>
              <span className="font-inter text-[11px] text-brand-white/60">{trigger}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="brand-card p-4 space-y-2">
        <h2 className="section-label">Learning Period</h2>
        <p className="font-inter text-[11px] text-brand-white/55 leading-relaxed">
          No trade execution through 2026-06-28. Debates and prediction logging run normally to build calibration data.
        </p>
      </div>

      <p className="text-center font-space text-[9px] tracking-widest pt-1"
        style={{ color: 'rgba(232,254,255,0.12)' }}>
        Sync complete △ M3OW
      </p>
    </div>
  )
}
