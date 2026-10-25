-- IN-BASE 008: Telefoner klargøres lokalt fra IN-BASE (uden Google AMAPI)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 007.
--
-- Google lukkede for interne løsninger på Android Management API, så
-- telefonerne klargøres nu af IN-BASE's egen styrings-app (assets/mdm) uden
-- server. Der er ingen fjernstyring – derfor forsvinder Google-felterne, og
-- statusserne bliver: Afventer klargøring, Klargjort, Udgået
-- (svarer til app/domain/mdm_enhed.py).

alter table public.mdm_devices drop constraint if exists mdm_devices_status_check;

update public.mdm_devices set status = case status
    when 'Afventer aktivering' then 'Afventer klargøring'
    when 'Aktiveret' then 'Klargjort'
    when 'I drift' then 'Klargjort'
    else 'Udgået' end;

alter table public.mdm_devices alter column status set default 'Afventer klargøring';
alter table public.mdm_devices add constraint mdm_devices_status_check
    check (status in ('Afventer klargøring', 'Klargjort', 'Udgået'));

alter table public.mdm_devices
    drop column if exists amapi_name,
    drop column if exists policy,
    drop column if exists last_seen_at;
alter table public.mdm_devices rename column enrolled_at to provisioned_at;

-- ---------- Ændr en eller flere telefoner (ét kald) -------------------------
-- p_changes = [{id, <kolonne>: værdi, ...}, ...]. Returnerer antal ændrede rækker.

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
            if v_key not in ('id', 'name', 'phone_number', 'note', 'status', 'manufacturer',
                             'model', 'serial_number', 'imei', 'android_version',
                             'provisioned_at') then
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
