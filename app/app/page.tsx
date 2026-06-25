export const dynamic = 'force-dynamic'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import type { Scan } from '@/lib/types'

const VIX_COLOR: Record<string, string> = {
  low:      'text-brand-cyan    border-brand-cyan/50',
  normal:   'text-brand-cyan/60 border-brand-cyan/25',
  elevated: 'text-brand-gold    border-brand-gold/50',
  high:     'text-brand-magenta border-brand-magenta/50',
}

function fmt$(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

export default async function Dashboard() {
  const [scanRes, pendingRes, resolvedRes] = await Promise.all([
    supabase.from('scans').select('*').order('created_at', { ascending: false }).limit(1).single(),
    supabase.from('predictions')
      .select('id, ticker, confidence_score, predicted_move_pct, predicted_timeframe_days')
      .eq('approval_status', 'approved').eq('executed', false),
    supabase.from('predictions')
      .select('actual_move_pct, position_size_pct, equity_at_entry')
      .eq('resolved', true).not('actual_move_pct', 'is', null),
  ])

  const scan     = scanRes.data as Scan | null
  const pending  = pendingRes.data ?? []
  const resolved = resolvedRes.data ?? []

  const pnl = resolved.reduce((sum, p) => {
    if (p.actual_move_pct == null || p.position_size_pct == null || p.equity_at_entry == null) return sum
    return sum + (p.actual_move_pct / 100) * (p.position_size_pct / 100) * p.equity_at_entry
  }, 0)

  const today   = new Date().toISOString().split('T')[0]
  const isToday = scan?.scan_date === today

  return (
    <div className="p-4 space-y-3 max-w-[480px] mx-auto pb-8">

      <div className="pt-3 pb-1 flex items-center justify-between">
        <div>
          <h1 className="font-play uppercase tracking-[0.25em] text-brand-white text-sm">Trading System</h1>
          <p className="font-space text-[10px] text-brand-white/30 tracking-widest mt-0.5">
            {new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }).toUpperCase()}
          </p>
        </div>
        <div className="text-right">
          <div className="section-label">STATUS</div>
          <div className="font-space text-[10px] text-brand-cyan tracking-wider mt-0.5">● ONLINE</div>
        </div>
      </div>

      {scan ? (
        <div className="brand-card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="section-label">Market Regime</span>
            {!isToday && (
              <span className="font-space text-[9px] text-brand-white/25 tracking-wider">{scan.scan_date}</span>
            )}
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <span className={`font-space text-[10px] px-2.5 py-1 rounded border tracking-widest ${VIX_COLOR[scan.vix_regime ?? 'normal']}`}>
              VIX {scan.vix?.toFixed(1)} — {(scan.vix_regime ?? 'normal').toUpperCase()}
            </span>
            <span className={`font-space text-[10px] px-2.5 py-1 rounded border tracking-widest ${
              scan.macro_go
                ? 'text-brand-cyan border-brand-cyan/50'
                : 'text-brand-magenta border-brand-magenta/50'
            }`}>
              {scan.macro_go ? '▶ MACRO GO' : '■ MACRO HALT'}
            </span>
          </div>

          {!scan.macro_go && scan.macro_cautions?.length > 0 && (
            <p className="font-inter text-[11px] text-brand-white/35 border-l-2 border-brand-magenta/30 pl-2 leading-relaxed">
              {scan.macro_cautions.join(' · ')}
            </p>
          )}

          <div className="grid grid-cols-3 gap-2 pt-2 border-t border-brand-cyan/10">
            {[
              { val: scan.watchlist?.length ?? 0,          label: 'SCANNED'                      },
              { val: scan.debate_candidates?.length ?? 0,  label: 'DEBATED'                      },
              { val: pending.length, label: 'QUEUED', highlight: pending.length > 0 },
            ].map(({ val, label, highlight }) => (
              <div key={label} className="text-center">
                <div className={`font-orbitron text-2xl leading-none ${highlight ? 'text-brand-gold neon-gold' : 'text-brand-white'}`}>
                  {val}
                </div>
                <div className="section-label mt-1.5">{label}</div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="brand-card p-8 text-center space-y-1">
          <p className="font-space text-[11px] text-brand-white/25 tracking-widest">NO SIGNAL DATA</p>
          <p className="font-space text-[10px] text-brand-white/15 tracking-widest">NEXT SCAN: 08:00 CT</p>
        </div>
      )}

      {pending.length > 0 && (
        <Link href="/approvals" className="block brand-card p-4"
          style={{ borderColor: 'rgba(255,185,56,0.4)', boxShadow: '0 0 14px rgba(255,185,56,0.07)' }}>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-play uppercase tracking-widest text-brand-gold text-sm neon-gold">
                {pending.length} trade{pending.length > 1 ? 's' : ''} queued
              </p>
              <p className="font-space text-[10px] text-brand-white/35 mt-0.5 tracking-wider">
                {pending.slice(0, 3).map(p => p.ticker).join(' · ')}
                {pending.length > 3 ? ` +${pending.length - 3}` : ''}
              </p>
            </div>
            <span className="text-brand-gold/50 font-orbitron text-lg">›</span>
          </div>
        </Link>
      )}

      <div className="brand-card p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="section-label">Realized P&L</span>
          <span className="font-space text-[9px] text-brand-white/25 tracking-wider">{resolved.length} RESOLVED</span>
        </div>
        <div className={`font-orbitron text-3xl leading-none ${pnl >= 0 ? 'text-brand-cyan neon-text' : 'text-brand-magenta'}`}>
          {pnl >= 0 ? '+' : ''}{fmt$(pnl)}
        </div>
        <p className="font-space text-[9px] text-brand-white/20 mt-1.5 tracking-wider">EST. AFTER 30% TAX</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Link href="/predictions" className="brand-card p-4 flex flex-col gap-2">
          <span className="section-label">TRADES</span>
          <span className="font-play uppercase tracking-wider text-sm text-brand-white">Predictions</span>
          <span className="font-space text-[9px] text-brand-white/25 tracking-wider">HISTORY &amp; DEBATES</span>
        </Link>
        <Link href="/positions" className="brand-card p-4 flex flex-col gap-2">
          <span className="section-label">HOLDINGS</span>
          <span className="font-play uppercase tracking-wider text-sm text-brand-white">Positions</span>
          <span className="font-space text-[9px] text-brand-white/25 tracking-wider">ACTIVE TRADES</span>
        </Link>
      </div>

      <Link href="/scans" className="block brand-card p-4">
        <div className="flex items-center justify-between">
          <div>
            <span className="section-label">CLOUD RUNS</span>
            <p className="font-play uppercase tracking-wider text-sm text-brand-white mt-1">Scan History</p>
            <p className="font-space text-[9px] text-brand-white/25 tracking-wider mt-0.5">PRE-MKT · MIDDAY · PM</p>
          </div>
          <span className="text-brand-white/25 font-orbitron text-lg">›</span>
        </div>
      </Link>

      <p className="text-center font-space text-[9px] tracking-widest pt-1"
        style={{ color: 'rgba(232,254,255,0.12)' }}>
        Sync complete △ M3OW
      </p>
    </div>
  )
}
