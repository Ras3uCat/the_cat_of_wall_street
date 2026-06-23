export const dynamic = 'force-dynamic'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import type { Prediction } from '@/lib/types'

const STATUS_STYLE: Record<string, string> = {
  pending:  'border-brand-gold/60    text-brand-gold',
  approved: 'border-brand-cyan/60    text-brand-cyan',
  rejected: 'border-brand-magenta/60 text-brand-magenta',
}

export default async function PredictionsPage({ searchParams }: { searchParams: Promise<{ page?: string }> }) {
  const { page: pageParam } = await searchParams
  const page     = Math.max(1, parseInt(pageParam ?? '1'))
  const PAGE_SIZE = 20
  const from     = (page - 1) * PAGE_SIZE

  const { data, count } = await supabase
    .from('predictions')
    .select('*', { count: 'exact' })
    .order('created_at', { ascending: false })
    .range(from, from + PAGE_SIZE - 1)

  const predictions = (data ?? []) as Prediction[]
  const totalPages  = Math.ceil((count ?? 0) / PAGE_SIZE)

  return (
    <div className="p-4 space-y-3 max-w-[480px] mx-auto pb-8">

      <div className="pt-3 flex items-center justify-between">
        <h1 className="font-play uppercase tracking-[0.25em] text-brand-white text-sm">Predictions</h1>
        {count != null && (
          <span className="font-space text-[9px] text-brand-white/25 tracking-widest">{count} TOTAL</span>
        )}
      </div>

      {predictions.length === 0 && (
        <div className="brand-card p-8 text-center">
          <p className="font-space text-[11px] text-brand-white/25 tracking-widest">NO PREDICTIONS YET</p>
        </div>
      )}

      {predictions.map(p => {
        const afterTax = p.predicted_move_pct != null ? p.predicted_move_pct * 0.70 : null
        return (
          <Link key={p.id} href={`/predictions/${p.id}`} className="block brand-card p-4 space-y-2.5">
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="font-play uppercase tracking-widest text-brand-white text-lg">{p.ticker}</span>
                <span className="font-space text-[10px] text-brand-white/25 tracking-wider ml-2">{p.scan_date}</span>
              </div>
              <div className="flex items-center gap-1.5 flex-wrap justify-end mt-0.5">
                {p.approval_status && (
                  <span className={`font-space text-[9px] px-2 py-0.5 rounded border tracking-widest ${STATUS_STYLE[p.approval_status]}`}>
                    {p.approval_status.toUpperCase()}
                  </span>
                )}
                {p.executed && (
                  <span className="font-space text-[9px] px-2 py-0.5 rounded border border-brand-cyan/35 text-brand-cyan/55 tracking-widest">EXEC</span>
                )}
                {p.resolved && (
                  <span className="font-space text-[9px] px-2 py-0.5 rounded border border-brand-white/15 text-brand-white/35 tracking-widest">DONE</span>
                )}
              </div>
            </div>

            <div className="flex items-center gap-3">
              <span className={`font-orbitron text-xs tracking-widest ${p.score_passed ? 'text-brand-cyan neon-text' : 'text-brand-white/25'}`}>
                {p.score_passed ? 'ENTER' : 'SKIP'}
              </span>
              {p.confidence_score != null && (
                <span className="font-space text-[10px] text-brand-white/40 tracking-wider">
                  SCORE <span className="font-orbitron text-brand-white">{p.confidence_score}</span>
                </span>
              )}
              {afterTax != null && (
                <span className={`font-orbitron text-[10px] ${afterTax >= 0 ? 'text-brand-cyan' : 'text-brand-magenta'}`}>
                  {afterTax >= 0 ? '+' : ''}{afterTax.toFixed(1)}%
                </span>
              )}
            </div>

            {p.signals_fired?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {p.signals_fired.slice(0, 4).map(s => (
                  <span key={s} className="font-space text-[9px] border border-brand-cyan/20 text-brand-cyan/45 px-1.5 py-0.5 rounded tracking-wide">
                    {s}
                  </span>
                ))}
                {p.signals_fired.length > 4 && (
                  <span className="font-space text-[9px] border border-brand-white/10 text-brand-white/25 px-1.5 py-0.5 rounded">
                    +{p.signals_fired.length - 4}
                  </span>
                )}
              </div>
            )}

            {p.resolved && p.direction_correct != null && (
              <div className={`font-orbitron text-[11px] tracking-widest ${p.direction_correct ? 'text-brand-cyan' : 'text-brand-magenta'}`}>
                {p.direction_correct ? '◆ WIN' : '◇ LOSS'}
                {p.actual_move_pct != null && ` · ${p.actual_move_pct >= 0 ? '+' : ''}${p.actual_move_pct.toFixed(1)}%`}
              </div>
            )}
          </Link>
        )
      })}

      {totalPages > 1 && (
        <div className="flex justify-center gap-3 pt-2 pb-4">
          {page > 1 && (
            <Link href={`/predictions?page=${page - 1}`}
              className="font-space text-[10px] tracking-widest px-4 py-2 brand-card text-brand-cyan/60">
              ← PREV
            </Link>
          )}
          <span className="font-space text-[10px] px-4 py-2 text-brand-white/25 tracking-widest self-center">
            {page} / {totalPages}
          </span>
          {page < totalPages && (
            <Link href={`/predictions?page=${page + 1}`}
              className="font-space text-[10px] tracking-widest px-4 py-2 brand-card text-brand-cyan/60">
              NEXT →
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
