-- IN-BASE 017: Lønnr. tildeles af HR før kontrakten (onboarding)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 016.
-- Ingen sager eller sagsopgaver ændres – kun arbejdsgangsskabeloner.
--
-- HR opretter medarbejderen i ERP og tildeler lønnr.; lønnr. står på kontrakten.
-- Derfor ændres opgaven "Lønnr. tildelt" i onboardingskabelonerne:
--   før:  Administration, spor kontrakt, afhænger af kontrakten, milepæl kontrakt, frist -3
--   efter: HR, spor hr, ingen forudsætninger, milepæl kandidat, frist -14
-- og kontrakten afhænger nu også af 'loennr'. Samme regler som standarden i
-- app/domain/skabelon.py (_ONBOARDING_BASIS).
--
-- Versionering som i programmet: den nuværende udgave gemmes som snapshot i
-- workflow_template_versions, og versionen tælles op. Igangværende sager har
-- deres egne kopier af opgaverne og påvirkes ikke.
--
-- Kun skabeloner, hvor opgaven stadig står som den oprindelige standard
-- (Administration + afhænger af kontrakten), ændres – egne tilretninger røres
-- ikke. Kan køres flere gange (anden kørsel finder intet at ændre).

do $$
declare
    t record;
begin
    for t in
        select w.* from public.workflow_templates w
        where w.process = 'onboarding'
          and exists (select 1 from public.workflow_template_tasks k
                      where k.template_id = w.id and k.task_key = 'loennr'
                        and k.department = 'Administration' and k.depends_on = '{kontrakt}')
    loop
        -- Snapshot af den nuværende version (samme form som programmets skabeloner).
        insert into public.workflow_template_versions (template_id, version, snapshot)
        select t.id, t.version, jsonb_build_object(
            'id', t.id, 'navn', t.name, 'proces', t.process, 'beskrivelse', t.description,
            'stillinger', to_jsonb(t.positions), 'aktiv', t.active, 'version', t.version,
            'opgaver', coalesce((
                select jsonb_agg(jsonb_build_object(
                    'navn', k.name, 'beskrivelse', k.description, 'ansvarlig', k.responsible,
                    'udstyr', k.equipment, 'milepael', k.milestone,
                    'frist_dage', k.due_offset_days, 'obligatorisk', k.mandatory,
                    'noegle', k.task_key, 'spor', k.track, 'afdeling', k.department,
                    'afhaenger_af', to_jsonb(k.depends_on), 'betingelse', k.condition)
                    order by k.sort_order)
                from public.workflow_template_tasks k where k.template_id = t.id), '[]'::jsonb))
        on conflict (template_id, version) do nothing;

        update public.workflow_template_tasks
        set department = 'HR', responsible = '', track = 'hr', depends_on = '{}',
            milestone = 'kandidat', due_offset_days = -14,
            description = 'HR opretter medarbejderen i ERP og tildeler lønnr. Markeres som '
                          'udført, når lønnr. udfyldes på forløbet. Kontrakten kan først '
                          'sendes herefter.'
        where template_id = t.id and task_key = 'loennr';

        update public.workflow_template_tasks
        set depends_on = array_append(depends_on, 'loennr')
        where template_id = t.id and task_key = 'kontrakt'
          and not ('loennr' = any(depends_on));

        update public.workflow_templates
        set version = version + 1, updated_at = now(), updated_by = 'migrering 017'
        where id = t.id;
    end loop;
end $$;
