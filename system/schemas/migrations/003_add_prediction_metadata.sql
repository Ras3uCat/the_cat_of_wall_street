-- Migration 003: add post-debate metadata columns to predictions table
-- These are written via update_prediction() after the 7-agent debate completes,
-- NOT in the initial insert_prediction() call. Applying this migration allows
-- db.update_prediction() calls for these fields to succeed.
-- Run in Supabase SQL editor.

alter table predictions
  add column if not exists approval_status  text,
  add column if not exists equity_at_entry  numeric,
  add column if not exists debate_narrative text;

comment on column predictions.approval_status is
  'approved | skipped | vetoed — set by Trader agent after debate, not at scan time';

comment on column predictions.equity_at_entry is
  'Account equity (USD) at the moment the trade was entered — for P&L sizing accuracy';

comment on column predictions.debate_narrative is
  'Full 7-agent debate transcript — stored after debate completes via update_prediction()';
