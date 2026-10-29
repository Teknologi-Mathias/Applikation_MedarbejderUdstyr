# IN-BASE – build og release

En ny version bygges med én kommando fra projektmappen:

```powershell
.\scripts\build_windows.ps1
```

Resultat: `release\IN-BASE-Setup-v<version>.exe` + `.sha256`.

## Tre måder at køre IN-BASE på

| | Hvad | Bruges til |
|---|---|---|
| **Udviklingsstart** | `python main.py` fra `.venv` | Daglig udvikling. Læser `.env` i projektmappen og `%APPDATA%\IN-BASE\.env`; logs i `Lokal\`. |
| **PyInstaller-build** | `dist\IN-BASE\IN-BASE.exe` + `_internal\` | Mellemtrin: hele appen inkl. Python, Qt og Supabase-klienten i én mappe. Kan startes direkte til test. |
| **Installer** | `release\IN-BASE-Setup-v<version>.exe` | Det, brugerne får. Installerer mappen ovenfor, laver genveje og afinstallation. Kræver ikke Python. |

Den installerede app læser KUN `%APPDATA%\IN-BASE\.env`. Den fil lægger
installeren selv på plads (se "Forbindelsen til Supabase" nedenfor) og skriver logs i
`%LOCALAPPDATA%\IN-BASE`. Ingen af delene ligger i installationsmappen, så
de bevares ved opgradering og afinstallation.

## Første opsætning (én gang pr. build-pc)

1. **Python 3.12+** (projektet bruges med 3.14) – python.org.
2. **Virtuelt miljø og pakker** – fra projektmappen:
   ```powershell
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements-build.txt
   ```
   `requirements-build.txt` = `requirements.txt` (kørsel) + PyInstaller.
3. **Inno Setup 6 eller 7**:
   ```powershell
   winget install --id JRSoftware.InnoSetup -e
   ```
   eller hent det fra https://jrsoftware.org/isdl.php. Scriptet finder
   `ISCC.exe` i `Program Files`, `Program Files (x86)` og
   `%LOCALAPPDATA%\Programs`. Ligger det andetsteds:
   `.\scripts\build_windows.ps1 -InnoSetupPath "C:\...\ISCC.exe"` eller
   miljøvariablen `INBASE_ISCC`.
4. Tillad evt. lokale scripts: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Pakkerne installeres ikke på ny ved hver release – scriptet tjekker kun, at
de findes.

## Udgiv en ny version

1. **Ret versionsnummeret ét sted:** `__version__` i `app/__init__.py`
   (semantisk: `MAJOR.MINOR.PATCH`, fx `0.7.1` → `0.7.2` for rettelser,
   `0.8.0` for nye funktioner). Visningen "V0.7.1" i programmet, .exe-filens
   versionsinfo, installeren og filnavnet følger automatisk. Versionen øges
   aldrig af sig selv.
2. **Commit** ændringerne. Scriptet bygger kun fra en ren arbejdskopi
   (`git status`), så en release altid kan genskabes fra et commit
   (`-TilladUcommittet` til en afprøvningsbuild, der ikke kan udgives).
3. **Byg:**
   ```powershell
   .\scripts\build_windows.ps1
   ```
   Trin: miljøtjek → version → git (ren arbejdskopi, commit) → hele den lokale
   testpakke → ryd `build\pyinstaller` og `dist\IN-BASE` → PyInstaller → kontrol
   af appen (version, assets, SSL-certifikater, ingen `.env`/persondata,
   `--selvtest`) → Inno Setup (højst 50 MB) → SHA-256 + følgefil `.json` (version,
   påkrævet skema, commit) → rapport. Fejler et trin, stopper scriptet med
   `RELEASE IKKE GENNEMFØRT` og exit-kode 1. (`-Udgiv` udgiver direkte fra
   buildet – normalt gøres det i programmet, se trin 6.)
4. **Find resultatet** i `release\`:
   ```
   release\IN-BASE-Setup-v0.7.1.exe
   release\IN-BASE-Setup-v0.7.1.exe.sha256
   ```
   Tidligere versioner bliver liggende. Bygges samme version igen, erstattes
   den – det står i rapporten. `release\` er udelukket fra Git.
5. **Afprøv** som pilotbruger (den centrale opdatering henter den selv – se
   nedenfor) eller med installeren på en anden pc:
   * Kør installeren → start IN-BASE → log på → åbn en sag.
   * Programmets version står nederst i sidebaren og på login-skærmen;
     installerens version under *Indstillinger → Apps* i Windows.
   * Kontrolsum: `Get-FileHash .\IN-BASE-Setup-v0.7.1.exe -Algorithm SHA256`
     skal give værdien i `.sha256`-filen.
   * Opgradering: installér den nye version oven på den gamle – konfiguration
     og login bevares.
6. **Udgiv i IN-BASE:** *Indstillinger → Opdateringer* (kun administratorer). Træk
   `release\IN-BASE-Setup-v<version>.exe` ind i feltet (eller *Vælg fil…*), skriv
   hvad der er nyt, og klik *Udgiv til pilot*. Når pilotbrugerne har afprøvet den:
   vælg versionen og *Frigiv til alle…* (evt. 25 %, så 100 %).
7. **Tag** commit'et i git (`v<version>`) – scriptet tagger aldrig selv.

### Hvilke tests kører scriptet – og hvorfor

Scriptet kører **hele den lokale testpakke** (`python -m unittest discover -s
tests -t .`, ca. 2 minutter): domæne, services, samtidighed/fletning, UI
(offscreen), konfiguration, release og opdatering. Docker- og E2E-testene
springer selv over. Plus selvtesten af den byggede .exe.

Ved ændringer i migreringer, RLS eller RPC'er køres også integrationstesten mod
den lokale database, før releasen bygges (VS Code-tasken "Tests: lokal
Supabase-integration (Docker)" eller `INBASE_LOKAL_PGRST_URL=http://127.0.0.1:3999`
+ `pytest tests/test_supabase_lokal.py`).

| Ændring | Kør mindst |
|---|---|
| Tekst/layout i én side | `ruff check --select F` + den berørte testfil |
| Domæne/services | + `test_services`, `test_samtidighed`, `test_arbejdsspor`, `test_behov` |
| Migrering, RLS, RPC | + Docker-integrationen |
| Release | buildscriptet (hele den lokale pakke + selvtest) |

## Central opdatering (alle klienter fra Supabase)

IN-BASE opdaterer sig selv. Klienterne tjekker ved log på og hver 4. time
(`app/services/opdatering_service.py`), henter en ny installer i baggrunden fra
den private Storage-bucket `releases`, kontrollerer SHA-256 og spørger brugeren
"Opdater og genstart". Installeren kører stille (`/OPDATERING=1`) og starter
IN-BASE igen. Ingen administratorrettigheder; konfiguration og login bevares.

Udgivelse sker i **IN-BASE → Indstillinger → Opdateringer** (kun administratorer):

* **Ny version:** træk installeren ind. Pakken kontrolleres, før noget sendes:
  filnavn, versionen inde i exe-filen (et omdøbt build afvises), størrelse (højst
  50 MB), kontrolsum (`.sha256`), følgefilen `.json` fra buildet (skemakrav + commit),
  at versionen er nyere end alt udgivet, og at **databasen har det skema, versionen
  kræver** (ellers: kør migreringerne først – klienterne ville ikke kunne starte).
  Uploaden kører i baggrunden; versionen udgives til **pilot**.
* **Udgivne versioner:** *Frigiv til alle…* (andel i %), *Træk tilbage / gyldig igen*,
  *Kræv som mindste version…* (kun en version, der er frigivet til 100 %) og *Ryd
  gamle installere…*.

`tools\udgiv_version.py` er reserven fra kommandolinjen – med samme regler:

| Kommando (`python tools\udgiv_version.py …`) | Virkning |
|---|---|
| `udgiv <installer> [--noter] [--tvungen]` | Kontrol + upload + registrering som **pilot** (det gør `-Udgiv`). |
| `frigiv <version> [--procent N]` | **Stabil** for alle (eller N % – gradvis udrulning). |
| `tilbagetraek <version> [--fortryd]` | Stopper versionen. Klienter på den går tilbage til den nyeste gyldige. |
| `minimum <version>` | Ældre klienter skal opdatere, før de kan arbejde videre. |
| `status` | Udgivelser og hvilken version hver bruger sidst kørte. |
| `ryd [--behold 5]` | Sletter gamle installere fra Storage. |

* **Pilotbrugere** sættes under *Indstillinger → Brugere → Pilotkanal til/fra*.
  Kolonnerne *Version* og *Kanal* viser, hvad hver bruger kører.
* **Rækkefølge ved databaseændringer:** (1) additiv migrering, der slutter med en
  række i `schema_migrations`, (2) hæv `KRAEVET_SKEMA` i `app/__init__.py`, hvis
  klienten afhænger af migreringen, (3) byg og udgiv, (4) frigiv, (5) når alle kører
  den nye version: `minimum`. En klient, der kræver et nyere skema end databasen,
  stopper med en klar besked i stedet for at miste felter lydløst.
* **Rollback:** `tilbagetraek` den dårlige version – klienterne går selv tilbage til
  den nyeste gyldige. Eller udgiv en rettelse med et højere versionsnummer.
* **Supabase Free:** højst 50 MB pr. fil (buildet stopper ved større installer) og
  begrænset udgående trafik pr. måned. Udgiv gerne ofte til pilot, men frigiv til
  stabil samlet (fx ugentligt) og kør `ryd` jævnligt. Pakkestørrelse: spec'en
  udelader ubrugte Qt-dele (Quick/QML, PDF, software-OpenGL, oversættelser), og
  `requirements.txt` bruger `PySide6-Essentials`.
* **Første gang:** versioner før den centrale opdatering (0.9.x) kan ikke opdatere
  sig selv. Kør migrering 019, og installér den første version med opdatering
  manuelt på alle pc'er – derefter sker det af sig selv.
* **Fejlfinding:** klientens log (`%LOCALAPPDATA%\IN-BASE\Logs\in-base.log`) og
  installerens log (`%LOCALAPPDATA%\IN-BASE\Opdateringer\installer.log`). En hentet
  installer, der ikke passer med kontrolsummen, slettes og køres aldrig.
* **Ikke afprøvet endnu (gør det på en pilot-pc):** at Inno Setup ruller korrekt
  tilbage, hvis en installation afbrydes efter `[InstallDelete]` af `_internal`.

## Installeren (installer\IN-BASE.iss)

* `AppId` `{C5BFD02A-D4D8-418F-8093-BC7609B78B60}` er fast for alle versioner –
  derfor opgraderer en ny version den gamle. **Må aldrig ændres.**
* Installerer altid pr. bruger i `%LOCALAPPDATA%\Programs\IN-BASE` uden
  administratorrettigheder.
* Startmenu-genvej; skrivebordsgenvej kan vælges.
* Ved opgradering slettes kun `{app}\_internal` (gamle biblioteker), før de nye
  kopieres ind. Kører IN-BASE (også ved uret), bedes den lukket.
* Afinstallation fjerner kun programfilerne. Konfiguration
  (`%APPDATA%\IN-BASE`) og logs (`%LOCALAPPDATA%\IN-BASE`) bliver liggende.
  Skal de væk, slettes de manuelt efter afinstallation – fx ved udskiftning
  af pc: `Remove-Item "$env:APPDATA\IN-BASE", "$env:LOCALAPPDATA\IN-BASE" -Recurse`.
* Installeren rører aldrig Supabase-databasen.

### Forbindelsen til Supabase (`%APPDATA%\IN-BASE\.env`)

* Buildscriptet laver filen med `tools\lav_klientkonfig.py` ud fra
  projektets `.env` – **kun** `INBASE_SUPABASE_URL` og
  `INBASE_SUPABASE_ANON_KEY`. Testlogin og alt andet i `.env` kommer aldrig
  med, og en secret-/service_role-nøgle stopper buildet.
* Andet projekt (fx et testprojekt):
  `.\scripts\build_windows.ps1 -KlientKonfig C:\sti\til\andet.env`.
* Installeren lægger filen i `%APPDATA%\IN-BASE\.env` **kun hvis den mangler**
  (`onlyifdoesntexist`) og fjerner den ikke ved afinstallation
  (`uninsneveruninstall`). En rettet konfiguration overlever altså
  opgraderinger. Skifter I Supabase-projekt, skal filen rettes/slettes på
  pc'erne – en ny installer overskriver den ikke.
* Filen ligger ikke i `IN-BASE.exe` eller installationsmappen; buildet stopper,
  hvis en `.env` havner i app-mappen.
* Publishable-nøglen er offentlig af natur (den findes i enhver klient);
  adgangen beskyttes af brugerens login og RLS i databasen.

## Fejlfinding

* **Hvor står fejlen?** I konsollen under det trin, der fejlede (scriptet
  skriver `[n] ...` for hvert trin). PyInstaller-detaljer:
  `build\pyinstaller\MedarbejderUdstyr\warn-MedarbejderUdstyr.txt`.
  Selvtest-fejl: `build\pyinstaller\selvtest\Logs\in-base.log`.
  Den installerede apps log: `%LOCALAPPDATA%\IN-BASE\Logs\in-base.log`.
* **Manglende Python-pakke:**
  `.venv\Scripts\python.exe -m pip install -r requirements-build.txt`
* **Ny runtime-pakke** (fx et nyt bibliotek med dynamiske imports): tilføj den
  til `requirements.txt` og – hvis den mangler i den byggede app – til
  `_skjulte`/`collect_data_files` i `MedarbejderUdstyr.spec`. Byg igen;
  `--clean` sikrer, at intet gammelt genbruges.
* **Nye eller ændrede assets** (ikon, logo): læg dem i `assets\` (pakkes
  automatisk med) og byg igen. Nyt ikon: `python tools\lav_ikon.py`.
* **Inno Setup ikke fundet:** se "Første opsætning", trin 3.
* **"scripts er deaktiveret på dette system":** se trin 4, eller kør
  `powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1`.

## Filer

| Fil | Rolle |
|---|---|
| `app/__init__.py` | `__version__` – eneste versionskilde |
| `MedarbejderUdstyr.spec` | PyInstaller (onedir; `INBASE_ONEFILE=1` giver én .exe uden installer) |
| `installer/IN-BASE.iss` | Inno Setup |
| `scripts/build_windows.ps1` | Hele releasen i én kommando |
| `requirements-build.txt` | Kørselspakker + PyInstaller |
| `tools/lav_klientkonfig.py` | Laver installerens `%APPDATA%\IN-BASE\.env` (kun URL + publishable-nøgle) |
| `tools/udgiv_version.py` | Central opdatering: udgiv, frigiv, tilbagetræk, minimum, status, ryd |
| `app/services/opdatering_service.py` | Klientens tjek, download og installation (regler: `app/domain/opdatering.py`) |
| `tests/test_release.py` | Tests af versions- og buildkonfigurationen |
| `tests/test_opdatering.py` | Versionsvalg, skemavagt og download med kontrolsum |
