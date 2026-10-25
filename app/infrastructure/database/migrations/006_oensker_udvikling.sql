-- IN-BASE 006: Ønsker & Udvikling (fejlmeldinger, ønsker og forbedringsforslag)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 005.
--
-- Datamodel:
--   development_requests          én indmelding (stabilt UUID + løbenummer #N)
--   development_request_comments  kommentarer; internal = administratornote
--   development_request_events    ændringshistorik pr. felt (insert-only)
--
-- Rettigheder (håndhæves HER – skjulte knapper i programmet er ikke sikkerhed):
--   Medlem (aktiv profil)  : ser alle indmeldinger, offentlige kommentarer og
--                            historik; opretter indmeldinger; kommenterer;
--                            redigerer teksten i EGNE indmeldinger, mens de har
--                            status Indsendt.
--   Administrator          : derudover status, prioritet, ansvarlig, planlagt
--                            version, løsning, interne noter og sletning.
--   anon / uden profil     : intet.
-- Al skrivning (undtagen sletning) går gennem RPC'erne nedenfor. Indsender og
-- forfatter sættes ud fra auth.uid() – aldrig ud fra noget, klienten sender.
--
-- Statusser, kategorier, prioriteter og tilladte statusovergange svarer til
-- app/domain/indmelding.py.
--
-- Vedhæftede filer er bevidst ikke med i første version (se
-- docs/ARKITEKTUR.md, "Kendte begrænsninger").

-- ---------- Tabeller ---------------------------------------------------------

create table public.development_requests (
    id                     uuid primary key default gen_random_uuid(),
    number                 bigint generated always as identity unique,
    title                  text not null check (length(trim(title)) between 1 and 200),
    description            text not null default '',
    category               text not null check (category in (
                               'Fejlmelding', 'Nyt ønske', 'Automatisering', 'Data og ERP',
                               'Forbedring af arbejdsgang', 'Andet')),
    current_behavior       text not null default '',   -- problem / nuværende adfærd
    desired_outcome        text not null default '',   -- ønsket resultat
    business_impact        text not null default '',   -- forventet forretningsmæssig effekt
    additional_info        text not null default '',
    status                 text not null default 'Indsendt' check (status in (
                               'Indsendt', 'Til vurdering', 'Accepteret', 'Afvist', 'Planlagt',
                               'Under udvikling', 'Til test', 'Udgivet')),
    priority               text not null default 'Normal'
                           check (priority in ('Lav', 'Normal', 'Høj', 'Kritisk')),
    submitted_by           uuid references public.user_profiles (id) on delete set null,
    submitted_by_username  text not null,               -- bevares, hvis brugeren slettes
    assignee_id            uuid references public.user_profiles (id) on delete set null,
    assignee_username      text not null default '',
    planned_version        text not null default '' check (length(planned_version) <= 40),
    resolution             text not null default '',   -- afsluttende løsning / begrundelse
    created_at             timestamptz not null default now(),
    updated_at             timestamptz not null default now(),
    version                integer not null default 1,
    constraint development_requests_text_length check (
        greatest(length(description), length(current_behavior), length(desired_outcome),
                 length(business_impact), length(additional_info), length(resolution)) <= 10000
    )
);
create index development_requests_status_idx on public.development_requests (status);
create index development_requests_updated_idx on public.development_requests (updated_at desc);
create index development_requests_submitter_idx on public.development_requests (submitted_by);

create trigger development_requests_version
    before update on public.development_requests
    for each row execute function public.inbase_bump_version();

create table public.development_request_comments (
    id               uuid primary key default gen_random_uuid(),
    request_id       uuid not null references public.development_requests (id) on delete cascade,
    author_id        uuid references public.user_profiles (id) on delete set null,
    author_username  text not null,
    body             text not null check (length(trim(body)) between 1 and 5000),
    internal         boolean not null default false,   -- kun synlig for administratorer
    created_at       timestamptz not null default now()
);
create index development_request_comments_request_idx
    on public.development_request_comments (request_id, created_at);

create table public.development_request_events (
    id              bigint generated always as identity primary key,   -- rækkefølge
    request_id      uuid not null references public.development_requests (id) on delete cascade,
    occurred_at     timestamptz not null default now(),
    actor_id        uuid,                                              -- auth.uid()
    actor_username  text not null,
    action          text not null check (action in ('oprettet', 'aendret')),
    field           text not null default '',
    old_value       text not null default '',
    new_value       text not null default ''
);
create index development_request_events_request_idx
    on public.development_request_events (request_id, id);

-- ---------- Privilegier og RLS ----------------------------------------------

do $$
declare t text;
begin
    foreach t in array array[
        'development_requests', 'development_request_comments', 'development_request_events']
    loop
        execute format('revoke all on public.%I from anon, authenticated, public', t);
        execute format('grant select on public.%I to authenticated', t);
        execute format('grant all on public.%I to service_role', t);
        execute format('alter table public.%I enable row level security', t);
    end loop;
end $$;
-- Ingen direkte insert/update: kun via RPC. Sletning direkte (RLS: kun admin).
grant delete on public.development_requests         to authenticated;
grant delete on public.development_request_comments to authenticated;

create policy development_requests_select on public.development_requests
    for select to authenticated using ((select public.inbase_is_member()));
create policy development_requests_admin_delete on public.development_requests
    for delete to authenticated using ((select public.inbase_is_admin()));

create policy development_request_comments_select on public.development_request_comments
    for select to authenticated
    using ((select public.inbase_is_member()) and (not internal or (select public.inbase_is_admin())));
create policy development_request_comments_admin_delete on public.development_request_comments
    for delete to authenticated using ((select public.inbase_is_admin()));

create policy development_request_events_select on public.development_request_events
    for select to authenticated using ((select public.inbase_is_member()));
-- Historikken kan hverken ændres eller slettes af klienten (ingen grants/politikker).

-- ---------- Regler (interne hjælpere) --------------------------------------

create or replace function public.inbase_request_transition_allowed(p_from text, p_to text)
returns boolean language sql immutable set search_path = '' as $$
    select p_from = p_to or (p_from, p_to) in (
        ('Indsendt', 'Til vurdering'), ('Indsendt', 'Accepteret'), ('Indsendt', 'Afvist'),
        ('Til vurdering', 'Indsendt'), ('Til vurdering', 'Accepteret'), ('Til vurdering', 'Afvist'),
        ('Accepteret', 'Planlagt'), ('Accepteret', 'Under udvikling'), ('Accepteret', 'Afvist'),
        ('Planlagt', 'Accepteret'), ('Planlagt', 'Under udvikling'), ('Planlagt', 'Afvist'),
        ('Under udvikling', 'Planlagt'), ('Under udvikling', 'Til test'),
        ('Til test', 'Under udvikling'), ('Til test', 'Udgivet'),
        ('Udgivet', 'Under udvikling'),
        ('Afvist', 'Til vurdering'));
$$;

create or replace function public.inbase_validate_request(r public.development_requests)
returns void language plpgsql immutable set search_path = '' as $$
begin
    if length(trim(coalesce(r.title, ''))) = 0 then
        raise exception 'Indmeldingen skal have en titel.' using errcode = 'IB422';
    end if;
    if length(r.title) > 200 then
        raise exception 'Titlen må højst være 200 tegn.' using errcode = 'IB422';
    end if;
    if length(trim(coalesce(r.description, ''))) = 0 then
        raise exception 'Skriv en beskrivelse af indmeldingen.' using errcode = 'IB422';
    end if;
    if coalesce(r.category, '') not in ('Fejlmelding', 'Nyt ønske', 'Automatisering',
                                        'Data og ERP', 'Forbedring af arbejdsgang', 'Andet') then
        raise exception 'Vælg en gyldig kategori.' using errcode = 'IB422';
    end if;
    if coalesce(r.status, '') not in ('Indsendt', 'Til vurdering', 'Accepteret', 'Afvist',
                                      'Planlagt', 'Under udvikling', 'Til test', 'Udgivet') then
        raise exception 'Ukendt status: %', r.status using errcode = 'IB422';
    end if;
    if coalesce(r.priority, '') not in ('Lav', 'Normal', 'Høj', 'Kritisk') then
        raise exception 'Ukendt prioritet: %', r.priority using errcode = 'IB422';
    end if;
    if length(coalesce(r.planned_version, '')) > 40 then
        raise exception 'Planlagt version må højst være 40 tegn.' using errcode = 'IB422';
    end if;
    if greatest(length(r.description), length(r.current_behavior), length(r.desired_outcome),
                length(r.business_impact), length(r.additional_info), length(r.resolution)) > 10000 then
        raise exception 'En tekst må højst være 10.000 tegn.' using errcode = 'IB422';
    end if;
    if r.status = 'Afvist' and length(trim(coalesce(r.resolution, ''))) = 0 then
        raise exception 'Skriv en begrundelse i feltet Løsning, når en indmelding afvises.'
            using errcode = 'IB422';
    end if;
end;
$$;

revoke execute on function public.inbase_request_transition_allowed(text, text)
    from public, anon, authenticated;
revoke execute on function public.inbase_validate_request(public.development_requests)
    from public, anon, authenticated;

-- ---------- Opret en indmelding ---------------------------------------------
-- p_request = {title, description, category, current_behavior, desired_outcome,
--              business_impact, additional_info}. Status (Indsendt), prioritet
-- (Normal) og indsender sættes her – ikke af klienten.

create or replace function public.inbase_create_request(p_request jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_uid  uuid := auth.uid();
    v_user text := public.inbase_current_username();
    v_r    jsonb := coalesce(p_request, '{}'::jsonb);
    v_new  public.development_requests%rowtype;
begin
    if v_user is null then
        raise exception 'Du har ikke adgang til IN-BASE.' using errcode = 'IB403';
    end if;
    v_new.title            := trim(coalesce(v_r->>'title', ''));
    v_new.description      := coalesce(v_r->>'description', '');
    v_new.category         := coalesce(v_r->>'category', '');
    v_new.current_behavior := coalesce(v_r->>'current_behavior', '');
    v_new.desired_outcome  := coalesce(v_r->>'desired_outcome', '');
    v_new.business_impact  := coalesce(v_r->>'business_impact', '');
    v_new.additional_info  := coalesce(v_r->>'additional_info', '');
    v_new.status           := 'Indsendt';
    v_new.priority         := 'Normal';
    v_new.planned_version  := '';
    v_new.resolution       := '';
    perform public.inbase_validate_request(v_new);

    insert into public.development_requests (
        title, description, category, current_behavior, desired_outcome, business_impact,
        additional_info, submitted_by, submitted_by_username)
    values (v_new.title, v_new.description, v_new.category, v_new.current_behavior,
            v_new.desired_outcome, v_new.business_impact, v_new.additional_info, v_uid, v_user)
    returning * into v_new;

    insert into public.development_request_events (request_id, actor_id, actor_username,
                                                   action, field, new_value)
    values (v_new.id, v_uid, v_user, 'oprettet', 'status', v_new.status);
    return to_jsonb(v_new);
end;
$$;

-- ---------- Ændr en indmelding (med optimistisk låsning) --------------------
-- p_changes = kun de felter, der ændres:
--   tekst (indsender, mens status er Indsendt – eller administrator):
--     title, description, category, current_behavior, desired_outcome,
--     business_impact, additional_info
--   behandling (kun administrator):
--     status, priority, assignee (brugernavn, "" = ingen), planned_version, resolution
-- Hver ændret værdi registreres i development_request_events.

create or replace function public.inbase_update_request(
    p_id uuid, p_expected_version integer, p_changes jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_uid     uuid := auth.uid();
    v_user    text := public.inbase_current_username();
    v_admin   boolean := public.inbase_is_admin();
    v_changes jsonb := coalesce(p_changes, '{}'::jsonb);
    v_old     public.development_requests%rowtype;
    v_new     public.development_requests%rowtype;
    v_key     text;
begin
    if v_user is null then
        raise exception 'Du har ikke adgang til IN-BASE.' using errcode = 'IB403';
    end if;
    select * into v_old from public.development_requests where id = p_id for update;
    if not found then
        raise exception 'Indmeldingen findes ikke længere – den er slettet af en anden.'
            using errcode = 'IB409';
    end if;
    if p_expected_version is distinct from v_old.version then
        raise exception 'Indmeldingen er ændret af en anden, efter du åbnede den. Dine ændringer er ikke gemt – åbn den igen og gentag dem.'
            using errcode = 'IB409';
    end if;

    for v_key in select jsonb_object_keys(v_changes) loop
        if v_key in ('status', 'priority', 'assignee', 'planned_version', 'resolution') then
            if not v_admin then
                raise exception 'Kun administratorer kan ændre status, prioritet, ansvarlig, planlagt version og løsning.'
                    using errcode = 'IB403';
            end if;
        elsif v_key in ('title', 'description', 'category', 'current_behavior',
                        'desired_outcome', 'business_impact', 'additional_info') then
            if not v_admin and not (v_old.submitted_by = v_uid and v_old.status = 'Indsendt') then
                raise exception 'Du kan kun redigere dine egne indmeldinger, mens de har status Indsendt.'
                    using errcode = 'IB403';
            end if;
        else
            raise exception 'Ukendt felt: %', v_key using errcode = 'IB422';
        end if;
    end loop;

    v_new := v_old;
    v_new.title            := coalesce(trim(v_changes->>'title'), v_old.title);
    v_new.description      := coalesce(v_changes->>'description', v_old.description);
    v_new.category         := coalesce(v_changes->>'category', v_old.category);
    v_new.current_behavior := coalesce(v_changes->>'current_behavior', v_old.current_behavior);
    v_new.desired_outcome  := coalesce(v_changes->>'desired_outcome', v_old.desired_outcome);
    v_new.business_impact  := coalesce(v_changes->>'business_impact', v_old.business_impact);
    v_new.additional_info  := coalesce(v_changes->>'additional_info', v_old.additional_info);
    v_new.status           := coalesce(v_changes->>'status', v_old.status);
    v_new.priority         := coalesce(v_changes->>'priority', v_old.priority);
    v_new.planned_version  := coalesce(trim(v_changes->>'planned_version'), v_old.planned_version);
    v_new.resolution       := coalesce(v_changes->>'resolution', v_old.resolution);
    if v_changes ? 'assignee' then
        if coalesce(trim(v_changes->>'assignee'), '') = '' then
            v_new.assignee_id := null;
            v_new.assignee_username := '';
        else
            select p.id, p.username into v_new.assignee_id, v_new.assignee_username
            from public.user_profiles p
            where lower(p.username) = lower(trim(v_changes->>'assignee')) and p.active;
            if not found then
                raise exception 'Ukendt eller deaktiveret bruger: %', v_changes->>'assignee'
                    using errcode = 'IB422';
            end if;
        end if;
    end if;

    if not public.inbase_request_transition_allowed(v_old.status, v_new.status) then
        raise exception 'Status kan ikke ændres fra "%" til "%".', v_old.status, v_new.status
            using errcode = 'IB422';
    end if;
    perform public.inbase_validate_request(v_new);
    if v_new is not distinct from v_old then
        return to_jsonb(v_old);   -- intet ændret: ingen ny version, ingen historik
    end if;

    update public.development_requests set
        title = v_new.title, description = v_new.description, category = v_new.category,
        current_behavior = v_new.current_behavior, desired_outcome = v_new.desired_outcome,
        business_impact = v_new.business_impact, additional_info = v_new.additional_info,
        status = v_new.status, priority = v_new.priority, assignee_id = v_new.assignee_id,
        assignee_username = v_new.assignee_username, planned_version = v_new.planned_version,
        resolution = v_new.resolution
    where id = p_id
    returning * into v_new;

    insert into public.development_request_events (request_id, actor_id, actor_username,
                                                   action, field, old_value, new_value)
    select p_id, v_uid, v_user, 'aendret', f.felt, f.fra, f.til
    from (values
        (1, 'title', v_old.title, v_new.title),
        (2, 'category', v_old.category, v_new.category),
        (3, 'description', v_old.description, v_new.description),
        (4, 'current_behavior', v_old.current_behavior, v_new.current_behavior),
        (5, 'desired_outcome', v_old.desired_outcome, v_new.desired_outcome),
        (6, 'business_impact', v_old.business_impact, v_new.business_impact),
        (7, 'additional_info', v_old.additional_info, v_new.additional_info),
        (8, 'status', v_old.status, v_new.status),
        (9, 'priority', v_old.priority, v_new.priority),
        (10, 'assignee', v_old.assignee_username, v_new.assignee_username),
        (11, 'planned_version', v_old.planned_version, v_new.planned_version),
        (12, 'resolution', v_old.resolution, v_new.resolution)
    ) as f(nr, felt, fra, til)
    where f.fra is distinct from f.til
    order by f.nr;
    return to_jsonb(v_new);
end;
$$;

-- ---------- Kommentarer -------------------------------------------------------
-- Alle medlemmer kan skrive offentlige kommentarer; kun administratorer
-- interne noter (internal = true), som kun administratorer kan læse (RLS).

create or replace function public.inbase_add_request_comment(
    p_request_id uuid, p_body text, p_internal boolean default false)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_uid  uuid := auth.uid();
    v_user text := public.inbase_current_username();
    v_row  public.development_request_comments%rowtype;
begin
    if v_user is null then
        raise exception 'Du har ikke adgang til IN-BASE.' using errcode = 'IB403';
    end if;
    if coalesce(p_internal, false) and not public.inbase_is_admin() then
        raise exception 'Kun administratorer kan skrive interne noter.' using errcode = 'IB403';
    end if;
    if length(trim(coalesce(p_body, ''))) = 0 then
        raise exception 'Skriv en kommentar.' using errcode = 'IB422';
    end if;
    if length(trim(p_body)) > 5000 then
        raise exception 'En kommentar må højst være 5.000 tegn.' using errcode = 'IB422';
    end if;
    if not exists (select 1 from public.development_requests where id = p_request_id) then
        raise exception 'Indmeldingen findes ikke længere.' using errcode = 'IB409';
    end if;
    insert into public.development_request_comments (request_id, author_id, author_username,
                                                     body, internal)
    values (p_request_id, v_uid, v_user, trim(p_body), coalesce(p_internal, false))
    returning * into v_row;
    return to_jsonb(v_row);
end;
$$;

-- ---------- Hvem må kalde hvad ---------------------------------------------

revoke execute on function public.inbase_create_request(jsonb)                   from public, anon;
revoke execute on function public.inbase_update_request(uuid, integer, jsonb)    from public, anon;
revoke execute on function public.inbase_add_request_comment(uuid, text, boolean) from public, anon;
grant execute on function public.inbase_create_request(jsonb)                    to authenticated;
grant execute on function public.inbase_update_request(uuid, integer, jsonb)     to authenticated;
grant execute on function public.inbase_add_request_comment(uuid, text, boolean) to authenticated;
