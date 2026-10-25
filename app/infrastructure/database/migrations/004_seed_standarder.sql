-- IN-BASE 004: bevidste standarder for en NY database (ingen forretningsdata).
-- GENERERET af tools/generer_standard_seed.py – ret standarderne i Python og
-- generér filen igen. Kan køres flere gange (on conflict do nothing).

-- Områder (Indstillinger → Organisation)
insert into public.areas (id, name, sort_order, active)
select id, name, sort_order, active from jsonb_populate_recordset(null::public.areas,
'[
 {
  "id": "80fbe15b-9a2e-5204-a581-efbe272a7a4a",
  "name": "Område Nord",
  "sort_order": 0,
  "active": true
 },
 {
  "id": "7d4e69ca-a935-54bd-9cc6-475aaec38751",
  "name": "Område Syd",
  "sort_order": 1,
  "active": true
 },
 {
  "id": "d599dfb6-166f-531f-b844-3553388cb338",
  "name": "Område Øst",
  "sort_order": 2,
  "active": true
 },
 {
  "id": "29150b8e-9fe2-533e-8421-4fb866bf233a",
  "name": "Område Vest",
  "sort_order": 3,
  "active": true
 }
]'::jsonb)
on conflict do nothing;

-- sager
insert into public.workflow_templates (id, process, name, description, positions, active, version, sort_order, updated_by, updated_at)
select id, process, name, description, positions, active, version, sort_order, updated_by, updated_at from jsonb_populate_recordset(null::public.workflow_templates,
'[
 {
  "id": "336a3635-473b-5449-b2c1-f3e7766e11dd",
  "process": "offboarding",
  "name": "Standard",
  "description": "",
  "positions": [],
  "active": true,
  "version": 1,
  "sort_order": 0,
  "updated_by": "standard",
  "updated_at": "2026-01-01T00:00:00+00:00"
 },
 {
  "id": "260a06e7-8bc4-5af7-b2bb-2ce002ee15fd",
  "process": "offboarding",
  "name": "Tom sag (tilføj opgaver selv)",
  "description": "",
  "positions": [],
  "active": true,
  "version": 1,
  "sort_order": 1,
  "updated_by": "standard",
  "updated_at": "2026-01-01T00:00:00+00:00"
 },
 {
  "id": "77c9cdb6-1097-5c77-9867-ddbec2fc54c1",
  "process": "onboarding",
  "name": "Onboarding – standard",
  "description": "Ad Hoc og Afløsere",
  "positions": [
   "Ad Hoc",
   "Afløser"
  ],
  "active": true,
  "version": 1,
  "sort_order": 2,
  "updated_by": "standard",
  "updated_at": "2026-01-01T00:00:00+00:00"
 },
 {
  "id": "3c5bb04a-fdc6-5bca-8b90-3bd9b97c0af6",
  "process": "onboarding",
  "name": "Onboarding – FM/DM",
  "description": "Ledere: ekstra introduktion",
  "positions": [
   "FM",
   "DM"
  ],
  "active": true,
  "version": 1,
  "sort_order": 3,
  "updated_by": "standard",
  "updated_at": "2026-01-01T00:00:00+00:00"
 }
]'::jsonb)
on conflict do nothing;

insert into public.workflow_template_tasks (name, description, responsible, equipment, milestone, due_offset_days, mandatory, id, template_id, sort_order)
select name, description, responsible, equipment, milestone, due_offset_days, mandatory, id, template_id, sort_order from jsonb_populate_recordset(null::public.workflow_template_tasks,
'[
 {
  "name": "Er lukket i NAV?",
  "description": "",
  "responsible": "IT",
  "equipment": "",
  "milestone": "",
  "due_offset_days": 0,
  "mandatory": true,
  "id": "6c27b901-7152-50fe-a392-5e0106fa0465",
  "template_id": "336a3635-473b-5449-b2c1-f3e7766e11dd",
  "sort_order": 0
 },
 {
  "name": "Modtag og spær tankkort",
  "description": "",
  "responsible": "Administration",
  "equipment": "Tankkort",
  "milestone": "",
  "due_offset_days": 0,
  "mandatory": true,
  "id": "de4f6863-24df-5436-8388-cc4810a326db",
  "template_id": "336a3635-473b-5449-b2c1-f3e7766e11dd",
  "sort_order": 1
 },
 {
  "name": "Modtag telefon og SIM-kort",
  "description": "",
  "responsible": "IT",
  "equipment": "Telefon og SIM-kort",
  "milestone": "",
  "due_offset_days": 7,
  "mandatory": true,
  "id": "731bb587-3e87-5876-89fb-83ed4fdc7d34",
  "template_id": "336a3635-473b-5449-b2c1-f3e7766e11dd",
  "sort_order": 2
 },
 {
  "name": "Modtag tøj",
  "description": "",
  "responsible": "Administration",
  "equipment": "Tøj",
  "milestone": "",
  "due_offset_days": 14,
  "mandatory": true,
  "id": "328f2431-02ab-5efc-a230-202b471e505a",
  "template_id": "336a3635-473b-5449-b2c1-f3e7766e11dd",
  "sort_order": 3
 },
 {
  "name": "Afslut og dokumentér afviklingen",
  "description": "",
  "responsible": "Ansvarlig leder",
  "equipment": "",
  "milestone": "",
  "due_offset_days": 21,
  "mandatory": true,
  "id": "42673945-d3f0-501e-a8fd-d2f175ca3383",
  "template_id": "336a3635-473b-5449-b2c1-f3e7766e11dd",
  "sort_order": 4
 },
 {
  "name": "Kandidat godkendt",
  "description": "",
  "responsible": "HR",
  "equipment": "",
  "milestone": "kandidat",
  "due_offset_days": -14,
  "mandatory": true,
  "id": "73419c61-5ad7-55c7-b846-d733f23f009e",
  "template_id": "77c9cdb6-1097-5c77-9867-ddbec2fc54c1",
  "sort_order": 0
 },
 {
  "name": "Kontrakt sendt",
  "description": "",
  "responsible": "HR",
  "equipment": "",
  "milestone": "kontrakt",
  "due_offset_days": -10,
  "mandatory": true,
  "id": "2692d59d-6fff-504e-b20e-c3171893707f",
  "template_id": "77c9cdb6-1097-5c77-9867-ddbec2fc54c1",
  "sort_order": 1
 },
 {
  "name": "Kontrakt underskrevet og bekræftet",
  "description": "",
  "responsible": "HR",
  "equipment": "",
  "milestone": "kontrakt",
  "due_offset_days": -3,
  "mandatory": true,
  "id": "c6f387ac-b388-5caa-8769-44721f994c0f",
  "template_id": "77c9cdb6-1097-5c77-9867-ddbec2fc54c1",
  "sort_order": 2
 },
 {
  "name": "Lønnr. tildelt",
  "description": "",
  "responsible": "Løn",
  "equipment": "",
  "milestone": "kontrakt",
  "due_offset_days": -1,
  "mandatory": true,
  "id": "b367380c-d4b0-5572-9425-e678aac0d66c",
  "template_id": "77c9cdb6-1097-5c77-9867-ddbec2fc54c1",
  "sort_order": 3
 },
 {
  "name": "Første oplæring planlagt",
  "description": "",
  "responsible": "Butik",
  "equipment": "",
  "milestone": "oplaering",
  "due_offset_days": 0,
  "mandatory": true,
  "id": "dac4f8c3-f886-5ee9-bfa2-ad58231e5879",
  "template_id": "77c9cdb6-1097-5c77-9867-ddbec2fc54c1",
  "sort_order": 4
 },
 {
  "name": "Første oplæring gennemført",
  "description": "",
  "responsible": "Butik",
  "equipment": "",
  "milestone": "oplaering",
  "due_offset_days": 7,
  "mandatory": true,
  "id": "9c2f00fb-fd13-5aed-9892-54168174c48c",
  "template_id": "77c9cdb6-1097-5c77-9867-ddbec2fc54c1",
  "sort_order": 5
 },
 {
  "name": "Oprettet i medarbejderappen",
  "description": "",
  "responsible": "Butik",
  "equipment": "",
  "milestone": "jobs",
  "due_offset_days": 7,
  "mandatory": true,
  "id": "54546c78-1db5-51e7-ba85-2b53ecf39f0b",
  "template_id": "77c9cdb6-1097-5c77-9867-ddbec2fc54c1",
  "sort_order": 6
 },
 {
  "name": "Første job tildelt",
  "description": "",
  "responsible": "Butik",
  "equipment": "",
  "milestone": "jobs",
  "due_offset_days": 14,
  "mandatory": true,
  "id": "6b3652f0-48d0-5f1e-b554-c789359eecb4",
  "template_id": "77c9cdb6-1097-5c77-9867-ddbec2fc54c1",
  "sort_order": 7
 },
 {
  "name": "Kandidat godkendt",
  "description": "",
  "responsible": "HR",
  "equipment": "",
  "milestone": "kandidat",
  "due_offset_days": -14,
  "mandatory": true,
  "id": "7fddd427-1fb5-5150-893e-58b7ef2e48e4",
  "template_id": "3c5bb04a-fdc6-5bca-8b90-3bd9b97c0af6",
  "sort_order": 0
 },
 {
  "name": "Kontrakt sendt",
  "description": "",
  "responsible": "HR",
  "equipment": "",
  "milestone": "kontrakt",
  "due_offset_days": -10,
  "mandatory": true,
  "id": "4cf58edd-b644-54d6-a9c8-534d38baecc3",
  "template_id": "3c5bb04a-fdc6-5bca-8b90-3bd9b97c0af6",
  "sort_order": 1
 },
 {
  "name": "Kontrakt underskrevet og bekræftet",
  "description": "",
  "responsible": "HR",
  "equipment": "",
  "milestone": "kontrakt",
  "due_offset_days": -3,
  "mandatory": true,
  "id": "7dc9c571-c4d3-52ef-8e05-10ef7d41b8e7",
  "template_id": "3c5bb04a-fdc6-5bca-8b90-3bd9b97c0af6",
  "sort_order": 2
 },
 {
  "name": "Lønnr. tildelt",
  "description": "",
  "responsible": "Løn",
  "equipment": "",
  "milestone": "kontrakt",
  "due_offset_days": -1,
  "mandatory": true,
  "id": "e2ef38d9-10ab-5fda-8292-fa23fd55b724",
  "template_id": "3c5bb04a-fdc6-5bca-8b90-3bd9b97c0af6",
  "sort_order": 3
 },
 {
  "name": "Første oplæring planlagt",
  "description": "",
  "responsible": "Butik",
  "equipment": "",
  "milestone": "oplaering",
  "due_offset_days": 0,
  "mandatory": true,
  "id": "bae98c62-652e-5c85-bcbb-d8a0e7e87e29",
  "template_id": "3c5bb04a-fdc6-5bca-8b90-3bd9b97c0af6",
  "sort_order": 4
 },
 {
  "name": "Første oplæring gennemført",
  "description": "",
  "responsible": "Butik",
  "equipment": "",
  "milestone": "oplaering",
  "due_offset_days": 7,
  "mandatory": true,
  "id": "87875be6-cf08-56bc-b264-0b4337cfc40e",
  "template_id": "3c5bb04a-fdc6-5bca-8b90-3bd9b97c0af6",
  "sort_order": 5
 },
 {
  "name": "Oprettet i medarbejderappen",
  "description": "",
  "responsible": "Butik",
  "equipment": "",
  "milestone": "jobs",
  "due_offset_days": 7,
  "mandatory": true,
  "id": "6b3fb91c-22da-59d9-b44c-6b7c4a759e27",
  "template_id": "3c5bb04a-fdc6-5bca-8b90-3bd9b97c0af6",
  "sort_order": 6
 },
 {
  "name": "Første job tildelt",
  "description": "",
  "responsible": "Butik",
  "equipment": "",
  "milestone": "jobs",
  "due_offset_days": 14,
  "mandatory": true,
  "id": "d7094b16-2d85-51a9-9249-ef584351439f",
  "template_id": "3c5bb04a-fdc6-5bca-8b90-3bd9b97c0af6",
  "sort_order": 7
 },
 {
  "name": "Introduktion til ledelsesopgaver",
  "description": "",
  "responsible": "Områdeleder",
  "equipment": "",
  "milestone": "oplaering",
  "due_offset_days": 14,
  "mandatory": true,
  "id": "334168a3-9034-518b-8803-a139b2d713e1",
  "template_id": "3c5bb04a-fdc6-5bca-8b90-3bd9b97c0af6",
  "sort_order": 8
 }
]'::jsonb)
on conflict do nothing;

-- mails
insert into public.message_templates (id, name, category, tone, due_days, subject, body, active, sort_order, updated_at, updated_by)
select id, name, category, tone, due_days, subject, body, active, sort_order, updated_at, updated_by from jsonb_populate_recordset(null::public.message_templates,
'[
 {
  "id": "16220e31-3492-5560-b9d0-3cb9f5a80ff2",
  "name": "Første venlige påmindelse",
  "category": "Første påmindelse",
  "tone": "Venlig",
  "due_days": 7,
  "subject": "Returnering af udstyr",
  "body": "Hej {fornavn}\n\nVi mangler fortsat at modtage følgende udstyr:\n{manglende_udstyr}\n\nVi beder dig venligst sørge for, at det resterende udstyr returneres senest {frist}. Returvejledningen fremgår af den tidligere fremsendte e-mail.\n\nPå forhånd tak for din hjælp.",
  "active": true,
  "sort_order": 0,
  "updated_at": "2026-01-01T00:00:00+00:00",
  "updated_by": "standard"
 },
 {
  "id": "ae36856b-3fcd-5599-9ef0-de978ec989d0",
  "name": "Anden rykker med tydelig frist",
  "category": "Anden rykker",
  "tone": "Bestemt",
  "due_days": 5,
  "subject": "Rykker: Udstyr skal returneres senest {frist}",
  "body": "Hej {fornavn}\n\nVi har tidligere skrevet til dig om returnering af udstyr, men har endnu ikke modtaget:\n{manglende_udstyr}\n\nUdstyret skal være returneret senest {frist}. Returvejledningen fremgår af den tidligere fremsendte e-mail.\n\nHar du spørgsmål, er du velkommen til at svare på denne mail.",
  "active": true,
  "sort_order": 1,
  "updated_at": "2026-01-01T00:00:00+00:00",
  "updated_by": "standard"
 }
]'::jsonb)
on conflict do nothing;

-- paamindelser
insert into public.notification_rules (id, name, rule, days, repeat_days, title, body, active, sort_order, updated_at, updated_by)
select id, name, rule, days, repeat_days, title, body, active, sort_order, updated_at, updated_by from jsonb_populate_recordset(null::public.notification_rules,
'[
 {
  "id": "308b20c5-7863-5951-829e-e05c3b62cd17",
  "name": "Forsinket opgave",
  "rule": "opgave_forsinket",
  "days": 0,
  "repeat_days": 1,
  "title": "Forsinket: {opgave}",
  "body": "{navn} · Ansvarlig: {ansvarlig} · {dage} dage over frist",
  "active": true,
  "sort_order": 0,
  "updated_at": "2026-01-01T00:00:00+00:00",
  "updated_by": "standard"
 },
 {
  "id": "eacd7777-7ecd-53e7-821b-4d709d2b895f",
  "name": "Frist i dag",
  "rule": "frist_i_dag",
  "days": 0,
  "repeat_days": 1,
  "title": "Frist i dag: {opgave}",
  "body": "{navn} · Ansvarlig: {ansvarlig}",
  "active": true,
  "sort_order": 1,
  "updated_at": "2026-01-01T00:00:00+00:00",
  "updated_by": "standard"
 },
 {
  "id": "a6e9ccf0-2829-5b23-8675-7625deaab441",
  "name": "Rykker venter på afsendelse",
  "rule": "rykker_ikke_sendt",
  "days": 2,
  "repeat_days": 1,
  "title": "Rykker ikke markeret som sendt",
  "body": "Rykkeren til {navn} blev oprettet for {dage} dage siden.",
  "active": true,
  "sort_order": 2,
  "updated_at": "2026-01-01T00:00:00+00:00",
  "updated_by": "standard"
 },
 {
  "id": "539f0b48-559e-5d8e-88d7-a39d630c228d",
  "name": "Intet svar efter rykker",
  "rule": "intet_svar_efter_rykker",
  "days": 7,
  "repeat_days": 1,
  "title": "Overvej næste rykker: {navn}",
  "body": "Mangler stadig: {manglende_udstyr}",
  "active": true,
  "sort_order": 3,
  "updated_at": "2026-01-01T00:00:00+00:00",
  "updated_by": "standard"
 },
 {
  "id": "cb3ebf98-105b-5f92-bb53-4fc4c9f2cfa8",
  "name": "Fratrædelse nærmer sig",
  "rule": "fratraedelse_naermer_sig",
  "days": 3,
  "repeat_days": 1,
  "title": "{navn} stopper om {dage} dage",
  "body": "Sørg for, at opgaverne er fordelt inden sidste arbejdsdag.",
  "active": true,
  "sort_order": 4,
  "updated_at": "2026-01-01T00:00:00+00:00",
  "updated_by": "standard"
 },
 {
  "id": "19ab8424-d539-5c13-95e0-37246769579c",
  "name": "Stillestående sag",
  "rule": "sag_stillestaaende",
  "days": 14,
  "repeat_days": 7,
  "title": "Ingen bevægelse: {navn}",
  "body": "Sagen har ikke ændret sig i {dage} dage.",
  "active": true,
  "sort_order": 5,
  "updated_at": "2026-01-01T00:00:00+00:00",
  "updated_by": "standard"
 }
]'::jsonb)
on conflict do nothing;
