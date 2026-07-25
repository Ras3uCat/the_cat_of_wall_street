-- Migration 016: resolution fidelity columns + timeframe_accuracy view
-- (planning/features/02_backlog/06_resolution_fidelity_upgrades.md)
--
-- resolve.py has only ever scored direction-at-expiry against a close price.
-- That overstates accuracy for any prediction that would have hit a stop
-- loss before the eventual correct move, and understates it for one that
-- hit target before reversing. It also can't separate real signal edge from
-- riding a broad market move. These columns let resolve.py record that
-- richer picture without changing the existing actual_move_pct/
-- direction_correct fields anything already reads.

alter table predictions
  add column if not exists max_favorable_pct  numeric,  -- best move in predicted direction, 0..N (%), from OHLC path entry->exit
  add column if not exists max_adverse_pct     numeric,  -- worst move against predicted direction, 0..N (%), from OHLC path entry->exit
  add column if not exists would_have_stopped  boolean,  -- true if max_adverse_pct >= assumed stop-loss pct at any point before exit
  add column if not exists spy_move_pct        numeric,  -- SPY's % move over the same entry->exit window
  add column if not exists excess_move_pct     numeric;  -- actual_move_pct - spy_move_pct (alpha vs. beta)

comment on column predictions.max_favorable_pct is 'Best intraday-bar move in the predicted direction between entry and exit, magnitude only.';
comment on column predictions.max_adverse_pct is 'Worst intraday-bar move against the predicted direction between entry and exit, magnitude only. Computed from daily high/low, not true intraday sequencing.';
comment on column predictions.would_have_stopped is 'Whether max_adverse_pct would have breached DEFAULT_STOP_LOSS_PCT before resolution. Does not know if this happened before or after the favorable excursion — a same-bar ambiguity inherent to daily OHLC.';
comment on column predictions.spy_move_pct is 'SPY % move over the same entry_date -> exit_date window as this prediction.';
comment on column predictions.excess_move_pct is 'actual_move_pct minus spy_move_pct — per-prediction alpha vs. beta.';

-- ============================================================
-- VIEW: timeframe_accuracy
-- Buckets resolved predictions by predicted_timeframe_days per the
-- Section 3 signal-timeframe guide, so the weekly/monthly review can see
-- which holding-period band is actually accurate rather than only the
-- system-wide average.
-- ============================================================
create or replace view timeframe_accuracy as
select
  case
    when predicted_timeframe_days <= 3  then '0-3d (intraday/flow)'
    when predicted_timeframe_days <= 10 then '4-10d (news cycle)'
    when predicted_timeframe_days <= 30 then '11-30d (insider/informed)'
    else                                      '31d+ (structural/multi-signal)'
  end                                                            as timeframe_bucket,
  count(*)                                                       as total_predictions,
  count(*) filter (where resolved = true)                        as resolved_count,
  round(
    100.0 * count(*) filter (where direction_correct = true)
    / nullif(count(*) filter (where resolved = true), 0), 1
  )                                                              as direction_accuracy_pct,
  round(avg(actual_move_pct) filter (where resolved = true), 2)  as avg_actual_move_pct,
  round(avg(excess_move_pct) filter (where resolved = true), 2)  as avg_excess_move_pct,
  round(
    100.0 * count(*) filter (where would_have_stopped = true)
    / nullif(count(*) filter (where resolved = true), 0), 1
  )                                                              as would_have_stopped_pct,
  case
    when count(*) filter (where resolved = true) < 10 then true
    else false
  end                                                            as insufficient_data
from predictions
where predicted_timeframe_days is not null
group by 1
order by direction_accuracy_pct desc nulls last;
