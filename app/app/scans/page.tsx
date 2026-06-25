export const dynamic = 'force-dynamic'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import type { Scan } from '@/lib/types'

const SESSION_LABEL: Record<string, string> = {
  pre_market: 'PRE-MKT',
  midday:     'MIDDAY',
  pm_window:  'PM',
}

const SESSION_COLOR: Record<string, string> = {
  pre_market: 'text-brand-cyan border-brand-cyan/50',
  midday:     'text-brand-gold border-brand-gold/50',
  pm_window:  'text-brand-magenta border-brand-magenta/50',
}

const VIX_COLOR: Record<string, string> = {
  low:      'text-brand-cyan',
  normal:   'text-brand-cyan/60',
  elevated: 'text-brand-gold',
  high:     'text-brand-magenta',
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
  }).toUpperCase()
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'America/Chicago',
  }).toUpperCase() + ' CT'
}

export default async function ScansPage() {
  const [scansRes, predsRes] = await Promise.all([
    supabase
      .from('scans')
      .select('id,scan_date,session_type,outcome_summary,vix,vix_regime,macro_go,watchlist,debate_candidates,eligible_tickers,created_at')
      .order('created_at', { ascending: false })
      .limit(30),
    supabase
      .from('predictions')
      .select('scan_id,approval_status')
      .not('scan_id', 'is', null),
  ])

  const scans = (scansRes.data ?? []) as Scan[]
  const preds = predsRes.data ?? []

  const entersByScan = preds.reduce<Record<string, number>>((acc, p) => {
    if (p.approval_status === 'approved' && p.scan_id) {
      acc[p.scan_id] = (acc[p.scan_id] ?? 0) + 1
    }
    return acc
  }, {})

  return (
    <div className="p-4 space-y-3 max-w-[480px] mx-auto pb-8">
      <div className="pt-3 pb-1 flex items-center justify-between">
        <div>
          <h1 className="font-play uppercase tracking-[0.25em] text-brand-white text-sm">Scan History</h1>
          <p className="font-space text-[10px] text-brand-white/30 tracking-widest mt-0.5">ALL CLOUD RUNS</p>
        </div>
        <span className="font-space text-[10px] text-brand-white/25 tracking-wider">{scans.length} RUNS</span>
      </div>

      {scans.length === 0 ? (
        <div className="brand-card p-8 text-center">
          <p className="font-space text-[11px] text-brand-white/25 tracking-widest">NO SCAN RUNS YET</p>
        </div>
      ) : (
        <div className="space-y-2">
          {scans.map(scan => {
            const session = scan.session_type ?? 'pre_market'
            const enters  = entersByScan[scan.id] ?? 0

            return (
              <div key={scan.id} className="brand-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`font-space text-[9px] px-2 py-0.5 rounded border tracking-widest ${SESSION_COLOR[session]}`}>
                      {SESSION_LABEL[session] ?? session.toUpperCase()}
                    </span>
                    <span className="font-play text-xs text-brand-white tracking-wide">
                      {formatDate(scan.created_at)}
                    </span>
                  </div>
                  <span className="font-space text-[9px] text-brand-white/25 tracking-wider">
                    {formatTime(scan.created_at)}
                  </span>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  {scan.vix != null && (
                    <span className={`font-space text-[10px] tracking-widest ${VIX_COLOR[scan.vix_regime ?? 'normal']}`}>
                      VIX {scan.vix.toFixed(1)}
                    </span>
                  )}
                  <span className={`font-space text-[10px] tracking-widest ${
                    scan.macro_go ? 'text-brand-cyan/70' : 'text-brand-magenta'
                  }`}>
                    {scan.macro_go ? '▶ GO' : '■ HALT'}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 pt-2 border-t border-brand-cyan/10">
                  {[
                    { val: scan.watchlist?.length ?? 0,         label: 'SCANNED'  },
                    { val: scan.debate_candidates?.length ?? 0, label: 'DEBATED'  },
                    { val: enters,                              label: 'ENTER', highlight: enters > 0 },
                  ].map(({ val, label, highlight }) => (
                    <div key={label} className="text-center">
                      <div className={`font-orbitron text-xl leading-none ${highlight ? 'text-brand-gold neon-gold' : 'text-brand-white'}`}>
                        {val}
                      </div>
                      <div className="section-label mt-1">{label}</div>
                    </div>
                  ))}
                </div>

                {scan.outcome_summary && (
                  <p className="font-inter text-[11px] text-brand-white/40 border-l-2 border-brand-cyan/20 pl-2 leading-relaxed">
                    {scan.outcome_summary}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
