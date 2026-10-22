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
* **Indstillinger** – tema, notifikationer, adgangskode, offline, påmindelser
  og (for administratorer) organisation, brugere og data & sikkerhed.

Arkitekturen er beskrevet i [docs/ARKITEKTUR.md](docs/ARKITEKTUR.md), og
databaseforberedelsen i
[app/infrastructure/database/README.md](app/infrastructure/database/README.md).

## Kom i gang (udvikling)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Første gang findes kun brugeren **admin / admin** – skift koden under
*Indstillinger → Generelt*.

Valgfrie miljøvariabler (se `.env.example`):

| Variabel | Betydning |
|---|---|
| `INBASE_DATA` | Central datamappe (standard: `Data/` ved programmet). Kan være et netværksdrev. |
| `INBASE_LOKAL` | Lokal mappe til offline-kopi, log og præferencer (standard: `Lokal/`). |
| `INBASE_SUPABASE_*` | Forberedt – Supabase er ikke tilsluttet endnu. |

## Tests

```
python -m unittest discover -s tests -t .
```

Testene kører i midlertidige mapper og rører aldrig rigtige data. UI-testene
kører offscreen.

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
    backup_service.py, lagring_service.py (online/offline + synkronisering)
  repositories/                 base.py (grænseflader), fejl.py, json/ (nuværende lagring)
  infrastructure/               stier.py, logning.py, database/ (Supabase – forberedt)
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

## Data, offline og sikkerhed

* **Central datamappe** (`Data/`): sager, skabeloner, brugere, indstillinger.
  Ældre data migreres automatisk ved opstart – efter en backup.
* **Arbejd offline** (*Indstillinger → Generelt*): lokal kopi + ændringslog;
  synkroniseres med versionskontrol, når du går online. Konflikter
  overskrives aldrig – du vælger selv. Der skiftes aldrig automatisk.
* **Backup:** dagligt og testet; gendannelse tager først en backup.
* **Login er BETA:** adgangskoder gemmes som saltede hashes, men brugerfilen
  er ikke beskyttet. Reel adgangskontrol kommer med Supabase Auth + RLS.

Læg programmet i en mappe brugerne kan skrive i, **ikke** i `C:\Program Files`.

## Byg Windows-program

```
pyinstaller MedarbejderUdstyr.spec
```

Resultatet er `dist/IN-BASE.exe`. `Data/` og `Lokal/` oprettes ved siden af.
Versionen (vist i Jobliste og Egenskaber) læses fra `VERSION` i `app/__init__.py`.

## Logo og ikon

* `assets/IN-BASE-logo.svg` / `IN-BASE logo.png` – det originale logo.
* `assets/IN-BASE-ikon.svg` – samme grafik, kvadratisk beskåret, så det er
  tydeligt i små størrelser (proceslinje, Jobliste, notifikationer).
* `assets/IN-BASE.ico` – Windows-ikonet (16–256 px). Ændres logoet, så ret
  `IN-BASE-ikon.svg` og kør `python tools/lav_ikon.py`.
