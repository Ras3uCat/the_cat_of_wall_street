-- Migration 001: add per-prediction signal breakdown columns
-- Run in Supabase SQL editor.
-- These columns capture whether the convergence that drove a debate
-- was fundamental-signal-led vs. technical-only, enabling calibration
-- of the "technicals add +1 only with ≥1 fundamental" rule.

alter table predictions
  add column if not exists fundamental_signals_fired integer,
  add column if not exists technical_signal_fired    boolean;

comment on column predictions.fundamental_signals_fired is
  'Count of non-technical signals that fired (insider open-market buys, contracts, options, material 8-Ks)';

comment on column predictions.technical_signal_fired is
  'True if RSI/trend/volume-clustering fired at debate time — only adds to convergence when fundamental_signals_fired >= 1';
