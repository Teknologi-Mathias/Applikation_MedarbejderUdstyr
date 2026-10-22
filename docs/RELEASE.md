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

Den installerede app læser KUN `%APPDATA%\IN-BASE\.env` (se
docs/SUPABASE_OPSAETNING.md, afsnit 6) og skriver logs i
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
2. **Byg:**
   ```powershell
   .\scripts\build_windows.ps1
   ```
   Trin: miljøtjek → version → målrettede tests → ryd `build\pyinstaller` og
   `dist\IN-BASE` → PyInstaller → kontrol af appen (version, assets,
   SSL-certifikater, ingen `.env`/persondata, `--selvtest`) → Inno Setup →
   SHA-256 → rapport. Fejler et trin, stopper scriptet med
   `RELEASE IKKE GENNEMFØRT` og exit-kode 1.
3. **Find resultatet** i `release\`:
   ```
   release\IN-BASE-Setup-v0.7.1.exe
   release\IN-BASE-Setup-v0.7.1.exe.sha256
   ```
   Tidligere versioner bliver liggende. Bygges samme version igen, erstattes
   den – det står i rapporten. `release\` er udelukket fra Git.
4. **Afprøv** på en pc (helst en anden end build-pc'en):
   * Kør installeren → start IN-BASE → log på → åbn en sag.
   * Programmets version står nederst i sidebaren og på login-skærmen;
     installerens version under *Indstillinger → Apps* i Windows.
   * Kontrolsum: `Get-FileHash .\IN-BASE-Setup-v0.7.1.exe -Algorithm SHA256`
     skal give værdien i `.sha256`-filen.
   * Opgradering: installér den nye version oven på den gamle – konfiguration
     og login bevares.
5. **Commit, tag og distribution** gøres manuelt – scriptet gør det aldrig.

### Hvilke tests kører scriptet – og hvorfor

Scriptet kører kun de tests, en release afhænger af:

| Test | Hvorfor |
|---|---|
| `tests.test_release` | Én versionskilde; version i metadata og filnavn; AppId, rettigheder, ingen sletning af brugerdata; spec pakker kun assets. |
| `tests.test_database` | Konfiguration (`%APPDATA%\IN-BASE\.env`), afvisning af hemmelige nøgler, valg af backend. |
| `tests.test_supabase_enhed` | Supabase-klientens afhængigheder, fejloversættelse og mapping. |

Plus selvtesten af den byggede .exe. Det er **ikke** en test af hele
programmet. Ved ændringer i forretningslogik, UI eller database køres den
relevante del af testpakken manuelt før releasen – og hele pakken ved større
ændringer: `.venv\Scripts\python.exe -m unittest discover -s tests -t .`

## Installeren (installer\IN-BASE.iss)

* `AppId` `{C5BFD02A-D4D8-418F-8093-BC7609B78B60}` er fast for alle versioner –
  derfor opgraderer en ny version den gamle. **Må aldrig ændres.**
* Installerer pr. bruger i `%LOCALAPPDATA%\Programs\IN-BASE` uden
  administratorrettigheder (kan vælges for alle brugere i en dialog).
* Startmenu-genvej; skrivebordsgenvej kan vælges.
* Ved opgradering slettes kun `{app}\_internal` (gamle biblioteker), før de nye
  kopieres ind. Kører IN-BASE (også ved uret), bedes den lukket.
* Afinstallation fjerner kun programfilerne. Konfiguration
  (`%APPDATA%\IN-BASE`) og logs (`%LOCALAPPDATA%\IN-BASE`) bliver liggende.
  Skal de væk, slettes de manuelt efter afinstallation – fx ved udskiftning
  af pc: `Remove-Item "$env:APPDATA\IN-BASE", "$env:LOCALAPPDATA\IN-BASE" -Recurse`.
* Installeren rører aldrig Supabase-databasen.

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
| `tests/test_release.py` | Tests af versions- og buildkonfigurationen |
