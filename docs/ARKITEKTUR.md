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
 Repositories app/repositories/ base.py (grænseflader) + json/ (i dag)
             │
 Infrastructure app/infrastructure/ stier, logning, database/ (forberedt)
```

Regler:
* UI indeholder ingen forretningsregler, ingen filadgang og ingen SQL.
  Handlinger går via controllere (`app/ui/modul_controller.py`) til services.
* Services får deres repositories via konstruktøren (se `bootstrap.py`).
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
| Login og adgangskoder | `app/services/auth_service.py` |
| Offline og synkronisering | `app/services/lagring_service.py` |
| Backup og slettepolitik | `app/services/backup_service.py` |
| Tema | `app/ui/theme.py` |
| Database (forberedt) | `app/infrastructure/database/` |

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

## Data og samtidighed (JSON)

* Sager identificeres med UUID (`id`, `person_id`) – aldrig lønnr.
* Hver skrivning læser filen forfra og ændrer kun én sag; versionsnummeret
  afviser samtidige ændringer (`KonfliktFejl`).
* Arkivering skriver målfilen først; findes en sag i begge filer, vises den
  som arkiveret.
* Ældre data migreres ved opstart – efter en automatisk backup.

## Kendte begrænsninger

* JSON-filer på et delt drev er ikke en rigtig flerbrugerdatabase; låsning
  sker pr. sag ved skrivning (optimistisk), ikke på filniveau.
* Login/roller er BETA: brugerfilen ligger i datamappen og kan redigeres af
  alle med adgang. Reel adgangskontrol kræver Supabase Auth + RLS.
* Tidspunkter gemmes som lokal tid uden tidszone (konverteres ved migrering).
* Supabase er ikke tilsluttet – se `app/infrastructure/database/README.md`.
