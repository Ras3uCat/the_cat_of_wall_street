-- Migration 004: price_history table
-- Stores daily OHLCV + market cap per ticker, written by fetch_market_data.py
-- after every successful yfinance fetch. Used as a Supabase-backed fallback
-- when yfinance is rate-limited or unavailable.

create table if not exists price_history (
  ticker      text    not null,
  date        date    not null,
  open        numeric,
  high        numeric,
  low         numeric,
  close       numeric,
  volume      bigint,
  market_cap  bigint,
  source      text    default 'yfinance',
  primary key (ticker, date)
);

create index if not exists price_history_ticker_date_idx on price_history(ticker, date desc);

alter table price_history enable row level security;
create policy "service_role_all" on price_history for all using (true);
