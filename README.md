# IN-BASE

**Interne processer, samlet ét sted.**
Et fælles sted til opfølgning, automatisering, dokumentation og sammenhæng
mellem virksomhedens eksisterende systemer.

Moduler:

* **Onboarding** – fra kandidat til aktiv medarbejder (stilling, område,
  milepæle: kandidat → kontrakt → første oplæring → jobs).
* **Offboarding** – afvikling af fratrådte medarbejdere: udstyr, rykkere,
  arkiv.
* **Dashboard / Action Center** – det, der kræver handling, på tværs af
  modulerne, samt nøgletal.
* **Ønsker & Udvikling** – virksomhedens fælles forbedringskø: fejlmeldinger,
  nye ønsker, automatisering, data/ERP og arbejdsgange – fra *Indsendt* til
  *Udgivet*, med prioritet, ansvarlig, kommentarer og historik.
* **Telefoner (MDM)** – kun administratorer: registrerer driftstelefoner ved
  ERP-enhedsnavn og klargør dem med QR-kode direkte fra IN-BASE (uden server).
  Kun basale apps, FL-UPDATE/FL-TMS og låst til drift. Se [docs/MDM_OPSAETNING.md](docs/MDM_OPSAETNING.md).
* **Indstillinger** – tema, notifikationer, adgangskode, offline, påmindelser
  og (for administratorer) organisation, brugere og data & sikkerhed.

Data ligger i en fælles **Supabase**-database, så flere brugere på forskellige
pc'er arbejder i de samme sager. Arkitekturen er beskrevet i
[docs/ARKITEKTUR.md](docs/ARKITEKTUR.md), opsætning og drift af Supabase i
[docs/SUPABASE_OPSAETNING.md](docs/SUPABASE_OPSAETNING.md) og databaselaget i
[app/infrastructure/database/README.md](app/infrastructure/database/README.md).

## Kom i gang (udvikling)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Konfiguration (se `.env.example`) i `%APPDATA%\IN-BASE\.env` eller – under
udvikling – `.env` i projektmappen:

| Variabel | Betydning |
|---|---|
| `INBASE_SUPABASE_URL` | Projektets URL, `https://<ref>.supabase.co`. |
| `INBASE_SUPABASE_ANON_KEY` | Den OFFENTLIGE publishable/anon-nøgle (aldrig secret/service_role). |
| `INBASE_BACKEND=json` | Kun udvikling/tests: den gamle lokale JSON-lagring (`INBASE_DATA`). |
| `INBASE_LOKAL` | Lokal mappe til log og notifikationslog (standard: `Lokal/`, færdig app: `%LOCALAPPDATA%\IN-BASE`). |

Uden konfiguration starter IN-BASE ikke (der skiftes aldrig stiltiende til
lokale data). Log på sker med brugernavn (fx `HAFRA`) og adgangskode – Supabase
Auth kontrollerer koden via et internt login-alias, og der bruges ingen e-mail.
Der findes ingen standardbruger; den første administrator oprettes efter
docs/SUPABASE_OPSAETNING.md (afsnit 5).

## Tests

```
python -m unittest discover -s tests -t .
```

Testene kører i midlertidige mapper og rører aldrig rigtige data. UI-testene
kører offscreen. Integrationstests mod en lokal database i Docker og mod en
lokal Supabase er beskrevet i docs/SUPABASE_OPSAETNING.md, afsnit 12.

## Struktur

```
main.py                         Opstart: logning → services → data → log på → vindue
app/
  bootstrap.py                  Vælger implementeringer og bygger alle services
  session.py                    Hvem er logget ind
  domain/                       Sager, opgaver, tidslinje, skabelonregler (ingen I/O)
    sag.py                      Fælles basis: opgaver, milepæle, version, manuel status
    onboarding.py / offboarding.py   Modulernes sagstyper og statusregler
    opgave.py, rykker.py, historik.py, skabelon.py
  services/                     Forretningsregler – det eneste UI'en kalder
    workflow.py                 Fælles arbejdsgangsmotor (opgaver fra skabelon, tidslinje)
    sag_service.py              Fælles sagshandlinger + onboarding_/offboarding_service.py
    action_center.py, paamindelser.py, rapport_service.py
    skabelon_service.py, auth_service.py, indstillinger_service.py
    backup_service.py (kun JSON), lagring_service.py (online; offline kun JSON)
  repositories/                 base.py (grænseflader), fejl.py,
    supabase/                   ALLE Supabase-kald + mapping.py (domæne ↔ kolonner)
    json/                       lokal JSON-lagring (udvikling/tests)
  infrastructure/               stier.py, logning.py, database/ (konfiguration,
                                forbindelse, SQL-migreringer, nulstilling)
    mdm/                        Telefoner (MDM): QR-kode og midlertidig klargøringsserver
supabase/functions/             Edge Functions: admin-create-user, admin-manage-user
android/                        IN-BASE Klargøring: Android-styrings-app (bygges til assets/mdm/)
  ui/                           Vinduer, sider, dialoger og controllere
tests/                          unittest-tests
docs/ARKITEKTUR.md              Lag, indgangspunkter og begrænsninger
```

## Status og regler

* **Offboarding:** alle obligatoriske opgaver udført/undtaget → *Afviklet*;
  noget påbegyndt → *Delvist afleveret*; ellers *Afventer Udstyr*.
* **Onboarding:** den første milepæl, der ikke er færdig, bestemmer status;
  opgaver under senere milepæle er låste. Springer en manuel status over
  manglende krav, er det en *kritisk overstyring* (begrundelse påkrævet,
  registreres i tidslinjen). Annullering arkiverer forløbet.
* Alle statusskift registreres i tidslinjen og bruges af nøgletallene.

## Skabeloner

Rettes under *Onboarding → Skabeloner*, *Offboarding → Skabeloner og mails*
og *Indstillinger → Påmindelser* (kun administratorer, kun online).
Arbejdsgangsskabeloner versionsstyres: ændringer gemmes som ny version og
påvirker kun nye forløb.

## Data, adgang og sikkerhed

* **Supabase** er den eneste fælles datakilde. Hver ændring gemmer kun den
  berørte sag (atomisk, med versionskontrol – samtidige ændringer giver
  "ændret af …", aldrig overskrivning).
* **Adgang** håndhæves i databasen (Row Level Security): kun brugere med en
  IN-BASE-profil ser data; kun administratorer ændrer opsætning, opretter
  brugere og sletter permanent. Tidslinjen kan ikke ændres.
* **Brugere** oprettes af en administrator i programmet (Edge Function med
  servernøgle – aldrig i klienten) og vælger egen kode ved første log på.
* **Ingen offline:** uden forbindelse vises en fejl, og intet gemmes lokalt.
* **Backup** tages af Supabase. Gamle JSON-data overføres ikke – se
  `tools/afvikl_gamle_data.py`.

## Byg Windows-program og installer

Ret versionen i `app/__init__.py` (`__version__`) og kør:

```powershell
.\scripts\build_windows.ps1
```

Resultatet er `release\IN-BASE-Setup-v<version>.exe` + SHA-256-kontrolsum.
Opsætning, afprøvning og fejlfinding: [docs/RELEASE.md](docs/RELEASE.md).
Installeren lægger forbindelsen til Supabase (URL + offentlig nøgle fra
projektets `.env`) i `%APPDATA%\IN-BASE\.env`, hvis filen mangler – den ligger
ikke i selve .exe-filen og overskrives aldrig ved opgradering.

## Logo og ikon

* `assets/IN-BASE-logo.svg` / `IN-BASE logo.png` – det originale logo.
* `assets/IN-BASE-ikon.svg` – samme grafik, kvadratisk beskåret, så det er
  tydeligt i små størrelser (proceslinje, Jobliste, notifikationer).
* `assets/IN-BASE.ico` – Windows-ikonet (16–256 px). Ændres logoet, så ret
  `IN-BASE-ikon.svg` og kør `python tools/lav_ikon.py`.
