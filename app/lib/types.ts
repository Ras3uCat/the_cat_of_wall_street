export type VixRegime = 'low' | 'normal' | 'elevated' | 'high'
export type ApprovalStatus = 'pending' | 'approved' | 'rejected'
export type ExitReason = 'stop_loss' | 'target_hit' | 'timeframe_expired' | 'thesis_invalidated' | 'manual_exit'

export interface Prediction {
  id: string
  scan_id: string | null
  ticker: string
  scan_date: string
  signals_fired: string[]
  signal_categories_count: number | null
  confidence_score: number | null
  confidence_component_convergence: number | null
  confidence_component_debate: number | null
  confidence_component_regime: number | null
  confidence_component_historical: number | null
  confidence_component_risk_mgr: number | null
  confidence_threshold: number | null
  score_passed: boolean | null
  cold_start: boolean
  agent: string | null
  predicted_direction: 'up' | 'down' | null
  predicted_move_pct: number | null
  predicted_timeframe_days: number | null
  vix_at_prediction: number | null
  market_regime: string | null
  executed: boolean
  skip_reason: string | null
  entry_price: number | null
  entry_date: string | null
  position_size_pct: number | null
  equity_at_entry: number | null
  resolved: boolean
  exit_price: number | null
  exit_date: string | null
  exit_reason: ExitReason | null
  actual_move_pct: number | null
  direction_correct: boolean | null
  accuracy_score: number | null
  lessons: string | null
  approval_status: ApprovalStatus | null
  debate_narrative: string | null
  created_at: string
  updated_at: string
}

export type SessionType = 'pre_market' | 'midday' | 'pm_window'

export interface Scan {
  id: string
  scan_date: string
  session_type: SessionType | null
  outcome_summary: string | null
  vix: number | null
  vix_regime: VixRegime | null
  macro_go: boolean | null
  macro_cautions: string[]
  watchlist: string[]
  eligible_tickers: string[]
  debate_candidates: string[]
  ineligible_tickers: { ticker: string; reasons: string[] }[]
  sector_rotation: {
    in_favor: string[]
    out_of_favor: string[]
    spy_return_1m_pct: number | null
  } | null
  created_at: string
}

export interface SignalAccuracy {
  signals_fired: string[]
  total_predictions: number
  resolved_count: number
  direction_accuracy_pct: number | null
  avg_confidence_score: number | null
  avg_win_pct: number | null
  avg_loss_pct: number | null
  insufficient_data: boolean
  earliest_prediction: string | null
  latest_prediction: string | null
}

export interface ConfidenceCalibration {
  confidence_band: string
  resolved_count: number
  direction_accuracy_pct: number | null
  avg_actual_move_pct: number | null
}
