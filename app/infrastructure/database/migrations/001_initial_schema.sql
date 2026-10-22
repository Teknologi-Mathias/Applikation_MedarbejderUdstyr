-- IN-BASE: første relationelle datamodel (Supabase / PostgreSQL 15+)
--
-- Principper:
-- * Alle tabeller har UUID-primærnøgler. Lønnr. er en attribut på
--   ansættelsesforholdet – aldrig en identitet (kandidater har intet lønnr.).
-- * people (identitet) er adskilt fra employment_records (ansættelse) og
--   lifecycle_cases (onboarding-/offboardingsag), så stillingsskift og
--   genansættelser ikke giver dublerede personer.
-- * Statusser er kontrollerede værdier (CHECK), ikke fri tekst.
-- * lifecycle_cases.version bruges til optimistisk låsning: klienten
--   opdaterer med "WHERE id = $1 AND version = $2"; triggeren tæller op.
-- * audit_events er insert-only (se 002_rls_policies.sql).
--
-- Kør ikke mod produktion før migreringen af JSON-data er valideret
-- (app/infrastructure/database/migrering.py).

create extension if not exists "pgcrypto";

-- ---------- Organisation -------------------------------------------------

create table areas (
    id          uuid primary key default gen_random_uuid(),
    name        text not null unique,
    active      boolean not null default true,
    created_at  timestamptz not null default now()
);

create table positions (
    id    uuid primary key default gen_random_uuid(),
    code  text not null unique check (code in ('Ad Hoc', 'FM', 'DM', 'Afløser')),
    name  text not null
);

-- ---------- Brugere (knyttet til Supabase Auth) --------------------------

create table user_profiles (
    id                     uuid primary key references auth.users (id) on delete cascade,
    username               text not null unique,
    display_name           text not null default '',
    role                   text not null default 'Bruger'
                           check (role in ('Administrator', 'Bruger')),
    theme                  text not null default 'lilla' check (theme in ('lilla', 'lys')),
    windows_notifications  boolean not null default true,
    created_at             timestamptz not null default now()
);

-- ---------- Personer og ansættelser --------------------------------------

create table people (
    id          uuid primary key default gen_random_uuid(),
    full_name   text not null check (length(trim(full_name)) > 0),
    email       text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create table employment_records (
    id                uuid primary key default gen_random_uuid(),
    person_id         uuid not null references people (id) on delete cascade,
    payroll_number    text,                       -- lønnr. (kan mangle for kandidater)
    position_id       uuid references positions (id),
    area_id           uuid references areas (id),
    employment_date   date,
    first_work_day    date,
    termination_date  date,                       -- sidste arbejdsdag (offboarding)
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);
create unique index employment_records_payroll_number_uq
    on employment_records (payroll_number) where payroll_number is not null;

-- ---------- Skabeloner -----------------------------------------------------

create table workflow_templates (
    id            uuid primary key default gen_random_uuid(),
    legacy_id     text unique,                    -- id fra skabeloner.json
    process       text not null check (process in ('onboarding', 'offboarding')),
    name          text not null,
    description   text not null default '',
    positions     text[] not null default '{}',  -- tom = alle stillinger
    active        boolean not null default true,
    version       integer not null default 1,
    updated_at    timestamptz not null default now(),
    updated_by    text
);

-- Tidligere versioner (igangværende sager påvirkes ikke af nye versioner).
create table workflow_template_versions (
    template_id  uuid not null references workflow_templates (id) on delete cascade,
    version      integer not null,
    snapshot     jsonb not null,
    created_at   timestamptz not null default now(),
    primary key (template_id, version)
);

create table workflow_template_tasks (
    id               uuid primary key default gen_random_uuid(),
    template_id      uuid not null references workflow_templates (id) on delete cascade,
    sort_order       integer not null,
    name             text not null,
    description      text not null default '',
    responsible      text not null default '',   -- rolle eller bruger
    equipment        text not null default '',   -- offboarding: udstyr der skal returneres
    milestone        text not null default ''
                     check (milestone in ('', 'kandidat', 'kontrakt', 'oplaering', 'jobs')),
    due_offset_days  integer not null default 0,  -- fra sagens startdato
    mandatory        boolean not null default true
);

create table message_templates (                 -- mails/rykkere
    id          uuid primary key default gen_random_uuid(),
    legacy_id   text unique,
    name        text not null,
    category    text not null,
    tone        text not null,
    due_days    integer not null default 7,
    subject     text not null,
    body        text not null,
    active      boolean not null default true
);

create table notification_rules (                -- påmindelser (Windows-notifikationer)
    id           uuid primary key default gen_random_uuid(),
    legacy_id    text unique,
    name         text not null,
    rule         text not null check (rule in (
                     'opgave_forsinket', 'frist_i_dag', 'fratraedelse_naermer_sig',
                     'rykker_ikke_sendt', 'intet_svar_efter_rykker', 'sag_stillestaaende')),
    days         integer not null default 0,
    repeat_days  integer not null default 1,
    title        text not null,
    body         text not null default '',
    active       boolean not null default true
);

-- ---------- Sager ----------------------------------------------------------

create table lifecycle_cases (
    id                    uuid primary key default gen_random_uuid(),
    person_id             uuid not null references people (id),
    employment_record_id  uuid references employment_records (id),
    process               text not null check (process in ('onboarding', 'offboarding')),
    status                text not null,
    status_manual         boolean not null default false,
    status_reason         text not null default '',
    responsible           text not null default '',
    comment               text not null default '',
    tracking_link         text not null default '',
    template_id           uuid references workflow_templates (id),
    template_version      integer,
    archived_on           date,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now(),
    version               integer not null default 1,
    constraint lifecycle_cases_status_check check (
        (process = 'offboarding' and status in
            ('Afventer Udstyr', 'Delvist afleveret', 'Afviklet'))
        or (process = 'onboarding' and status in
            ('Kandidat', 'Afventer kontrakt', 'Afventer første oplæring',
             'Afventer jobs', 'Aktiv', 'Annulleret'))
    ),
    constraint lifecycle_cases_manual_reason check (
        not status_manual or length(trim(status_reason)) > 0
    )
);
create index lifecycle_cases_process_idx on lifecycle_cases (process, archived_on);

create table case_tasks (
    id            uuid primary key default gen_random_uuid(),
    case_id       uuid not null references lifecycle_cases (id) on delete cascade,
    legacy_id     text,
    sort_order    integer not null default 0,
    name          text not null,
    description   text not null default '',
    responsible   text not null default '',
    due_date      date,
    status        text not null default 'Ikke startet'
                  check (status in ('Ikke startet', 'I gang', 'Afventer', 'Udført', 'Undtaget')),
    mandatory     boolean not null default true,
    reason        text not null default '',
    next_action   text not null default '',
    equipment     text not null default '',
    milestone     text not null default '',
    completed_at  timestamptz,
    constraint case_tasks_exempt_reason check (status <> 'Undtaget' or length(trim(reason)) > 0)
);
create index case_tasks_case_idx on case_tasks (case_id);

create table case_reminders (                    -- rykkere
    id             uuid primary key default gen_random_uuid(),
    case_id        uuid not null references lifecycle_cases (id) on delete cascade,
    legacy_id      text,
    template_name  text not null default '',
    category       text not null default '',
    subject        text not null default '',
    due_date       date,
    created_at     timestamptz not null default now(),
    created_by     text not null default '',
    sent_at        timestamptz,
    sent_by        text not null default ''
);

create table audit_events (                      -- tidslinje (insert-only)
    id           uuid primary key default gen_random_uuid(),
    case_id      uuid not null references lifecycle_cases (id) on delete cascade,
    sequence     integer not null,
    occurred_at  timestamptz not null,
    actor        text not null,
    action       text not null,
    comment      text not null default '',
    reference    text not null default '',
    data         jsonb,
    hash         text,                            -- hash-kæde fra den lokale version
    unique (case_id, sequence)
);

-- ---------- Optimistisk låsning og tidsstempler ---------------------------

create or replace function inbase_bump_version() returns trigger
language plpgsql as $$
begin
    new.version := old.version + 1;
    new.updated_at := now();
    return new;
end;
$$;

create trigger lifecycle_cases_version
    before update on lifecycle_cases
    for each row execute function inbase_bump_version();
