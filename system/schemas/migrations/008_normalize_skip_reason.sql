-- Migration 008: normalize skip_reason vocabulary + enforce as a real enum (GAP-75)
-- Mirrors GAP-58's fix for signals_fired: skip_reason was documented only in a
-- schema comment, never enforced, and drifted into duplicate spellings for the
-- same underlying reason:
--   'score_below_threshold' / 'score below threshold' / 'confidence_below_threshold'
-- (all from debate.py's inconsistent fallback string), plus one class of row
-- that concatenated event-specific detail directly into the field instead of
-- leaving it in debate_narrative:
--   'risk_management_rule: NFP release day-before (Section 6 binary macro event hard stop)'
-- This silently fragmented any query grouping by skip_reason — including the
-- GAP-75 threshold-resolution fix, which depends on being able to reliably
-- select "everything that was a near-miss/vetoed skip with a real thesis."
-- Run in Supabase SQL editor (or via db.run_migration if SUPABASE_ACCESS_TOKEN set).

-- One-time backfill: normalize existing rows to canonical values.
update predictions set skip_reason = 'score_below_threshold'
  where skip_reason in ('score below threshold', 'confidence_below_threshold');

update predictions set skip_reason = 'risk_management_rule'
  where skip_reason like 'risk_management_rule:%';

-- Enforce going forward — same pattern as exit_reason's existing check constraint.
alter table predictions
  add constraint predictions_skip_reason_check check (skip_reason is null or skip_reason in (
    'learning_period',
    'score_below_threshold',
    'risk_manager_veto',
    'risk_management_rule',
    'technical_hard_stop',
    'adversarial_review_downgrade',
    'macro_filter',
    'universe_filter',
    'manual_skip'
  ));

comment on column predictions.skip_reason is
  'Canonical reason enum — see SKIP_REASON_VALUES in config.py. Never concatenate event-specific detail into this field; it belongs in debate_narrative.';

-- ============================================================
-- Fix confidence_score_calibration: the `where score_passed = true` filter
-- meant the '50-64' and '0-49' bands could never be populated (nothing with
-- score < ~65 ever has score_passed=true), making half the view permanently
-- dead and making it structurally impossible to check whether the confidence
-- threshold itself is in the right place. GAP-75's widened resolve.py pass
-- now resolves below-threshold predictions too, so this view needs to
-- actually include them.
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
group by confidence_band
order by confidence_band desc;
