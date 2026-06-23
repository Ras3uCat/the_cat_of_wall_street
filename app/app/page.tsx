export const dynamic = 'force-dynamic'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import type { Scan } from '@/lib/types'

const VIX_REGIME_COLORS: Record<string, string> = {
  low: 'bg-green-900 text-green-300',
  normal: 'bg-blue-900 text-blue-300',
  elevated: 'bg-yellow-900 text-yellow-300',
  high: 'bg-red-900 text-red-300',
}

function fmt$(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

export default async function Dashboard() {
  const [scanRes, pendingRes, resolvedRes] = await Promise.all([
    supabase.from('scans').select('*').order('created_at', { ascending: false }).limit(1).single(),
    supabase.from('predictions').select('id, ticker, confidence_score, predicted_move_pct, predicted_timeframe_days')
      .eq('approval_status', 'approved').eq('executed', false),
    supabase.from('predictions').select('actual_move_pct, position_size_pct, equity_at_entry')
      .eq('resolved', true).not('actual_move_pct', 'is', null),
  ])

  const scan = scanRes.data as Scan | null
  const pending = pendingRes.data ?? []
  const resolved = resolvedRes.data ?? []

  const pnl = resolved.reduce((sum, p) => {
    if (p.actual_move_pct == null || p.position_size_pct == null || p.equity_at_entry == null) return sum
    return sum + (p.actual_move_pct / 100) * (p.position_size_pct / 100) * p.equity_at_entry
  }, 0)

  const today = new Date().toISOString().split('T')[0]
  const isToday = scan?.scan_date === today

  return (
    <div className="p-4 space-y-4 max-w-[480px] mx-auto">
      <header className="flex items-center justify-between pt-2">
        <div>
          <h1 className="text-xl font-bold">Cat of Wall Street</h1>
          <p className="text-slate-400 text-xs">{new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })}</p>
        </div>
        <span className="text-3xl">🐱</span>
      </header>

      {scan ? (
        <section className="bg-slate-800 rounded-2xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-300">Market Regime</span>
            {!isToday && <span className="text-xs text-slate-500">Last scan: {scan.scan_date}</span>}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${VIX_REGIME_COLORS[scan.vix_regime ?? 'normal']}`}>
              VIX {scan.vix?.toFixed(1)} — {scan.vix_regime?.toUpperCase()}
            </span>
            <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${scan.macro_go ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}`}>
              {scan.macro_go ? 'MACRO GO' : 'MACRO HALT'}
            </span>
          </div>
          {!scan.macro_go && scan.macro_cautions?.length > 0 && (
            <p className="text-xs text-slate-400">{scan.macro_cautions.join(' · ')}</p>
          )}
          <div className="grid grid-cols-3 gap-2 pt-1">
            <div className="text-center">
              <div className="text-lg font-bold">{scan.watchlist?.length ?? 0}</div>
              <div className="text-xs text-slate-400">Scanned</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold">{scan.debate_candidates?.length ?? 0}</div>
              <div className="text-xs text-slate-400">Debated</div>
            </div>
            <div className="text-center">
              <div className={`text-lg font-bold ${pending.length > 0 ? 'text-amber-400' : ''}`}>{pending.length}</div>
              <div className="text-xs text-slate-400">Pending</div>
            </div>
          </div>
        </section>
      ) : (
        <section className="bg-slate-800 rounded-2xl p-4 text-center text-slate-400 text-sm">
          No scans yet — system will run at 8 AM CT
        </section>
      )}

      {pending.length > 0 && (
        <Link href="/approvals" className="block bg-amber-900/40 border border-amber-700/50 rounded-2xl p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-semibold text-amber-300">{pending.length} trade{pending.length > 1 ? 's' : ''} queued for execution</p>
              <p className="text-xs text-slate-400 mt-0.5">
                {pending.slice(0, 3).map(p => p.ticker).join(', ')}{pending.length > 3 ? ` +${pending.length - 3} more` : ''}
              </p>
            </div>
            <span className="text-amber-400 text-xl">›</span>
          </div>
        </Link>
      )}

      <section className="bg-slate-800 rounded-2xl p-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm font-medium text-slate-300">Realized P&L</span>
          <span className="text-xs text-slate-500">{resolved.length} resolved</span>
        </div>
        <div className={`text-2xl font-bold ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {pnl >= 0 ? '+' : ''}{fmt$(pnl)}
        </div>
        <p className="text-xs text-slate-500 mt-1">After-tax estimate (30% rate assumed)</p>
      </section>

      <div className="grid grid-cols-2 gap-3">
        <Link href="/predictions" className="bg-slate-800 rounded-2xl p-4 flex flex-col gap-1">
          <span className="text-2xl">📋</span>
          <span className="text-sm font-medium">All Predictions</span>
          <span className="text-xs text-slate-400">History & debates</span>
        </Link>
        <Link href="/positions" className="bg-slate-800 rounded-2xl p-4 flex flex-col gap-1">
          <span className="text-2xl">💼</span>
          <span className="text-sm font-medium">Open Positions</span>
          <span className="text-xs text-slate-400">Active trades</span>
        </Link>
      </div>
    </div>
  )
}
