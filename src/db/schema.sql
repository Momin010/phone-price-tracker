-- Run this ONCE in the Supabase dashboard -> SQL Editor -> New query -> Run.
-- Creates the prices table the scraper writes to and the API reads from.

create table if not exists public.prices (
  id          bigint generated always as identity primary key,
  site_id     text        not null,
  type        text        not null,
  sku         text        not null,
  label       text,
  price       numeric,
  currency    text,
  country     text,
  raw_price   text,
  url         text,
  ok          boolean     not null default true,
  error       text,
  scraped_at  timestamptz not null default now()
);

create index if not exists idx_prices_lookup
  on public.prices (site_id, sku, scraped_at desc);

-- We talk to the table only with the service (secret) key, which bypasses RLS.
-- Enable RLS with no public policies so the anon/publishable key can't read/write
-- directly (the Vercel API is the only public door, and it checks x-api-key).
alter table public.prices enable row level security;
