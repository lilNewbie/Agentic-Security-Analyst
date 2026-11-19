create table if not exists node_state (
  company_id            uuid not null references companies(company_id),
  rubric_id              text not null,
  state                  text not null check (state in (
                           'unknown', 'not_applicable', 'pending_gate', 'vague',
                           'conflicted', 'verified', 'user_confirmed', 'attempted_unknown'
                         )),
  filled_slots           text[] not null default '{}',
  empty_required_slots   text[] not null default '{}',
  confidence             numeric(4,3) not null default 0,
  provenance_count       integer not null default 0,
  last_touched           timestamptz,
  attempted_and_unknown  boolean not null default false,

  primary key (company_id, rubric_id)
);

-- conflicts get their own table rather than a jsonb array on node_state,
-- since you'll query/filter/resolve them independently (§3.4)
create table if not exists conflicts (
  conflict_id          uuid primary key default gen_random_uuid(),
  company_id           uuid not null references companies(company_id),
  rubric_id            text not null,
  slot                 text not null,
  kind                 text not null check (kind in (
                          'policy_vs_practice', 'stale_vs_current',
                          'source_disagreement', 'user_vs_document', 'scope_ambiguity'
                        )),
  entry_a              uuid not null references entries(entry_id),
  entry_b              uuid not null references entries(entry_id),
  summary              text not null,
  resolution_question  text not null,
  status               text not null default 'open' check (status in ('open', 'resolved', 'dismissed')),
  resolved_by_entry    uuid references entries(entry_id),
  created_at           timestamptz not null default now(),

  foreign key (company_id, rubric_id) references node_state(company_id, rubric_id)
);

create index on node_state (company_id, state);
create index on conflicts (company_id, status);