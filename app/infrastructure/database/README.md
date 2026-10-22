# Database (Supabase / PostgreSQL) – forberedelse

**Status: ikke tilsluttet.** IN-BASE gemmer i dag data som JSON i den
centrale datamappe (`app/repositories/json/`). Intet i programmet forbinder
til en database, og intet foregiver at gøre det.

## Hvor ligger hvad?

| Fil | Indhold |
|---|---|
| `config.py` | Den ENESTE læsning af databasekonfiguration (miljøvariabler). |
| `connection.py` | Det ENESTE sted, en forbindelse oprettes. Fejler i dag tydeligt. |
| `migrations/001_initial_schema.sql` | Tabeller, nøgler, kontrollerede statusser, versions-trigger. |
| `migrations/002_rls_policies.sql` | Row Level Security og roller. |
| `migrering.py` | Forbereder JSON-data til import og validerer dem mod kilden. |
| `../../repositories/base.py` | Grænsefladerne en Supabase-implementering skal opfylde. |
| `../../bootstrap.py` | Her vælges hvilke repositories (JSON/Supabase) der bruges. |

## Konfiguration

Kopiér `.env.example` fra projektroden og sæt:

```
INBASE_SUPABASE_URL=https://<projekt>.supabase.co
INBASE_SUPABASE_ANON_KEY=<offentlig anon/publishable nøgle>
```

**Aldrig** `service_role`-nøgle, databaseadgangskode eller andre privilegerede
hemmeligheder i Windows-programmet – `config.py` afviser dem. Adgang styres
af brugerens login (Supabase Auth) og RLS-politikkerne.

## Datamodel (kort)

```
people ──< employment_records ──< lifecycle_cases ──< case_tasks
                                        │          ├──< case_reminders
                                        │          └──< audit_events (insert-only)
workflow_templates ──< workflow_template_tasks
                  └──< workflow_template_versions
areas, positions, message_templates, notification_rules, user_profiles
```

* Personens identitet (`people`) er adskilt fra ansættelsen
  (`employment_records`: lønnr., stilling, område, datoer) og fra sagen
  (`lifecycle_cases`: onboarding/offboarding). Genansættelse = ny ansættelse
  og ny sag på samme person.
* Lønnr. er valgfrit og unikt, når det findes – aldrig primærnøgle.
* Sager har `version` (optimistisk låsning) – samme princip som JSON-lagringen.

## Implementeringsplan

1. Tilføj `supabase` til `requirements.txt`; implementér `opret_klient()`.
2. `SupabaseAuth` i `app/services/auth_service.py`-mønstret (log på, skift
   kode via Supabase Auth – kode håndteres aldrig lokalt).
3. `app/repositories/supabase/` med `SupabaseSagRepository` m.fl., der
   opfylder `app/repositories/base.py`:
   * `gem()` = `update ... where id = :id and version = :version`; 0 rækker
     → `KonfliktFejl`. Sag + opgaver + hændelser gemmes i én transaktion
     (en PostgreSQL-funktion kaldt via RPC), så de lykkes eller fejler samlet.
4. Kør `001` og `002` i Supabase; gennemgå RLS med MASAN.
5. Kør `python -m app.infrastructure.database.migrering --data Data --ud ud`,
   importér tabellerne i rækkefølgen areas → positions → people →
   employment_records → workflow_* → message_templates → notification_rules →
   lifecycle_cases → case_tasks → case_reminders → audit_events, og
   sammenhold antal med `rapport.json`. Originaldata slettes ikke.
6. Vælg Supabase-repositories i `bootstrap.py`.

## Offline og synkronisering

Offline-tilstanden (`app/services/lagring_service.py`) virker i dag mod den
centrale JSON-mappe: lokal kopi + ændringslog + versionskontrol ved
synkronisering; konflikter overskrives aldrig. Samme strategi skal bruges mod
Supabase. Overvej SQLite til den lokale kopi og ændringskøen, når der er
mange brugere. Der skiftes aldrig automatisk mellem datakilder.
