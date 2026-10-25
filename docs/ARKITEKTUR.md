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
| Brugernavnsregler | `app/domain/bruger.py` |
| Login-alias (brugernavn → Supabase Auth) | `app/repositories/supabase/mapping.py` (`login_alias`) |
| Brugeradministration (server) | `supabase/functions/admin-create-user`, `admin-manage-user` |
| Ønsker & Udvikling | `app/domain/indmelding.py`, `app/services/indmelding_service.py`, `app/ui/indmelding_side.py`, `indmelding_dialog.py` |
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

## Login, session og adgang

* Login med brugernavn + adgangskode. `SupabaseAuthService` normaliserer
  brugernavnet; `SupabaseKontoRepository` oversætter det til kontoens interne,
  ikke-leveringsbare login-alias (`hafra@brugere.in-base.invalid`), fordi
  Supabase Auth kun logger på med e-mail/telefon. Supabase Auth kontrollerer
  koden; aliaset forlader aldrig repository-laget.
* Adgang kræver en AKTIV profil i `user_profiles` (`inbase_is_member()`,
  migrering 005). Rollen læses altid fra databasen.
* Sessionen ligger kun i hukommelsen (`persist_session=False`). Hovedvinduet
  kalder hvert minut `auth.kontroller_session()`; er sessionen udløbet, kontoen
  deaktiveret eller rollen ændret, kastes `SessionUdloebetFejl`, og
  hovedvinduet logger ud på én fælles måde (`ui/fejl.py` →
  `saet_session_haandtering`): åbne dialoger lukkes, timeren stoppes, data
  fjernes fra siderne, log på vises.
* Andre brugeres konti administreres kun af Edge Functions (servernøglen er
  aldrig i klienten). Den første administrator oprettes med
  `inbase_bootstrap_first_admin()` i SQL Editor – der findes ingen standardbruger.

## Ønsker & Udvikling

Selvstændigt menupunkt (ikke en del af onboarding/offboarding) – virksomhedens
fælles forbedringskø for fejlmeldinger, ønsker, automatisering, data/ERP og
arbejdsgange.

* Domæne (`indmelding.py`): kategorier, 8 statusser, tilladte
  statusovergange, 4 prioriteter. Samme værdier i migrering 006 (en test
  sikrer, at de stemmer overens).
* Service (`indmelding_service.py`): validering og rettigheder med tydelige
  beskeder. Databasen håndhæver de samme regler (RLS + RPC), også uden om
  programmet.
* Data (migrering 006): `development_requests` (UUID + løbenummer, version til
  optimistisk låsning), `development_request_comments` (`internal` = note kun
  for administratorer) og `development_request_events` (historik pr. felt,
  insert-only). Indsender/forfatter sættes af RPC'erne ud fra `auth.uid()`.
* Rettigheder: alle medlemmer ser køen, opretter og kommenterer; indsenderen
  retter egen tekst, mens status er *Indsendt*; kun administratorer ændrer
  status, prioritet, ansvarlig, planlagt version og løsning, skriver interne
  noter og sletter.
* UI: `IndmeldingSide` bygger på den fælles `SagListeSide` (søgning i titel og
  beskrivelse, filtre for visning/status/kategori/prioritet);
  `IndmeldingDialog` har fanerne Detaljer, Behandling, Kommentarer og Historik.

## Adgang pr. modul

Administratorer ser alt. Andre brugere har en liste af moduler på profilen
(`user_profiles.module_access`, migrering 010). Listen sættes under Indstillinger →
Brugere → Moduladgang. NULL betyder standarden: Onboarding, Offboarding og Ønsker &
Udvikling. Reglerne ligger i `app/domain/adgang.py`.

* Moduler uden adgang vises med 🔒 i menuen. I stedet for siden vises `LaastSide`,
  og modulets data hentes ikke.
* Låsen gælder i programmet. Kun Telefoner er også låst i databasen
  (`inbase_has_module('telefoner')`).
* Ændrer en administrator adgangen, logges brugeren ud ved næste sessionstjek,
  ligesom ved rolleskift.

## Telefoner (MDM)

Selvstændigt menupunkt, kun for administratorer. Driftstelefoner registreres ved
ERP-enhedsnavn (fx ISM589, unikt) og klargøres med QR-kode direkte fra IN-BASE –
uden server. Drift: [MDM_OPSAETNING.md](MDM_OPSAETNING.md).

* `android/` er IN-BASE Klargøring, en lille Device Owner-app i Java. Den bygges
  til `assets/mdm/inbase-klargoering.apk` (`scripts/byg_klargoering_apk.ps1`) og
  pakkes med i programmet. Den låser telefonen, skjuler apps, sætter baggrund,
  installerer FL-UPDATE og melder tilbage – alt sammen offline på telefonen.
* QR-koden (`infrastructure/mdm/qr.py`) indeholder downloadadressen på pc'en,
  APK'ens SHA-256, Wi-Fi og ekstra-data (enhedsnavn, engangskode, FL-UPDATE-link).
* `infrastructure/mdm/lokal_server.py` er en midlertidig http-server (port 8765).
  Den kører kun, mens klargøringsvinduet er åbent. Rapporten fra telefonen kræver
  engangskoden og flyttes til UI-tråden med et Qt-signal.
* Supabase: én række pr. telefon (`mdm_devices`, migrering 007 + 008). Der
  skrives kun ved oprettelse, rettelser og når en telefon melder sig klargjort.
  Der er ingen fjernstyring og ingen baggrundstrafik.
* Google Android Management API blev fravalgt, fordi Google siden oktober 2025
  ikke tillader interne løsninger (kvote 0 uden godkendelse).

## Data og samtidighed (Supabase)

* Sager gemmes via RPC `inbase_save_case`: sag, person, ansættelse og de
  ændrede opgaver/rykkere + nye tidslinjehændelser i én transaktion.
  Versionen tjekkes i databasen; afviger den → `KonfliktFejl`.
* Repositoryet husker rækkerne fra sidste hentning og sender kun forskellen.
  Skrivninger gentages aldrig automatisk (ingen dubletter ved netværksfejl).
* Hovedvinduet tjekker hvert minut en let signatur (antal + seneste
  `updated_at` pr. proces) og genindlæser kun ved ændringer.
* RLS: alle medlemmer (brugere med aktiv profil) deler sager; opsætning,
  brugere og permanent sletning kun for administratorer; tidslinjen er insert-only.

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
  udvikling og tests. Ingen standardbruger: første administrator via
  `tools/opret_json_administrator.py`.
* Ønsker & Udvikling: ingen vedhæftede filer, ingen e-mailnotifikationer og
  ingen integration med eksterne udviklingssystemer i første version.
  Vedhæftninger kræver sikker fillagring med adgangskontrol (fx Supabase
  Storage med RLS-politikker pr. indmelding) – en mulig senere udvidelse.
  Kommentarer fra andre ses, når detaljerne åbnes igen (ingen live-opdatering).
