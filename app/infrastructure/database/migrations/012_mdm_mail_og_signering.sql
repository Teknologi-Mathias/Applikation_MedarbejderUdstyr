-- IN-BASE 012: Firma-mail pr. telefon og signeringsnøgle til styrings-appen
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 011.
--
-- Firma-mail (Gmail med IMAP) kan nu slås til og fra på en klargjort telefon
-- med en ændringskode – uden nulstilling. IN-BASE gemmer her, om telefonen har
-- firma-mail, så det kan ses i listen. Selve reglen ligger på telefonen.
--
-- inbase_mdm_update_devices er som i 010, plus feltet mail.
--
-- Desuden: projektets signeringsnøgle til styrings-appen (IN-BASE Klargøring).
-- Telefonerne accepterer kun opdateringer, der er signeret med samme nøgle som
-- den app, de blev klargjort med. Nøglen ligger derfor ét sted, kun læsbar for
-- administratorer, og hentes af scripts\byg_klargoering_apk.ps1, når en
-- administrator bygger appen. Den kan oprettes én gang og aldrig ændres eller
-- slettes fra klienten – en ny nøgle ville kræve, at alle telefoner nulstilles.

alter table public.mdm_devices
    add column if not exists mail boolean not null default false;

create table if not exists public.mdm_signing_key (
    id              smallint primary key default 1 check (id = 1),   -- højst én nøgle
    keystore_base64 text not null check (length(keystore_base64) <= 20000),
    store_password  text not null check (length(store_password) between 16 and 100),
    key_alias       text not null default 'inbase' check (length(key_alias) <= 50),
    reserve_code    text not null default '' check (length(reserve_code) <= 20),
    created_by      uuid default auth.uid(),
    created_at      timestamptz not null default now()
);

revoke all on public.mdm_signing_key from anon, authenticated, public;
grant select, insert on public.mdm_signing_key to authenticated;
grant all on public.mdm_signing_key to service_role;
alter table public.mdm_signing_key enable row level security;

drop policy if exists mdm_signing_key_admin_select on public.mdm_signing_key;
drop policy if exists mdm_signing_key_admin_insert on public.mdm_signing_key;
create policy mdm_signing_key_admin_select on public.mdm_signing_key
    for select to authenticated using ((select public.inbase_is_admin()));
create policy mdm_signing_key_admin_insert on public.mdm_signing_key
    for insert to authenticated with check ((select public.inbase_is_admin()));

create or replace function public.inbase_mdm_update_devices(p_changes jsonb)
returns integer language plpgsql security definer set search_path = '' as $$
declare
    v_c     jsonb;
    v_key   text;
    v_count integer := 0;
begin
    if not public.inbase_has_module('telefoner') then
        raise exception 'Du har ikke adgang til Telefoner.' using errcode = 'IB403';
    end if;
    if jsonb_typeof(coalesce(p_changes, '[]'::jsonb)) <> 'array' then
        raise exception 'p_changes skal være en liste.' using errcode = 'IB422';
    end if;
    for v_c in select * from jsonb_array_elements(coalesce(p_changes, '[]'::jsonb)) loop
        for v_key in select jsonb_object_keys(v_c) loop
            if v_key not in ('id', 'name', 'phone_number', 'note', 'status', 'manufacturer',
                             'model', 'serial_number', 'imei', 'android_version',
                             'provisioned_at', 'reset_code', 'mail') then
                raise exception 'Ukendt felt: %', v_key using errcode = 'IB422';
            end if;
        end loop;
        if v_c ? 'name' and exists (select 1 from public.mdm_devices
                                    where name = upper(trim(v_c->>'name'))
                                      and id <> (v_c->>'id')::uuid) then
            raise exception 'Der findes allerede en telefon med enhedsnavnet %.',
                upper(trim(v_c->>'name')) using errcode = 'IB422';
        end if;
        update public.mdm_devices d set
            name            = coalesce(upper(trim(v_c->>'name')), d.name),
            phone_number    = coalesce(v_c->>'phone_number', d.phone_number),
            note            = coalesce(v_c->>'note', d.note),
            status          = coalesce(v_c->>'status', d.status),
            manufacturer    = coalesce(v_c->>'manufacturer', d.manufacturer),
            model           = coalesce(v_c->>'model', d.model),
            serial_number   = coalesce(v_c->>'serial_number', d.serial_number),
            imei            = coalesce(v_c->>'imei', d.imei),
            android_version = coalesce(v_c->>'android_version', d.android_version),
            reset_code      = coalesce(v_c->>'reset_code', d.reset_code),
            mail            = coalesce((v_c->>'mail')::boolean, d.mail),
            provisioned_at  = case when v_c ? 'provisioned_at'
                                   then (v_c->>'provisioned_at')::timestamptz
                                   else d.provisioned_at end
        where d.id = (v_c->>'id')::uuid;
        if found then
            v_count := v_count + 1;
        end if;
    end loop;
    return v_count;
end;
$$;
