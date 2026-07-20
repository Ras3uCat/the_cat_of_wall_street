-- Migration 013: weekly_reviews table (GAP-81)
-- Section 7's self-improvement protocol had no durable output — it was meant
-- to run every Monday but had no automated trigger at all (confirmed via
-- systemctl/journalctl: zero timers reference signal_accuracy or any Section 7
-- query). This table gives the new catws-weekly-review.timer somewhere to
-- write its findings, so the review survives past the push notification that
-- announces it.

create table if not exists weekly_reviews (
  id           bigint generated always as identity primary key,
  week_of      date not null,       -- the Monday this review covers
  summary      text not null,       -- findings + draft recommendations, per Section 7 — recommendations only, never auto-applied
  created_at   timestamptz default now()
);

create index if not exists weekly_reviews_week_of_idx on weekly_reviews(week_of desc);

alter table weekly_reviews enable row level security;
create policy "service_role_all" on weekly_reviews for all using (true);
