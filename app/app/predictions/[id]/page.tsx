export const dynamic = 'force-dynamic'
import { notFound } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import type { Prediction } from '@/lib/types'
import ApproveButtons from '@/components/ApproveButtons'

const COMPONENT_LABELS: Record<string, string> = {
  convergence: 'Signal Convergence',
  debate: 'Debate Outcome',
  regime: 'Market Regime',
  historical: 'Historical Accuracy',
  risk_mgr: 'Risk Manager',
}

export default async function PredictionDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const { data } = await supabase.from('predictions').select('*').eq('id', id).single()
  if (!data) notFound()
  const p = data as Prediction

  const afterTax = p.predicted_move_pct != null ? p.predicted_move_pct * 0.70 : null
  const components = [
    { key: 'convergence', val: p.confidence_component_convergence },
    { key: 'debate', val: p.confidence_component_debate },
    { key: 'regime', val: p.confidence_component_regime },
    { key: 'historical', val: p.confidence_component_historical },
    { key: 'risk_mgr', val: p.confidence_component_risk_mgr },
  ].filter(c => c.val != null)

  return (
    <div className="p-4 space-y-4 max-w-[480px] mx-auto pb-8">
      <div className="pt-2 flex items-start justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">{p.ticker}</h1>
          <p className="text-slate-400 text-sm">{p.scan_date}</p>
        </div>
        <div className="text-right">
          <div className={`text-xl font-bold ${p.score_passed ? 'text-green-400' : 'text-slate-400'}`}>
            {p.score_passed ? 'ENTER' : 'SKIP'}
          </div>
          {p.confidence_score != null && (
            <div className="text-slate-400 text-sm">Score: {p.confidence_score}</div>
          )}
        </div>
      </div>

      <section className="bg-slate-800 rounded-2xl p-4 space-y-2">
        <h2 className="text-sm font-medium text-slate-300">Trade Parameters</h2>
        <div className="grid grid-cols-2 gap-3 text-sm">
          {p.predicted_direction && (
            <div>
              <div className="text-slate-400">Direction</div>
              <div className={`font-semibold ${p.predicted_direction === 'up' ? 'text-green-400' : 'text-red-400'}`}>
                {p.predicted_direction === 'up' ? 'LONG' : 'SHORT'}
              </div>
            </div>
          )}
          {p.predicted_move_pct != null && (
            <div>
              <div className="text-slate-400">Target move</div>
              <div className="font-semibold">+{p.predicted_move_pct.toFixed(1)}%</div>
            </div>
          )}
          {afterTax != null && (
            <div>
              <div className="text-slate-400">After-tax (30%)</div>
              <div className={`font-semibold ${afterTax >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {afterTax >= 0 ? '+' : ''}{afterTax.toFixed(1)}%
              </div>
            </div>
          )}
          {p.predicted_timeframe_days != null && (
            <div>
              <div className="text-slate-400">Timeframe</div>
              <div className="font-semibold">{p.predicted_timeframe_days}d</div>
            </div>
          )}
          {p.vix_at_prediction != null && (
            <div>
              <div className="text-slate-400">VIX</div>
              <div className="font-semibold">{p.vix_at_prediction.toFixed(1)}</div>
            </div>
          )}
          {p.market_regime && (
            <div>
              <div className="text-slate-400">Regime</div>
              <div className="font-semibold capitalize">{p.market_regime}</div>
            </div>
          )}
        </div>
      </section>

      {components.length > 0 && (
        <section className="bg-slate-800 rounded-2xl p-4 space-y-3">
          <h2 className="text-sm font-medium text-slate-300">Confidence Breakdown</h2>
          {components.map(({ key, val }) => (
            <div key={key}>
              <div className="flex justify-between text-xs text-slate-400 mb-1">
                <span>{COMPONENT_LABELS[key]}</span>
                <span>{val}/20</span>
              </div>
              <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${((val ?? 0) / 20) * 100}%` }} />
              </div>
            </div>
          ))}
          {p.confidence_score != null && (
            <div className="pt-1 border-t border-slate-700 flex justify-between text-sm font-semibold">
              <span>Total</span>
              <span>{p.confidence_score}/100</span>
            </div>
          )}
        </section>
      )}

      {p.signals_fired?.length > 0 && (
        <section className="bg-slate-800 rounded-2xl p-4 space-y-2">
          <h2 className="text-sm font-medium text-slate-300">Signals Fired</h2>
          <div className="flex flex-wrap gap-1.5">
            {p.signals_fired.map(s => (
              <span key={s} className="text-xs bg-slate-700 text-slate-300 px-2.5 py-1 rounded-full">{s}</span>
            ))}
          </div>
        </section>
      )}

      {p.debate_narrative && (
        <section className="bg-slate-800 rounded-2xl p-4 space-y-2">
          <h2 className="text-sm font-medium text-slate-300">Agent Debate</h2>
          <div className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">{p.debate_narrative}</div>
        </section>
      )}

      {p.resolved && (
        <section className="bg-slate-800 rounded-2xl p-4 space-y-2">
          <h2 className="text-sm font-medium text-slate-300">Outcome</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            {p.actual_move_pct != null && (
              <div>
                <div className="text-slate-400">Actual move</div>
                <div className={`font-semibold ${p.actual_move_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {p.actual_move_pct >= 0 ? '+' : ''}{p.actual_move_pct.toFixed(2)}%
                </div>
              </div>
            )}
            {p.direction_correct != null && (
              <div>
                <div className="text-slate-400">Direction</div>
                <div className={`font-semibold ${p.direction_correct ? 'text-green-400' : 'text-red-400'}`}>
                  {p.direction_correct ? 'CORRECT' : 'WRONG'}
                </div>
              </div>
            )}
            {p.exit_reason && (
              <div>
                <div className="text-slate-400">Exit reason</div>
                <div className="font-semibold capitalize">{p.exit_reason.replace('_', ' ')}</div>
              </div>
            )}
            {p.accuracy_score != null && (
              <div>
                <div className="text-slate-400">Accuracy score</div>
                <div className="font-semibold">{p.accuracy_score}</div>
              </div>
            )}
          </div>
          {p.lessons && (
            <p className="text-xs text-slate-400 pt-2 border-t border-slate-700">{p.lessons}</p>
          )}
        </section>
      )}

      {p.approval_status === 'pending' && (
        <ApproveButtons predictionId={p.id} />
      )}
    </div>
  )
}
