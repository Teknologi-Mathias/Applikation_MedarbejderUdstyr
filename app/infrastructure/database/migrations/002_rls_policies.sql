-- IN-BASE 002: privilegier og Row Level Security
--
-- Desktopklienten bruger kun den offentlige publishable/anon-nøgle + brugerens
-- login (Supabase Auth). AL adgangskontrol håndhæves her i databasen – skjulte
-- knapper i programmet er ikke sikkerhed.
--
-- Hvem er hvem?
--   anon           (ikke logget ind)          : ingen adgang til noget.
--   authenticated  UDEN user_profiles-række    : ingen adgang (fx selvregistrerede).
--   Medlem         (har profil, rolle Bruger)  : læser alle fælles data; skriver
--                                                sager KUN via inbase_save_case().
--   Administrator  (profil med rolle Administrator): derudover indstillinger,
--                                                skabeloner og permanent sletning.
--   service_role   (kun Edge Functions)         : opretter/sletter konti og profiler.
--
-- IN-BASE er et fælles virksomhedssystem: sager, opgaver og skabeloner er
-- IKKE begrænset til "egne rækker" (ingen user_id = auth.uid() på sagsdata).
-- Personlige data er kun brugerprofilen (tema, notifikationer).

-- ---------- Hjælpefunktioner (bruges i politikker og RPC'er) ---------------

create or replace function public.inbase_is_member() returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.user_profiles where id = auth.uid());
$$;

create or replace function public.inbase_is_admin() returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from public.user_profiles where id = auth.uid() and role = 'Administrator'
    );
$$;

create or replace function public.inbase_current_username() returns text
language sql stable security definer set search_path = '' as $$
    select username from public.user_profiles where id = auth.uid();
$$;

-- ---------- Privilegier ----------------------------------------------------
-- Supabase giver som standard anon/authenticated alle rettigheder på nye
-- tabeller. Dem fjerner vi og giver kun det nødvendige tilbage.

do $$
declare t text;
begin
    foreach t in array array[
        'areas', 'positions', 'app_settings', 'user_profiles', 'people',
        'employment_records', 'workflow_templates', 'workflow_template_versions',
        'workflow_template_tasks', 'message_templates', 'notification_rules',
        'lifecycle_cases', 'case_tasks', 'case_reminders', 'audit_events']
    loop
        execute format('revoke all on public.%I from anon, authenticated, public', t);
        execute format('grant select on public.%I to authenticated', t);
        execute format('grant all on public.%I to service_role', t);
        execute format('alter table public.%I enable row level security', t);
    end loop;
end $$;

-- Opsætning, som administratorer ændrer direkte (RLS nedenfor begrænser til admin).
grant insert, update on public.areas             to authenticated;
grant insert, update on public.app_settings      to authenticated;
grant insert, update on public.message_templates to authenticated;
grant insert, update on public.notification_rules to authenticated;

-- Egen profil: KUN tema og notifikationer. Rolle, brugernavn, e-mail og
-- must_change_password kan ikke ændres af klienten (kolonne-privilegier).
grant update (theme, windows_notifications) on public.user_profiles to authenticated;

-- Sager, opgaver, rykkere, personer, ansættelser, tidslinje og
-- arbejdsgangsskabeloner: ingen direkte skrivning. Kun via RPC (003), så
-- versionskontrol, atomisk lagring og insert-only tidslinje håndhæves.

-- Funktioner er som standard eksekverbare for PUBLIC – det fjernes.
revoke execute on function public.inbase_is_member()        from public, anon;
revoke execute on function public.inbase_is_admin()         from public, anon;
revoke execute on function public.inbase_current_username() from public, anon;
grant  execute on function public.inbase_is_member()        to authenticated;
grant  execute on function public.inbase_is_admin()         to authenticated;
grant  execute on function public.inbase_current_username() to authenticated;
revoke execute on function public.inbase_bump_version()     from public, anon, authenticated;
revoke execute on function public.inbase_touch_updated_at() from public, anon, authenticated;

-- ---------- Politikker: læsning for medlemmer ------------------------------

do $$
declare t text;
begin
    foreach t in array array[
        'areas', 'positions', 'app_settings', 'people', 'employment_records',
        'workflow_templates', 'workflow_template_versions', 'workflow_template_tasks',
        'message_templates', 'notification_rules', 'lifecycle_cases', 'case_tasks',
        'case_reminders', 'audit_events']
    loop
        execute format('create policy %I on public.%I for select to authenticated '
                       'using ((select public.inbase_is_member()))', t || '_select', t);
    end loop;
end $$;

-- ---------- Politikker: administratorer skriver opsætning -------------------

do $$
declare t text;
begin
    foreach t in array array['areas', 'app_settings', 'message_templates', 'notification_rules']
    loop
        execute format('create policy %I on public.%I for insert to authenticated '
                       'with check ((select public.inbase_is_admin()))', t || '_admin_insert', t);
        execute format('create policy %I on public.%I for update to authenticated '
                       'using ((select public.inbase_is_admin())) '
                       'with check ((select public.inbase_is_admin()))', t || '_admin_update', t);
    end loop;
end $$;

-- ---------- Brugerprofiler -------------------------------------------------
-- Læs: egen profil; administratorer alle. Andre brugeres navne til
-- "Ansvarlig"-listen hentes via inbase_user_directory() (kun navn + brugernavn).

create policy user_profiles_select on public.user_profiles for select to authenticated
    using (id = (select auth.uid()) or (select public.inbase_is_admin()));
create policy user_profiles_update_own on public.user_profiles for update to authenticated
    using (id = (select auth.uid())) with check (id = (select auth.uid()));
-- Ingen insert/delete-politik: profiler oprettes og slettes kun af service_role.

-- ---------- Beskyttelse af administratorrollen ------------------------------
-- Der skal altid være mindst én administrator – også ved sletning af en konto
-- (auth.users → cascade → user_profiles) og ved rolleskift.

create or replace function public.inbase_keep_one_admin() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if old.role = 'Administrator'
       and (tg_op = 'DELETE' or new.role <> 'Administrator')
       and not exists (select 1 from public.user_profiles
                       where role = 'Administrator' and id <> old.id) then
        raise exception 'Der skal altid være mindst én administrator.'
            using errcode = 'IB422';
    end if;
    return coalesce(new, old);
end;
$$;
revoke execute on function public.inbase_keep_one_admin() from public, anon, authenticated;

create trigger user_profiles_keep_one_admin
    before update of role or delete on public.user_profiles
    for each row execute function public.inbase_keep_one_admin();
