export const dynamic = 'force-dynamic'
import { supabase } from '@/lib/supabase'
import type { SignalAccuracy, ConfidenceCalibration, Prediction } from '@/lib/types'

const MIN_PREDICTIONS = 30

function SegBar({ value, max = 100 }: { value: number; max?: number }) {
  const SEGS   = 10
  const filled = Math.round((value / max) * SEGS)
  return (
    <span className="font-mono text-brand-cyan text-[11px] tracking-[0.1em]">
      {'[' + '■'.repeat(filled) + '□'.repeat(SEGS - filled) + ']'}
    </span>
  )
}

export default async function PerformancePage() {
  const [resolvedRes, signalRes, calibRes] = await Promise.all([
    supabase.from('predictions')
      .select('direction_correct, confidence_score, actual_move_pct, resolved')
      .eq('resolved', true),
    supabase.from('signal_accuracy').select('*').order('resolved_count', { ascending: false }).limit(20),
    supabase.from('confidence_score_calibration').select('*').order('confidence_band'),
  ])

  const resolved    = (resolvedRes.data ?? []) as Pick<Prediction, 'direction_correct' | 'confidence_score' | 'actual_move_pct' | 'resolved'>[]
  const signals     = (signalRes.data ?? []) as SignalAccuracy[]
  const calibration = (calibRes.data ?? []) as ConfidenceCalibration[]

  const total   = resolved.length
  const correct = resolved.filter(p => p.direction_correct === true).length
  const winRate = total > 0 ? (correct / total * 100).toFixed(1) : null

  const avgWin  = resolved.filter(p => p.direction_correct && p.actual_move_pct != null)
    .reduce((s, p, _, a) => s + (p.actual_move_pct! / a.length), 0)
  const avgLoss = resolved.filter(p => p.direction_correct === false && p.actual_move_pct != null)
    .reduce((s, p, _, a) => s + (p.actual_move_pct! / a.length), 0)

  return (
    <div className="p-4 space-y-3 max-w-[480px] mx-auto pb-8">

      <div className="pt-3">
        <h1 className="font-play uppercase tracking-[0.25em] text-brand-white text-sm">Performance</h1>
      </div>

      {total < MIN_PREDICTIONS && (
        <div className="brand-card p-3" style={{ borderColor: 'rgba(255,185,56,0.35)', boxShadow: '0 0 10px rgba(255,185,56,0.05)' }}>
          <p className="font-space text-[10px] text-brand-gold tracking-widest">
            ◈ LEARNING PERIOD — {total}/{MIN_PREDICTIONS} PREDICTIONS RESOLVED
          </p>
        </div>
      )}

      <div className="brand-card p-4">
        <h2 className="section-label mb-4">Overall</h2>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="font-orbitron text-2xl leading-none text-brand-white">{total}</div>
            <div className="section-label mt-1.5">RESOLVED</div>
          </div>
          <div>
            <div className={`font-orbitron text-2xl leading-none ${winRate != null && parseFloat(winRate) >= 50 ? 'text-brand-cyan neon-text' : 'text-brand-magenta'}`}>
              {winRate != null ? `${winRate}%` : '—'}
            </div>
            <div className="section-label mt-1.5">WIN RATE</div>
          </div>
          <div>
            <div className="font-orbitron text-2xl leading-none text-brand-white">{correct}</div>
            <div className="section-label mt-1.5">CORRECT</div>
          </div>
        </div>
        {total > 0 && (
          <div className="mt-4 pt-3 border-t border-brand-cyan/10 flex gap-5">
            <div>
              <span className="section-label">AVG WIN </span>
              <span className="font-orbitron text-[11px] text-brand-cyan">+{avgWin.toFixed(1)}%</span>
            </div>
            <div>
              <span className="section-label">AVG LOSS </span>
              <span className="font-orbitron text-[11px] text-brand-magenta">{avgLoss.toFixed(1)}%</span>
            </div>
          </div>
        )}
      </div>

      {calibration.length > 0 && (
        <div className="brand-card p-4 space-y-4">
          <h2 className="section-label">Confidence Calibration</h2>
          {calibration.map(c => (
            <div key={c.confidence_band} className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="font-space text-[10px] text-brand-white/50 tracking-wider w-20 shrink-0">{c.confidence_band}</span>
                <SegBar value={c.direction_accuracy_pct ?? 0} max={100} />
                <span className="font-orbitron text-[10px] text-brand-cyan/60 w-10 text-right">
                  {c.direction_accuracy_pct != null ? `${c.direction_accuracy_pct.toFixed(0)}%` : '—'}
                </span>
              </div>
              <div className="font-space text-[9px] text-brand-white/20 tracking-wider pl-20">{c.resolved_count} TRADES</div>
            </div>
          ))}
        </div>
      )}

      {signals.length > 0 && (
        <div className="brand-card p-4 space-y-1">
          <h2 className="section-label mb-3">Signal Accuracy</h2>
          {signals.map((s, i) => (
            <div key={i} className="flex items-start justify-between gap-2 py-2 border-b border-brand-cyan/5 last:border-0">
              <div className="flex-1 min-w-0">
                <div className="font-space text-[10px] text-brand-white/55 tracking-wide truncate">
                  {Array.isArray(s.signals_fired) ? s.signals_fired.slice(0, 2).join(' · ') : s.signals_fired}
                </div>
                <div className="font-space text-[9px] text-brand-white/20 tracking-wider mt-0.5">{s.resolved_count} TRADES</div>
              </div>
              <div className="text-right shrink-0">
                {s.insufficient_data ? (
                  <span className="font-space text-[9px] text-brand-white/20 tracking-wider">INSUFFICIENT</span>
                ) : (
                  <span className={`font-orbitron text-xs ${(s.direction_accuracy_pct ?? 0) >= 50 ? 'text-brand-cyan' : 'text-brand-magenta'}`}>
                    {s.direction_accuracy_pct?.toFixed(0)}%
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
