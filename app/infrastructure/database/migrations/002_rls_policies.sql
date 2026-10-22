-- IN-BASE: Row Level Security
--
-- Desktopklienten bruger kun den offentlige anon-nøgle + brugerens login
-- (Supabase Auth). Al adgangskontrol sker her i databasen.
--
-- Roller (user_profiles.role):
--   Administrator: alt, inkl. skabeloner, brugere og permanent sletning.
--   Bruger:        læse/skrive sager, opgaver og rykkere; læse opsætning.
-- audit_events kan kun indsættes og læses – aldrig ændres eller slettes.
--
-- BEMÆRK: Ændring af egen rolle forhindres af user_profiles_update_own
-- (WITH CHECK sammenligner med den gemte rolle). Gennemgå politikkerne med
-- MASAN, før databasen tages i brug.

create or replace function inbase_is_admin() returns boolean
language sql stable security definer set search_path = public as $$
    select exists (
        select 1 from user_profiles where id = auth.uid() and role = 'Administrator'
    );
$$;

-- Slå RLS til på alle tabeller.
alter table areas                      enable row level security;
alter table positions                  enable row level security;
alter table user_profiles              enable row level security;
alter table people                     enable row level security;
alter table employment_records         enable row level security;
alter table workflow_templates         enable row level security;
alter table workflow_template_versions enable row level security;
alter table workflow_template_tasks    enable row level security;
alter table message_templates          enable row level security;
alter table notification_rules         enable row level security;
alter table lifecycle_cases            enable row level security;
alter table case_tasks                 enable row level security;
alter table case_reminders             enable row level security;
alter table audit_events               enable row level security;

-- ---------- Opsætning: alle læser, administratorer skriver ---------------

do $$
declare t text;
begin
    foreach t in array array['areas', 'positions', 'workflow_templates',
                             'workflow_template_versions', 'workflow_template_tasks',
                             'message_templates', 'notification_rules']
    loop
        execute format('create policy %I on %I for select to authenticated using (true)',
                       t || '_select', t);
        execute format('create policy %I on %I for all to authenticated '
                       'using (inbase_is_admin()) with check (inbase_is_admin())',
                       t || '_admin_write', t);
    end loop;
end $$;

-- ---------- Brugerprofiler -------------------------------------------------

create policy user_profiles_select on user_profiles for select to authenticated
    using (id = auth.uid() or inbase_is_admin());
create policy user_profiles_update_own on user_profiles for update to authenticated
    using (id = auth.uid())
    with check (id = auth.uid()
                and role = (select p.role from user_profiles p where p.id = auth.uid()));
create policy user_profiles_admin on user_profiles for all to authenticated
    using (inbase_is_admin()) with check (inbase_is_admin());

-- ---------- Sagsdata: alle brugere arbejder, kun administratorer sletter --

do $$
declare t text;
begin
    foreach t in array array['people', 'employment_records', 'lifecycle_cases',
                             'case_tasks', 'case_reminders']
    loop
        execute format('create policy %I on %I for select to authenticated using (true)',
                       t || '_select', t);
        execute format('create policy %I on %I for insert to authenticated with check (true)',
                       t || '_insert', t);
        execute format('create policy %I on %I for update to authenticated '
                       'using (true) with check (true)', t || '_update', t);
        execute format('create policy %I on %I for delete to authenticated '
                       'using (inbase_is_admin())', t || '_delete', t);
    end loop;
end $$;

-- ---------- Tidslinje: insert-only ------------------------------------------

create policy audit_events_select on audit_events for select to authenticated using (true);
create policy audit_events_insert on audit_events for insert to authenticated
    with check (actor = (select username from user_profiles where id = auth.uid()));
-- Ingen update- eller delete-politik: hændelser kan ikke ændres eller slettes.
