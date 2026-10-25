-- IN-BASE 005: login med brugernavn og aktive/deaktiverede brugere
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 001-004 (se
-- docs/SUPABASE_OPSAETNING.md). Ændrer ikke forretningsdata.
--
-- Brugere logger på med BRUGERNAVN (fx HAFRA) og adgangskode. Supabase Auth
-- kender kun e-mail/telefon som login, så hver konto har et internt, IKKE-
-- leveringsbart login-alias afledt af brugernavnet:
--
--     HAFRA  ->  hafra@brugere.in-base.invalid
--
-- ".invalid" er et reserveret topdomæne (RFC 2606) – der kan aldrig sendes
-- post dertil. Aliaset vises ikke i IN-BASE og bruges ikke til kommunikation.
-- Adgangskoder kontrolleres stadig udelukkende af Supabase Auth. SAMME regel:
-- app/repositories/supabase/mapping.py (login_alias) og
-- supabase/functions/_shared/admin.ts (loginAlias).
--
-- Ændringer:
-- 1. user_profiles.username er altid normaliseret (uden mellemrum, STORE bogstaver).
-- 2. user_profiles.active: en deaktiveret konto er ikke medlem (ingen adgang
--    til data via RLS), og Edge Function admin-manage-user spærrer den samtidig
--    i Supabase Auth. Der skal altid være mindst én AKTIV administrator.
-- 3. Eksisterende konti flyttes over på login-aliasset (engangsskridt).
-- 4. user_profiles.email fjernes: IN-BASE gemmer ikke brugernes e-mail.
-- 5. Ny engangsprocedure for den første administrator (brugernavn i stedet for e-mail).

-- ---------- Login-alias -----------------------------------------------------

create or replace function public.inbase_login_alias(p_username text)
returns text language sql immutable set search_path = '' as $$
    select lower(trim(p_username)) || '@brugere.in-base.invalid';
$$;
revoke execute on function public.inbase_login_alias(text) from public, anon, authenticated;
grant execute on function public.inbase_login_alias(text) to service_role;

-- ---------- 1. Normaliserede brugernavne -----------------------------------
-- Det unikke indeks på lower(username) (001) gør brugernavne unikke uanset
-- store/små bogstaver; nu gemmes de desuden altid med store bogstaver.

update public.user_profiles set username = upper(trim(username))
where username is distinct from upper(trim(username));

alter table public.user_profiles drop constraint if exists user_profiles_username_check;
alter table public.user_profiles add constraint user_profiles_username_check check (
    username ~ '^[A-Z0-9]([A-Z0-9._-]{0,38}[A-Z0-9])$' and position('..' in username) = 0
);

-- ---------- 2. Aktive og deaktiverede brugere ------------------------------

alter table public.user_profiles add column if not exists active boolean not null default true;
-- Klienten kan stadig kun ændre theme og windows_notifications (002) –
-- active og role ændres kun af Edge Function admin-manage-user (service_role).

create or replace function public.inbase_is_member() returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.user_profiles where id = auth.uid() and active);
$$;

create or replace function public.inbase_is_admin() returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from public.user_profiles
        where id = auth.uid() and role = 'Administrator' and active
    );
$$;

create or replace function public.inbase_current_username() returns text
language sql stable security definer set search_path = '' as $$
    select username from public.user_profiles where id = auth.uid() and active;
$$;

-- Navne til "Ansvarlig"-listen: kun aktive brugere.
create or replace function public.inbase_user_directory()
returns table (username text, display_name text)
language sql stable security definer set search_path = '' as $$
    select p.username, p.display_name from public.user_profiles p
    where public.inbase_is_member() and p.active
    order by lower(p.username);
$$;

-- Mindst én AKTIV administrator – også ved deaktivering, rolleskift og sletning.
create or replace function public.inbase_keep_one_admin() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if old.role = 'Administrator' and old.active
       and (tg_op = 'DELETE' or new.role <> 'Administrator' or not new.active)
       and not exists (select 1 from public.user_profiles
                       where role = 'Administrator' and active and id <> old.id) then
        raise exception 'Der skal altid være mindst én aktiv administrator.'
            using errcode = 'IB422';
    end if;
    return coalesce(new, old);
end;
$$;
revoke execute on function public.inbase_keep_one_admin() from public, anon, authenticated;

drop trigger if exists user_profiles_keep_one_admin on public.user_profiles;
create trigger user_profiles_keep_one_admin
    before update of role, active or delete on public.user_profiles
    for each row execute function public.inbase_keep_one_admin();

-- ---------- 3. Eksisterende konti over på login-aliasset -------------------
-- Konti MED en IN-BASE-profil får login-aliasset som Auth-e-mail, så de kan
-- logge på med brugernavn. Konti uden profil røres ikke. Har SQL Editor ikke
-- rettighed til auth-skemaet, springes skridtet over med en advarsel – se
-- docs/SUPABASE_OPSAETNING.md, "Fra e-mail- til brugernavnslogin".

do $$
begin
    update auth.users u
    set email = public.inbase_login_alias(p.username),
        email_confirmed_at = coalesce(u.email_confirmed_at, now())
    from public.user_profiles p
    where p.id = u.id
      and lower(coalesce(u.email, '')) <> public.inbase_login_alias(p.username);

    update auth.identities i
    set identity_data = i.identity_data
                        || jsonb_build_object('email', public.inbase_login_alias(p.username))
    from public.user_profiles p
    where p.id = i.user_id and i.provider = 'email';
exception when insufficient_privilege then
    raise warning 'Eksisterende konti kunne ikke flyttes til login-aliasset (%). Se docs/SUPABASE_OPSAETNING.md.', sqlerrm;
end $$;

-- ---------- 4. Ingen e-mail i profilen -------------------------------------

alter table public.user_profiles drop column if exists email;

-- ---------- 5. Første administrator (engangsprocedure) ---------------------
-- Køres af projektejeren i SQL Editor (som postgres) – kan IKKE kaldes fra
-- programmet eller API'et. Afvises, hvis der allerede findes en aktiv
-- administrator. Forudsætter en Auth-bruger med login-aliasset som e-mail
-- (Authentication → Users → Add user, "Auto Confirm User" slået til).

drop function if exists public.inbase_bootstrap_first_admin(text, text, text);

create or replace function public.inbase_bootstrap_first_admin(
    p_username text, p_display_name text default '')
returns uuid language plpgsql security definer set search_path = '' as $$
declare
    v_username text := upper(trim(p_username));
    v_alias    text := public.inbase_login_alias(p_username);
    v_uid      uuid;
begin
    if exists (select 1 from public.user_profiles where role = 'Administrator' and active) then
        raise exception 'Der findes allerede en aktiv administrator. Opret nye brugere fra IN-BASE.';
    end if;
    select id into v_uid from auth.users where lower(email) = v_alias;
    if v_uid is null then
        raise exception 'Der findes ingen Auth-bruger med login-aliasset %. Opret den først under Authentication → Users → Add user (e-mail: %, "Auto Confirm User" slået til).',
            v_alias, v_alias;
    end if;
    insert into public.user_profiles (id, username, display_name, role, must_change_password, active)
    values (v_uid, v_username, coalesce(nullif(trim(p_display_name), ''), v_username),
            'Administrator', false, true)
    on conflict (id) do update
        set role = 'Administrator', active = true, username = excluded.username,
            display_name = excluded.display_name;
    return v_uid;
end;
$$;
revoke execute on function public.inbase_bootstrap_first_admin(text, text)
    from public, anon, authenticated, service_role;
