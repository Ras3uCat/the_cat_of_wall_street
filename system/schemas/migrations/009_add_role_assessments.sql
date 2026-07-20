-- Migration 009: debate_role_assessments table (GAP-76)
-- agent_accuracy groups by `predictions.agent`, which is hardcoded to
-- 'trader_synthesizer' on every row (there's exactly one final decision-maker
-- per prediction) — that view is structurally correct but can never show more
-- than one line, so there's no way to tell whether the Fundamental Analyst's
-- "High evidence quality" calls, the Sentiment Analyst's read, or the
-- Technical Analyst's entry-timing read are actually adding predictive value
-- independent of the final score. This adds a child table so each of the
-- three analyst roles' qualitative output is captured per-prediction instead
-- of being locked inside the freeform debate_narrative text.
--
-- Scoped to the three assessor roles (Fundamental/Sentiment/Technical), not
-- the Bull/Bear debaters — those are advocates by construction (Bull always
-- argues up, long-only v1 scope), so their "accuracy" trivially mirrors the
-- overall direction_correct rate and adds no independent signal.

create table if not exists debate_role_assessments (
  id             bigint generated always as identity primary key,
  prediction_id  text not null references predictions(id),
  role           text not null check (role in (
                    'fundamental_analyst',
                    'sentiment_analyst',
                    'technical_analyst'
                  )),
  stance         text not null,  -- fundamental/sentiment: 'bullish'|'bearish'|'neutral'; technical: 'good'|'neutral'|'poor' (entry timing)
  quality        text,           -- fundamental_analyst only: 'high'|'medium'|'low' evidence quality; null for other roles
  created_at     timestamptz default now()
);

create index if not exists debate_role_assessments_prediction_idx on debate_role_assessments(prediction_id);
create index if not exists debate_role_assessments_role_stance_idx on debate_role_assessments(role, stance);

alter table debate_role_assessments enable row level security;
create policy "service_role_all" on debate_role_assessments for all using (true);

-- ============================================================
-- VIEW: role_accuracy
-- Per role+stance (+quality where set): does this role's read actually
-- correlate with the trade working out? Same insufficient_data convention
-- as signal_accuracy.
-- ============================================================
create or replace view role_accuracy as
select
  a.role,
  a.stance,
  a.quality,
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
from debate_role_assessments a
join predictions p on p.id = a.prediction_id
group by a.role, a.stance, a.quality
order by a.role, a.stance;
