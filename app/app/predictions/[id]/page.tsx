export const dynamic = 'force-dynamic'
import { notFound } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import type { Prediction } from '@/lib/types'
import ApproveButtons from '@/components/ApproveButtons'

const COMPONENT_LABELS: Record<string, string> = {
  convergence: 'CONVERGENCE',
  debate:      'DEBATE',
  regime:      'REGIME',
  historical:  'HISTORICAL',
  risk_mgr:    'RISK MGR',
}

const COMPONENT_MAX: Record<string, number> = {
  convergence: 30,
  debate:      25,
  regime:      20,
  historical:  15,
  risk_mgr:    10,
}

function SegBar({ value, max }: { value: number; max: number }) {
  const SEGS   = 10
  const filled = Math.min(SEGS, Math.max(0, Math.round((value / max) * SEGS)))
  return (
    <span className="font-mono text-brand-cyan text-xs tracking-[0.1em]">
      {'[' + '■'.repeat(filled) + '□'.repeat(SEGS - filled) + ']'}
    </span>
  )
}

export default async function PredictionDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const { data } = await supabase.from('predictions').select('*').eq('id', id).single()
  if (!data) notFound()
  const p = data as Prediction

  const afterTax = p.predicted_move_pct != null ? p.predicted_move_pct * 0.70 : null
  const components = [
    { key: 'convergence', val: p.confidence_component_convergence },
    { key: 'debate',      val: p.confidence_component_debate      },
    { key: 'regime',      val: p.confidence_component_regime      },
    { key: 'historical',  val: p.confidence_component_historical  },
    { key: 'risk_mgr',    val: p.confidence_component_risk_mgr    },
  ].filter(c => c.val != null)

  return (
    <div className="p-4 space-y-3 max-w-[480px] mx-auto pb-8">

      <div className="pt-3 flex items-start justify-between gap-2">
        <div>
          <h1 className="font-play uppercase tracking-[0.3em] text-brand-white text-2xl">{p.ticker}</h1>
          <p className="font-space text-[10px] text-brand-white/30 tracking-widest mt-0.5">{p.scan_date}</p>
        </div>
        <div className="text-right">
          <div className={`font-orbitron text-xl tracking-widest ${p.score_passed ? 'text-brand-cyan neon-text' : 'text-brand-white/25'}`}>
            {p.score_passed ? 'ENTER' : 'SKIP'}
          </div>
          {p.confidence_score != null && (
            <div className="font-space text-[10px] text-brand-white/35 tracking-wider mt-0.5">
              SCORE <span className="font-orbitron text-brand-white">{p.confidence_score}</span>
            </div>
          )}
        </div>
      </div>

      <div className="brand-card p-4 space-y-3">
        <h2 className="section-label">Trade Parameters</h2>
        <div className="grid grid-cols-2 gap-3">
          {p.predicted_direction && (
            <div>
              <div className="section-label mb-1">Direction</div>
              <div className={`font-orbitron text-xs tracking-widest ${p.predicted_direction === 'up' ? 'text-brand-cyan' : 'text-brand-magenta'}`}>
                {p.predicted_direction === 'up' ? '▲ LONG' : '▼ SHORT'}
              </div>
            </div>
          )}
          {p.predicted_move_pct != null && (
            <div>
              <div className="section-label mb-1">Target Move</div>
              <div className="font-orbitron text-xs text-brand-cyan tracking-wider">+{p.predicted_move_pct.toFixed(1)}%</div>
            </div>
          )}
          {afterTax != null && (
            <div>
              <div className="section-label mb-1">After-Tax (30%)</div>
              <div className={`font-orbitron text-xs tracking-wider ${afterTax >= 0 ? 'text-brand-cyan' : 'text-brand-magenta'}`}>
                {afterTax >= 0 ? '+' : ''}{afterTax.toFixed(1)}%
              </div>
            </div>
          )}
          {p.predicted_timeframe_days != null && (
            <div>
              <div className="section-label mb-1">Timeframe</div>
              <div className="font-orbitron text-xs text-brand-white tracking-wider">{p.predicted_timeframe_days}D</div>
            </div>
          )}
          {p.vix_at_prediction != null && (
            <div>
              <div className="section-label mb-1">VIX</div>
              <div className="font-orbitron text-xs text-brand-white tracking-wider">{p.vix_at_prediction.toFixed(1)}</div>
            </div>
          )}
          {p.market_regime && (
            <div>
              <div className="section-label mb-1">Regime</div>
              <div className="font-space text-xs text-brand-white/70 tracking-wider uppercase">{p.market_regime}</div>
            </div>
          )}
        </div>
      </div>

      {components.length > 0 && (
        <div className="brand-card p-4 space-y-3">
          <h2 className="section-label">Confidence Breakdown</h2>
          {components.map(({ key, val }) => (
            <div key={key} className="flex items-center justify-between gap-3">
              <span className="font-space text-[10px] text-brand-white/35 tracking-wider w-24 shrink-0">
                {COMPONENT_LABELS[key]}
              </span>
              <SegBar value={val ?? 0} max={COMPONENT_MAX[key]} />
              <span className="font-orbitron text-[10px] text-brand-cyan/60 w-8 text-right">{val}/{COMPONENT_MAX[key]}</span>
            </div>
          ))}
          {p.confidence_score != null && (
            <div className="pt-2 border-t border-brand-cyan/10 flex items-center justify-between">
              <span className="section-label">Total</span>
              <span className="font-orbitron text-sm text-brand-cyan">{p.confidence_score}/100</span>
            </div>
          )}
        </div>
      )}

      {p.signals_fired?.length > 0 && (
        <div className="brand-card p-4 space-y-2">
          <h2 className="section-label">Signals Fired</h2>
          <div className="flex flex-wrap gap-1.5">
            {p.signals_fired.map(s => (
              <span key={s} className="font-space text-[9px] border border-brand-cyan/22 text-brand-cyan/55 px-2 py-0.5 rounded tracking-wide">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {p.debate_narrative && (
        <div className="brand-card p-4 space-y-2">
          <h2 className="section-label">Agent Debate</h2>
          <div className="font-inter text-[11px] text-brand-white/65 whitespace-pre-wrap leading-relaxed">{p.debate_narrative}</div>
        </div>
      )}

      {p.resolved && (
        <div className="brand-card p-4 space-y-3">
          <h2 className="section-label">Outcome</h2>
          <div className="grid grid-cols-2 gap-3">
            {p.actual_move_pct != null && (
              <div>
                <div className="section-label mb-1">Actual Move</div>
                <div className={`font-orbitron text-sm tracking-wider ${p.actual_move_pct >= 0 ? 'text-brand-cyan' : 'text-brand-magenta'}`}>
                  {p.actual_move_pct >= 0 ? '+' : ''}{p.actual_move_pct.toFixed(2)}%
                </div>
              </div>
            )}
            {p.direction_correct != null && (
              <div>
                <div className="section-label mb-1">Direction</div>
                <div className={`font-orbitron text-[11px] tracking-widest ${p.direction_correct ? 'text-brand-cyan' : 'text-brand-magenta'}`}>
                  {p.direction_correct ? '◆ CORRECT' : '◇ WRONG'}
                </div>
              </div>
            )}
            {p.exit_reason && (
              <div>
                <div className="section-label mb-1">Exit Reason</div>
                <div className="font-space text-xs text-brand-white/60 uppercase tracking-wider">{p.exit_reason.replace('_', ' ')}</div>
              </div>
            )}
            {p.accuracy_score != null && (
              <div>
                <div className="section-label mb-1">Accuracy Score</div>
                <div className="font-orbitron text-sm text-brand-white">{p.accuracy_score}</div>
              </div>
            )}
          </div>
          {p.lessons && (
            <p className="font-inter text-[11px] text-brand-white/35 pt-2 border-t border-brand-cyan/10 leading-relaxed">{p.lessons}</p>
          )}
        </div>
      )}

      {p.approval_status === 'approved' && !p.executed && (
        <ApproveButtons predictionId={p.id} />
      )}
    </div>
  )
}
