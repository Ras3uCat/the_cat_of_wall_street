import { supabase } from '@/lib/supabase'
import type { Prediction } from '@/lib/types'

interface PriceRow {
  ticker: string
  date: string
  close: number
}

export type PriceHistory = Map<string, { date: string; close: number }[]>

export async function fetchPriceHistory(tickers: string[]): Promise<PriceHistory> {
  const uniqueTickers = [...new Set(tickers)]
  const history: PriceHistory = new Map()
  if (uniqueTickers.length === 0) return history

  const { data } = await supabase
    .from('price_history')
    .select('ticker,date,close')
    .in('ticker', uniqueTickers)
    .order('date', { ascending: true })

  for (const row of (data ?? []) as PriceRow[]) {
    const rows = history.get(row.ticker) ?? []
    rows.push({ date: row.date, close: row.close })
    history.set(row.ticker, rows)
  }
  return history
}

export interface HypotheticalPnl {
  entryPrice: number | null
  currentPrice: number | null
  currentPriceDate: string | null
  pnlPct: number | null
}

export function computeHypotheticalPnl(p: Prediction, history: PriceHistory): HypotheticalPnl {
  const rows = history.get(p.ticker) ?? []
  if (rows.length === 0 || !p.predicted_direction) {
    return { entryPrice: null, currentPrice: null, currentPriceDate: null, pnlPct: null }
  }

  const asOfScanDate = [...rows].reverse().find(r => r.date <= p.scan_date)
  const entryPrice = p.entry_price ?? asOfScanDate?.close ?? null

  const latest = rows[rows.length - 1]
  const currentPrice = latest.close
  const currentPriceDate = latest.date

  if (entryPrice == null || currentPrice == null) {
    return { entryPrice, currentPrice: null, currentPriceDate: null, pnlPct: null }
  }

  const rawPct = ((currentPrice - entryPrice) / entryPrice) * 100
  const pnlPct = Math.round((p.predicted_direction === 'up' ? rawPct : -rawPct) * 100) / 100

  return { entryPrice, currentPrice, currentPriceDate, pnlPct }
}
