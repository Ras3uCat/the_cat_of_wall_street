-- Migration 005: short_interest_history, options_flow_history, macro_history
-- These tables accumulate daily snapshots for the weekly/monthly review
-- and as Supabase-backed fallbacks when live APIs are unavailable.

-- ============================================================
-- TABLE: short_interest_history
-- Written by fetch_market_data.py after every successful yfinance fetch.
-- FINRA data is bi-weekly so many rows will repeat the same values.
-- ============================================================
create table if not exists short_interest_history (
  ticker                      text    not null,
  date                        date    not null,
  short_interest_pct_float    numeric,
  shares_short                bigint,
  shares_short_prior_month    bigint,
  short_interest_change_pct   numeric,
  short_ratio_days_to_cover   numeric,
  short_signal                text,
  primary key (ticker, date)
);

create index if not exists si_history_ticker_date_idx on short_interest_history(ticker, date desc);

alter table short_interest_history enable row level security;
create policy "service_role_all" on short_interest_history for all using (true);

-- ============================================================
-- TABLE: options_flow_history
-- Written by fetch_options.py after every successful fetch.
-- Stores daily aggregates (not individual contracts) for correlation
-- analysis in the weekly self-improvement loop.
-- ============================================================
create table if not exists options_flow_history (
  ticker                  text    not null,
  date                    date    not null,
  put_call_ratio          numeric,
  total_call_volume       integer,
  total_put_volume        integer,
  unusual_call_count      integer,
  unusual_put_count       integer,
  options_signal_strength text,
  primary key (ticker, date)
);

create index if not exists options_flow_ticker_date_idx on options_flow_history(ticker, date desc);

alter table options_flow_history enable row level security;
create policy "service_role_all" on options_flow_history for all using (true);

-- ============================================================
-- TABLE: macro_history
-- Written by fetch_macro.py after every successful fetch.
-- One row per trading day. Used by the monthly review to correlate
-- VIX regime and calendar proximity with prediction outcomes.
-- ============================================================
create table if not exists macro_history (
  date              date    primary key,
  vix               numeric,
  vix_regime        text,
  macro_go          boolean,
  fed_days_out      integer,
  cpi_days_out      integer,
  nfp_days_out      integer,
  fed_next_meeting  date,
  cpi_next_release  date,
  nfp_next_release  date
);

alter table macro_history enable row level security;
create policy "service_role_all" on macro_history for all using (true);
