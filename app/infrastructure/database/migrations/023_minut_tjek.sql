-- IN-BASE 023: Minut-tjekket i ét kald (mindre Supabase-trafik)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 022.
--
-- Hovedvinduet tjekker hvert minut for ændringer. Før lavede det ca. 9 kald
-- (profil, indstillinger, områder, to sagssignaturer, alle skabeloner, kalender).
-- inbase_tick() samler profilen og signaturerne i ét lille svar; klienten henter
-- kun det, hvis signatur har ændret sig.
--
-- security invoker: RLS gælder, så signaturerne kun dækker det, brugeren ser
-- (som inbase_case_signature fra 019). Kalendersignaturen kontrollerer selv adgangen.

create or replace function public.inbase_tick()
returns jsonb language sql stable security invoker set search_path = '' as $$
    select jsonb_build_object(
        'profile', (select to_jsonb(p) from public.user_profiles p where p.id = auth.uid()),
        'cases', jsonb_build_object(
            'onboarding', public.inbase_case_signature('onboarding'),
            'offboarding', public.inbase_case_signature('offboarding')),
        'calendar', public.inbase_calendar_signature(),
        -- Indstillinger, områder og brugere (Indstillinger-siden viser dem alle).
        'settings', jsonb_build_array(
            (select count(*) from public.app_settings),
            (select max(updated_at) from public.app_settings),
            (select md5(coalesce(string_agg(name || ':' || sort_order || ':' || active, ','
                                            order by name), ''))
             from public.areas),
            (select count(*) from public.user_profiles),
            (select max(updated_at) from public.user_profiles)),
        'templates', jsonb_build_array(
            (select count(*) from public.workflow_templates),
            (select max(updated_at) from public.workflow_templates),
            (select count(*) from public.message_templates),
            (select max(updated_at) from public.message_templates),
            (select count(*) from public.notification_rules),
            (select max(updated_at) from public.notification_rules)));
$$;
revoke execute on function public.inbase_tick() from public, anon;
grant execute on function public.inbase_tick() to authenticated;

insert into public.schema_migrations (version, name) values (23, '023_minut_tjek')
on conflict (version) do nothing;
