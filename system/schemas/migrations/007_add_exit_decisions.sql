-- Migration 007: exit_decisions table
-- GAP-74: predictions/signal_accuracy/agent_accuracy/confidence_score_calibration
-- only ever scored entry theses (direction/magnitude vs. signals fired). Every
-- actual sell judgment call in trading_system.md Section 12 — Trigger B (target
-- hit: exit vs. hold & trail), Trigger D (timeframe expiry: exit vs. extend),
-- Triggers E/F/G (thesis/earnings/tax review) — was human-in-the-loop with no
-- record of which choice was made or how it turned out. Unlike prediction
-- accuracy, this can't be reconstructed after the fact once live trading starts
-- 2026-08-21 — the decision has to be captured at the moment it's made.
-- Run in Supabase SQL editor (or via db.run_migration if SUPABASE_ACCESS_TOKEN set).

create table if not exists exit_decisions (
  id                        bigint generated always as identity primary key,
  prediction_id             text not null references predictions(id),
  ticker                    text not null,
  trigger                   text not null check (trigger in (
                               'trigger_b_target_hit',
                               'trigger_d_timeframe_expiry',
                               'trigger_e_thesis_invalidation',
                               'trigger_f_earnings_proximity',
                               'trigger_g_tax_timing'
                             )),
  choice                    text not null,   -- vocabulary varies by trigger — see trading_system.md Section 12 (e.g. 'exit_now' | 'hold_and_trail' | 'extend' | 'held' | 'no_action')
  rationale                 text,
  price_at_decision         numeric not null,
  decided_at                timestamptz not null default now(),

  -- Trigger D only
  original_timeframe_days   integer,
  extended_to_days          integer,

  -- Filled in later by resolve_exit_decisions.py once EXIT_DECISION_EVAL_DAYS
  -- have passed — the ticker's actual price move after the decision, independent
  -- of which path was taken (same counterfactual trick resolve.py already uses
  -- for unexecuted learning-period predictions).
  counterfactual_price      numeric,
  counterfactual_date       date,
  counterfactual_move_pct   numeric,
  counterfactual_resolved   boolean not null default false,

  created_at                timestamptz default now()
);

create index if not exists exit_decisions_prediction_idx on exit_decisions(prediction_id);
create index if not exists exit_decisions_trigger_idx on exit_decisions(trigger);
create index if not exists exit_decisions_unresolved_idx on exit_decisions(counterfactual_resolved) where counterfactual_resolved = false;

alter table exit_decisions enable row level security;
create policy "service_role_all" on exit_decisions for all using (true);

-- ============================================================
-- VIEW: exit_decision_accuracy
-- Per trigger+choice: does the market keep moving in a direction that
-- validates or invalidates the judgment call made? Same insufficient_data
-- convention as signal_accuracy (< 10 resolved observations).
-- ============================================================
create or replace view exit_decision_accuracy as
select
  trigger,
  choice,
  count(*)                                                                  as total_decisions,
  count(*) filter (where counterfactual_resolved = true)                    as resolved_count,
  round(avg(counterfactual_move_pct)
        filter (where counterfactual_resolved = true), 2)                  as avg_move_after_decision_pct,
  case
    when count(*) filter (where counterfactual_resolved = true) < 10 then true
    else false
  end                                                                       as insufficient_data
from exit_decisions
group by trigger, choice
order by trigger, choice;
