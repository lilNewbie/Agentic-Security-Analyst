create table if not exists entries (
    entry_id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(company_id) on delete cascade,
    rubric_id text not null,
    slot text not null,
    value jsonb not null,
    confidence numeric(4,3) not null,

    source_kind text not null check (source_kind in ('document', 'user', 'inference_gate')),
    source_id text,
    source_type text check (source_type in ('policy','assessment','contract','infra','user','message')),
    source_span text,
    source_locator jsonb,
    source_authored_at timestamptz,
    source_speaker text,

    created_at timestamptz not null default now(),
    superseded_by uuid references entries(entry_id),
    supersede_reason text check (supersede_reason in ('user_correction','newer_evidence','conflict_resolution'))
);

create index on entries (company_id, rubric_id, slot);
create index on entries (superseded_by);

create or replace function reject_entries_mutation()
returns trigger as $$
begin
    raise exception 'entries table is append-only; % not allowed', TG_OP;
end;
$$ language plpgsql;

create trigger entries_no_delete
    before delete on entries
    for each row execute function reject_entries_mutation();

create trigger entries_no_update
    before update on entries
    for each row execute function reject_entries_mutation();