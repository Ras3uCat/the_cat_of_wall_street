-- Migration 011: per-prediction sector status (GAP-78)
-- sector_rotation (in_favor/out_of_favor) only lives on the `scans` table
-- (one snapshot per scan, all 11 GICS sectors), never persisted onto the
-- individual prediction row for the ticker being debated — despite Component
-- 3 (Market Regime Alignment) partly scoring on it, and the Sentiment
-- Analyst (Role 2) stating it in every debate output. Same underlying issue
-- as the "Sector Rotation Field Gotcha" memory note (per-ticker
-- sector_rotation_status reads 'unknown' at the scan-packet layer even when
-- the scan-level record has real data) — without a persisted per-prediction
-- value, there's no way to ever check "do predictions entered when the
-- sector was in_favor actually outperform out_of_favor/mixed ones."

alter table predictions
  add column if not exists sector_status text check (sector_status in ('in_favor', 'mixed', 'out_of_favor', 'unknown'));

comment on column predictions.sector_status is
  'Ticker''s sector rotation status at debate time (Role 2 Sentiment Analyst output), cross-checked against the scan-level sector_rotation record — see memory note on the per-ticker field defaulting to unknown.';

-- ============================================================
-- VIEW: sector_status_accuracy
-- ============================================================
create or replace view sector_status_accuracy as
select
  sector_status,
  count(*)                                                                as total,
  count(*) filter (where resolved = true)                                 as resolved_count,
  round(
    100.0 * count(*) filter (where direction_correct = true)
    / nullif(count(*) filter (where resolved = true), 0), 1
  )                                                                       as direction_accuracy_pct,
  case
    when count(*) filter (where resolved = true) < 10 then true
    else false
  end                                                                     as insufficient_data
from predictions
where sector_status is not null
group by sector_status
order by sector_status;
