-- IN-BASE 025: Lås skærmlåsen op fra IN-BASE (Telefoner → Handling → Lås skærmlåsen op…)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 024.
--
-- Har en bruger ændret og glemt mønsteret, beder IN-BASE telefonen om at sætte en
-- midlertidig PIN (skærmlåskoden fra IN-BASE). Det går over samme tjek som Find telefon
-- (024): telefonen ser anmodningen, når nogen tegner et forkert mønster, når den sættes i
-- laderen/pc'en, eller én gang i timen.
--
--   unlock_requested_at  sat af IN-BASE, nulstilles, når telefonen svarer
--   unlock_ready         telefonens nulstillingsnøgle er aktiv (Android aktiverer den ved
--                        første oplåsning efter opdateringen) – skrives kun, når den ændres
--   unlock_result        seneste svar: {ok, fejl, modtaget}
--
-- inbase_mdm_phone_checkin får p_report (valgfri), så telefoner med styrings-app 7.0, der
-- kalder uden den, virker uændret. inbase_mdm_update_devices er som i 024, plus
-- unlock_requested_at (null = annuller).

alter table public.mdm_devices
    add column if not exists unlock_requested_at timestamptz,
    add column if not exists unlock_ready        boolean not null default false,
    add column if not exists unlock_result       jsonb;

-- ---------- Telefonens tjek (som 024 + p_report) ---------------------------
drop function if exists public.inbase_mdm_phone_checkin(text, text, jsonb);

create or replace function public.inbase_mdm_phone_checkin(p_name text, p_key text,
                                                            p_location jsonb default null,
                                                            p_report jsonb default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_d    public.mdm_devices%rowtype;
    v_l    jsonb := p_location;
    v_r    jsonb := coalesce(p_report, '{}'::jsonb);
    v_svar jsonb;
begin
    select * into v_d from public.mdm_devices
    where name = upper(trim(coalesce(p_name, ''))) and archived_at is null and reset_code <> '';
    if not found or coalesce(p_key, '') <> encode(sha256(convert_to('sporing:' || v_d.reset_code,
                                                                    'UTF8')), 'hex') then
        return jsonb_build_object('find', false, 'laas_op', false);
    end if;
    if jsonb_typeof(v_r->'laas_op_klar') = 'boolean'
       and (v_r->>'laas_op_klar')::boolean <> v_d.unlock_ready then
        update public.mdm_devices set unlock_ready = (v_r->>'laas_op_klar')::boolean
        where id = v_d.id;
    end if;
    if jsonb_typeof(v_r->'laas_op') = 'object' then
        update public.mdm_devices set
            unlock_result = jsonb_strip_nulls(jsonb_build_object(
                'ok', coalesce((v_r->'laas_op'->>'ok')::boolean, false),
                'fejl', left(v_r->'laas_op'->>'fejl', 200),
                'modtaget', now())),
            unlock_requested_at = null, last_checkin_at = now()
        where id = v_d.id;
        v_d.unlock_requested_at := null;
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
        v_d.locate_requested_at := null;
    elsif v_d.last_checkin_at is null or v_d.last_checkin_at < now() - interval '1 hour' then
        update public.mdm_devices set last_checkin_at = now() where id = v_d.id;
    end if;
    return jsonb_build_object('find', v_d.locate_requested_at is not null,
                              'laas_op', v_d.unlock_requested_at is not null);
end;
$$;
revoke execute on function public.inbase_mdm_phone_checkin(text, text, jsonb, jsonb) from public;
grant execute on function public.inbase_mdm_phone_checkin(text, text, jsonb, jsonb)
    to anon, authenticated;

-- ---------- Ændringer fra IN-BASE (som 024 + unlock_requested_at) ----------
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
                             'locate_requested_at', 'unlock_requested_at') then
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
                                       else d.locate_requested_at end,
            unlock_requested_at = case when v_c ? 'unlock_requested_at'
                                       then (v_c->>'unlock_requested_at')::timestamptz
                                       else d.unlock_requested_at end
        where d.id = (v_c->>'id')::uuid;
        if found then
            v_count := v_count + 1;
        end if;
    end loop;
    return v_count;
end;
$$;

insert into public.schema_migrations (version, name) values (25, '025_mdm_laas_op')
on conflict (version) do nothing;
