# Database (Supabase / PostgreSQL)

Supabase er IN-BASE's fælles datakilde. Opsætning og drift:
[docs/SUPABASE_OPSAETNING.md](../../../docs/SUPABASE_OPSAETNING.md).

## Hvor ligger hvad?

| Fil | Indhold |
|---|---|
| `config.py` | Den ENESTE læsning af konfiguration (`%APPDATA%\IN-BASE\.env`, miljø). Afviser privilegerede nøgler. |
| `connection.py` | Det ENESTE sted, Supabase-klienten oprettes (én pr. kørsel, session kun i hukommelsen). |
| `migrations/001`–`004` | Skema, RLS/privilegier, RPC-funktioner, bevidste standarder. Køres manuelt i rækkefølge. |
| `migrations/005` | Login med brugernavn (internt login-alias), aktive/deaktiverede brugere, første administrator. |
| `migrations/006` | Ønsker & Udvikling: indmeldinger, kommentarer, historik, RLS og RPC'er. |
| `migrations/014` | Arbejdsspor på opgaver, HR's behov på sager, afdelinger (roller) på brugere. |
| `migrations/015` | Standarder (genereres af `tools/generer_standard_seed.py`; 004 ændres ikke længere). |
| `migrations/019` | Skemaversion (`schema_migrations`), krav til klienten, delt signatur, central opdatering (`app_releases` + Storage `releases`), opdateringskanal pr. bruger. |
| `migrations/020` | Kalender: `calendars` + `calendar_events` (serier, undtagelser, rettede forekomster), modulet `kalender`. Ingen direkte tabeladgang – kun RPC'er (`inbase_calendar_*`). |
| `migrations/021` | Kalenderdeling: `calendar_shares` (freebusy/read/write), maskering af titler i databasen, administratorers adgang og moderation. |
| `reset/nulstil_forretningsdata.sql` | Engangs-tømning af forretningsdata (kræver bekræftelse). |
| `../../repositories/supabase/` | ALLE kald til tabeller, RPC, Auth og Edge Functions. |
| `../../repositories/supabase/mapping.py` | Den ENESTE oversættelse domæne ↔ kolonner (feltkort). |
| `../../../supabase/functions/` | Edge Functions til brugeradministration (servernøgle kun dér). |
| `../../bootstrap.py` | Vælger Supabase- eller JSON-repositories. |

## Datamodel

```
people ──< employment_records ──< lifecycle_cases ──< case_tasks
   (identitet)   (lønnr., stilling,      │          ├──< case_reminders
                  område, datoer)        │          └──< audit_events (insert-only)
workflow_templates ──< workflow_template_tasks
                  └──< workflow_template_versions
areas, positions, app_settings, message_templates, notification_rules
auth.users ──1:1── user_profiles (brugernavn, rolle, roles = afdelinger, active, tema,
                                   must_change_password)
case_tasks: task_key, track, department, depends_on[] (andre opgavers task_key),
            condition (behov), planned_at – lifecycle_cases.needs: HR's behov (JSON)
   (e-mail = internt login-alias)
user_profiles ──< development_requests ──< development_request_comments
 (indsender/ansvarlig)                 └──< development_request_events (insert-only)
user_profiles ──< calendars ──< calendar_events ──< calendar_events (rettede forekomster,
   (ejer)       │               (rrule, exdates)      recurrence_of + original_start)
                └──< calendar_shares >── user_profiles (modtager, level)
```

## Skrivning

* Sager skrives KUN via `inbase_save_case(p_case, p_expected_version)`:
  sag, person, ansættelse, ændrede opgaver/rykkere og nye hændelser i én
  transaktion. Forkert version → `IB409` → `KonfliktFejl`. Klienten sender kun
  de rækker, der er ændret siden sagen blev hentet.
* Tidslinjen er insert-only; hændelser kan kun registreres i eget navn.
* Skabeloner (arbejdsgange) via `inbase_save_workflow_template` (alle med modulet, 011);
  mail-/påmindelsesskabeloner, områder og Organisation direkte (RLS: alle medlemmer;
  backup/slettepolitik kun admin).
* Permanent sletning via `inbase_delete_case` (kun admin) – sletter også
  personen, hvis ingen anden sag bruger den.
* Ønsker & Udvikling via `inbase_create_request`, `inbase_update_request`
  (versionstjek, rettigheder, statusovergange, historik pr. felt) og
  `inbase_add_request_comment`. Sletning direkte (RLS: kun admin).
* Kalender KUN via RPC'erne fra 020/021 (også læsning: `inbase_calendars`,
  `inbase_calendar_events`), så titler kan maskeres ("Optaget") i databasen. Adgangen
  afgøres ét sted: `inbase_calendar_access(kalender)` → owner > write > read > admin >
  freebusy (eller ingen). Moderation (dele, slette): `inbase_calendar_can_moderate`.

## Nyt felt – uden at duplikere databasekode

1. Ny migrering `0NN_<navn>.sql`: `alter table public.<tabel> add column ...;` – og til
   sidst `insert into public.schema_migrations (version, name) values (NN, '0NN_<navn>')
   on conflict do nothing;`. Hæv `KRAEVET_SKEMA` i `app/__init__.py` til NN, så en
   klient aldrig kører mod en database, hvor kolonnen mangler (den ville ellers blive
   droppet lydløst af `inbase_columns`).
2. Én linje i det relevante feltkort i `repositories/supabase/mapping.py`,
   fx `("telefon", "phone", TEKST)` i `PERSON_FELTER`.
3. Feltet i domænets `til_dict()`/`fra_dict()` (som for JSON).

RPC-funktionerne udleder selv kolonnelisten fra tabellen, så de skal ikke
ændres. UI, services og controllere kalder ikke databasen og berøres kun, hvis
feltet skal vises/redigeres.

Ny tabel/funktion: migrering (tabel + RLS-politik + grants), metode i et
repository i `repositories/supabase/`, evt. grænseflade i `repositories/base.py`
og valg i `bootstrap.py`.
