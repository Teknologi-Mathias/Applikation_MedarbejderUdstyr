-- IN-BASE 001: datamodel (Supabase / PostgreSQL 15+)
--
-- Køres én gang i Supabase Dashboard → SQL Editor (se README.md i mappen
-- ovenover for rækkefølgen 001 → 004). Appen ændrer aldrig selv skemaet.
--
-- Principper:
-- * Alle tabeller har UUID-primærnøgler. Lønnr. er en attribut på
--   ansættelsesforholdet – aldrig en identitet (kandidater har intet lønnr.).
--   Lønnr. er IKKE unikt i databasen: samme person kan have en onboarding-
--   og en offboardingsag. Reglen "ét lønnr. pr. proces" ligger i services.
-- * people (identitet) er adskilt fra employment_records (ansættelse) og
--   lifecycle_cases (onboarding-/offboardingsag).
-- * Statusser er kontrollerede værdier (CHECK) og svarer til domænet
--   (app/domain/offboarding.py, onboarding.py, opgave.py).
-- * lifecycle_cases.version bruges til optimistisk låsning. Alle skrivninger
--   af sager går gennem inbase_save_case() (003), som tjekker versionen.
-- * audit_events (tidslinjen) kan kun indsættes – se 002 og 003.
-- * Ingen forretningsdata oprettes her; kun faste stillinger (positions).

create extension if not exists pgcrypto;

-- ---------- Organisation -------------------------------------------------

create table public.areas (
    id          uuid primary key default gen_random_uuid(),
    name        text not null unique check (length(trim(name)) > 0),
    sort_order  integer not null default 0,
    active      boolean not null default true,
    created_at  timestamptz not null default now()
);

create table public.positions (
    id          uuid primary key default gen_random_uuid(),
    code        text not null unique check (code in ('Ad Hoc', 'FM', 'DM', 'Afløser')),
    name        text not null,
    sort_order  integer not null default 0
);

insert into public.positions (code, name, sort_order) values
    ('Ad Hoc', 'Ad Hoc', 1), ('FM', 'FM', 2), ('DM', 'DM', 3), ('Afløser', 'Afløser', 4);

-- Fælles indstillinger (Indstillinger → Organisation / Data & sikkerhed).
-- Områder ligger i areas; alt andet her som nøgle → JSON-værdi.
create table public.app_settings (
    key         text primary key,
    value       jsonb not null,
    updated_at  timestamptz not null default now(),
    updated_by  text not null default ''
);

-- ---------- Brugere (knyttet til Supabase Auth) --------------------------
--
-- auth.users er selve kontoen (e-mail + adgangskode). user_profiles er
-- IN-BASE-profilen med SAMME id. Kun en profil giver adgang til data
-- (inbase_is_member() i 002) – en konto uden profil kan intet.
-- Profiler oprettes kun af Edge Function admin-create-user (service role)
-- eller af engangsfunktionen inbase_bootstrap_first_admin() (003).

create table public.user_profiles (
    id                     uuid primary key references auth.users (id) on delete cascade,
    username               text not null check (username ~ '^[A-Za-z0-9._-]{2,40}$'),
    display_name           text not null default '',
    email                  text not null default '',
    role                   text not null default 'Bruger'
                           check (role in ('Administrator', 'Bruger')),
    theme                  text not null default 'lilla' check (theme in ('lilla', 'lys')),
    windows_notifications  boolean not null default true,
    must_change_password   boolean not null default true,
    created_at             timestamptz not null default now(),
    updated_at             timestamptz not null default now()
);
create unique index user_profiles_username_uq on public.user_profiles (lower(username));

-- ---------- Personer og ansættelser --------------------------------------

create table public.people (
    id          uuid primary key,
    full_name   text not null check (length(trim(full_name)) > 0),
    email       text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create table public.employment_records (
    id                uuid primary key default gen_random_uuid(),
    person_id         uuid not null references public.people (id) on delete cascade,
    payroll_number    text,                       -- lønnr. (kan mangle for kandidater)
    position_id       uuid references public.positions (id),
    area_id           uuid references public.areas (id),
    employment_date   date,
    first_work_day    date,
    termination_date  date,                       -- sidste arbejdsdag (offboarding)
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);
create index employment_records_person_idx on public.employment_records (person_id);
create index employment_records_payroll_idx on public.employment_records (payroll_number);

-- ---------- Skabeloner -----------------------------------------------------

create table public.workflow_templates (
    id            uuid primary key,
    process       text not null check (process in ('onboarding', 'offboarding')),
    name          text not null check (length(trim(name)) > 0),
    description   text not null default '',
    positions     text[] not null default '{}',  -- tom = alle stillinger
    active        boolean not null default true,
    version       integer not null default 1,
    sort_order    integer not null default 0,
    updated_at    timestamptz not null default now(),
    updated_by    text not null default ''
);

-- Tidligere versioner (igangværende sager påvirkes ikke af nye versioner).
create table public.workflow_template_versions (
    template_id  uuid not null references public.workflow_templates (id) on delete cascade,
    version      integer not null,
    snapshot     jsonb not null,
    created_at   timestamptz not null default now(),
    primary key (template_id, version)
);

create table public.workflow_template_tasks (
    id               uuid primary key default gen_random_uuid(),
    template_id      uuid not null references public.workflow_templates (id) on delete cascade,
    sort_order       integer not null,
    name             text not null,
    description      text not null default '',
    responsible      text not null default '',   -- afdeling eller bruger
    equipment        text not null default '',   -- offboarding: udstyr der skal returneres
    milestone        text not null default ''
                     check (milestone in ('', 'kandidat', 'kontrakt', 'oplaering', 'jobs')),
    due_offset_days  integer not null default 0,  -- fra sagens startdato
    mandatory        boolean not null default true
);
create index workflow_template_tasks_template_idx on public.workflow_template_tasks (template_id);

create table public.message_templates (           -- mails/rykkere
    id          uuid primary key,
    name        text not null,
    category    text not null,
    tone        text not null,
    due_days    integer not null default 7,
    subject     text not null default '',
    body        text not null default '',
    active      boolean not null default true,
    sort_order  integer not null default 0,
    updated_at  timestamptz not null default now(),
    updated_by  text not null default ''
);

create table public.notification_rules (          -- påmindelser (Windows-notifikationer)
    id           uuid primary key,
    name         text not null,
    rule         text not null check (rule in (
                     'opgave_forsinket', 'frist_i_dag', 'fratraedelse_naermer_sig',
                     'rykker_ikke_sendt', 'intet_svar_efter_rykker', 'sag_stillestaaende')),
    days         integer not null default 0,
    repeat_days  integer not null default 1,
    title        text not null default '',
    body         text not null default '',
    active       boolean not null default true,
    sort_order   integer not null default 0,
    updated_at   timestamptz not null default now(),
    updated_by   text not null default ''
);

-- ---------- Sager ----------------------------------------------------------

create table public.lifecycle_cases (
    id                    uuid primary key,
    person_id             uuid not null references public.people (id),
    employment_record_id  uuid references public.employment_records (id) on delete set null,
    process               text not null check (process in ('onboarding', 'offboarding')),
    status                text not null,
    status_manual         boolean not null default false,
    status_reason         text not null default '',
    responsible           text not null default '',
    comment               text not null default '',
    tracking_link         text not null default '',
    template_id           uuid references public.workflow_templates (id) on delete set null,
    template_name         text not null default '',
    template_version      integer,
    archived_on           date,
    created_at            timestamptz not null default now(),
    created_by            text not null default '',
    updated_at            timestamptz not null default now(),
    updated_by            text not null default '',
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
create index lifecycle_cases_process_idx on public.lifecycle_cases (process, archived_on);
create index lifecycle_cases_updated_idx on public.lifecycle_cases (process, updated_at desc);

create table public.case_tasks (
    id            uuid primary key,
    case_id       uuid not null references public.lifecycle_cases (id) on delete cascade,
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
create index case_tasks_case_idx on public.case_tasks (case_id);

create table public.case_reminders (              -- rykkere (kun offboarding)
    id             uuid primary key,
    case_id        uuid not null references public.lifecycle_cases (id) on delete cascade,
    sort_order     integer not null default 0,
    template_name  text not null default '',
    category       text not null default '',
    subject        text not null default '',
    due_date       date,
    created_at     timestamptz not null default now(),
    created_by     text not null default '',
    sent_at        timestamptz,
    sent_by        text not null default ''
);
create index case_reminders_case_idx on public.case_reminders (case_id);

create table public.audit_events (                -- tidslinje (insert-only)
    id           uuid primary key default gen_random_uuid(),
    case_id      uuid not null references public.lifecycle_cases (id) on delete cascade,
    sequence     integer not null check (sequence >= 0),
    occurred_at  timestamptz not null,
    actor        text not null,
    action       text not null,
    comment      text not null default '',
    reference    text not null default '',
    data         jsonb,
    hash         text,                            -- hash-kæde beregnet af klienten
    recorded_at  timestamptz not null default now(),
    recorded_by  uuid,                            -- auth.uid() for den, der gemte
    unique (case_id, sequence)
);

-- ---------- Optimistisk låsning og tidsstempler ---------------------------

create or replace function public.inbase_bump_version() returns trigger
language plpgsql set search_path = '' as $$
begin
    new.version := old.version + 1;
    new.updated_at := now();
    return new;
end;
$$;

create trigger lifecycle_cases_version
    before update on public.lifecycle_cases
    for each row execute function public.inbase_bump_version();

create or replace function public.inbase_touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

create trigger people_touch before update on public.people
    for each row execute function public.inbase_touch_updated_at();
create trigger employment_records_touch before update on public.employment_records
    for each row execute function public.inbase_touch_updated_at();
create trigger user_profiles_touch before update on public.user_profiles
    for each row execute function public.inbase_touch_updated_at();
