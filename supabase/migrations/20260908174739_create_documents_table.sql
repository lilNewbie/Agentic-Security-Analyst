create table if not exists public.documents (
    id              uuid primary key default gen_random_uuid(),
    company_id      uuid not null references public.companies(company_id) on delete cascade,
    filename        text not null,
    source_type     text not null,
    doc_class       text not null,
    authored_at     text,
    uploaded_at     timestamptz not null default now(),
    page_count      integer not null default 0,
    raw_path        text
);

create index on public.documents (company_id);

alter table public.documents enable row level security;

create table if not exists public.chunks (
    id              uuid primary key default gen_random_uuid(),
    doc_id          uuid not null references public.documents(id) on delete cascade,
    chunk_id        text not null unique,
    source_type     text not null,
    doc_title       text,
    authored_at     text,
    page            integer,
    char_start      integer,
    char_end        integer,
    created_at      timestamptz not null default now()
);

create index on public.chunks (doc_id);

alter table public.chunks enable row level security;
