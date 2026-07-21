-- Migration 015: wash_sale_check must only consider real executed trades (GAP-85)
--
-- Discovered 2026-07-21: the 2026-07-20 midday scan blocked 19 of 26 watchlist
-- tickers with "Sold at loss within 30 days (2026-07-20) — wash sale rule
-- applies." Root cause: GAP-75 (2026-07-20) widened resolve.py's counterfactual
-- pass so unexecuted predictions (never real trades, no shares ever bought or
-- sold) get resolved against real price data to build calibration signal. That
-- was the right fix for learning — but wash_sale_check's query never filtered
-- on executed = true, only resolved = true, so a counterfactual prediction
-- that resolved wrong-direction now reads exactly like a real IRS-relevant
-- loss sale. The wash sale rule is a real tax concept that only applies to
-- actual sales of actual shares — it has no meaning for a trade that was
-- never placed. This bug is a direct, previously-unforeseen side effect of
-- yesterday's own fix, not a pre-existing issue.

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
    and executed = true
    and resolved = true
    and exit_date >= current_date - interval '30 days'
    and (
      (predicted_direction = 'up'   and actual_move_pct < 0) or
      (predicted_direction = 'down' and actual_move_pct > 0)
    );
end;
$$ language plpgsql;
