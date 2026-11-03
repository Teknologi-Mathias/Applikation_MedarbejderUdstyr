-- IN-BASE 021: Kalender (fase 2 – deling og fælles kalendere)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 020.
--
-- calendar_shares: en kalender delt med en bruger på et af tre niveauer:
--   freebusy  kun ledig/optaget (titler og detaljer skjules: "Optaget")
--   read      se alle detaljer
--   write     oprette, rette og slette begivenheder
-- En "fælles kalender" er blot en kalender, ejeren deler.
--
-- Adgang (inbase_calendar_access – det ene sted, den afgøres):
--   owner > write > read > admin > freebusy (det bedste niveau gælder).
--   'admin': administratorer ser alle kalendere med alle detaljer (som 'read'; en
--   kalender, der er delt med administratoren, tæller som delt).
--   Private begivenheder vises som "Optaget" for alle andre end ejeren – også
--   for administratorer og brugere med 'write' (som heller ikke kan rette dem).
-- Moderation: ejeren og administratorer kan dele, fjerne delinger og slette
-- kalendere og begivenheder (fx ved upassende indhold).
-- Maskeringen sker HER (inbase_calendar_events), så en titel aldrig sendes til
-- en, der kun må se ledig/optaget.

-- ---------- Tabel --------------------------------------------------------------

create table public.calendar_shares (
    calendar_id  uuid not null references public.calendars (id) on delete cascade,
    user_id      uuid not null references public.user_profiles (id) on delete cascade,
    level        text not null check (level in ('freebusy', 'read', 'write')),
    created_by   uuid references public.user_profiles (id) on delete set null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    primary key (calendar_id, user_id)
);
create index calendar_shares_user_idx on public.calendar_shares (user_id);

revoke all on public.calendar_shares from anon, authenticated, public;
grant all on public.calendar_shares to service_role;
alter table public.calendar_shares enable row level security;

-- ---------- Adgang ------------------------------------------------------------

create or replace function public.inbase_calendar_access(p_calendar_id uuid)
returns text language sql stable security definer set search_path = '' as $$
    select case
        when not public.inbase_has_module('kalender') then null
        when exists (select 1 from public.calendars
                     where id = p_calendar_id and owner_id = auth.uid()) then 'owner'
        else coalesce(
            (select level from public.calendar_shares
             where calendar_id = p_calendar_id and user_id = auth.uid() and level <> 'freebusy'),
            case when public.inbase_is_admin()
                      and exists (select 1 from public.calendars where id = p_calendar_id)
                 then 'admin' end,
            (select level from public.calendar_shares
             where calendar_id = p_calendar_id and user_id = auth.uid()))
    end;
$$;

-- Ejeren eller en administrator (moderation: dele, fjerne delinger, slette).
create or replace function public.inbase_calendar_can_moderate(p_calendar_id uuid)
returns boolean language sql stable security definer set search_path = '' as $$
    select coalesce(public.inbase_calendar_access(p_calendar_id), '') in ('owner', 'admin')
        or (public.inbase_is_admin() and public.inbase_has_module('kalender'));
$$;

create or replace function public.inbase_calendar_json(p_calendar public.calendars)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
    v_access text := public.inbase_calendar_access(p_calendar.id);
    v_owner  public.user_profiles%rowtype;
begin
    select * into v_owner from public.user_profiles where id = p_calendar.owner_id;
    return to_jsonb(p_calendar) || jsonb_build_object(
        'access', v_access,
        'owner_username', v_owner.username,
        'owner_display_name', coalesce(nullif(v_owner.display_name, ''), v_owner.username),
        'shares', case when public.inbase_calendar_can_moderate(p_calendar.id) then (
            select coalesce(jsonb_agg(jsonb_build_object(
                       'username', p.username,
                       'display_name', coalesce(nullif(p.display_name, ''), p.username),
                       'level', s.level) order by lower(p.username)), '[]'::jsonb)
            from public.calendar_shares s
            join public.user_profiles p on p.id = s.user_id
            where s.calendar_id = p_calendar.id) else '[]'::jsonb end);
end;
$$;

-- Begivenheden, som brugeren må se den: maskeret ("Optaget") ved ledig/optaget og ved
-- private begivenheder i andres kalendere.
create or replace function public.inbase_calendar_event_view(
    p_event public.calendar_events, p_access text)
returns jsonb language sql stable security definer set search_path = '' as $$
    select case
        when p_access = 'freebusy' or (p_event.private and p_access <> 'owner') then
            to_jsonb(p_event) - 'created_by' || jsonb_build_object(
                'title', 'Optaget', 'description', '', 'location', '', 'ical_uid', '',
                'reminder_minutes', null, 'created_by_username', null,
                'masked', true, 'access', p_access)
        else public.inbase_calendar_event_json(p_event)
             || jsonb_build_object('masked', false, 'access', p_access)
    end;
$$;

-- ---------- Læsning -----------------------------------------------------------

create or replace function public.inbase_calendars()
returns jsonb language sql stable security definer set search_path = '' as $$
    select coalesce(jsonb_agg(public.inbase_calendar_json(c) order by c.created_at, c.id), '[]')
    from public.calendars c
    where public.inbase_calendar_access(c.id) is not null;
$$;

create or replace function public.inbase_calendar_events(p_from timestamptz, p_to timestamptz)
returns jsonb language sql stable security definer set search_path = '' as $$
    with synlige as (
        select c.id, public.inbase_calendar_access(c.id) as access from public.calendars c
    ), serier as (
        select e.* from public.calendar_events e
        where e.calendar_id in (select id from synlige where access is not null)
          and e.starts_at < p_to and (e.recur_until is null or e.recur_until >= p_from)
    )
    select coalesce(jsonb_agg(public.inbase_calendar_event_view(e, s.access)
                              order by e.starts_at, e.id), '[]')
    from (
        select * from serier
        union
        select r.* from public.calendar_events r
        where r.recurrence_of in (select id from serier where rrule <> '')
    ) e
    join synlige s on s.id = e.calendar_id;
$$;

-- Ændrer sig også, når en deling til brugeren (eller i en synlig kalender) ændres.
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
        'shares', (select count(*) from public.calendar_shares
                   where calendar_id in (select id from synlige)),
        'updated', greatest((select max(updated_at) from synlige),
                            (select max(updated_at) from public.calendar_events
                             where calendar_id in (select id from synlige)),
                            (select max(updated_at) from public.calendar_shares
                             where calendar_id in (select id from synlige))));
$$;

-- ---------- Begivenheder: owner og write skriver ------------------------------

-- En privat begivenhed i en andens kalender kan kun ejeren rette (og administratorer slette).
create or replace function public.inbase_calendar_require_event(
    p_event public.calendar_events, p_delete boolean)
returns void language plpgsql stable security definer set search_path = '' as $$
declare
    v_access text := public.inbase_calendar_access(p_event.calendar_id);
begin
    if p_delete and public.inbase_calendar_can_moderate(p_event.calendar_id) then
        return;
    end if;
    perform public.inbase_calendar_require(p_event.calendar_id, array['owner', 'write']);
    if p_event.private and v_access <> 'owner' then
        raise exception 'Begivenheden er privat – kun ejeren kan ændre den.' using errcode = 'IB403';
    end if;
end;
$$;

create or replace function public.inbase_calendar_event_create(p_event jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_new public.calendar_events;
begin
    v_new := public.inbase_calendar_event_fields(null, p_event);
    perform public.inbase_calendar_require(v_new.calendar_id, array['owner', 'write']);
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
    perform public.inbase_calendar_require_event(v_old, false);
    if p_expected_version is distinct from v_old.version then
        raise exception 'Begivenheden er ændret et andet sted, efter du åbnede den. Dine ændringer er ikke gemt – åbn den igen.'
            using errcode = 'IB409';
    end if;
    if coalesce(p_event, '{}'::jsonb) ?| array['id', 'recurrence_of', 'original_start', 'ical_uid'] then
        raise exception 'Begivenhedens id og serie kan ikke ændres.' using errcode = 'IB422';
    end if;
    v_new := public.inbase_calendar_event_fields(v_old, p_event);
    if v_new.calendar_id <> v_old.calendar_id then
        perform public.inbase_calendar_require(v_new.calendar_id, array['owner', 'write']);
        if v_old.rrule <> '' or v_old.recurrence_of is not null then
            raise exception 'En gentaget begivenhed kan ikke flyttes til en anden kalender.'
                using errcode = 'IB422';
        end if;
    end if;
    if v_new.private and not v_old.private
            and public.inbase_calendar_access(v_new.calendar_id) <> 'owner' then
        raise exception 'Kun ejeren kan gøre en begivenhed privat.' using errcode = 'IB403';
    end if;
    update public.calendar_events set
        calendar_id = v_new.calendar_id, title = v_new.title, description = v_new.description,
        location = v_new.location, starts_at = v_new.starts_at, ends_at = v_new.ends_at,
        all_day = v_new.all_day, private = v_new.private,
        reminder_minutes = v_new.reminder_minutes, rrule = v_new.rrule,
        recur_until = v_new.recur_until, exdates = v_new.exdates
    where id = p_id
    returning * into v_new;
    if v_new.rrule = '' then
        delete from public.calendar_events where recurrence_of = p_id;
    end if;
    return public.inbase_calendar_event_json(v_new);
end;
$$;

create or replace function public.inbase_calendar_event_delete(p_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare
    v_old public.calendar_events%rowtype;
begin
    select * into v_old from public.calendar_events where id = p_id;
    if not found then
        return;     -- allerede slettet
    end if;
    if not public.inbase_has_module('kalender') then
        raise exception 'Du har ikke adgang til Kalender.' using errcode = 'IB403';
    end if;
    perform public.inbase_calendar_require_event(v_old, true);
    delete from public.calendar_events where id = p_id;
end;
$$;

-- Import også i kalendere, man kan redigere i (fx en fælles kalender).
create or replace function public.inbase_calendar_import(p_calendar_id uuid, p_events jsonb)
returns integer language plpgsql security definer set search_path = '' as $$
declare
    v_e     jsonb;
    v_new   public.calendar_events;
    v_serie uuid;
    v_antal integer := 0;
    v_n     integer;
begin
    perform public.inbase_calendar_require(p_calendar_id, array['owner', 'write']);
    if jsonb_typeof(coalesce(p_events, '[]'::jsonb)) <> 'array' then
        raise exception 'p_events skal være en liste.' using errcode = 'IB422';
    end if;
    if jsonb_array_length(p_events) > 500 then
        raise exception 'Højst 500 begivenheder pr. kald.' using errcode = 'IB422';
    end if;
    for v_e in select e from jsonb_array_elements(coalesce(p_events, '[]'::jsonb)) e
               order by (e ? 'recurrence_of_uid') loop
        v_serie := null;
        if v_e ? 'recurrence_of_uid' then
            select id into v_serie from public.calendar_events
            where calendar_id = p_calendar_id and ical_uid = v_e->>'recurrence_of_uid'
              and original_start is null and rrule <> '';
            if v_serie is null then
                continue;
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

-- ---------- Kalendere: sletning ved ejer eller administrator ------------------

create or replace function public.inbase_calendar_delete(p_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
    if not exists (select 1 from public.calendars where id = p_id) then
        raise exception 'Kalenderen findes ikke længere.' using errcode = 'IB409';
    end if;
    if not public.inbase_calendar_can_moderate(p_id) then
        raise exception 'Kun ejeren eller en administrator kan slette kalenderen.' using errcode = 'IB403';
    end if;
    delete from public.calendars where id = p_id;
end;
$$;

-- ---------- Deling ------------------------------------------------------------

create or replace function public.inbase_calendar_share_set(
    p_calendar_id uuid, p_username text, p_level text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_kalender public.calendars%rowtype;
    v_bruger   public.user_profiles%rowtype;
begin
    select * into v_kalender from public.calendars where id = p_calendar_id;
    if not found then
        raise exception 'Kalenderen findes ikke længere.' using errcode = 'IB409';
    end if;
    if not public.inbase_calendar_can_moderate(p_calendar_id) then
        raise exception 'Kun ejeren eller en administrator kan dele kalenderen.' using errcode = 'IB403';
    end if;
    if p_level is null or p_level not in ('freebusy', 'read', 'write') then
        raise exception 'Ukendt delingsniveau.' using errcode = 'IB422';
    end if;
    select * into v_bruger from public.user_profiles
    where username = upper(trim(coalesce(p_username, ''))) and active
      and (role = 'Administrator' or module_access is null or 'kalender' = any(module_access));
    if not found then
        raise exception 'Brugeren findes ikke, er deaktiveret eller har ikke adgang til Kalender.'
            using errcode = 'IB422';
    end if;
    if v_bruger.id = v_kalender.owner_id then
        raise exception 'Kalenderen tilhører allerede %.', v_bruger.username using errcode = 'IB422';
    end if;
    insert into public.calendar_shares (calendar_id, user_id, level, created_by)
    values (p_calendar_id, v_bruger.id, p_level, auth.uid())
    on conflict (calendar_id, user_id) do update set level = excluded.level, updated_at = now();
    return public.inbase_calendar_json(v_kalender);
end;
$$;

-- Ejeren/en administrator fjerner en deling – eller modtageren fjerner sig selv.
create or replace function public.inbase_calendar_share_remove(p_calendar_id uuid, p_username text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_kalender public.calendars%rowtype;
    v_bruger   uuid;
begin
    select * into v_kalender from public.calendars where id = p_calendar_id;
    if not found then
        raise exception 'Kalenderen findes ikke længere.' using errcode = 'IB409';
    end if;
    select id into v_bruger from public.user_profiles
    where username = upper(trim(coalesce(p_username, '')));
    if v_bruger is distinct from auth.uid()
            and not public.inbase_calendar_can_moderate(p_calendar_id) then
        raise exception 'Kun ejeren eller en administrator kan fjerne delinger.' using errcode = 'IB403';
    end if;
    delete from public.calendar_shares where calendar_id = p_calendar_id and user_id = v_bruger;
    return public.inbase_calendar_json(v_kalender);
end;
$$;

-- ---------- Hvem må kalde hvad ---------------------------------------------

do $$
declare
    f text;
begin
    foreach f in array array[
        'inbase_calendar_can_moderate(uuid)',
        'inbase_calendar_event_view(public.calendar_events, text)',
        'inbase_calendar_require_event(public.calendar_events, boolean)'] loop
        execute format('revoke execute on function public.%s from public, anon, authenticated', f);
    end loop;
    foreach f in array array[
        'inbase_calendar_share_set(uuid, text, text)', 'inbase_calendar_share_remove(uuid, text)'] loop
        execute format('revoke execute on function public.%s from public, anon', f);
        execute format('grant execute on function public.%s to authenticated', f);
    end loop;
end $$;

insert into public.schema_migrations (version, name) values (21, '021_kalender_deling')
on conflict (version) do nothing;
