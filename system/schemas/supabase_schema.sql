-- ============================================================
-- Cat of Wall Street — Supabase Schema
-- Run this in the Supabase SQL editor to initialize the database.
-- ============================================================

-- ============================================================
-- TABLE: scans
-- One row per daily scan run. Stores macro snapshot and which
-- tickers were evaluated and whether they proceeded to debate.
-- ============================================================
create table if not exists scans (
  id                      text primary key,          -- format: scan_2026-06-21
  scan_date               date not null,
  vix                     numeric,
  vix_regime              text,                       -- low | normal | elevated | high
  macro_go                boolean,
  macro_cautions          text[],
  watchlist               text[],
  eligible_tickers        text[],
  debate_candidates       text[],
  macro_blocked_all       boolean,                    -- true when VIX>25 or FOMC day blocked all new entries
  ineligible_tickers      jsonb,                      -- [{ticker, reasons}]
  sector_rotation         jsonb,                      -- full sector rotation output
  created_at              timestamptz default now()
);

-- ============================================================
-- TABLE: predictions
-- One row per trade opportunity evaluated, whether executed or
-- skipped. This is the learning backbone of the system.
-- Every signal-driven opportunity gets logged here.
-- ============================================================
create table if not exists predictions (
  id                          text primary key,       -- format: pred_20260621_001
  scan_id                     text references scans(id),
  ticker                      text not null,
  scan_date                   date not null,

  -- Signal data
  signals_fired               text[],                 -- which signal categories converged
  signal_categories_count     integer,

  -- Confidence score (Section 3.5 of strategy doc)
  confidence_score            integer,                -- 0–100 composite
  confidence_component_convergence   integer,         -- 0–30
  confidence_component_debate        integer,         -- 0–25
  confidence_component_regime        integer,         -- 0–20
  confidence_component_historical    integer,         -- 0–15
  confidence_component_risk_mgr      integer,         -- 0–10
  confidence_threshold        integer,                -- required minimum at time of prediction
  score_passed                boolean,
  cold_start                  boolean default true,   -- true until 30+ resolved predictions

  -- Prediction details
  agent                       text,                   -- which agent issued the final call
  predicted_direction         text,                   -- up | down
  predicted_move_pct          numeric,
  predicted_timeframe_days    integer,
  vix_at_prediction           numeric,
  market_regime               text,

  -- Execution
  executed                    boolean default false,
  skip_reason                 text,                   -- null | score_below_threshold | risk_manager_veto | macro_filter | universe_filter | manual_skip
  entry_price                 numeric,
  entry_date                  date,
  position_size_pct           numeric,                -- % of account

  -- Resolution (filled in when prediction timeframe expires)
  resolved                    boolean default false,
  exit_price                  numeric,
  exit_date                   date,
  exit_reason                 text check (exit_reason in ('stop_loss','target_hit','timeframe_expired','thesis_invalidated','manual_exit')),
  actual_move_pct             numeric,
  direction_correct           boolean,
  accuracy_score              integer,                -- 0–100
  lessons                     text,

  created_at                  timestamptz default now(),
  updated_at                  timestamptz default now()
);

-- ============================================================
-- INDEXES
-- ============================================================
create index if not exists predictions_ticker_idx on predictions(ticker);
create index if not exists predictions_scan_date_idx on predictions(scan_date);
create index if not exists predictions_resolved_idx on predictions(resolved);
create index if not exists predictions_executed_idx on predictions(executed);
create index if not exists predictions_exit_date_idx on predictions(exit_date);

-- ============================================================
-- VIEW: signal_accuracy
-- Used by the weekly self-improvement loop to recalculate
-- signal weight recommendations.
-- Only includes resolved predictions with 10+ observations
-- per signal combination (insufficient_data flag otherwise).
-- ============================================================
create or replace view signal_accuracy as
select
  signals_fired,
  count(*)                                                      as total_predictions,
  count(*) filter (where resolved = true)                       as resolved_count,
  round(
    100.0 * count(*) filter (where direction_correct = true)
    / nullif(count(*) filter (where resolved = true), 0), 1
  )                                                             as direction_accuracy_pct,
  round(avg(confidence_score) filter (where resolved = true), 1) as avg_confidence_score,
  round(avg(actual_move_pct) filter (where resolved = true and direction_correct = true), 2) as avg_win_pct,
  round(avg(actual_move_pct) filter (where resolved = true and direction_correct = false), 2) as avg_loss_pct,
  case
    when count(*) filter (where resolved = true) < 10 then true
    else false
  end                                                           as insufficient_data,
  min(scan_date)                                                as earliest_prediction,
  max(scan_date)                                                as latest_prediction
from predictions
group by signals_fired
order by direction_accuracy_pct desc nulls last;

-- ============================================================
-- VIEW: agent_accuracy
-- Per-agent accuracy leaderboard for weekly review.
-- ============================================================
create or replace view agent_accuracy as
select
  agent,
  count(*)                                                      as total_calls,
  count(*) filter (where resolved = true)                       as resolved_count,
  round(
    100.0 * count(*) filter (where direction_correct = true)
    / nullif(count(*) filter (where resolved = true), 0), 1
  )                                                             as direction_accuracy_pct,
  round(avg(confidence_score), 1)                              as avg_confidence_score
from predictions
where agent is not null
group by agent
order by direction_accuracy_pct desc nulls last;

-- ============================================================
-- VIEW: confidence_score_calibration
-- Validates whether high-confidence calls outperform low ones.
-- Used in monthly review (Section 5.3).
-- ============================================================
create or replace view confidence_score_calibration as
select
  case
    when confidence_score >= 80 then '80–100 (high)'
    when confidence_score >= 65 then '65–79 (medium-high)'
    when confidence_score >= 50 then '50–64 (medium)'
    else '0–49 (low)'
  end                                                           as confidence_band,
  count(*) filter (where resolved = true)                       as resolved_count,
  round(
    100.0 * count(*) filter (where direction_correct = true)
    / nullif(count(*) filter (where resolved = true), 0), 1
  )                                                             as direction_accuracy_pct,
  round(avg(actual_move_pct) filter (where resolved = true), 2) as avg_actual_move_pct
from predictions
where score_passed = true
group by confidence_band
order by confidence_band desc;

-- ============================================================
-- FUNCTION: wash_sale_check
-- Called by universe_check.py to determine if repurchasing
-- this ticker would trigger an IRS wash sale disallowance.
-- Returns the most recent loss-sale date within 30 days, or null.
-- ============================================================
create or replace function wash_sale_check(p_ticker text)
returns table(last_loss_sale_date date, is_wash_sale_risk boolean) as $$
begin
  return query
  select
    max(exit_date)::date                                        as last_loss_sale_date,
    (max(exit_date) is not null)                               as is_wash_sale_risk
  from predictions
  where
    ticker = upper(p_ticker)
    and resolved = true
    and exit_date >= current_date - interval '30 days'
    and (
      (predicted_direction = 'up'   and actual_move_pct < 0) or
      (predicted_direction = 'down' and actual_move_pct > 0)
    );
end;
$$ language plpgsql;

-- ============================================================
-- RLS (Row Level Security)
-- Enable RLS and restrict to authenticated users only.
-- Use your service role key in the Python client (server-side).
-- ============================================================
alter table scans enable row level security;
alter table predictions enable row level security;

-- Allow all operations for authenticated service role (used by Python scripts)
create policy "service_role_all" on scans for all using (true);
create policy "service_role_all" on predictions for all using (true);
