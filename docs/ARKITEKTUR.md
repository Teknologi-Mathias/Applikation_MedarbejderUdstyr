# IN-BASE – arkitektur

## Lag

```
main.py ─► app/bootstrap.py (vælger implementeringer, bygger Tjenester)
             │
 UI          app/ui/            vinduer, sider, dialoger, controllere
             │  kalder kun ▼
 Services    app/services/      forretningsregler og arbejdsgange
             │  bruger ▼                         ▲ bruger
 Domain      app/domain/        sager, opgaver, tidslinje, skabelonregler
             │
 Repositories app/repositories/ base.py (grænseflader) + supabase/ (standard)
             │                                          + json/ (udvikling/tests)
 Infrastructure app/infrastructure/ stier, logning, database/ (konfiguration,
                                     forbindelse, SQL-migreringer)
 Server       supabase/functions/  Edge Functions til brugeradministration
```

Regler:
* UI indeholder ingen forretningsregler, ingen filadgang og ingen SQL.
  Handlinger går via controllere (`app/ui/modul_controller.py`) til services.
* Services får deres repositories via konstruktøren (se `bootstrap.py`) og
  kender kun grænsefladerne i `repositories/base.py` – aldrig Supabase.
* Alle Supabase-kald ligger i `app/repositories/supabase/`; oversættelsen
  domæne ↔ kolonner kun i `mapping.py`. Forbindelse og konfiguration kun i
  `app/infrastructure/database/`.
* Domænet kender hverken UI, filer eller databaser.
* Fejl fra datalaget er typede (`app/repositories/fejl.py`) og vises ens via
  `app/ui/fejl.py`; uventede fejl logges i `Lokal/Logs/in-base.log`.

## Vigtigste indgangspunkter

| Hvad | Hvor |
|---|---|
| Opstart | `main.py` |
| Hvilken lagring bruges | `app/bootstrap.py` |
| Sagsregler (fælles) | `app/services/sag_service.py`, `app/services/workflow.py` |
| Onboarding / offboarding | `app/services/onboarding_service.py`, `offboarding_service.py` |
| Statusberegning og milepæle | `app/domain/onboarding.py`, `offboarding.py`, `sag.py` |
| Action Center | `app/services/action_center.py` |
| Påmindelser (Windows) | `app/services/paamindelser.py` |
| Nøgletal | `app/services/rapport_service.py` |
| Login og adgangskoder | `app/services/auth_service.py` (`SupabaseAuthService`) |
| Brugeroprettelse (server) | `supabase/functions/admin-create-user`, `admin-manage-user` |
| Online-krav / offline (kun JSON) | `app/services/lagring_service.py` |
| Slettepolitik (backup kun JSON) | `app/services/backup_service.py` |
| Tema | `app/ui/theme.py` |
| Database | `app/infrastructure/database/`, `app/repositories/supabase/` |
| Opsætning og drift | `docs/SUPABASE_OPSAETNING.md` |

## Fælles arbejdsgangsmotor

Onboarding og offboarding er to moduler oven på samme motor:

* `Sag` (domæne): opgaver, milepæle (opgaver låses, til forrige milepæl er
  færdig), tidslinje, version, manuel status med begrundelse.
* Skabeloner (`skabeloner.json`, slags "sager") har `proces`, `stillinger`,
  milepæl pr. opgave og versionering. Opgaver kopieres ind i sagen ved
  oprettelse, så ændrede skabeloner ikke rammer igangværende forløb.
* `workflow.registrer_aendringer()` skriver alle ændringer i tidslinjen,
  inkl. strukturerede statusskift, som nøgletallene bygger på.
* UI'en er også fælles: `SagListeSide`, `ModulOversigtSide`,
  `OpgaveOversigtSide`, `SagDialog` og `SkabelonSide` konfigureres pr. modul i
  `app/ui/moduler.py`.

## Data og samtidighed (Supabase)

* Sager gemmes via RPC `inbase_save_case`: sag, person, ansættelse og de
  ændrede opgaver/rykkere + nye tidslinjehændelser i én transaktion.
  Versionen tjekkes i databasen; afviger den → `KonfliktFejl`.
* Repositoryet husker rækkerne fra sidste hentning og sender kun forskellen.
  Skrivninger gentages aldrig automatisk (ingen dubletter ved netværksfejl).
* Hovedvinduet tjekker hvert minut en let signatur (antal + seneste
  `updated_at` pr. proces) og genindlæser kun ved ændringer.
* RLS: alle medlemmer (brugere med profil) deler sager; opsætning, brugere
  og permanent sletning kun for administratorer; tidslinjen er insert-only.

## Data og samtidighed (JSON – kun udvikling/tests)

* Sager identificeres med UUID (`id`, `person_id`) – aldrig lønnr.
* Hver skrivning læser filen forfra og ændrer kun én sag; versionsnummeret
  afviser samtidige ændringer (`KonfliktFejl`).
* Arkivering skriver målfilen først; findes en sag i begge filer, vises den
  som arkiveret.
* Ældre JSON-format opdateres ved opstart – efter en backup (kun JSON-tilstand).
  Der importeres aldrig data fra JSON til Supabase.

## Kendte begrænsninger

* Ingen offline i Supabase-tilstand: uden forbindelse vises en fejl.
* Domænet bruger lokal tid uden tidszone; den konverteres til/fra timestamptz
  i `mapping.py` (forudsætter samme tidszone på pc'erne).
* JSON-tilstandens login er BETA (brugerfil uden beskyttelse) – kun til
  udvikling og tests.
