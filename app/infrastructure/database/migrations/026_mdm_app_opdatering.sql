-- IN-BASE 026: Automatisk opdatering af styrings-appen på telefonerne
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 025.
--
-- Telefoner → Opdater telefoner → "Udgiv til alle telefoner" lægger den nye styrings-app
-- her. Telefonerne (styrings-app 8.0+) ser versionen ved deres tjek (024/025), henter appen
-- og installerer den selv – uden kode, Wi-Fi eller pc i nærheden. Android installerer kun en
-- app, der er signeret med samme nøgle (migrering 012), og telefonen tjekker kontrolsummen.
--
--   mdm_app_release  én række: den udgivne version (overskrives ved næste udgivelse)
--   mdm_devices.app_version  telefonens version, meldt ved tjekket (skrives kun ved ændring)
--
-- Appen hentes gennem inbase_mdm_phone_app med telefonens nøgle, så den ikke ligger offentligt.
-- Trafik: ca. 2 MB pr. telefon pr. udgivelse.

create table if not exists public.mdm_app_release (
    id                   integer primary key default 1 check (id = 1),
    version_code         integer not null check (version_code > 0),
    version_name         text not null check (length(version_name) between 1 and 20),
    sha256               text not null,
    size_bytes           integer not null,
    apk                  bytea not null,
    published_at         timestamptz not null default now(),
    published_by_username text not null default ''
);
revoke all on public.mdm_app_release from anon, authenticated, public;
grant all on public.mdm_app_release to service_role;
alter table public.mdm_app_release enable row level security;

alter table public.mdm_devices
    add column if not exists app_version text not null default '' check (length(app_version) <= 20);

-- ---------- Udgiv (IN-BASE) --------------------------------------------------
create or replace function public.inbase_mdm_publish_app(p_version_code integer,
                                                          p_version_name text, p_apk text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_apk bytea;
    v_nu  integer;
begin
    if not public.inbase_has_module('telefoner') then
        raise exception 'Du har ikke adgang til Telefoner.' using errcode = 'IB403';
    end if;
    v_apk := decode(coalesce(p_apk, ''), 'base64');
    if length(v_apk) < 4 or substring(v_apk from 1 for 4) <> '\x504b0304'::bytea then
        raise exception 'Filen er ikke en Android-app (APK).' using errcode = 'IB422';
    end if;
    if length(v_apk) > 30 * 1024 * 1024 then
        raise exception 'Styrings-appen er for stor (højst 30 MB).' using errcode = 'IB422';
    end if;
    select version_code into v_nu from public.mdm_app_release where id = 1;
    if v_nu is not null and p_version_code <= v_nu then
        raise exception 'Version % er allerede udgivet. Byg en nyere version (højere versionCode).',
            v_nu using errcode = 'IB422';
    end if;
    insert into public.mdm_app_release (id, version_code, version_name, sha256, size_bytes, apk,
                                        published_at, published_by_username)
    values (1, p_version_code, trim(p_version_name), encode(sha256(v_apk), 'hex'), length(v_apk),
            v_apk, now(), public.inbase_current_username())
    on conflict (id) do update set
        version_code = excluded.version_code, version_name = excluded.version_name,
        sha256 = excluded.sha256, size_bytes = excluded.size_bytes, apk = excluded.apk,
        published_at = excluded.published_at,
        published_by_username = excluded.published_by_username;
    return public.inbase_mdm_app_info();
end;
$$;
revoke execute on function public.inbase_mdm_publish_app(integer, text, text) from public, anon;
grant execute on function public.inbase_mdm_publish_app(integer, text, text) to authenticated;

-- Den udgivne version uden selve filen ({} = intet udgivet).
create or replace function public.inbase_mdm_app_info()
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
    if not public.inbase_has_module('telefoner') then
        raise exception 'Du har ikke adgang til Telefoner.' using errcode = 'IB403';
    end if;
    return coalesce((select jsonb_build_object(
                        'version_code', version_code, 'version_name', version_name,
                        'sha256', sha256, 'size_bytes', size_bytes,
                        'published_at', published_at, 'published_by', published_by_username)
                     from public.mdm_app_release where id = 1), '{}'::jsonb);
end;
$$;
revoke execute on function public.inbase_mdm_app_info() from public, anon;
grant execute on function public.inbase_mdm_app_info() to authenticated;

-- ---------- Telefonens nøgletjek (fælles for tjek og hentning) --------------
create or replace function public.inbase_mdm_phone_device(p_name text, p_key text)
returns public.mdm_devices language sql stable security definer set search_path = '' as $$
    select * from public.mdm_devices
    where name = upper(trim(coalesce(p_name, ''))) and archived_at is null and reset_code <> ''
      and coalesce(p_key, '') = encode(sha256(convert_to('sporing:' || reset_code, 'UTF8')), 'hex');
$$;
revoke execute on function public.inbase_mdm_phone_device(text, text) from public, anon, authenticated;

-- ---------- Telefonen henter appen (base64) ---------------------------------
create or replace function public.inbase_mdm_phone_app(p_name text, p_key text)
returns text language plpgsql stable security definer set search_path = '' as $$
begin
    if (public.inbase_mdm_phone_device(p_name, p_key)).id is null then
        return null;
    end if;
    -- encode() ombryder hver 76. tegn – uden linjeskift er den lettere at afkode på telefonen.
    return (select replace(encode(apk, 'base64'), E'\n', '') from public.mdm_app_release
            where id = 1);
end;
$$;
revoke execute on function public.inbase_mdm_phone_app(text, text) from public;
grant execute on function public.inbase_mdm_phone_app(text, text) to anon, authenticated;

-- ---------- Telefonens tjek (som 025 + version og app) ----------------------
create or replace function public.inbase_mdm_phone_checkin(p_name text, p_key text,
                                                            p_location jsonb default null,
                                                            p_report jsonb default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_d    public.mdm_devices%rowtype;
    v_l    jsonb := p_location;
    v_r    jsonb := coalesce(p_report, '{}'::jsonb);
    v_svar jsonb;
    v_app  jsonb;
begin
    v_d := public.inbase_mdm_phone_device(p_name, p_key);
    if v_d.id is null then
        return jsonb_build_object('find', false, 'laas_op', false);
    end if;
    if jsonb_typeof(v_r->'laas_op_klar') = 'boolean'
       and (v_r->>'laas_op_klar')::boolean <> v_d.unlock_ready then
        update public.mdm_devices set unlock_ready = (v_r->>'laas_op_klar')::boolean
        where id = v_d.id;
    end if;
    if jsonb_typeof(v_r->'version') = 'string' and left(v_r->>'version', 20) <> v_d.app_version then
        update public.mdm_devices set app_version = left(v_r->>'version', 20) where id = v_d.id;
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
    select jsonb_build_object('version_code', version_code, 'sha256', sha256) into v_app
    from public.mdm_app_release where id = 1;
    return jsonb_strip_nulls(jsonb_build_object(
        'find', v_d.locate_requested_at is not null,
        'laas_op', v_d.unlock_requested_at is not null,
        'app', v_app));
end;
$$;

insert into public.schema_migrations (version, name) values (26, '026_mdm_app_opdatering')
on conflict (version) do nothing;
