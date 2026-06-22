export const dynamic = 'force-dynamic'
import { supabase } from '@/lib/supabase'
import type { SignalAccuracy, ConfidenceCalibration, Prediction } from '@/lib/types'

const MIN_PREDICTIONS = 30

export default async function PerformancePage() {
  const [resolvedRes, signalRes, calibRes] = await Promise.all([
    supabase.from('predictions').select('direction_correct, confidence_score, actual_move_pct, resolved')
      .eq('resolved', true),
    supabase.from('signal_accuracy').select('*').order('resolved_count', { ascending: false }).limit(20),
    supabase.from('confidence_score_calibration').select('*').order('confidence_band'),
  ])

  const resolved = (resolvedRes.data ?? []) as Pick<Prediction, 'direction_correct' | 'confidence_score' | 'actual_move_pct' | 'resolved'>[]
  const signals = (signalRes.data ?? []) as SignalAccuracy[]
  const calibration = (calibRes.data ?? []) as ConfidenceCalibration[]

  const total = resolved.length
  const correct = resolved.filter(p => p.direction_correct === true).length
  const winRate = total > 0 ? (correct / total * 100).toFixed(1) : null

  const avgWin = resolved.filter(p => p.direction_correct && p.actual_move_pct != null)
    .reduce((s, p, _, a) => s + (p.actual_move_pct! / a.length), 0)
  const avgLoss = resolved.filter(p => p.direction_correct === false && p.actual_move_pct != null)
    .reduce((s, p, _, a) => s + (p.actual_move_pct! / a.length), 0)

  return (
    <div className="p-4 space-y-4 max-w-[480px] mx-auto pb-8">
      <h1 className="text-xl font-bold pt-2">Performance</h1>

      {total < MIN_PREDICTIONS && (
        <div className="bg-amber-900/30 border border-amber-700/50 rounded-2xl p-4 text-sm text-amber-300">
          Learning period — {total} prediction{total !== 1 ? 's' : ''} resolved, need {MIN_PREDICTIONS}+ to calibrate
        </div>
      )}

      <section className="bg-slate-800 rounded-2xl p-4">
        <h2 className="text-sm font-medium text-slate-300 mb-3">Overall</h2>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="text-2xl font-bold">{total}</div>
            <div className="text-xs text-slate-400">Resolved</div>
          </div>
          <div>
            <div className={`text-2xl font-bold ${winRate != null && parseFloat(winRate) >= 50 ? 'text-green-400' : 'text-red-400'}`}>
              {winRate != null ? `${winRate}%` : '—'}
            </div>
            <div className="text-xs text-slate-400">Win Rate</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{correct}</div>
            <div className="text-xs text-slate-400">Correct</div>
          </div>
        </div>
        {total > 0 && (
          <div className="mt-3 flex gap-4 text-sm">
            <div>
              <span className="text-slate-400">Avg win: </span>
              <span className="text-green-400">+{avgWin.toFixed(1)}%</span>
            </div>
            <div>
              <span className="text-slate-400">Avg loss: </span>
              <span className="text-red-400">{avgLoss.toFixed(1)}%</span>
            </div>
          </div>
        )}
      </section>

      {calibration.length > 0 && (
        <section className="bg-slate-800 rounded-2xl p-4 space-y-3">
          <h2 className="text-sm font-medium text-slate-300">Confidence Calibration</h2>
          {calibration.map(c => (
            <div key={c.confidence_band}>
              <div className="flex justify-between text-xs text-slate-400 mb-1">
                <span>{c.confidence_band}</span>
                <span>{c.direction_accuracy_pct != null ? `${c.direction_accuracy_pct.toFixed(0)}% win` : '—'} · {c.resolved_count} trades</span>
              </div>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full"
                  style={{ width: `${c.direction_accuracy_pct ?? 0}%` }}
                />
              </div>
            </div>
          ))}
        </section>
      )}

      {signals.length > 0 && (
        <section className="bg-slate-800 rounded-2xl p-4 space-y-3">
          <h2 className="text-sm font-medium text-slate-300">Signal Accuracy</h2>
          <div className="space-y-2">
            {signals.map((s, i) => (
              <div key={i} className="flex items-start justify-between gap-2 text-sm py-2 border-b border-slate-700/50 last:border-0">
                <div className="flex-1 min-w-0">
                  <div className="text-slate-300 text-xs truncate">
                    {Array.isArray(s.signals_fired) ? s.signals_fired.slice(0, 2).join(', ') : s.signals_fired}
                  </div>
                  <div className="text-slate-500 text-xs">{s.resolved_count} trades</div>
                </div>
                <div className="text-right shrink-0">
                  {s.insufficient_data ? (
                    <span className="text-slate-500 text-xs">insufficient data</span>
                  ) : (
                    <span className={`font-semibold ${(s.direction_accuracy_pct ?? 0) >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                      {s.direction_accuracy_pct?.toFixed(0)}%
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
