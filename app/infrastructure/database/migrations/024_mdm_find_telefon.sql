-- IN-BASE 024: Find telefon (Telefoner → Handling → Find telefon…)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 023.
--
-- Telefonen kan ikke kaldes udefra (mobilnettets fælles IP-adresse, ingen
-- Google-push), så den spørger selv: når skærmen tændes, når den kommer på nettet
-- og én gang i timen. Er der bedt om dens position, sender den én position.
--
--   locate_requested_at  sat af IN-BASE (Find telefon), nulstilles, når telefonen svarer
--   last_checkin_at      senest set (opdateres højst én gang i timen – minimal skrivning)
--   location             seneste svar: {lat, lng, noejagtighed, tid, batteri} eller {fejl, tid}
--                        – overskrives hver gang, ingen historik
--
-- Telefonen logger ikke ind. Den kalder inbase_mdm_phone_checkin som anon med sit
-- enhedsnavn og nøglen sha256('sporing:' || nulstillingskode) i hex – nulstillingskoden
-- har telefonen og tabellen allerede (009). Forkert navn eller nøgle giver samme svar
-- som "intet at gøre", så funktionen afslører ingenting.
--
-- inbase_mdm_update_devices er som i 013, plus feltet locate_requested_at (null = annuller).

alter table public.mdm_devices
    add column if not exists locate_requested_at timestamptz,
    add column if not exists last_checkin_at     timestamptz,
    add column if not exists location            jsonb;

-- ---------- Telefonens tjek ------------------------------------------------
create or replace function public.inbase_mdm_phone_checkin(p_name text, p_key text,
                                                            p_location jsonb default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_d    public.mdm_devices%rowtype;
    v_l    jsonb := p_location;
    v_svar jsonb;
begin
    select * into v_d from public.mdm_devices
    where name = upper(trim(coalesce(p_name, ''))) and archived_at is null and reset_code <> '';
    if not found or coalesce(p_key, '') <> encode(sha256(convert_to('sporing:' || v_d.reset_code,
                                                                    'UTF8')), 'hex') then
        return jsonb_build_object('find', false);
    end if;
    if jsonb_typeof(v_l) = 'object' then
        -- Kun de kendte felter gemmes, og teksterne afkortes.
        v_svar := jsonb_strip_nulls(jsonb_build_object(
            'lat', (v_l->>'lat')::double precision,
            'lng', (v_l->>'lng')::double precision,
            'noejagtighed', round((v_l->>'noejagtighed')::numeric),
            'batteri', round((v_l->>'batteri')::numeric),
            'tid', left(v_l->>'tid', 40),
            'fejl', left(v_l->>'fejl', 200),
            'modtaget', now()));
        update public.mdm_devices set location = v_svar, locate_requested_at = null,
                                      last_checkin_at = now()
        where id = v_d.id;
        return jsonb_build_object('find', false);
    end if;
    if v_d.last_checkin_at is null or v_d.last_checkin_at < now() - interval '1 hour' then
        update public.mdm_devices set last_checkin_at = now() where id = v_d.id;
    end if;
    return jsonb_build_object('find', v_d.locate_requested_at is not null);
end;
$$;
revoke execute on function public.inbase_mdm_phone_checkin(text, text, jsonb) from public;
grant execute on function public.inbase_mdm_phone_checkin(text, text, jsonb) to anon, authenticated;

-- ---------- Ændringer fra IN-BASE (som 013 + locate_requested_at) ----------
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
                             'provisioned_at', 'reset_code', 'mail', 'archived_at',
                             'locate_requested_at') then
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
                                   else d.archived_at end,
            locate_requested_at = case when v_c ? 'locate_requested_at'
                                       then (v_c->>'locate_requested_at')::timestamptz
                                       else d.locate_requested_at end
        where d.id = (v_c->>'id')::uuid;
        if found then
            v_count := v_count + 1;
        end if;
    end loop;
    return v_count;
end;
$$;

insert into public.schema_migrations (version, name) values (24, '024_mdm_find_telefon')
on conflict (version) do nothing;
