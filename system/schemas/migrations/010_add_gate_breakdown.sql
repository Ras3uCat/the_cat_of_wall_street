-- Migration 010: structured Gate A-E breakdown (GAP-77)
-- Component 2 (Debate Outcome Quality) is five binary gates per Role 7:
--   A - near-term catalyst cited        (+8/+0)
--   B - unanswered material bear risk   (-8/+0)
--   C - TA timing AND FA evidence good  (+7/+0)
--   D - timeframe matches signal guide  (+5/+0)
--   E - "why now" answered              (+5/+0)
-- Only the summed total (confidence_component_debate) was ever stored, so
-- there's no way to tell which individual gates actually predict outcomes —
-- e.g. does Gate A (catalyst cited) matter more than Gate D (timeframe
-- match)? One row per prediction, so plain columns rather than a child table.

alter table predictions
  add column if not exists gate_a_catalyst_cited     boolean,
  add column if not exists gate_b_unanswered_bear_risk boolean,
  add column if not exists gate_c_ta_fa_good          boolean,
  add column if not exists gate_d_timeframe_matches   boolean,
  add column if not exists gate_e_why_now_answered    boolean;

comment on column predictions.gate_a_catalyst_cited is 'Role 7 Gate A: near-term catalyst cited (specific event/date <= 5 days)';
comment on column predictions.gate_b_unanswered_bear_risk is 'Role 7 Gate B: TRUE means Bearish raised a material risk Bull never answered (penalty gate — TRUE is bad)';
comment on column predictions.gate_c_ta_fa_good is 'Role 7 Gate C: TA timing AND FA evidence both Good/High';
comment on column predictions.gate_d_timeframe_matches is 'Role 7 Gate D: timeframe matches the Section 3 signal-guide table';
comment on column predictions.gate_e_why_now_answered is 'Role 7 Gate E: "why now" answered with a real catalyst, not "valuation only"';

-- ============================================================
-- VIEW: gate_accuracy
-- Per gate, per value (true/false): does this gate actually correlate with
-- the trade working out? Unpivoted via UNION ALL since the gates are columns,
-- not rows, on predictions.
-- ============================================================
create or replace view gate_accuracy as
select 'gate_a_catalyst_cited' as gate, gate_a_catalyst_cited as value,
  count(*) as total, count(*) filter (where resolved = true) as resolved_count,
  round(100.0 * count(*) filter (where direction_correct = true) / nullif(count(*) filter (where resolved = true), 0), 1) as direction_accuracy_pct
from predictions where gate_a_catalyst_cited is not null group by gate_a_catalyst_cited
union all
select 'gate_b_unanswered_bear_risk', gate_b_unanswered_bear_risk,
  count(*), count(*) filter (where resolved = true),
  round(100.0 * count(*) filter (where direction_correct = true) / nullif(count(*) filter (where resolved = true), 0), 1)
from predictions where gate_b_unanswered_bear_risk is not null group by gate_b_unanswered_bear_risk
union all
select 'gate_c_ta_fa_good', gate_c_ta_fa_good,
  count(*), count(*) filter (where resolved = true),
  round(100.0 * count(*) filter (where direction_correct = true) / nullif(count(*) filter (where resolved = true), 0), 1)
from predictions where gate_c_ta_fa_good is not null group by gate_c_ta_fa_good
union all
select 'gate_d_timeframe_matches', gate_d_timeframe_matches,
  count(*), count(*) filter (where resolved = true),
  round(100.0 * count(*) filter (where direction_correct = true) / nullif(count(*) filter (where resolved = true), 0), 1)
from predictions where gate_d_timeframe_matches is not null group by gate_d_timeframe_matches
union all
select 'gate_e_why_now_answered', gate_e_why_now_answered,
  count(*), count(*) filter (where resolved = true),
  round(100.0 * count(*) filter (where direction_correct = true) / nullif(count(*) filter (where resolved = true), 0), 1)
from predictions where gate_e_why_now_answered is not null group by gate_e_why_now_answered
order by gate, value;
