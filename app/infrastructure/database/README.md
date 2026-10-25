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
auth.users ──1:1── user_profiles (brugernavn, rolle, active, tema, must_change_password)
   (e-mail = internt login-alias)
user_profiles ──< development_requests ──< development_request_comments
 (indsender/ansvarlig)                 └──< development_request_events (insert-only)
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

## Nyt felt – uden at duplikere databasekode

1. Ny migrering `00N_<navn>.sql`: `alter table public.<tabel> add column ...;`
2. Én linje i det relevante feltkort i `repositories/supabase/mapping.py`,
   fx `("telefon", "phone", TEKST)` i `PERSON_FELTER`.
3. Feltet i domænets `til_dict()`/`fra_dict()` (som for JSON).

RPC-funktionerne udleder selv kolonnelisten fra tabellen, så de skal ikke
ændres. UI, services og controllere kalder ikke databasen og berøres kun, hvis
feltet skal vises/redigeres.

Ny tabel/funktion: migrering (tabel + RLS-politik + grants), metode i et
repository i `repositories/supabase/`, evt. grænseflade i `repositories/base.py`
og valg i `bootstrap.py`.
