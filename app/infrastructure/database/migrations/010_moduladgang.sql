-- IN-BASE 010: Adgang pr. modul
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 009.
--
-- user_profiles.module_access: de moduler, en (ikke-administrator) bruger må se.
-- NULL = standarden (onboarding, offboarding, oensker – som før). Administratorer
-- har altid alt. Kun administratorer kan ændre listen (inbase_set_module_access);
-- brugerne kan stadig kun selv ændre tema og notifikationer (002).
--
-- Låsen håndhæves i programmet. Telefoner (mdm_devices) var kun for
-- administratorer og åbnes her for brugere med modulet 'telefoner'.
-- Modulnavnene svarer til app/domain/adgang.py.

alter table public.user_profiles add column if not exists module_access text[]
    check (module_access <@ array['onboarding', 'offboarding', 'oensker', 'telefoner']::text[]);

-- ---------- Har den aktuelle bruger adgang til et modul? ---------------------

create or replace function public.inbase_has_module(p_module text)
returns boolean language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from public.user_profiles
        where id = auth.uid() and active and (
            role = 'Administrator'
            or (module_access is null and p_module in ('onboarding', 'offboarding', 'oensker'))
            or p_module = any(module_access)));
$$;
revoke execute on function public.inbase_has_module(text) from public, anon;
grant execute on function public.inbase_has_module(text) to authenticated;

-- ---------- Administrator sætter en brugers moduler -------------------------

create or replace function public.inbase_set_module_access(p_user_id uuid, p_modules text[])
returns void language plpgsql security definer set search_path = '' as $$
begin
    if not public.inbase_is_admin() then
        raise exception 'Kun administratorer kan ændre moduladgang.' using errcode = 'IB403';
    end if;
    if not coalesce(p_modules, '{}') <@ array['onboarding', 'offboarding', 'oensker', 'telefoner'] then
        raise exception 'Ukendt modul.' using errcode = 'IB422';
    end if;
    update public.user_profiles set module_access = p_modules where id = p_user_id;
    if not found then
        raise exception 'Brugeren findes ikke længere.' using errcode = 'IB409';
    end if;
end;
$$;
revoke execute on function public.inbase_set_module_access(uuid, text[]) from public, anon;
grant execute on function public.inbase_set_module_access(uuid, text[]) to authenticated;

-- ---------- Telefoner: adgang med modulet 'telefoner' -----------------------

drop policy if exists mdm_devices_admin_select on public.mdm_devices;
drop policy if exists mdm_devices_admin_delete on public.mdm_devices;
create policy mdm_devices_select on public.mdm_devices
    for select to authenticated using ((select public.inbase_has_module('telefoner')));
create policy mdm_devices_delete on public.mdm_devices
    for delete to authenticated using ((select public.inbase_has_module('telefoner')));

create or replace function public.inbase_mdm_create_device(p_device jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_d   jsonb := coalesce(p_device, '{}'::jsonb);
    v_new public.mdm_devices%rowtype;
begin
    if not public.inbase_has_module('telefoner') then
        raise exception 'Du har ikke adgang til Telefoner.' using errcode = 'IB403';
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
                             'provisioned_at', 'reset_code') then
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
