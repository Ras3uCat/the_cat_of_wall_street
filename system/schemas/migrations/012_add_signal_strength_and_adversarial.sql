-- Migration 012: per-signal strength + Adversarial Reviewer tracking (GAP-79)
--
-- Part A — signal_strengths (1:many, mirrors debate_role_assessments):
-- Component 1 (Signal Convergence) rates each fired signal Strong/Moderate/
-- Weak individually, but only the summed points land in
-- confidence_component_convergence. Can't tell whether e.g. a "Strong"
-- gov_contracts signal actually predicts better than a "Moderate" one.
create table if not exists signal_strengths (
  id             bigint generated always as identity primary key,
  prediction_id  text not null references predictions(id),
  signal_name    text not null,  -- one of SIGNAL_CATEGORY_NAMES (config.py)
  strength       text not null check (strength in ('strong', 'moderate', 'weak')),
  created_at     timestamptz default now()
);

create index if not exists signal_strengths_prediction_idx on signal_strengths(prediction_id);
create index if not exists signal_strengths_name_strength_idx on signal_strengths(signal_name, strength);

alter table signal_strengths enable row level security;
create policy "service_role_all" on signal_strengths for all using (true);

create or replace view signal_strength_accuracy as
select
  s.signal_name,
  s.strength,
  count(*)                                                                as total,
  count(*) filter (where p.resolved = true)                               as resolved_count,
  round(
    100.0 * count(*) filter (where p.direction_correct = true)
    / nullif(count(*) filter (where p.resolved = true), 0), 1
  )                                                                       as direction_accuracy_pct,
  case
    when count(*) filter (where p.resolved = true) < 10 then true
    else false
  end                                                                     as insufficient_data
from signal_strengths s
join predictions p on p.id = s.prediction_id
group by s.signal_name, s.strength
order by s.signal_name, s.strength;

-- Part B — Adversarial Reviewer verdict (1:1, ENTER proposals only):
alter table predictions
  add column if not exists adversarial_status text check (adversarial_status in ('cleared', 'challenge'));

comment on column predictions.adversarial_status is
  'Adversarial Reviewer verdict (Role 7 Step 4) — only set for ENTER proposals that reached that step. CHALLENGE means Component 2 was reduced 8pts before the final threshold check.';

create or replace view adversarial_reviewer_accuracy as
select
  adversarial_status,
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
where adversarial_status is not null
group by adversarial_status
order by adversarial_status;
