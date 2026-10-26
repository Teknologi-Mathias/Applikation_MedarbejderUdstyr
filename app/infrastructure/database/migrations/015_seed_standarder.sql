-- IN-BASE 015: bevidste standarder (ingen forretningsdata). Køres EFTER 014.
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
  "id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "process": "onboarding",
  "name": "Onboarding – arbejdsspor",
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
  "id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "process": "onboarding",
  "name": "Onboarding – arbejdsspor FM/DM",
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

insert into public.workflow_template_tasks (name, description, responsible, equipment, milestone, due_offset_days, mandatory, task_key, track, department, depends_on, condition, id, template_id, sort_order)
select name, description, responsible, equipment, milestone, due_offset_days, mandatory, task_key, track, department, depends_on, condition, id, template_id, sort_order from jsonb_populate_recordset(null::public.workflow_template_tasks,
'[
 {
  "name": "Er lukket i NAV?",
  "description": "",
  "responsible": "IT",
  "equipment": "",
  "milestone": "",
  "due_offset_days": 0,
  "mandatory": true,
  "task_key": "",
  "track": "",
  "department": "",
  "depends_on": [],
  "condition": "",
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
  "task_key": "",
  "track": "",
  "department": "",
  "depends_on": [],
  "condition": "",
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
  "task_key": "",
  "track": "",
  "department": "",
  "depends_on": [],
  "condition": "",
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
  "task_key": "",
  "track": "",
  "department": "",
  "depends_on": [],
  "condition": "",
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
  "task_key": "",
  "track": "",
  "department": "",
  "depends_on": [],
  "condition": "",
  "id": "42673945-d3f0-501e-a8fd-d2f175ca3383",
  "template_id": "336a3635-473b-5449-b2c1-f3e7766e11dd",
  "sort_order": 4
 },
 {
  "name": "Kandidat godkendt",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "kandidat",
  "due_offset_days": -14,
  "mandatory": true,
  "task_key": "kandidat_godkendt",
  "track": "hr",
  "department": "HR",
  "depends_on": [],
  "condition": "",
  "id": "8d1bfb23-e1c9-5eae-8570-8db088b83058",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 0
 },
 {
  "name": "Behov registreret (tøj, mobil, mail, bil)",
  "description": "HR tager stilling til udstyr og behov i forløbets behovsregistrering.",
  "responsible": "",
  "equipment": "",
  "milestone": "kandidat",
  "due_offset_days": -14,
  "mandatory": true,
  "task_key": "behov_registreret",
  "track": "hr",
  "department": "HR",
  "depends_on": [],
  "condition": "",
  "id": "81ea9d64-e8b7-5511-a785-e29ad4ee4463",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 1
 },
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
  "depends_on": [
   "kandidat_godkendt"
  ],
  "condition": "",
  "id": "26c0b61f-0bfc-57dc-ad8a-ef2189bd24f3",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 2
 },
 {
  "name": "Lønnr. tildelt",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "kontrakt",
  "due_offset_days": -3,
  "mandatory": true,
  "task_key": "loennr",
  "track": "kontrakt",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "",
  "id": "a5948038-4454-56f5-9ff7-ec10320cf541",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 3
 },
 {
  "name": "Polo sendt",
  "description": "",
  "responsible": "",
  "equipment": "Polo",
  "milestone": "jobs",
  "due_offset_days": -3,
  "mandatory": true,
  "task_key": "polo",
  "track": "toej",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "polo",
  "id": "a31f1795-cbef-5fb7-b148-43796d31fab8",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 4
 },
 {
  "name": "Fleece sendt",
  "description": "",
  "responsible": "",
  "equipment": "Fleece",
  "milestone": "jobs",
  "due_offset_days": -3,
  "mandatory": true,
  "task_key": "fleece",
  "track": "toej",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "fleece",
  "id": "cb7e16e6-709e-54ab-ab84-4029db9b3366",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 5
 },
 {
  "name": "Telefon og SIM-kort klargjort og sendt",
  "description": "",
  "responsible": "",
  "equipment": "Telefon og SIM-kort",
  "milestone": "jobs",
  "due_offset_days": -3,
  "mandatory": true,
  "task_key": "telefon",
  "track": "telefon",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "mobil",
  "id": "ce6bc9c0-4bc2-579b-b1de-57d0eb0a202d",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 6
 },
 {
  "name": "E-mailkonto oprettet",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "jobs",
  "due_offset_days": -2,
  "mandatory": true,
  "task_key": "email",
  "track": "email",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "email",
  "id": "0ea57dda-8d3f-5449-ae8d-ceba7d9bc46f",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 7
 },
 {
  "name": "Firmabil klar",
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
  "id": "db5fbfae-df3a-56cd-bbdf-9ed201942925",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 8
 },
 {
  "name": "Oplæringsvagt booket",
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
  "id": "9606ed8d-fb7b-5220-9835-221b50c69b52",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 9
 },
 {
  "name": "Første oplæring gennemført",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "oplaering",
  "due_offset_days": 7,
  "mandatory": true,
  "task_key": "oplaering_gennemfoert",
  "track": "oplaering",
  "department": "HR",
  "depends_on": [
   "oplaering_booket",
   "kontrakt"
  ],
  "condition": "",
  "id": "cc463a95-74c3-578c-b668-cb9d75a2cf0c",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 10
 },
 {
  "name": "Oprettet i medarbejderappen",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "jobs",
  "due_offset_days": 0,
  "mandatory": true,
  "task_key": "medarbejderapp",
  "track": "opstart",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "",
  "id": "3c4883b7-0da2-5b31-85dc-742f12c4626b",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 11
 },
 {
  "name": "Første job tildelt",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "jobs",
  "due_offset_days": 14,
  "mandatory": true,
  "task_key": "foerste_job",
  "track": "opstart",
  "department": "",
  "depends_on": [
   "oplaering_gennemfoert"
  ],
  "condition": "",
  "id": "b9269be5-6b9a-53f9-adcc-20c3af5f5096",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 12
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
  "id": "d4b09e4e-e0a4-5590-9b34-0ee9ced44347",
  "template_id": "670684e6-0dd2-523e-b678-bfaea564acf0",
  "sort_order": 13
 },
 {
  "name": "Kandidat godkendt",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "kandidat",
  "due_offset_days": -14,
  "mandatory": true,
  "task_key": "kandidat_godkendt",
  "track": "hr",
  "department": "HR",
  "depends_on": [],
  "condition": "",
  "id": "d937d300-b0fa-5dfd-96af-adcf921d326e",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 0
 },
 {
  "name": "Behov registreret (tøj, mobil, mail, bil)",
  "description": "HR tager stilling til udstyr og behov i forløbets behovsregistrering.",
  "responsible": "",
  "equipment": "",
  "milestone": "kandidat",
  "due_offset_days": -14,
  "mandatory": true,
  "task_key": "behov_registreret",
  "track": "hr",
  "department": "HR",
  "depends_on": [],
  "condition": "",
  "id": "8a886818-97af-5520-8a82-2e067107f985",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 1
 },
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
  "depends_on": [
   "kandidat_godkendt"
  ],
  "condition": "",
  "id": "c1957a43-69df-5ce3-a781-ce75adcc5299",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 2
 },
 {
  "name": "Lønnr. tildelt",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "kontrakt",
  "due_offset_days": -3,
  "mandatory": true,
  "task_key": "loennr",
  "track": "kontrakt",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "",
  "id": "c162fa50-bc80-5825-9d17-b1ba9d0699a6",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 3
 },
 {
  "name": "Polo sendt",
  "description": "",
  "responsible": "",
  "equipment": "Polo",
  "milestone": "jobs",
  "due_offset_days": -3,
  "mandatory": true,
  "task_key": "polo",
  "track": "toej",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "polo",
  "id": "346ecba7-754b-55f8-b315-eb841b597ef1",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 4
 },
 {
  "name": "Fleece sendt",
  "description": "",
  "responsible": "",
  "equipment": "Fleece",
  "milestone": "jobs",
  "due_offset_days": -3,
  "mandatory": true,
  "task_key": "fleece",
  "track": "toej",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "fleece",
  "id": "24cd6074-8abd-5998-b067-ff6af08396c8",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 5
 },
 {
  "name": "Telefon og SIM-kort klargjort og sendt",
  "description": "",
  "responsible": "",
  "equipment": "Telefon og SIM-kort",
  "milestone": "jobs",
  "due_offset_days": -3,
  "mandatory": true,
  "task_key": "telefon",
  "track": "telefon",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "mobil",
  "id": "0744cf75-882c-525a-8bca-37a65f49bdb0",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 6
 },
 {
  "name": "E-mailkonto oprettet",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "jobs",
  "due_offset_days": -2,
  "mandatory": true,
  "task_key": "email",
  "track": "email",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "email",
  "id": "89f7804d-d1cc-5246-9cdf-4ede246f71f4",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 7
 },
 {
  "name": "Firmabil klar",
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
  "id": "87c9f893-58bd-5026-804a-2fd982f7e3f9",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 8
 },
 {
  "name": "Oplæringsvagt booket",
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
  "id": "52b3a791-4233-5d74-8a29-3c8ca00c61a2",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 9
 },
 {
  "name": "Første oplæring gennemført",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "oplaering",
  "due_offset_days": 7,
  "mandatory": true,
  "task_key": "oplaering_gennemfoert",
  "track": "oplaering",
  "department": "HR",
  "depends_on": [
   "oplaering_booket",
   "kontrakt"
  ],
  "condition": "",
  "id": "7312c1e2-a6a8-550b-be07-e0f358b405a6",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 10
 },
 {
  "name": "Oprettet i medarbejderappen",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "jobs",
  "due_offset_days": 0,
  "mandatory": true,
  "task_key": "medarbejderapp",
  "track": "opstart",
  "department": "Administration",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "",
  "id": "e6a10cdd-487d-5ce1-81cd-744eac1914ac",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 11
 },
 {
  "name": "Første job tildelt",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "jobs",
  "due_offset_days": 14,
  "mandatory": true,
  "task_key": "foerste_job",
  "track": "opstart",
  "department": "",
  "depends_on": [
   "oplaering_gennemfoert"
  ],
  "condition": "",
  "id": "3a22bbf1-2a6a-5b44-b214-ab4a7b042a11",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 12
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
  "id": "066f917d-7148-5c33-a7a1-72dfa3b405ea",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 13
 },
 {
  "name": "Introduktion til ledelsesopgaver",
  "description": "",
  "responsible": "",
  "equipment": "",
  "milestone": "oplaering",
  "due_offset_days": 14,
  "mandatory": true,
  "task_key": "ledelsesintro",
  "track": "oplaering",
  "department": "HR",
  "depends_on": [
   "kontrakt"
  ],
  "condition": "",
  "id": "ff87edc3-1eb5-5cc8-9b9c-91822cfa707c",
  "template_id": "10b66103-6a04-5463-9a45-ac9e987238b1",
  "sort_order": 14
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

-- Onboarding-skabeloner fra før arbejdssporene: deaktiveres (slettes ikke)
update public.workflow_templates set active = false where id in ('77c9cdb6-1097-5c77-9867-ddbec2fc54c1', '3c5bb04a-fdc6-5bca-8b90-3bd9b97c0af6');
