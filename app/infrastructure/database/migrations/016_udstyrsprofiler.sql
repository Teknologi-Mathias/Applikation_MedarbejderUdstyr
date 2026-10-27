-- IN-BASE 016: Standardprofiler for udstyr pr. stilling (onboarding)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 015.
-- Kun tilføjelser: ingen data slettes eller ændres. Kan køres flere gange.
--
-- * app_settings får nøglen 'udstyrsprofiler' (JSON: {stilling: behov uden
--   størrelser}). Valideres i app/domain/behov.py (valider_profiler); her
--   sikres kun, at værdien er et JSON-objekt.
-- * Profilerne hører til Indstillinger → Organisation, som alle medlemmer må
--   ændre (011). Medlemspolitikkerne udvides derfor med den nye nøgle – de
--   øvrige nøgler (backup og slettepolitik) er fortsat kun for administratorer.
-- * Uden denne migrering kan kun administratorer gemme Organisation, fordi
--   programmet også sender profilerne.

insert into public.app_settings (key, value)
values ('udstyrsprofiler', '{}'::jsonb)
on conflict (key) do nothing;

alter table public.app_settings
    drop constraint if exists app_settings_udstyrsprofiler_objekt;
alter table public.app_settings
    add constraint app_settings_udstyrsprofiler_objekt
    check (key <> 'udstyrsprofiler' or jsonb_typeof(value) = 'object');

drop policy if exists app_settings_member_insert on public.app_settings;
drop policy if exists app_settings_member_update on public.app_settings;
create policy app_settings_member_insert on public.app_settings for insert to authenticated
    with check ((select public.inbase_is_member())
                and key in ('ansvarlige', 'stillestaaende_dage', 'naermer_sig_dage',
                            'udstyrsprofiler'));
create policy app_settings_member_update on public.app_settings for update to authenticated
    using ((select public.inbase_is_member())
           and key in ('ansvarlige', 'stillestaaende_dage', 'naermer_sig_dage',
                       'udstyrsprofiler'))
    with check ((select public.inbase_is_member())
                and key in ('ansvarlige', 'stillestaaende_dage', 'naermer_sig_dage',
                            'udstyrsprofiler'));
