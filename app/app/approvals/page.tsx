export const dynamic = 'force-dynamic'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import type { Prediction } from '@/lib/types'
import ApproveButtons from '@/components/ApproveButtons'

export default async function ApprovalsPage() {
  const { data } = await supabase
    .from('predictions')
    .select('*')
    .eq('approval_status', 'approved')
    .eq('executed', false)
    .order('created_at', { ascending: false })

  const predictions = (data ?? []) as Prediction[]

  return (
    <div className="p-4 space-y-3 max-w-[480px] mx-auto pb-8">

      <div className="pt-3 flex items-center justify-between">
        <h1 className="font-play uppercase tracking-[0.25em] text-brand-white text-sm">Queued Trades</h1>
        <span className="font-orbitron text-sm text-brand-gold neon-gold">{predictions.length}</span>
      </div>

      {predictions.length === 0 && (
        <div className="brand-card p-8 text-center">
          <p className="font-space text-[11px] text-brand-white/25 tracking-widest">NO TRADES QUEUED</p>
        </div>
      )}

      {predictions.map(p => {
        const afterTax = p.predicted_move_pct != null ? p.predicted_move_pct * 0.70 : null
        const timeSensitive = p.predicted_timeframe_days != null && p.predicted_timeframe_days <= 3
        return (
          <div key={p.id} className="brand-card p-4 space-y-3"
            style={timeSensitive ? { borderColor: 'rgba(255,185,56,0.45)', boxShadow: '0 0 14px rgba(255,185,56,0.07)' } : undefined}>

            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-play uppercase tracking-[0.2em] text-brand-white text-xl">{p.ticker}</span>
                  {timeSensitive && (
                    <span className="font-space text-[9px] border border-brand-gold/55 text-brand-gold px-2 py-0.5 rounded tracking-widest">
                      TIME-SENSITIVE
                    </span>
                  )}
                </div>
                <span className="font-space text-[10px] text-brand-white/25 tracking-wider">{p.scan_date}</span>
              </div>
              <div className="text-right">
                {p.confidence_score != null && (
                  <div className="font-orbitron text-xl text-brand-cyan neon-text">{p.confidence_score}</div>
                )}
                <div className="section-label mt-0.5">SCORE</div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              {p.predicted_direction && (
                <div className="p-2 text-center rounded border border-brand-cyan/15">
                  <div className="section-label mb-1">DIR</div>
                  <div className={`font-orbitron text-[10px] tracking-widest ${p.predicted_direction === 'up' ? 'text-brand-cyan' : 'text-brand-magenta'}`}>
                    {p.predicted_direction === 'up' ? '▲ LONG' : '▼ SHORT'}
                  </div>
                </div>
              )}
              {afterTax != null && (
                <div className="p-2 text-center rounded border border-brand-cyan/15">
                  <div className="section-label mb-1">NET</div>
                  <div className={`font-orbitron text-[10px] ${afterTax >= 0 ? 'text-brand-cyan' : 'text-brand-magenta'}`}>
                    {afterTax >= 0 ? '+' : ''}{afterTax.toFixed(1)}%
                  </div>
                </div>
              )}
              {p.predicted_timeframe_days != null && (
                <div className="p-2 text-center rounded border border-brand-cyan/15">
                  <div className="section-label mb-1">DAYS</div>
                  <div className="font-orbitron text-[10px] text-brand-white">{p.predicted_timeframe_days}D</div>
                </div>
              )}
            </div>

            {p.signals_fired?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {p.signals_fired.slice(0, 5).map(s => (
                  <span key={s} className="font-space text-[9px] border border-brand-cyan/20 text-brand-cyan/45 px-1.5 py-0.5 rounded tracking-wide">
                    {s}
                  </span>
                ))}
              </div>
            )}

            {p.debate_narrative && (
              <p className="font-inter text-[11px] text-brand-white/35 line-clamp-3 border-l border-brand-cyan/20 pl-2 leading-relaxed">
                {p.debate_narrative.slice(0, 200)}…
              </p>
            )}

            <div className="pt-1 border-t border-brand-cyan/10">
              <Link href={`/predictions/${p.id}`}
                className="font-space text-[10px] text-brand-cyan/50 tracking-widest">
                FULL DEBATE →
              </Link>
            </div>

            <ApproveButtons predictionId={p.id} />
          </div>
        )
      })}
    </div>
  )
}
