-- IN-BASE 007: Telefoner (MDM) – driftstelefoner styret via Google AMAPI
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 006.
--
-- Datamodel:
--   mdm_devices   én række pr. telefon, identificeret ved enhedsnavnet fra
--                 ERP (fx ISM589, unikt). Selve styringen (politikker, QR-token,
--                 kommandoer) ligger hos Google – her gemmes kun registret.
--                 Tildeling til medarbejdere sker i ERP, ikke her.
--
-- Trafik: tabellen er lille og skrives kun ved oprettelse, administrators
-- rettelser og manuel "Opdater status" (alle ændringer i ét RPC-kald).
--
-- Rettigheder (håndhæves HER):
--   Administrator : læser, opretter, ændrer og sletter.
--   Alle andre    : intet.
--
-- Statusser svarer til app/domain/mdm_enhed.py.

-- ---------- Tabel ------------------------------------------------------------

create table public.mdm_devices (
    id                   uuid primary key,            -- sættes af IN-BASE (= additionalData i QR-token)
    name                 text not null check (name ~ '^[A-Z0-9][A-Z0-9-]{1,19}$'),  -- ERP-enhedsnavn
    phone_number         text not null default '' check (length(phone_number) <= 30),
    note                 text not null default '' check (length(note) <= 2000),
    status               text not null default 'Afventer aktivering' check (status in (
                             'Afventer aktivering', 'Aktiveret', 'I drift', 'Spærret', 'Nulstillet')),
    amapi_name           text not null default '',    -- enterprises/<id>/devices/<id>
    policy               text not null default 'fl-opsaetning'
                         check (policy in ('fl-opsaetning', 'fl-drift')),
    manufacturer         text not null default '',
    model                text not null default '',
    serial_number        text not null default '',
    imei                 text not null default '',
    android_version      text not null default '',
    last_seen_at         timestamptz,
    enrolled_at          timestamptz,
    created_by           uuid references public.user_profiles (id) on delete set null,
    created_by_username  text not null,
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now(),
    version              integer not null default 1
);
create unique index mdm_devices_name_uq on public.mdm_devices (name);

create trigger mdm_devices_version
    before update on public.mdm_devices
    for each row execute function public.inbase_bump_version();

-- ---------- Privilegier og RLS ----------------------------------------------

revoke all on public.mdm_devices from anon, authenticated, public;
grant select, delete on public.mdm_devices to authenticated;
grant all on public.mdm_devices to service_role;
alter table public.mdm_devices enable row level security;

create policy mdm_devices_admin_select on public.mdm_devices
    for select to authenticated using ((select public.inbase_is_admin()));
create policy mdm_devices_admin_delete on public.mdm_devices
    for delete to authenticated using ((select public.inbase_is_admin()));

-- ---------- Opret en telefon -------------------------------------------------
-- p_device = {id, name, phone_number, note}. Status og opretter
-- sættes her.

create or replace function public.inbase_mdm_create_device(p_device jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_d   jsonb := coalesce(p_device, '{}'::jsonb);
    v_new public.mdm_devices%rowtype;
begin
    if not public.inbase_is_admin() then
        raise exception 'Kun administratorer kan administrere telefoner.' using errcode = 'IB403';
    end if;
    if length(trim(coalesce(v_d->>'name', ''))) = 0 then
        raise exception 'Angiv telefonens enhedsnavn fra ERP, fx ISM589.' using errcode = 'IB422';
    end if;
    if exists (select 1 from public.mdm_devices where name = upper(trim(v_d->>'name'))) then
        raise exception 'Der findes allerede en telefon med enhedsnavnet %.', upper(trim(v_d->>'name'))
            using errcode = 'IB422';
    end if;
    insert into public.mdm_devices (id, name, phone_number, note,
                                    created_by, created_by_username)
    values ((v_d->>'id')::uuid, upper(trim(v_d->>'name')), coalesce(v_d->>'phone_number', ''),
            coalesce(v_d->>'note', ''),
            auth.uid(), public.inbase_current_username())
    returning * into v_new;
    return to_jsonb(v_new);
end;
$$;

-- ---------- Ændr en eller flere telefoner (ét kald) -------------------------
-- p_changes = [{id, <kolonne>: værdi, ...}, ...]. Kun kolonnerne nedenfor kan
-- ændres; ukendte nøgler afvises. Returnerer antal ændrede rækker.

create or replace function public.inbase_mdm_update_devices(p_changes jsonb)
returns integer language plpgsql security definer set search_path = '' as $$
declare
    v_c     jsonb;
    v_key   text;
    v_count integer := 0;
begin
    if not public.inbase_is_admin() then
        raise exception 'Kun administratorer kan administrere telefoner.' using errcode = 'IB403';
    end if;
    if jsonb_typeof(coalesce(p_changes, '[]'::jsonb)) <> 'array' then
        raise exception 'p_changes skal være en liste.' using errcode = 'IB422';
    end if;
    for v_c in select * from jsonb_array_elements(coalesce(p_changes, '[]'::jsonb)) loop
        for v_key in select jsonb_object_keys(v_c) loop
            if v_key not in ('id', 'name', 'phone_number', 'note', 'status',
                             'amapi_name', 'policy', 'manufacturer', 'model', 'serial_number',
                             'imei', 'android_version', 'last_seen_at', 'enrolled_at') then
                raise exception 'Ukendt felt: %', v_key using errcode = 'IB422';
            end if;
        end loop;
        update public.mdm_devices d set
            name            = coalesce(upper(trim(v_c->>'name')), d.name),
            phone_number    = coalesce(v_c->>'phone_number', d.phone_number),
            note            = coalesce(v_c->>'note', d.note),
            status          = coalesce(v_c->>'status', d.status),
            amapi_name      = coalesce(v_c->>'amapi_name', d.amapi_name),
            policy          = coalesce(v_c->>'policy', d.policy),
            manufacturer    = coalesce(v_c->>'manufacturer', d.manufacturer),
            model           = coalesce(v_c->>'model', d.model),
            serial_number   = coalesce(v_c->>'serial_number', d.serial_number),
            imei            = coalesce(v_c->>'imei', d.imei),
            android_version = coalesce(v_c->>'android_version', d.android_version),
            last_seen_at    = case when v_c ? 'last_seen_at'
                                   then (v_c->>'last_seen_at')::timestamptz else d.last_seen_at end,
            enrolled_at     = case when v_c ? 'enrolled_at'
                                   then (v_c->>'enrolled_at')::timestamptz else d.enrolled_at end
        where d.id = (v_c->>'id')::uuid;
        if found then
            v_count := v_count + 1;
        end if;
    end loop;
    return v_count;
end;
$$;

-- ---------- Hvem må kalde hvad ---------------------------------------------

revoke execute on function public.inbase_mdm_create_device(jsonb)  from public, anon;
revoke execute on function public.inbase_mdm_update_devices(jsonb) from public, anon;
grant execute on function public.inbase_mdm_create_device(jsonb)   to authenticated;
grant execute on function public.inbase_mdm_update_devices(jsonb)  to authenticated;
