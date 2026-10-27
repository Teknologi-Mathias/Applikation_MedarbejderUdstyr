-- IN-BASE 018: Et enkelt onboardingflow + sletning af skabeloner
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 017.
-- Ingen sager eller sagsopgaver ændres eller slettes. Kan køres flere gange.
--
-- 1. Ny standardskabelon "Onboarding" (alle stillinger) med kun de opgaver, hvor
--    nogen skal gøre noget: kontrakt, udstyr sendt (samlet), firmabil bestilt,
--    oplæringsdag fastlagt og opfølgningssamtale. Det, HR afgør ved oprettelsen
--    (godkendelse, lønnr., behov, datoer), er felter – ikke opgaver.
--    Svarer til app/domain/skabelon.py (_ONBOARDING_BASIS), faste UUID'er som 015.
-- 2. De to tidligere standarder ("Onboarding – arbejdsspor" og "... FM/DM")
--    deaktiveres (slettes ikke – kan slettes i programmet, når de ikke bruges).
-- 3. Skabeloner kan slettes af medlemmer med adgang til modulet:
--    arbejdsgange via inbase_delete_workflow_template (samme modultjek som
--    inbase_save_workflow_template, 011); mails og påmindelser direkte (RLS).
--    Sager peger på skabelonen med "on delete set null" og beholder navnet og
--    deres egne opgaver.

-- ---------- 1. Ny standard ---------------------------------------------------

insert into public.workflow_templates (id, process, name, description, positions, active, version, sort_order, updated_by, updated_at)
select id, process, name, description, positions, active, version, sort_order, updated_by, updated_at from jsonb_populate_recordset(null::public.workflow_templates,
'[
 {
  "id": "bd92ab3b-8fce-52e5-8c2b-2d887bd2f74a",
  "process": "onboarding",
  "name": "Onboarding",
  "description": "Alle stillinger – udstyret følger behovet",
  "positions": [],
  "active": true,
  "version": 1,
  "sort_order": 2,
  "updated_by": "standard",
  "updated_at": "2026-10-27T00:00:00+00:00"
 }
]'::jsonb)
on conflict do nothing;

insert into public.workflow_template_tasks (name, description, responsible, equipment, milestone, due_offset_days, mandatory, task_key, track, department, depends_on, condition, id, template_id, sort_order)
select name, description, responsible, equipment, milestone, due_offset_days, mandatory, task_key, track, department, depends_on, condition, id, template_id, sort_order from jsonb_populate_recordset(null::public.workflow_template_tasks,
'[
 {
  "name": "Kontrakt sendt og modtaget retur",
  "description": "Afventer = sendt til medarbejderen. Udført = modtaget retur underskrevet.",
  "responsible": "",
  "equipment": "",
  "milestone": "kontrakt",
  "due_offset_days": -7,
  "mandatory": true,
  "task_key": "kontrakt",
  "track": "kontrakt",
  "department": "Administration",
  "depends_on": [],
  "condition": "",
  "id": "cf943cc6-0878-5503-b0df-cf2d1ebcffe0",
  "template_id": "bd92ab3b-8fce-52e5-8c2b-2d887bd2f74a",
  "sort_order": 0
 },
 {
  "name": "Udstyr sendt",
  "description": "Alt det udstyr, HR har valgt (telefon, e-mail, polo, fleece) – listen står på forløbet.",
  "responsible": "",
  "equipment": "",
  "milestone": "jobs",
  "due_offset_days": -3,
  "mandatory": true,
  "task_key": "udstyr",
  "track": "udstyr",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "udstyr",
  "id": "e94e0134-f08f-5e9e-b823-5dd7b8ff8caa",
  "template_id": "bd92ab3b-8fce-52e5-8c2b-2d887bd2f74a",
  "sort_order": 1
 },
 {
  "name": "Firmabil bestilt",
  "description": "",
  "responsible": "",
  "equipment": "Firmabil",
  "milestone": "jobs",
  "due_offset_days": 0,
  "mandatory": true,
  "task_key": "firmabil",
  "track": "firmabil",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "firmabil",
  "id": "bdfef782-10cc-5409-9c0b-3092ee1c8ebe",
  "template_id": "bd92ab3b-8fce-52e5-8c2b-2d887bd2f74a",
  "sort_order": 2
 },
 {
  "name": "Oplæringsdag fastlagt",
  "description": "Tidspunktet registreres som planlagt tidspunkt. Afventer = afventer bekræftelse fra oplæringsansvarlig. Udført = booket og bekræftet.",
  "responsible": "",
  "equipment": "",
  "milestone": "oplaering",
  "due_offset_days": -2,
  "mandatory": true,
  "task_key": "oplaering_booket",
  "track": "oplaering",
  "department": "HR",
  "depends_on": [],
  "condition": "",
  "id": "22796789-3d24-5e80-b54e-cf8f4645df88",
  "template_id": "bd92ab3b-8fce-52e5-8c2b-2d887bd2f74a",
  "sort_order": 3
 },
 {
  "name": "Opfølgningssamtale (1 uge efter start)",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "",
  "due_offset_days": 7,
  "mandatory": true,
  "task_key": "opfoelgning",
  "track": "opfoelgning",
  "department": "Merch",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "",
  "id": "7d7a4a2b-cab5-5447-8ad8-26a9e30e9e6b",
  "template_id": "bd92ab3b-8fce-52e5-8c2b-2d887bd2f74a",
  "sort_order": 4
 }
]'::jsonb)
on conflict do nothing;

-- ---------- 2. Tidligere standarder deaktiveres ---------------------------------

update public.workflow_templates set active = false
where id in ('670684e6-0dd2-523e-b678-bfaea564acf0', '10b66103-6a04-5463-9a45-ac9e987238b1');

-- ---------- 3. Sletning af skabeloner ------------------------------------------

create or replace function public.inbase_delete_workflow_template(p_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
    if not public.inbase_is_member()
       or exists (select 1 from public.workflow_templates
                  where id = p_id and not public.inbase_has_module(process)) then
        raise exception 'Du har ikke adgang til at slette skabeloner i dette modul.'
            using errcode = 'IB403';
    end if;
    -- Opgaver og versioner slettes med (on delete cascade); sager beholder deres kopier.
    delete from public.workflow_templates where id = p_id;
end;
$$;
revoke execute on function public.inbase_delete_workflow_template(uuid) from public, anon;
grant execute on function public.inbase_delete_workflow_template(uuid) to authenticated;

grant delete on public.message_templates  to authenticated;
grant delete on public.notification_rules to authenticated;
drop policy if exists message_templates_member_delete on public.message_templates;
create policy message_templates_member_delete on public.message_templates
    for delete to authenticated using ((select public.inbase_is_member()));
drop policy if exists notification_rules_member_delete on public.notification_rules;
create policy notification_rules_member_delete on public.notification_rules
    for delete to authenticated using ((select public.inbase_is_member()));
