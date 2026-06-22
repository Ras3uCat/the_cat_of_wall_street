export const dynamic = 'force-dynamic'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import type { Prediction } from '@/lib/types'

const STATUS_CHIP: Record<string, string> = {
  pending: 'bg-amber-900 text-amber-300',
  approved: 'bg-green-900 text-green-300',
  rejected: 'bg-red-900 text-red-300',
}

export default async function PredictionsPage({ searchParams }: { searchParams: Promise<{ page?: string }> }) {
  const { page: pageParam } = await searchParams
  const page = Math.max(1, parseInt(pageParam ?? '1'))
  const PAGE_SIZE = 20
  const from = (page - 1) * PAGE_SIZE

  const { data, count } = await supabase
    .from('predictions')
    .select('*', { count: 'exact' })
    .order('created_at', { ascending: false })
    .range(from, from + PAGE_SIZE - 1)

  const predictions = (data ?? []) as Prediction[]
  const totalPages = Math.ceil((count ?? 0) / PAGE_SIZE)

  return (
    <div className="p-4 space-y-3 max-w-[480px] mx-auto">
      <h1 className="text-xl font-bold pt-2">Predictions</h1>

      {predictions.length === 0 && (
        <p className="text-slate-400 text-sm text-center py-8">No predictions yet</p>
      )}

      {predictions.map(p => {
        const afterTax = p.predicted_move_pct != null ? p.predicted_move_pct * 0.70 : null
        return (
          <Link key={p.id} href={`/predictions/${p.id}`}
            className="block bg-slate-800 rounded-2xl p-4 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="font-bold text-lg">{p.ticker}</span>
                <span className="text-slate-400 text-xs ml-2">{p.scan_date}</span>
              </div>
              <div className="flex items-center gap-1.5 flex-wrap justify-end">
                {p.approval_status && (
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_CHIP[p.approval_status]}`}>
                    {p.approval_status}
                  </span>
                )}
                {p.executed && <span className="text-xs px-2 py-0.5 rounded-full bg-blue-900 text-blue-300">executed</span>}
                {p.resolved && <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">resolved</span>}
              </div>
            </div>

            <div className="flex items-center gap-3 text-sm">
              <span className={`font-semibold ${p.score_passed ? 'text-green-400' : 'text-slate-400'}`}>
                {p.score_passed ? 'ENTER' : 'SKIP'}
              </span>
              {p.confidence_score != null && (
                <span className="text-slate-300">Score: <span className="font-medium">{p.confidence_score}</span></span>
              )}
              {afterTax != null && (
                <span className="text-slate-400">
                  After-tax: <span className={afterTax >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {afterTax >= 0 ? '+' : ''}{afterTax.toFixed(1)}%
                  </span>
                </span>
              )}
            </div>

            {p.signals_fired?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {p.signals_fired.slice(0, 4).map(s => (
                  <span key={s} className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">{s}</span>
                ))}
                {p.signals_fired.length > 4 && (
                  <span className="text-xs bg-slate-700 text-slate-400 px-2 py-0.5 rounded-full">+{p.signals_fired.length - 4}</span>
                )}
              </div>
            )}

            {p.resolved && p.direction_correct != null && (
              <div className={`text-xs font-medium ${p.direction_correct ? 'text-green-400' : 'text-red-400'}`}>
                {p.direction_correct ? 'WIN' : 'LOSS'} · {p.actual_move_pct != null ? `${p.actual_move_pct >= 0 ? '+' : ''}${p.actual_move_pct.toFixed(1)}%` : ''}
              </div>
            )}
          </Link>
        )
      })}

      {totalPages > 1 && (
        <div className="flex justify-center gap-3 pt-2 pb-4">
          {page > 1 && (
            <Link href={`/predictions?page=${page - 1}`} className="px-4 py-2 bg-slate-800 rounded-xl text-sm">← Prev</Link>
          )}
          <span className="px-4 py-2 text-slate-400 text-sm">{page} / {totalPages}</span>
          {page < totalPages && (
            <Link href={`/predictions?page=${page + 1}`} className="px-4 py-2 bg-slate-800 rounded-xl text-sm">Next →</Link>
          )}
        </div>
      )}
    </div>
  )
}
