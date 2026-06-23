export const dynamic = 'force-dynamic'
import { supabase } from '@/lib/supabase'
import type { Prediction } from '@/lib/types'

function daysHeld(entryDate: string) {
  const entry = new Date(entryDate)
  const now   = new Date()
  return Math.floor((now.getTime() - entry.getTime()) / (1000 * 60 * 60 * 24))
}

export default async function PositionsPage() {
  const { data } = await supabase
    .from('predictions')
    .select('*')
    .eq('executed', true)
    .eq('resolved', false)
    .order('entry_date', { ascending: false })

  const positions = (data ?? []) as Prediction[]

  return (
    <div className="p-4 space-y-3 max-w-[480px] mx-auto pb-8">

      <div className="pt-3 flex items-center justify-between">
        <h1 className="font-play uppercase tracking-[0.25em] text-brand-white text-sm">Open Positions</h1>
        <span className="font-orbitron text-xs text-brand-white/35">{positions.length}</span>
      </div>

      {positions.length === 0 && (
        <div className="brand-card p-8 text-center">
          <p className="font-space text-[11px] text-brand-white/25 tracking-widest">NO OPEN POSITIONS</p>
        </div>
      )}

      {positions.map(p => {
        const days = p.entry_date ? daysHeld(p.entry_date) : null
        const timeframeLeft = p.predicted_timeframe_days != null && days != null
          ? p.predicted_timeframe_days - days
          : null
        const urgent = timeframeLeft != null && timeframeLeft <= 1
        return (
          <div key={p.id} className="brand-card p-4 space-y-3"
            style={urgent ? { borderColor: 'rgba(211,76,241,0.45)', boxShadow: '0 0 10px rgba(211,76,241,0.06)' } : undefined}>

            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="font-play uppercase tracking-[0.2em] text-brand-white text-xl">{p.ticker}</span>
                {p.entry_date && (
                  <p className="font-space text-[10px] text-brand-white/25 tracking-wider mt-0.5">
                    ENTERED {p.entry_date}
                  </p>
                )}
              </div>
              <div className="text-right">
                {days != null && (
                  <div className="font-orbitron text-xl text-brand-white leading-none">{days}</div>
                )}
                <div className="section-label mt-0.5">DAYS HELD</div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              {p.entry_price != null && (
                <div className="p-2 text-center rounded border border-brand-cyan/15">
                  <div className="section-label mb-1">ENTRY</div>
                  <div className="font-orbitron text-[11px] text-brand-white">${p.entry_price.toFixed(2)}</div>
                </div>
              )}
              {p.position_size_pct != null && (
                <div className="p-2 text-center rounded border border-brand-cyan/15">
                  <div className="section-label mb-1">SIZE</div>
                  <div className="font-orbitron text-[11px] text-brand-white">{p.position_size_pct}%</div>
                </div>
              )}
              {timeframeLeft != null && (
                <div className="p-2 text-center rounded border border-brand-cyan/15">
                  <div className="section-label mb-1">LEFT</div>
                  <div className={`font-orbitron text-[11px] ${
                    timeframeLeft <= 1 ? 'text-brand-magenta'
                    : timeframeLeft <= 3 ? 'text-brand-gold'
                    : 'text-brand-white'
                  }`}>{timeframeLeft}D</div>
                </div>
              )}
            </div>

            {p.predicted_move_pct != null && (
              <div className="flex gap-5">
                <div>
                  <span className="section-label">TARGET </span>
                  <span className="font-orbitron text-[11px] text-brand-cyan">+{p.predicted_move_pct.toFixed(1)}%</span>
                </div>
                {p.confidence_score != null && (
                  <div>
                    <span className="section-label">SCORE </span>
                    <span className="font-orbitron text-[11px] text-brand-white">{p.confidence_score}</span>
                  </div>
                )}
              </div>
            )}

            {p.signals_fired?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {p.signals_fired.slice(0, 4).map(s => (
                  <span key={s} className="font-space text-[9px] border border-brand-cyan/20 text-brand-cyan/45 px-1.5 py-0.5 rounded tracking-wide">
                    {s}
                  </span>
                ))}
              </div>
            )}

            {timeframeLeft != null && timeframeLeft <= 0 && (
              <div className="border border-brand-magenta/30 rounded-lg p-2 font-space text-[10px] text-brand-magenta tracking-widest">
                ■ TIMEFRAME EXPIRED — EXIT REVIEW AT NEXT SESSION
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
