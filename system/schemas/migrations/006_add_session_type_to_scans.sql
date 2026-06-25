-- Migration 006: session_type + outcome_summary on scans
-- Allows multiple scans per day (pre_market / midday / pm_window).
-- Scan IDs now use format: scan_2026-06-25_pre_market
-- Existing rows get session_type = 'pre_market' by default.

alter table scans
  add column if not exists session_type text default 'pre_market'
    check (session_type in ('pre_market', 'midday', 'pm_window')),
  add column if not exists outcome_summary text;

create index if not exists scans_session_type_idx on scans(session_type);
