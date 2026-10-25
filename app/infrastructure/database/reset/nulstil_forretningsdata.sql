-- IN-BASE: ENGANGSPROCEDURE – tøm alle IN-BASE-forretningsdata i Supabase.
--
-- ⚠ Sletter ALLE sager, personer, ansættelser, opgaver, rykkere, tidslinjer,
--   skabeloner, indstillinger, områder og indmeldinger i Ønsker & Udvikling
--   (med kommentarer og historik). Kan ikke fortrydes (kun via
--   Supabase-backup). Programmet kører ALDRIG denne fil – den køres manuelt af
--   projektets ejer i Supabase Dashboard → SQL Editor.
--
-- Rører IKKE: skemaet (tabeller, funktioner, politikker), positions (faste
-- stillinger), user_profiles og auth.users (brugere – se docs/SUPABASE_OPSAETNING.md),
-- andre skemaer eller uvedkommende tabeller.
--
-- Brug (alt i ÉN kørsel i SQL Editor):
--   1. Tag evt. en backup (Database → Backups).
--   2. Fjern "--" foran set-linjen nedenfor, og kør hele filen.
--   3. Kør derefter 004_seed_standarder.sql, hvis standardskabeloner og
--      -områder skal genetableres.
--   4. Sæt "--" foran set-linjen igen.

-- set inbase.bekraeft_nulstilling = 'JA-SLET-ALLE-INBASE-FORRETNINGSDATA';

begin;

do $$
begin
    if current_setting('inbase.bekraeft_nulstilling', true)
       is distinct from 'JA-SLET-ALLE-INBASE-FORRETNINGSDATA' then
        raise exception 'Nulstilling ikke bekræftet. Læs vejledningen øverst i filen.';
    end if;
end $$;

-- Én truncate af alle tabellerne på én gang håndterer fremmednøglerne
-- (sager -> opgaver/rykkere/tidslinje -> ansættelser -> personer -> skabeloner).
truncate table
    public.audit_events,
    public.case_reminders,
    public.case_tasks,
    public.lifecycle_cases,
    public.employment_records,
    public.people,
    public.workflow_template_versions,
    public.workflow_template_tasks,
    public.workflow_templates,
    public.message_templates,
    public.notification_rules,
    public.app_settings,
    public.areas;

-- Rester fra forbindelsestesten (test_supabase_connection.py), hvis tabellen findes.
do $$
begin
    if to_regclass('public.integration_probe') is not null then
        execute 'truncate table public.integration_probe';
    end if;
end $$;

-- Ønsker & Udvikling (migrering 006), hvis den er kørt. Løbenumrene starter forfra.
do $$
begin
    if to_regclass('public.development_requests') is not null then
        execute 'truncate table public.development_request_events, public.development_request_comments, public.development_requests restart identity';
    end if;
end $$;

commit;

-- Kontrol: alle tal skal være 0 (positions = 4 faste stillinger).
select 'lifecycle_cases' as tabel, count(*) from public.lifecycle_cases
union all select 'case_tasks', count(*) from public.case_tasks
union all select 'case_reminders', count(*) from public.case_reminders
union all select 'audit_events', count(*) from public.audit_events
union all select 'people', count(*) from public.people
union all select 'employment_records', count(*) from public.employment_records
union all select 'workflow_templates', count(*) from public.workflow_templates
union all select 'message_templates', count(*) from public.message_templates
union all select 'notification_rules', count(*) from public.notification_rules
union all select 'app_settings', count(*) from public.app_settings
union all select 'areas', count(*) from public.areas
union all select 'positions (forventet 4)', count(*) from public.positions
union all select 'user_profiles (røres ikke)', count(*) from public.user_profiles;
