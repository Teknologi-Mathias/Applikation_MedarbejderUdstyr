# IN-BASE med Supabase – opsætning og drift

Vejledning til projektets ejer. Følg trinene i rækkefølge første gang.
Intet i IN-BASE ændrer skemaet, sletter data eller opretter administratorer af
sig selv – alt herunder er bevidste, manuelle handlinger.

| Del | Hvor |
|---|---|
| SQL-migreringer | `app/infrastructure/database/migrations/001`–`004` |
| Engangs-nulstilling | `app/infrastructure/database/reset/nulstil_forretningsdata.sql` |
| Edge Functions | `supabase/functions/admin-create-user`, `admin-manage-user` |
| Klientkonfiguration | `%APPDATA%\IN-BASE\.env` på hver pc |
| Afvikling af gamle JSON-data | `python tools/afvikl_gamle_data.py` |

## Udgangspunkt (kontrolleret 22-10-2026)

Supabase-projektet indeholder **ingen** IN-BASE-tabeller endnu – kun tabellen
`integration_probe` med 1 række fra forbindelsestesten. Migreringerne er altså
ikke anvendt, og der er ingen gamle forretningsdata i Supabase. Den nye database
starter tom; gamle JSON-data importeres ikke.

## 1. Opret databasen (SQL Editor)

Dashboard → **SQL Editor** → **New query**. Indsæt og kør hver fil for sig,
i denne rækkefølge, og tjek at hver giver "Success":

1. `001_initial_schema.sql` – tabeller, nøgler, statusser, versionstrigger.
2. `002_rls_policies.sql` – privilegier og Row Level Security.
3. `003_rpc_functions.sql` – beskyttede funktioner (gem sag, slet sag, gem
   skabelon, brugerliste, første administrator).
4. `004_seed_standarder.sql` – de bevidste standarder: 4 områder, 4
   arbejdsgangsskabeloner, 2 mailskabeloner, 6 påmindelsesregler. Ingen
   forretningsdata. Kan køres igen uden dubletter.

Kør aldrig filerne igen på en database, hvor de allerede er anvendt (bortset
fra 004). Fremtidige ændringer kommer som nye filer `005_...`, `006_...`.

## 2. Auth-indstillinger

Dashboard → **Authentication**:

* **Sign In / Providers → "Allow new users to sign up": SLÅ FRA.** Så kan
  ingen oprette sig selv; konti oprettes kun af administratorer i IN-BASE.
  (Selv hvis nogen fik en konto, har den ingen adgang uden en IN-BASE-profil.)
* **Lad e-mail-udbyderen (Email provider) være slået TIL** – ellers blokeres
  alle e-mail-logins ("Email logins are disabled").
* **Minimum password length: 8** (samme krav som IN-BASE og Edge Functions).
* "Confirm email" er uden betydning: administratoren bekræfter adressen ved
  oprettelsen.

## 3. Fjern resterne fra forbindelsestesten

1. SQL Editor: `drop table if exists public.integration_probe;`
2. **Authentication → Users**: find testkontoen (e-mailen i
   `SUPABASE_TEST_EMAIL` i projektets gamle `.env`) → ⋯ → **Delete user**.
   Slet kun denne konto. Den må ikke genbruges som administrator.
3. Slet `test_supabase_connection.py` og linjerne `SUPABASE_URL`,
   `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_TEST_EMAIL`, `SUPABASE_TEST_PASSWORD`
   fra projektets `.env`. Den kode og de navne bruges ikke af IN-BASE.

## 4. Deploy Edge Functions

Funktionerne er den eneste vej til at oprette, nulstille og slette ANDRE
brugeres konti. De bruger servernøglen, som kun findes på Supabases server.

1. Installér Supabase CLI (fx `scoop install supabase`, eller hent
   `supabase_windows_amd64.tar.gz` fra github.com/supabase/cli/releases).
2. I projektmappen:
   ```
   supabase login
   supabase link --project-ref <projekt-ref>
   supabase functions deploy admin-create-user admin-manage-user
   ```
   `supabase/config.toml` sætter `verify_jwt = false`; funktionerne validerer
   selv sessionen (`auth.getUser`) og tjekker administratorrollen i
   `user_profiles`.
3. Servernøglen: `SUPABASE_URL` og projektets service-/secret-nøgle stilles
   automatisk til rådighed for funktionerne. Melder en funktion "Serveren
   mangler sin service-nøgle", så sæt den eksplicit (Project Settings → API
   Keys → *Secret keys*):
   ```
   supabase secrets set INBASE_SERVICE_KEY=<secret key>
   ```
   Secret-nøglen må **aldrig** i `.env` på en pc, i koden eller i `.exe`.

## 5. Den første administrator (engangsprocedure)

1. **Authentication → Users → Add user → Create new user**: din e-mail og en
   stærk adgangskode, **"Auto Confirm User" slået til**.
2. SQL Editor (kører som projektejer – funktionen kan ikke kaldes fra appen):
   ```sql
   select public.inbase_bootstrap_first_admin('din@firma.dk', 'brugernavn', 'Dit Navn');
   ```
   Funktionen afvises, hvis der allerede findes en administrator. Ingen bliver
   automatisk administrator.
3. Herefter oprettes ALLE andre brugere fra IN-BASE (trin 7).

Ændre rollen på en eksisterende bruger (ingen knap i programmet – bevidst):
```sql
update public.user_profiles set role = 'Administrator' where username = 'brugernavn';
```
Databasen afviser at fjerne den sidste administrator.

## 6. Konfiguration på hver pc

Opret `%APPDATA%\IN-BASE\.env` (fx `C:\Users\<navn>\AppData\Roaming\IN-BASE\.env`):

```
INBASE_SUPABASE_URL=https://<projekt-ref>.supabase.co
INBASE_SUPABASE_ANON_KEY=sb_publishable_<offentlig nøgle>
```

Værdierne findes under Project Settings → API Keys (*Publishable key*).
PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\IN-BASE" | Out-Null
@"
INBASE_SUPABASE_URL=https://<projekt-ref>.supabase.co
INBASE_SUPABASE_ANON_KEY=sb_publishable_<offentlig nøgle>
"@ | Set-Content -Encoding utf8 "$env:APPDATA\IN-BASE\.env"
```

* IN-BASE afviser at starte med en secret-/service_role-nøgle.
* Mangler filen, viser IN-BASE en fejl med stien – der skiftes aldrig til de
  gamle JSON-data.
* Fra kildekoden læses også `.env` i projektmappen (kun under udvikling).
* Logfiler: `%LOCALAPPDATA%\IN-BASE\Logs\in-base.log` (færdig app).

## 7. Brugere

**Opret:** IN-BASE → Indstillinger → Brugere → *+ Opret bruger*: brugernavn,
e-mail (bruges til log på), navn, rolle og en **midlertidig kode** (mindst 8
tegn). Giv koden til brugeren ad en sikker vej (ikke i samme mail som
e-mailadressen). Ved første log på skal brugeren vælge sin egen kode.

Bag knappen: Edge Function `admin-create-user` validerer din session og din
rolle i databasen, opretter Auth-kontoen (`auth.users`) og præcis én profil
(`user_profiles`) med samme UUID. Fejler profilen, slettes den nye konto
igen; er en tidligere oprettelse afbrudt (konto uden profil), fuldføres den
ved næste forsøg på samme konto.

**Hvorfor ikke e-mail-invitation?** En invitationsmail fører til en webside,
hvor koden vælges. IN-BASE er et skrivebordsprogram uden en sådan side; en
midlertidig kode + tvunget skift ved første log på giver samme sikkerhed uden
en ekstra webapp.

**Nulstil kode / slet:** samme side (Edge Function `admin-manage-user`). Man
kan ikke slette sig selv eller den sidste administrator. Navnet bevares i
tidslinjerne.

## 8. Afprøvning med to brugerprofiler

1. Pc/Windows-bruger A: start IN-BASE, log på som administratoren.
2. Opret brugeren "test.bruger" (rolle Bruger) med en midlertidig kode.
3. Pc/Windows-bruger B (med sin egen `%APPDATA%\IN-BASE\.env`): log på med
   test.brugers e-mail og den midlertidige kode → vælg ny kode.
4. A opretter en offboardingsag. B ser den (listerne opdateres automatisk
   inden for et minut) og markerer en opgave udført.
5. A og B åbner samme sag; A gemmer først, derefter B → B får "ændret af …",
   og intet overskrives.
6. B kan ikke se *Brugere*/*Data & sikkerhed* og får afslag, hvis B forsøger
   at ændre opsætning – afslaget kommer fra databasen, ikke kun fra knapperne.
7. Slet test.bruger igen, når afprøvningen er færdig.

Samme pc, to profiler: start én IN-BASE, log ud (sidebar), log på som den anden.

## 9. Gamle lokale data (JSON) afvikles

De gamle data overføres ikke. På hver pc, hvor IN-BASE har været brugt:

```
python tools/afvikl_gamle_data.py            # viser, ændrer intet
python tools/afvikl_gamle_data.py --slet     # sletter efter at du skriver SLET
python tools/afvikl_gamle_data.py --data X:\delt\IN-BASE\Data   # netværksdrev
```

Forretningsdata (slettes): `Data\medarbejdere.json`, `arkiv.json`,
`onboarding.json`, `onboarding_arkiv.json`, `skabeloner.json`,
`indstillinger.json`, `brugere.json` (gamle kode-hashes), `Data\Backup\`,
`Lokal\Offline\` og `%APPDATA%\MedarbejderUdstyr\Data\` (data fra ≤ V0.5.1).
Teknisk (beholdes, medmindre `--ogsaa-teknisk`): `notifikationslog.json`,
`praeferencer.json`, `Logs\`. Kildekode og `%APPDATA%\IN-BASE\.env` røres
aldrig. Skal HR beholde en sidste kopi, så tag den før sletning og opbevar
den efter jeres slettepolitik – uden for projektmappen.

## 10. Nulstil databasen (kun hvis nødvendigt, fx efter en testperiode)

`reset/nulstil_forretningsdata.sql` tømmer alle IN-BASE-forretningstabeller
(sager, personer, ansættelser, opgaver, rykkere, tidslinjer, skabeloner,
indstillinger, områder) og `integration_probe`, men IKKE skemaet, de faste
stillinger, brugerprofiler eller `auth`. Den kører kun, hvis
bekræftelseslinjen øverst i filen aktiveres i samme kørsel. Kør bagefter
`004_seed_standarder.sql` for at få standarderne tilbage. Programmet kan
ikke kalde nulstillingen.

## 11. Byg Windows-appen

```
.venv\Scripts\activate
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm MedarbejderUdstyr.spec           # mappe: dist\IN-BASE\IN-BASE.exe
dist\IN-BASE\IN-BASE.exe --selvtest                      # exit-kode 0 = OK (se loggen)
```

Test mappe-udgaven på en pc med `%APPDATA%\IN-BASE\.env`. Derefter evt. én fil:

```
set INBASE_ONEFILE=1
pyinstaller --noconfirm MedarbejderUdstyr.spec           # dist\IN-BASE.exe
```

Appen kræver hverken Python, database-adgangskode eller servernøgle.
Konfigurationen indlejres ikke; logs skrives i `%LOCALAPPDATA%\IN-BASE`.

## 12. Test

| Kommando | Kræver | Dækker |
|---|---|---|
| `python -m unittest discover -s tests -t .` | intet | domæne, services, JSON, konfiguration, mapping, Auth-service (mock) |
| `python tools/lokal_testdatabase.py` + `set INBASE_LOKAL_PGRST_URL=http://127.0.0.1:3999` + `python -m unittest tests.test_supabase_lokal` | Docker | repositories + SQL + RLS mod en lokal PostgreSQL/PostgREST, administratorregler i SQL |
| `tests.test_supabase_e2e` (se filens docstring) | Docker + Supabase CLI (`supabase start` + `supabase functions serve`) | Auth-login, Edge Functions, oprettelse/nulstilling/sletning, to "pc'er" |

E2E-testen opretter og sletter konti og kører kun med
`INBASE_E2E_OPRET_BRUGERE=1`. Brug den mod en lokal `supabase start` eller et
separat testprojekt – aldrig mod produktionsdata.

## Kendte begrænsninger

* **Ingen offline:** uden forbindelse vises en fejl; intet gemmes lokalt.
* **Backup** tages af Supabase (afhænger af abonnement; gratis projekter har
  ingen automatisk backup og sættes på pause efter en uge uden aktivitet).
* **Tidszone:** tidspunkter vises i pc'ens lokale tid (forudsætter dansk tid).
* **Rolleskift** sker med SQL (trin 5) – der er ingen knap i programmet.
