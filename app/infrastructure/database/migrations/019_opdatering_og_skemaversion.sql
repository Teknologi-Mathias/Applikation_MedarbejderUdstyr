-- IN-BASE 019: Skemaversion, central opdatering af klienterne og delt signatur
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 018. Kan køres igen.
-- Kun tilføjelser: ingen sager, opgaver eller brugere ændres.
--
-- 1. schema_migrations: hvilke migreringer der er kørt. Klienten kræver en
--    bestemt version (KRAEVET_SKEMA i app/__init__.py) og stopper med en klar
--    besked, hvis databasen er ældre – ellers ville nye felter forsvinde lydløst
--    (inbase_columns i 003 gemmer kun kolonner, der findes).
--    FREMOVER: hver ny migrering slutter med en insert i schema_migrations.
--    Første kørsel registrerer 001–019 som kørt – kør derfor 001–018 først.
-- 2. inbase_client_requirements(): skemaversion og mindste tilladte klientversion
--    (app_settings 'min_klient_version'). Kan kaldes FØR log på.
-- 3. inbase_case_signature(): antal + seneste ændring for aktive og arkiverede
--    sager hver for sig, så klienten kun genindlæser den halvdel, der er ændret.
-- 4. app_releases + Storage-bucket 'releases': udgivne versioner (installeren).
--    Udgives med tools/udgiv_version.py. Medlemmer læser; kun administratorer skriver.
-- 5. user_profiles: opdateringskanal (stabil/pilot, sættes af administratorer)
--    og den klientversion, brugeren sidst kørte.

-- ---------- 1. Skemaversion ---------------------------------------------------

create table if not exists public.schema_migrations (
    version     integer primary key check (version > 0),
    name        text not null default '',
    applied_at  timestamptz not null default now()
);
revoke all on public.schema_migrations from anon, authenticated, public;
grant select on public.schema_migrations to authenticated;
grant all on public.schema_migrations to service_role;
alter table public.schema_migrations enable row level security;
drop policy if exists schema_migrations_select on public.schema_migrations;
create policy schema_migrations_select on public.schema_migrations for select to authenticated
    using ((select public.inbase_is_member()));

insert into public.schema_migrations (version, name) values
    (1, '001_initial_schema'), (2, '002_rls_policies'), (3, '003_rpc_functions'),
    (4, '004_seed_standarder'), (5, '005_brugernavn_login'), (6, '006_oensker_udvikling'),
    (7, '007_mdm_enheder'), (8, '008_mdm_lokal_klargoering'), (9, '009_mdm_nulstillingskode'),
    (10, '010_moduladgang'), (11, '011_aaben_opsaetning'), (12, '012_mdm_mail_og_signering'),
    (13, '013_mdm_arkiv'), (14, '014_arbejdsspor'), (15, '015_seed_standarder'),
    (16, '016_udstyrsprofiler'), (17, '017_loennr_foer_kontrakt'),
    (18, '018_enkelt_onboardingflow'), (19, '019_opdatering_og_skemaversion')
on conflict (version) do nothing;

-- ---------- 2. Krav til klienten (også før log på) ----------------------------

create or replace function public.inbase_client_requirements()
returns jsonb language sql stable security definer set search_path = '' as $$
    select jsonb_build_object(
        'schema_version', coalesce((select max(version) from public.schema_migrations), 0),
        'min_client_version', coalesce(
            (select value #>> '{}' from public.app_settings where key = 'min_klient_version'),
            '0.0.0'));
$$;
revoke execute on function public.inbase_client_requirements() from public;
grant execute on function public.inbase_client_requirements() to anon, authenticated;

-- ---------- 3. Delt signatur (aktive / arkiv) ----------------------------------
-- security invoker: RLS gælder, så signaturen kun dækker de sager, brugeren ser.

create or replace function public.inbase_case_signature(p_process text)
returns jsonb language sql stable security invoker set search_path = '' as $$
    select jsonb_build_object(
        'aktive', jsonb_build_array(count(*) filter (where archived_on is null),
                                    max(updated_at) filter (where archived_on is null)),
        'arkiv', jsonb_build_array(count(*) filter (where archived_on is not null),
                                   max(updated_at) filter (where archived_on is not null)))
    from public.lifecycle_cases where process = p_process;
$$;
revoke execute on function public.inbase_case_signature(text) from public, anon;
grant execute on function public.inbase_case_signature(text) to authenticated;

-- ---------- 5. Opdateringskanal og klientversion pr. bruger --------------------

alter table public.user_profiles
    add column if not exists update_channel text not null default 'stabil'
        check (update_channel in ('stabil', 'pilot')),
    add column if not exists client_version text not null default '',
    add column if not exists client_seen_at timestamptz;

create or replace function public.inbase_update_channel() returns text
language sql stable security definer set search_path = '' as $$
    select update_channel from public.user_profiles where id = auth.uid() and active;
$$;
revoke execute on function public.inbase_update_channel() from public, anon;
grant execute on function public.inbase_update_channel() to authenticated;

-- Kun administratorer sætter kanalen (brugere kan stadig kun ændre tema og
-- notifikationer på egen profil, 002).
create or replace function public.inbase_set_update_channel(p_user_id uuid, p_channel text)
returns void language plpgsql security definer set search_path = '' as $$
begin
    if not public.inbase_is_admin() then
        raise exception 'Kun administratorer kan ændre opdateringskanal.' using errcode = 'IB403';
    end if;
    if p_channel is null or p_channel not in ('stabil', 'pilot') then
        raise exception 'Ukendt opdateringskanal.' using errcode = 'IB422';
    end if;
    update public.user_profiles set update_channel = p_channel where id = p_user_id;
    if not found then
        raise exception 'Brugeren findes ikke længere.' using errcode = 'IB409';
    end if;
end;
$$;
revoke execute on function public.inbase_set_update_channel(uuid, text) from public, anon;
grant execute on function public.inbase_set_update_channel(uuid, text) to authenticated;

-- Klienten melder sin version efter log på (Indstillinger → Brugere viser den).
create or replace function public.inbase_report_client(p_version text)
returns void language plpgsql security definer set search_path = '' as $$
begin
    if p_version is null or p_version !~ '^\d+\.\d+\.\d+$' then
        raise exception 'Ugyldigt versionsnummer.' using errcode = 'IB422';
    end if;
    update public.user_profiles set client_version = p_version, client_seen_at = now()
    where id = auth.uid() and active;
end;
$$;
revoke execute on function public.inbase_report_client(text) from public, anon;
grant execute on function public.inbase_report_client(text) to authenticated;

-- ---------- 4. Udgivne versioner -----------------------------------------------
-- channel: 'pilot' ses kun af brugere med opdateringskanal pilot; 'stabil' af alle.
-- rollout_percent: andel af stabil-brugerne, der får versionen (beregnes i klienten).
-- withdrawn: trukket tilbage – installeres ikke, og klienter på versionen går
-- tilbage til den nyeste gyldige (app/domain/opdatering.py).

create table if not exists public.app_releases (
    version          text primary key check (version ~ '^\d+\.\d+\.\d+$'),
    channel          text not null default 'pilot' check (channel in ('pilot', 'stabil')),
    storage_path     text not null check (length(trim(storage_path)) > 0),
    sha256           text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes       bigint not null check (size_bytes > 0),
    min_schema       integer not null default 0,
    mandatory        boolean not null default false,
    notes            text not null default '',
    rollout_percent  integer not null default 100 check (rollout_percent between 0 and 100),
    withdrawn        boolean not null default false,
    commit_hash      text not null default '',
    created_at       timestamptz not null default now(),
    created_by       text not null default ''
);
revoke all on public.app_releases from anon, authenticated, public;
grant select, insert, update, delete on public.app_releases to authenticated;
grant all on public.app_releases to service_role;
alter table public.app_releases enable row level security;

drop policy if exists app_releases_select on public.app_releases;
drop policy if exists app_releases_admin_insert on public.app_releases;
drop policy if exists app_releases_admin_update on public.app_releases;
drop policy if exists app_releases_admin_delete on public.app_releases;
create policy app_releases_select on public.app_releases for select to authenticated
    using ((select public.inbase_is_admin())
           or ((select public.inbase_is_member())
               and (channel = 'stabil' or (select public.inbase_update_channel()) = 'pilot')));
create policy app_releases_admin_insert on public.app_releases for insert to authenticated
    with check ((select public.inbase_is_admin()));
create policy app_releases_admin_update on public.app_releases for update to authenticated
    using ((select public.inbase_is_admin())) with check ((select public.inbase_is_admin()));
create policy app_releases_admin_delete on public.app_releases for delete to authenticated
    using ((select public.inbase_is_admin()));

-- Installeren ligger i en privat Storage-bucket (højst 50 MB pr. fil på Free).
-- Den lokale testdatabase (tests/sql/supabase_stub.sql) har ingen Storage.
do $$
begin
    if to_regclass('storage.objects') is null then
        raise notice 'Ingen Supabase Storage – bucket "releases" springes over.';
        return;
    end if;
    insert into storage.buckets (id, name, public, file_size_limit)
    values ('releases', 'releases', false, 52428800)
    on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit;

    execute 'drop policy if exists inbase_releases_select on storage.objects';
    execute 'drop policy if exists inbase_releases_insert on storage.objects';
    execute 'drop policy if exists inbase_releases_update on storage.objects';
    execute 'drop policy if exists inbase_releases_delete on storage.objects';
    execute $p$create policy inbase_releases_select on storage.objects for select to authenticated
        using (bucket_id = 'releases' and (select public.inbase_is_member()))$p$;
    execute $p$create policy inbase_releases_insert on storage.objects for insert to authenticated
        with check (bucket_id = 'releases' and (select public.inbase_is_admin()))$p$;
    execute $p$create policy inbase_releases_update on storage.objects for update to authenticated
        using (bucket_id = 'releases' and (select public.inbase_is_admin()))
        with check (bucket_id = 'releases' and (select public.inbase_is_admin()))$p$;
    execute $p$create policy inbase_releases_delete on storage.objects for delete to authenticated
        using (bucket_id = 'releases' and (select public.inbase_is_admin()))$p$;
end $$;
