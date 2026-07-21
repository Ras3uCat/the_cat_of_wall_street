-- Migration 014: ticker_accuracy + regime_accuracy views (GAP-62, GAP-84)
-- Both group on columns that already exist on `predictions` (ticker,
-- market_regime) — pure additive views, no new table/column needed.
--
-- GAP-62 (already scoped, previously blocked on volume): "no watchlist
-- removal mechanism... no per-ticker accuracy rollup anywhere." Fix option 1
-- from that gap's writeup: "Add a per-ticker rollup to Section 8... flag
-- tickers below a resolved-count or accuracy floor as removal candidates."
-- Today's GAP-75 resolution surge (148 resolved) makes this meaningful now —
-- several tickers already clear the 10-observation floor (PANW 24, BAH 16,
-- AMD 12, LMT 11, SAIC 11) with real spread: BAH 88%, SAIC 91% vs LMT 9%,
-- LHX 0%. Ryan still approves any actual removal manually — this view only
-- surfaces candidates, same as every other accuracy view in this schema.
--
-- GAP-84: market_regime (VIX regime at prediction time) has been a column
-- since the original schema, but nothing ever grouped on it — no way to
-- check "does this system actually perform differently by VIX regime,"
-- despite Section 8's monthly report template having a REGIME ANALYSIS
-- section with no query behind it.

create or replace view ticker_accuracy as
select
  ticker,
  count(*)                                                      as total_predictions,
  count(*) filter (where resolved = true)                       as resolved_count,
  round(
    100.0 * count(*) filter (where direction_correct = true)
    / nullif(count(*) filter (where resolved = true), 0), 1
  )                                                             as direction_accuracy_pct,
  round(avg(actual_move_pct) filter (where resolved = true and direction_correct = true), 2) as avg_win_pct,
  round(avg(actual_move_pct) filter (where resolved = true and direction_correct = false), 2) as avg_loss_pct,
  count(*) filter (where score_passed = true)                   as score_passed_count,
  case
    when count(*) filter (where resolved = true) < 10 then true
    else false
  end                                                           as insufficient_data,
  min(scan_date)                                                as earliest_prediction,
  max(scan_date)                                                as latest_prediction
from predictions
group by ticker
order by direction_accuracy_pct asc nulls last;

create or replace view regime_accuracy as
select
  market_regime,
  count(*)                                                      as total_predictions,
  count(*) filter (where resolved = true)                       as resolved_count,
  round(
    100.0 * count(*) filter (where direction_correct = true)
    / nullif(count(*) filter (where resolved = true), 0), 1
  )                                                             as direction_accuracy_pct,
  round(avg(vix_at_prediction) filter (where resolved = true), 1) as avg_vix,
  case
    when count(*) filter (where resolved = true) < 10 then true
    else false
  end                                                           as insufficient_data
from predictions
where market_regime is not null
group by market_regime
order by direction_accuracy_pct desc nulls last;
