-- IN-BASE 013: Arkiv under Telefoner (MDM)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 012.
--
-- "Fjern fra listen" sletter ikke længere telefonen, men arkiverer den
-- (archived_at sættes). Så bevares nulstillingskoden mm., og telefonen kan
-- gendannes fra Telefoner → Arkiv. Rettighederne er de samme som for resten af
-- tabellen (modulet Telefoner, migrering 010).
--
-- inbase_mdm_update_devices er som i 012, plus feltet archived_at (null = gendan).

alter table public.mdm_devices
    add column if not exists archived_at timestamptz;

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
                             'provisioned_at', 'reset_code', 'mail', 'archived_at') then
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
                                   else d.provisioned_at end,
            archived_at     = case when v_c ? 'archived_at'
                                   then (v_c->>'archived_at')::timestamptz
                                   else d.archived_at end
        where d.id = (v_c->>'id')::uuid;
        if found then
            v_count := v_count + 1;
        end if;
    end loop;
    return v_count;
end;
$$;
