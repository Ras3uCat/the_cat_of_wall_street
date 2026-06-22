export const dynamic = 'force-dynamic'
import { supabase } from '@/lib/supabase'
import type { Prediction } from '@/lib/types'

function daysHeld(entryDate: string) {
  const entry = new Date(entryDate)
  const now = new Date()
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
    <div className="p-4 space-y-4 max-w-[480px] mx-auto pb-8">
      <h1 className="text-xl font-bold pt-2">Open Positions</h1>

      {positions.length === 0 && (
        <div className="bg-slate-800 rounded-2xl p-8 text-center text-slate-400 text-sm">
          No open positions
        </div>
      )}

      {positions.map(p => {
        const days = p.entry_date ? daysHeld(p.entry_date) : null
        const timeframeLeft = p.predicted_timeframe_days != null && days != null
          ? p.predicted_timeframe_days - days
          : null
        return (
          <div key={p.id} className="bg-slate-800 rounded-2xl p-4 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="font-bold text-xl">{p.ticker}</span>
                {p.entry_date && (
                  <p className="text-slate-400 text-xs">Entered {p.entry_date}</p>
                )}
              </div>
              <div className="text-right">
                {days != null && (
                  <div className="text-lg font-bold">{days}d</div>
                )}
                <div className="text-xs text-slate-400">held</div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 text-sm">
              {p.entry_price != null && (
                <div className="bg-slate-700/50 rounded-xl p-2 text-center">
                  <div className="text-slate-400 text-xs">Entry</div>
                  <div className="font-semibold">${p.entry_price.toFixed(2)}</div>
                </div>
              )}
              {p.position_size_pct != null && (
                <div className="bg-slate-700/50 rounded-xl p-2 text-center">
                  <div className="text-slate-400 text-xs">Size</div>
                  <div className="font-semibold">{p.position_size_pct}%</div>
                </div>
              )}
              {timeframeLeft != null && (
                <div className={`bg-slate-700/50 rounded-xl p-2 text-center`}>
                  <div className="text-slate-400 text-xs">Days left</div>
                  <div className={`font-semibold ${timeframeLeft <= 1 ? 'text-red-400' : timeframeLeft <= 3 ? 'text-yellow-400' : ''}`}>
                    {timeframeLeft}d
                  </div>
                </div>
              )}
            </div>

            {p.predicted_move_pct != null && (
              <div className="flex gap-4 text-sm">
                <div>
                  <span className="text-slate-400">Target: </span>
                  <span className="text-green-400">+{p.predicted_move_pct.toFixed(1)}%</span>
                </div>
                {p.confidence_score != null && (
                  <div>
                    <span className="text-slate-400">Score: </span>
                    <span>{p.confidence_score}</span>
                  </div>
                )}
              </div>
            )}

            {p.signals_fired?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {p.signals_fired.slice(0, 4).map(s => (
                  <span key={s} className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">{s}</span>
                ))}
              </div>
            )}

            {timeframeLeft != null && timeframeLeft <= 0 && (
              <div className="bg-red-900/40 border border-red-700/50 rounded-xl p-2 text-xs text-red-300">
                Timeframe expired — exit review triggered at next session
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
