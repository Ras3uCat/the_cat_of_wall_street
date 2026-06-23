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
    <div className="p-4 space-y-4 max-w-[480px] mx-auto">
      <h1 className="text-xl font-bold pt-2">Queued Trades</h1>

      {predictions.length === 0 && (
        <div className="bg-slate-800 rounded-2xl p-8 text-center text-slate-400 text-sm">
          No trades queued
        </div>
      )}

      {predictions.map(p => {
        const afterTax = p.predicted_move_pct != null ? p.predicted_move_pct * 0.70 : null
        const isTimeSensitive = p.predicted_timeframe_days != null && p.predicted_timeframe_days <= 3
        return (
          <div key={p.id} className="bg-slate-800 rounded-2xl p-4 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-xl">{p.ticker}</span>
                  {isTimeSensitive && (
                    <span className="text-xs bg-red-900 text-red-300 px-2 py-0.5 rounded-full">TIME-SENSITIVE</span>
                  )}
                </div>
                <span className="text-slate-400 text-xs">{p.scan_date}</span>
              </div>
              <div className="text-right">
                {p.confidence_score != null && (
                  <div className="text-lg font-bold">{p.confidence_score}</div>
                )}
                <div className="text-xs text-slate-400">confidence</div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 text-sm">
              {p.predicted_direction && (
                <div className="bg-slate-700/50 rounded-xl p-2 text-center">
                  <div className="text-slate-400 text-xs">Direction</div>
                  <div className={`font-semibold ${p.predicted_direction === 'up' ? 'text-green-400' : 'text-red-400'}`}>
                    {p.predicted_direction === 'up' ? 'LONG' : 'SHORT'}
                  </div>
                </div>
              )}
              {afterTax != null && (
                <div className="bg-slate-700/50 rounded-xl p-2 text-center">
                  <div className="text-slate-400 text-xs">After-tax</div>
                  <div className={`font-semibold ${afterTax >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {afterTax >= 0 ? '+' : ''}{afterTax.toFixed(1)}%
                  </div>
                </div>
              )}
              {p.predicted_timeframe_days != null && (
                <div className="bg-slate-700/50 rounded-xl p-2 text-center">
                  <div className="text-slate-400 text-xs">Timeframe</div>
                  <div className="font-semibold">{p.predicted_timeframe_days}d</div>
                </div>
              )}
            </div>

            {p.signals_fired?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {p.signals_fired.slice(0, 5).map(s => (
                  <span key={s} className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">{s}</span>
                ))}
              </div>
            )}

            {p.debate_narrative && (
              <p className="text-xs text-slate-400 line-clamp-3">{p.debate_narrative.slice(0, 200)}…</p>
            )}

            <div className="flex items-center gap-2 pt-1">
              <Link href={`/predictions/${p.id}`}
                className="text-xs text-blue-400 underline">Full debate →</Link>
            </div>

            <ApproveButtons predictionId={p.id} />
          </div>
        )
      })}
    </div>
  )
}
