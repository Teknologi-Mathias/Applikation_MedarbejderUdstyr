-- IN-BASE 020: Kalender (fase 1 – egne kalendere)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 019.
--
-- Datamodel:
--   calendars        en kalender (ejer = den, der oprettede den)
--   calendar_events  en begivenhed; en serie har en RRULE (rrule) og evt.
--                    undtagelser (exdates). En rettet enkelt forekomst er en
--                    række med recurrence_of (seriens id) og original_start.
--
-- Rettigheder (håndhæves HER):
--   Kun ejeren ser og ændrer sine kalendere og deres begivenheder, og kun med
--   modulet 'kalender' (standard for alle). Deling kommer i 021.
--   Tabellerne kan ikke læses eller skrives direkte af klienten – al adgang går
--   gennem RPC'erne nedenfor, så deling (021) senere kan maskere felter
--   ("Optaget") uden at nogen kan læse titlen direkte fra tabellen.
--   inbase_calendar_access() er det ene sted, adgangen afgøres.
--
-- Tidspunkter er timestamptz; programmet arbejder i lokal dansk tid og
-- udfolder gentagelser selv (app/domain/kalender.py). recur_until (hvornår
-- seriens sidste forekomst slutter, NULL = uendelig) beregnes af programmet og
-- bruges kun til at finde de begivenheder, der kan ligge i et tidsrum.

-- ---------- Moduladgang: 'kalender' -------------------------------------------

do $$
declare
    v_navn text;
begin
    for v_navn in
        select c.conname from pg_constraint c
        where c.conrelid = 'public.user_profiles'::regclass and c.contype = 'c'
          and pg_get_constraintdef(c.oid) like '%module_access%'
    loop
        execute format('alter table public.user_profiles drop constraint %I', v_navn);
    end loop;
end $$;
alter table public.user_profiles add constraint user_profiles_module_access_check
    check (module_access <@ array['onboarding', 'offboarding', 'oensker', 'telefoner',
                                  'kalender']::text[]);

-- Kalender er slået til for alle – også dem, en administrator har valgt moduler for.
update public.user_profiles set module_access = module_access || array['kalender']
where module_access is not null and not ('kalender' = any(module_access));

create or replace function public.inbase_has_module(p_module text)
returns boolean language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from public.user_profiles
        where id = auth.uid() and active and (
            role = 'Administrator'
            or (module_access is null
                and p_module in ('onboarding', 'offboarding', 'oensker', 'kalender'))
            or p_module = any(module_access)));
$$;

create or replace function public.inbase_set_module_access(p_user_id uuid, p_modules text[])
returns void language plpgsql security definer set search_path = '' as $$
begin
    if not public.inbase_is_admin() then
        raise exception 'Kun administratorer kan ændre moduladgang.' using errcode = 'IB403';
    end if;
    if not coalesce(p_modules, '{}') <@ array['onboarding', 'offboarding', 'oensker', 'telefoner',
                                              'kalender'] then
        raise exception 'Ukendt modul.' using errcode = 'IB422';
    end if;
    update public.user_profiles set module_access = p_modules where id = p_user_id;
    if not found then
        raise exception 'Brugeren findes ikke længere.' using errcode = 'IB409';
    end if;
end;
$$;

-- ---------- Tabeller ---------------------------------------------------------

create table public.calendars (
    id          uuid primary key default gen_random_uuid(),
    owner_id    uuid not null references public.user_profiles (id) on delete cascade,
    name        text not null check (length(trim(name)) between 1 and 80),
    color       text not null default '#4F46E5' check (color ~ '^#[0-9A-Fa-f]{6}$'),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    version     integer not null default 1
);
create index calendars_owner_idx on public.calendars (owner_id);
create trigger calendars_version
    before update on public.calendars
    for each row execute function public.inbase_bump_version();

create table public.calendar_events (
    id                uuid primary key default gen_random_uuid(),
    calendar_id       uuid not null references public.calendars (id) on delete cascade,
    title             text not null check (length(trim(title)) between 1 and 200),
    description       text not null default '' check (length(description) <= 10000),
    location          text not null default '' check (length(location) <= 500),
    starts_at         timestamptz not null,
    ends_at           timestamptz not null,
    all_day           boolean not null default false,
    private           boolean not null default false,
    reminder_minutes  integer check (reminder_minutes between 0 and 40320),
    rrule             text not null default '' check (length(rrule) <= 500),
    recur_until       timestamptz,          -- seriens sidste slut; NULL = uendelig
    exdates           timestamptz[] not null default '{}',
    recurrence_of     uuid references public.calendar_events (id) on delete cascade,
    original_start    timestamptz,
    ical_uid          text not null default '' check (length(ical_uid) <= 500),
    created_by        uuid references public.user_profiles (id) on delete set null,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    version           integer not null default 1,
    constraint calendar_events_period check (ends_at >= starts_at),
    constraint calendar_events_override check ((recurrence_of is null) = (original_start is null)
                                               and (recurrence_of is null or rrule = ''))
);
create index calendar_events_range_idx on public.calendar_events (calendar_id, starts_at);
create index calendar_events_recurrence_idx on public.calendar_events (recurrence_of)
    where recurrence_of is not null;
-- Samme begivenhed importeres ikke to gange i samme kalender.
create unique index calendar_events_ical_uid_idx
    on public.calendar_events (calendar_id, ical_uid, original_start) nulls not distinct
    where ical_uid <> '';
create trigger calendar_events_version
    before update on public.calendar_events
    for each row execute function public.inbase_bump_version();

-- Ingen direkte adgang for klienten (heller ikke select) – kun RPC'erne.
do $$
declare
    t text;
begin
    foreach t in array array['calendars', 'calendar_events'] loop
        execute format('revoke all on public.%I from anon, authenticated, public', t);
        execute format('grant all on public.%I to service_role', t);
        execute format('alter table public.%I enable row level security', t);
    end loop;
end $$;

-- ---------- Adgang ------------------------------------------------------------
-- 'owner' eller NULL (ingen adgang). 021 tilføjer 'write', 'read' og 'freebusy'.

create or replace function public.inbase_calendar_access(p_calendar_id uuid)
returns text language sql stable security definer set search_path = '' as $$
    select case when public.inbase_has_module('kalender') and exists (
        select 1 from public.calendars where id = p_calendar_id and owner_id = auth.uid())
        then 'owner' end;
$$;

create or replace function public.inbase_calendar_json(p_calendar public.calendars)
returns jsonb language sql stable security definer set search_path = '' as $$
    select to_jsonb(p_calendar) || jsonb_build_object(
        'access', public.inbase_calendar_access(p_calendar.id),
        'owner_username', (select username from public.user_profiles
                           where id = p_calendar.owner_id));
$$;

create or replace function public.inbase_calendar_require(p_calendar_id uuid, p_levels text[])
returns void language plpgsql stable security definer set search_path = '' as $$
begin
    if not public.inbase_has_module('kalender') then
        raise exception 'Du har ikke adgang til Kalender.' using errcode = 'IB403';
    end if;
    if not exists (select 1 from public.calendars where id = p_calendar_id) then
        raise exception 'Kalenderen findes ikke længere.' using errcode = 'IB409';
    end if;
    if coalesce(public.inbase_calendar_access(p_calendar_id), '') <> all(p_levels) then
        raise exception 'Du har ikke rettighed til at ændre i denne kalender.' using errcode = 'IB403';
    end if;
end;
$$;

-- ---------- Kalendere ---------------------------------------------------------

create or replace function public.inbase_calendars()
returns jsonb language sql stable security definer set search_path = '' as $$
    select coalesce(jsonb_agg(public.inbase_calendar_json(c) order by c.created_at, c.id), '[]')
    from public.calendars c
    where public.inbase_calendar_access(c.id) is not null;
$$;

create or replace function public.inbase_calendar_create(p_calendar jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_c   jsonb := coalesce(p_calendar, '{}'::jsonb);
    v_new public.calendars%rowtype;
begin
    if not public.inbase_has_module('kalender') then
        raise exception 'Du har ikke adgang til Kalender.' using errcode = 'IB403';
    end if;
    if length(trim(coalesce(v_c->>'name', ''))) = 0 then
        raise exception 'Giv kalenderen et navn.' using errcode = 'IB422';
    end if;
    insert into public.calendars (id, owner_id, name, color)
    values (coalesce((v_c->>'id')::uuid, gen_random_uuid()), auth.uid(), trim(v_c->>'name'),
            coalesce(nullif(v_c->>'color', ''), '#4F46E5'))
    returning * into v_new;
    return public.inbase_calendar_json(v_new);
end;
$$;

create or replace function public.inbase_calendar_update(
    p_id uuid, p_expected_version integer, p_changes jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_c   jsonb := coalesce(p_changes, '{}'::jsonb);
    v_old public.calendars%rowtype;
    v_new public.calendars%rowtype;
    v_key text;
begin
    perform public.inbase_calendar_require(p_id, array['owner']);
    select * into v_old from public.calendars where id = p_id for update;
    if p_expected_version is distinct from v_old.version then
        raise exception 'Kalenderen er ændret et andet sted, efter du åbnede den. Åbn den igen.'
            using errcode = 'IB409';
    end if;
    for v_key in select jsonb_object_keys(v_c) loop
        if v_key not in ('name', 'color') then
            raise exception 'Ukendt felt: %', v_key using errcode = 'IB422';
        end if;
    end loop;
    update public.calendars set
        name  = coalesce(trim(v_c->>'name'), name),
        color = coalesce(v_c->>'color', color)
    where id = p_id
    returning * into v_new;
    return public.inbase_calendar_json(v_new);
end;
$$;

create or replace function public.inbase_calendar_delete(p_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
    perform public.inbase_calendar_require(p_id, array['owner']);
    delete from public.calendars where id = p_id;
end;
$$;

-- ---------- Begivenheder ------------------------------------------------------

create or replace function public.inbase_calendar_event_json(p_event public.calendar_events)
returns jsonb language sql stable security definer set search_path = '' as $$
    select to_jsonb(p_event) || jsonb_build_object(
        'created_by_username', (select username from public.user_profiles
                                where id = p_event.created_by));
$$;

-- Felterne fra p_event lagt oven på p_old (NULL: en ny begivenhed). Kontrollerer
-- seriens regler; recur_until = ends_at for en enkelt begivenhed.
create or replace function public.inbase_calendar_event_fields(
    p_old public.calendar_events, p_event jsonb)
returns public.calendar_events language plpgsql stable security definer set search_path = '' as $$
declare
    v_e   jsonb := coalesce(p_event, '{}'::jsonb);
    v_new public.calendar_events := p_old;
    v_key text;
begin
    for v_key in select jsonb_object_keys(v_e) loop
        if v_key not in ('id', 'calendar_id', 'title', 'description', 'location', 'starts_at',
                         'ends_at', 'all_day', 'private', 'reminder_minutes', 'rrule',
                         'recur_until', 'exdates', 'recurrence_of', 'original_start',
                         'ical_uid') then
            raise exception 'Ukendt felt: %', v_key using errcode = 'IB422';
        end if;
    end loop;
    if p_old.id is null then
        v_new.id := coalesce((v_e->>'id')::uuid, gen_random_uuid());
        v_new.recurrence_of := (v_e->>'recurrence_of')::uuid;
        v_new.original_start := (v_e->>'original_start')::timestamptz;
        v_new.ical_uid := coalesce(v_e->>'ical_uid', '');
        v_new.exdates := '{}';
        v_new.all_day := false;
        v_new.private := false;
        v_new.description := '';
        v_new.location := '';
        v_new.rrule := '';
    end if;
    v_new.calendar_id      := coalesce((v_e->>'calendar_id')::uuid, v_new.calendar_id);
    v_new.title            := coalesce(trim(v_e->>'title'), v_new.title);
    v_new.description      := coalesce(v_e->>'description', v_new.description);
    v_new.location         := coalesce(v_e->>'location', v_new.location);
    v_new.starts_at        := coalesce((v_e->>'starts_at')::timestamptz, v_new.starts_at);
    v_new.ends_at          := coalesce((v_e->>'ends_at')::timestamptz, v_new.ends_at);
    v_new.all_day          := coalesce((v_e->>'all_day')::boolean, v_new.all_day);
    v_new.private          := coalesce((v_e->>'private')::boolean, v_new.private);
    v_new.rrule            := coalesce(v_e->>'rrule', v_new.rrule);
    if v_e ? 'reminder_minutes' then
        v_new.reminder_minutes := (v_e->>'reminder_minutes')::integer;
    end if;
    if v_e ? 'recur_until' then
        v_new.recur_until := (v_e->>'recur_until')::timestamptz;
    end if;
    if v_e ? 'exdates' then
        v_new.exdates := array(select jsonb_array_elements_text(v_e->'exdates')::timestamptz);
    end if;

    if length(trim(coalesce(v_new.title, ''))) = 0 then
        raise exception 'Skriv en titel.' using errcode = 'IB422';
    end if;
    if v_new.starts_at is null or v_new.ends_at is null or v_new.ends_at < v_new.starts_at then
        raise exception 'Slut skal ligge efter start.' using errcode = 'IB422';
    end if;
    if v_new.rrule = '' then
        v_new.recur_until := v_new.ends_at;
        v_new.exdates := '{}';
    end if;
    if v_new.recurrence_of is not null and not exists (
            select 1 from public.calendar_events
            where id = v_new.recurrence_of and calendar_id = v_new.calendar_id and rrule <> '') then
        raise exception 'Serien findes ikke længere i kalenderen.' using errcode = 'IB409';
    end if;
    return v_new;
end;
$$;

create or replace function public.inbase_calendar_events(p_from timestamptz, p_to timestamptz)
returns jsonb language sql stable security definer set search_path = '' as $$
    with synlige as (
        select c.id from public.calendars c
        where public.inbase_calendar_access(c.id) is not null
    ), serier as (
        select e.* from public.calendar_events e
        where e.calendar_id in (select id from synlige)
          and e.starts_at < p_to and (e.recur_until is null or e.recur_until >= p_from)
    )
    select coalesce(jsonb_agg(public.inbase_calendar_event_json(e) order by e.starts_at, e.id), '[]')
    from (
        select * from serier
        union
        select r.* from public.calendar_events r
        where r.recurrence_of in (select id from serier where rrule <> '')
    ) e;
$$;

create or replace function public.inbase_calendar_event_create(p_event jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_new public.calendar_events;
begin
    v_new := public.inbase_calendar_event_fields(null, p_event);
    perform public.inbase_calendar_require(v_new.calendar_id, array['owner']);
    v_new.created_by := auth.uid();
    v_new.created_at := now();
    v_new.updated_at := now();
    v_new.version := 1;
    insert into public.calendar_events select v_new.*;
    return public.inbase_calendar_event_json(v_new);
end;
$$;

create or replace function public.inbase_calendar_event_update(
    p_id uuid, p_expected_version integer, p_event jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_old public.calendar_events%rowtype;
    v_new public.calendar_events;
begin
    select * into v_old from public.calendar_events where id = p_id for update;
    if not found then
        raise exception 'Begivenheden findes ikke længere – den er slettet et andet sted.'
            using errcode = 'IB409';
    end if;
    perform public.inbase_calendar_require(v_old.calendar_id, array['owner']);
    if p_expected_version is distinct from v_old.version then
        raise exception 'Begivenheden er ændret et andet sted, efter du åbnede den. Dine ændringer er ikke gemt – åbn den igen.'
            using errcode = 'IB409';
    end if;
    if coalesce(p_event, '{}'::jsonb) ?| array['id', 'recurrence_of', 'original_start', 'ical_uid'] then
        raise exception 'Begivenhedens id og serie kan ikke ændres.' using errcode = 'IB422';
    end if;
    v_new := public.inbase_calendar_event_fields(v_old, p_event);
    if v_new.calendar_id <> v_old.calendar_id then
        perform public.inbase_calendar_require(v_new.calendar_id, array['owner']);
        if v_old.rrule <> '' or v_old.recurrence_of is not null then
            raise exception 'En gentaget begivenhed kan ikke flyttes til en anden kalender.'
                using errcode = 'IB422';
        end if;
    end if;
    update public.calendar_events set
        calendar_id = v_new.calendar_id, title = v_new.title, description = v_new.description,
        location = v_new.location, starts_at = v_new.starts_at, ends_at = v_new.ends_at,
        all_day = v_new.all_day, private = v_new.private,
        reminder_minutes = v_new.reminder_minutes, rrule = v_new.rrule,
        recur_until = v_new.recur_until, exdates = v_new.exdates
    where id = p_id
    returning * into v_new;
    -- En serie, der ikke længere gentages, har ingen rettede forekomster.
    if v_new.rrule = '' then
        delete from public.calendar_events where recurrence_of = p_id;
    end if;
    return public.inbase_calendar_event_json(v_new);
end;
$$;

create or replace function public.inbase_calendar_event_delete(p_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare
    v_kalender uuid;
begin
    select calendar_id into v_kalender from public.calendar_events where id = p_id;
    if not found then
        return;     -- allerede slettet
    end if;
    perform public.inbase_calendar_require(v_kalender, array['owner']);
    delete from public.calendar_events where id = p_id;
end;
$$;

-- Import (.ics): p_events er en liste af begivenheder som til _create. Rettede
-- forekomster har original_start og recurrence_of_uid (seriens ical_uid) og
-- kobles til serien med den UID i samme kalender. Dubletter (samme ical_uid og
-- original_start i kalenderen) springes over. Returnerer antal oprettede.
create or replace function public.inbase_calendar_import(p_calendar_id uuid, p_events jsonb)
returns integer language plpgsql security definer set search_path = '' as $$
declare
    v_e     jsonb;
    v_new   public.calendar_events;
    v_serie uuid;
    v_antal integer := 0;
    v_n     integer;
begin
    perform public.inbase_calendar_require(p_calendar_id, array['owner']);
    if jsonb_typeof(coalesce(p_events, '[]'::jsonb)) <> 'array' then
        raise exception 'p_events skal være en liste.' using errcode = 'IB422';
    end if;
    if jsonb_array_length(p_events) > 500 then
        raise exception 'Højst 500 begivenheder pr. kald.' using errcode = 'IB422';
    end if;
    -- Serier og enkelte begivenheder først, så de rettede forekomster kan finde serien.
    for v_e in select e from jsonb_array_elements(coalesce(p_events, '[]'::jsonb)) e
               order by (e ? 'recurrence_of_uid') loop
        v_serie := null;
        if v_e ? 'recurrence_of_uid' then
            select id into v_serie from public.calendar_events
            where calendar_id = p_calendar_id and ical_uid = v_e->>'recurrence_of_uid'
              and original_start is null and rrule <> '';
            if v_serie is null then
                continue;   -- serien findes ikke (fx sprunget over) – forekomsten droppes
            end if;
        end if;
        v_new := public.inbase_calendar_event_fields(
            null, (v_e - 'recurrence_of_uid' - 'id')
                  || jsonb_build_object('calendar_id', p_calendar_id, 'recurrence_of', v_serie));
        v_new.created_by := auth.uid();
        v_new.created_at := now();
        v_new.updated_at := now();
        v_new.version := 1;
        insert into public.calendar_events select v_new.* on conflict do nothing;
        get diagnostics v_n = row_count;
        v_antal := v_antal + v_n;
    end loop;
    return v_antal;
end;
$$;

-- Ændrer sig, når en synlig kalender eller begivenhed er oprettet, ændret eller slettet.
create or replace function public.inbase_calendar_signature()
returns jsonb language sql stable security definer set search_path = '' as $$
    with synlige as (
        select c.id, c.updated_at from public.calendars c
        where public.inbase_calendar_access(c.id) is not null
    )
    select jsonb_build_object(
        'calendars', (select count(*) from synlige),
        'events', (select count(*) from public.calendar_events
                   where calendar_id in (select id from synlige)),
        'updated', greatest((select max(updated_at) from synlige),
                            (select max(updated_at) from public.calendar_events
                             where calendar_id in (select id from synlige))));
$$;

-- ---------- Hvem må kalde hvad ---------------------------------------------

do $$
declare
    f text;
begin
    foreach f in array array[
        'inbase_calendar_access(uuid)', 'inbase_calendar_json(public.calendars)',
        'inbase_calendar_require(uuid, text[])',
        'inbase_calendar_event_json(public.calendar_events)',
        'inbase_calendar_event_fields(public.calendar_events, jsonb)'] loop
        execute format('revoke execute on function public.%s from public, anon, authenticated', f);
    end loop;
    foreach f in array array[
        'inbase_calendars()', 'inbase_calendar_create(jsonb)',
        'inbase_calendar_update(uuid, integer, jsonb)', 'inbase_calendar_delete(uuid)',
        'inbase_calendar_events(timestamptz, timestamptz)', 'inbase_calendar_event_create(jsonb)',
        'inbase_calendar_event_update(uuid, integer, jsonb)', 'inbase_calendar_event_delete(uuid)',
        'inbase_calendar_import(uuid, jsonb)', 'inbase_calendar_signature()'] loop
        execute format('revoke execute on function public.%s from public, anon', f);
        execute format('grant execute on function public.%s to authenticated', f);
    end loop;
end $$;

insert into public.schema_migrations (version, name) values (20, '020_kalender')
on conflict (version) do nothing;
