create table if not exists companies (
  company_id          uuid primary key default gen_random_uuid(),
  name        text not null,
  metadata    jsonb default '{}'::jsonb,
  created_at  timestamptz not null default now()
);