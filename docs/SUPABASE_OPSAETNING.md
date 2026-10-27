# IN-BASE med Supabase – opsætning og drift

Vejledning til projektets ejer. Følg trinene i rækkefølge første gang.
Intet i IN-BASE ændrer skemaet, sletter data eller opretter administratorer af
sig selv – alt herunder er bevidste, manuelle handlinger.

| Del | Hvor |
|---|---|
| SQL-migreringer | `app/infrastructure/database/migrations/001`–`006` |
| Engangs-nulstilling | `app/infrastructure/database/reset/nulstil_forretningsdata.sql` |
| Edge Functions | `supabase/functions/admin-create-user`, `admin-manage-user` |
| Klientkonfiguration | `%APPDATA%\IN-BASE\.env` på hver pc |

**I kodebasen vs. manuelt:** Migreringer, Edge Functions og klient er færdige
i kodebasen. *Du* skal selv køre migreringerne i SQL Editor, rette
Auth-indstillingerne, deploye Edge Functions og oprette den første
administrator (trin 1, 2, 4 og 5). Det kan programmet ikke – og må ikke.

## Sådan virker login (brugernavn + adgangskode)

Brugerne logger på med **brugernavn** (fx `HAFRA`, `MASAN`, `SADAH`) og
adgangskode – ingen e-mail, ingen bekræftelsesmails, ingen
gendannelse via mail.

* Brugernavnet normaliseres altid: mellemrum fjernes, og der bruges STORE
  bogstaver (`" hafra"` = `HAFRA`). Det er unikt uanset store/små bogstaver,
  2-40 tegn (A-Z, 0-9, `.`, `-`, `_`) og er den identitet, der vises i
  programmet og står i tidslinjer, kommentarer og historik.
* Supabase Auth kan kun logge på med e-mail eller telefon. Hver konto har
  derfor et **internt login-alias**, som IN-BASE beregner ud fra
  brugernavnet: `HAFRA` → `hafra@brugere.in-base.invalid`. `.invalid` er et
  reserveret topdomæne (RFC 2606) – der kan aldrig sendes post dertil.
  Aliaset vises ikke i programmet, bruges ikke til kommunikation og er ikke
  brugerens private eller arbejdsmail.
* **Supabase Auth kontrollerer adgangskoden** – IN-BASE gemmer, hasher eller
  logger aldrig adgangskoder eller tokens. Sessionen ligger kun i
  hukommelsen (skrives ikke til disk) og fornyes automatisk.
* Forkert kode, ukendt brugernavn og deaktiveret konto giver **samme**
  besked, så login ikke afslører, hvilke brugernavne der findes.
* Reglen for aliaset står tre steder og skal være ens:
  `app/repositories/supabase/mapping.py` (`login_alias`),
  `supabase/functions/_shared/admin.ts` (`loginAlias`) og migrering 005
  (`inbase_login_alias`).

## 1. Opret databasen (SQL Editor)

Dashboard → **SQL Editor** → **New query**. Indsæt og kør hver fil for sig,
i denne rækkefølge, og tjek at hver giver "Success":

1. `001_initial_schema.sql` – tabeller, nøgler, statusser, versionstrigger.
2. `002_rls_policies.sql` – privilegier og Row Level Security.
3. `003_rpc_functions.sql` – beskyttede funktioner (gem sag, slet sag, gem
   skabelon, brugerliste).
4. `004_seed_standarder.sql` – de bevidste standarder: 4 områder, 4
   arbejdsgangsskabeloner, 2 mailskabeloner, 6 påmindelsesregler. Ingen
   forretningsdata. Kan køres igen uden dubletter.
5. `005_brugernavn_login.sql` – login med brugernavn, aktive/deaktiverede
   brugere, ny procedure for første administrator, e-mail fjernes fra
   profilerne. Flytter eksisterende konti over på login-aliasset (se
   "Fra e-mail- til brugernavnslogin" nedenfor).
6. `006_oensker_udvikling.sql` – tabeller, RLS og funktioner til Ønsker & Udvikling.
7. `007_mdm_enheder.sql` – tabellen `mdm_devices` og funktionerne til Telefoner
   (MDM). Kun administratorer har adgang (se docs/MDM_OPSAETNING.md).
8. `008_mdm_lokal_klargoering.sql` – Telefoner klargøres lokalt fra IN-BASE
   (statusser og felter uden Google AMAPI).
9. `009_mdm_nulstillingskode.sql` – nulstillingskode pr. telefon (kun administratorer).
10. `010_moduladgang.sql` – adgang pr. modul på brugerprofilen (Indstillinger → Brugere →
    Moduladgang). Telefoner åbnes for brugere med modulet.
11. `011_aaben_opsaetning.sql` – alle brugere ændrer skabeloner (i deres moduler),
    påmindelser og Organisation. Brugere, moduladgang, backup/slettepolitik og
    permanent sletning er stadig kun for administratorer.
12. `012_mdm_mail_og_signering.sql` – Telefoner: om telefonen har firma-mail (kan slås til/fra
    med en ændringskode) og styrings-appens signeringsnøgle, kun for administratorer
    (se docs/MDM_OPSAETNING.md).
13. `013_mdm_arkiv.sql` – Telefoner: "Fjern fra listen" arkiverer i stedet for at slette
    (Telefoner → Arkiv), så nulstillingskoden bevares, og telefonen kan gendannes.
14. `014_arbejdsspor.sql` – parallelle arbejdsspor: opgaver får nøgle, spor, afdeling,
    forudsætninger, betingelse og planlagt tidspunkt; sager får HR's behov (`needs`);
    brugere får afdelinger (`roles`, sættes af administratorer via `inbase_set_roles`).
    Kun tilføjelser – ingen data ændres eller slettes.
15. `015_seed_standarder.sql` – standarderne igen (genereret), nu med onboarding-
    skabelonerne "Onboarding – arbejdsspor" (+ FM/DM). De gamle onboarding-
    standarder fra 004 deaktiveres (slettes ikke). Kan køres igen uden dubletter.
16. `016_udstyrsprofiler.sql` – standardprofiler for udstyr pr. stilling
    (`app_settings.udstyrsprofiler`, tom som standard). Medlemmer må ændre nøglen
    (Indstillinger → Organisation). Kun tilføjelser; kan køres igen. Indtil den er
    kørt, kan kun administratorer gemme Organisation.

17. `017_loennr_foer_kontrakt.sql` – onboardingskabelonerne: "Lønnr. tildelt" er en
    HR-opgave i kandidatfasen, og kontrakten venter på den (lønnr. står på
    kontrakten). Ny skabelonversion; sager påvirkes ikke. Kan køres igen.

18. `018_enkelt_onboardingflow.sql` – ny standardskabelon "Onboarding" (5 opgaver,
    alle stillinger); de tidligere arbejdsspor-standarder deaktiveres (slettes
    ikke). Sletning af skabeloner: RPC `inbase_delete_workflow_template` (modultjek)
    og delete for mails og påmindelser. Sager påvirkes ikke. Kan køres igen.

Kør aldrig filerne igen på en database, hvor de allerede er anvendt (bortset
fra 004, 015, 016, 017 og 018). Fremtidige ændringer kommer som nye filer `019_...`.

### Fra e-mail- til brugernavnslogin (hvis 001-004 allerede er kørt)

Har du allerede kørt 001-004 og oprettet en administrator med e-mail, så kør
blot 005 og 006. 005 flytter alle konti, der har en IN-BASE-profil, over på
deres login-alias og normaliserer brugernavnene. Herefter logger du på med
brugernavnet (fx `MASAN`) og den **samme** adgangskode som før.

* Giver 005 advarslen *"Eksisterende konti kunne ikke flyttes til
  login-aliasset"*, har SQL Editor ikke fået lov til at ændre `auth.users`.
  Så er det nemmest at starte forfra med brugerne (programmet er ikke i
  produktion): slet de gamle konti under **Authentication → Users**, og opret
  den første administrator igen efter trin 5.
* Brugernavne, der ikke overholder de nye regler (fx starter med `.`), får
  005 til at fejle. Ret dem først i `user_profiles`, eller slet kontoen.

## 2. Auth-indstillinger

Dashboard → **Authentication**:

* **Sign In / Providers → "Allow new users to sign up": SLÅ FRA.** Så kan
  ingen oprette sig selv; konti oprettes kun af administratorer i IN-BASE.
  (Selv hvis nogen fik en konto, har den ingen adgang uden en aktiv
  IN-BASE-profil.)
* **Lad e-mail-udbyderen (Email provider) være slået TIL.** Login-aliasset er
  teknisk set en e-mail-/adgangskodekonto – uden udbyderen blokeres alle
  logins ("Email logins are disabled"). Der sendes aldrig mails.
* **Minimum password length: 8** (samme krav som IN-BASE og Edge Functions).
* "Confirm email" er uden betydning: kontiene oprettes bekræftede.

## 3. Fjern resterne fra forbindelsestesten

1. SQL Editor: `drop table if exists public.integration_probe;`
2. **Authentication → Users**: find testkontoen (e-mailen i
   `SUPABASE_TEST_EMAIL` i projektets gamle `.env`) → ⋯ → **Delete user**.
   Slet kun denne konto. Den må ikke genbruges som administrator.
3. Slet linjerne `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`,
   `SUPABASE_TEST_EMAIL`, `SUPABASE_TEST_PASSWORD` fra projektets `.env`
   (forbindelsestesten er fjernet fra kodebasen). Navnene bruges ikke af IN-BASE.

## 4. Deploy Edge Functions

Funktionerne er den eneste vej til at oprette, nulstille, (de)aktivere,
ændre rolle på og slette ANDRE brugeres konti. De bruger servernøglen, som
kun findes på Supabases server. **Deploy dem igen, hver gang filerne i
`supabase/functions/` ændres** – den nye klient kalder handlinger
(`set_active`, `set_role`), som ældre udgaver ikke kender.

1. Installér Supabase CLI (fx `scoop install supabase`, eller hent
   `supabase_windows_amd64.tar.gz` fra github.com/supabase/cli/releases).
2. I projektmappen:
   ```
   supabase login
   supabase link --project-ref <projekt-ref>
   supabase functions deploy admin-create-user admin-manage-user --use-api
   ```
   `--use-api` lader Supabase bygge funktionerne – Docker er ikke nødvendig.
   `supabase/config.toml` sætter `verify_jwt = false`; funktionerne validerer
   selv sessionen (`auth.getUser`) og tjekker, at kalderen er **aktiv**
   administrator i `user_profiles`.
3. Servernøglen: `SUPABASE_URL` og projektets service-/secret-nøgle stilles
   automatisk til rådighed for funktionerne. Melder en funktion "Serveren
   mangler sin service-nøgle", så sæt den eksplicit (Project Settings → API
   Keys → *Secret keys*):
   ```
   supabase secrets set INBASE_SERVICE_KEY=<secret key>
   ```
   Secret-nøglen må **aldrig** i `.env` på en pc, i koden eller i `.exe`.

## 5. Den første administrator (engangsprocedure)

1. **Authentication → Users → Add user → Create new user**:
   * E-mail: login-aliasset for dit brugernavn, fx
     `masan@brugere.in-base.invalid` (brugernavnet med små bogstaver +
     `@brugere.in-base.invalid`).
   * En stærk adgangskode (mindst 8 tegn).
   * **"Auto Confirm User" slået til.**
2. SQL Editor (kører som projektejer – funktionen kan ikke kaldes fra appen
   eller API'et):
   ```sql
   select public.inbase_bootstrap_first_admin('MASAN', 'Dit Navn');
   ```
   Funktionen finder Auth-kontoen ud fra aliasset og opretter profilen som
   administrator. Den afvises, hvis der allerede findes en aktiv
   administrator – det er ikke en permanent genvej. Ingen bliver automatisk
   administrator, og der findes ingen standardbruger (`admin/admin` er fjernet).
3. Start IN-BASE og log på med `MASAN` og adgangskoden.
4. Herefter oprettes ALLE andre brugere fra IN-BASE (trin 7).

## 6. Konfiguration på hver pc

**Med installeren sker det automatisk.** `scripts\build_windows.ps1` tager
URL og publishable-nøgle fra projektets `.env` (kun de to værdier), og
installeren lægger dem i `%APPDATA%\IN-BASE\.env` – men kun hvis brugeren
ikke allerede har filen. Den overskrives aldrig ved opgradering og slettes
ikke ved afinstallation. Den ligger ikke i selve `IN-BASE.exe`.

Skal en pc pege på et andet projekt, eller kører du appen uden installer,
så opret/ret filen `%APPDATA%\IN-BASE\.env` manuelt
(fx `C:\Users\<navn>\AppData\Roaming\IN-BASE\.env`):

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
* Logfiler: `%LOCALAPPDATA%\IN-BASE\Logs\in-base.log` (færdig app). Der logges
  brugernavne, men aldrig adgangskoder eller tokens.

## 7. Brugere

Alt sker under **IN-BASE → Indstillinger → Brugere** (kun administratorer).
Knapperne kalder Edge Functions, som selv tjekker, at du er aktiv
administrator – en almindelig bruger kan ikke oprette brugere eller tildele
sig selv (eller andre) administratorrettigheder, heller ikke uden om programmet.

* **Opret:** brugernavn (fx `HAFRA`), evt. visningsnavn, rolle og en
  **midlertidig kode** (mindst 8 tegn). Giv brugernavn og kode til brugeren
  ad en sikker vej (helst hver for sig). Ved første log på skal brugeren
  vælge sin egen kode. Bag knappen opretter `admin-create-user` Auth-kontoen
  med login-aliasset (bekræftet, ingen mail) og præcis én profil med samme
  UUID. Fejler profilen, slettes den nye konto igen; er en tidligere
  oprettelse afbrudt (konto uden profil), fuldføres den ved næste forsøg.
* **Nulstil adgangskode:** ny midlertidig kode; brugeren skal vælge en ny ved
  næste log på. (Der er bevidst ingen "glemt kode"-mail – kontakt en
  administrator.)
* **Egen kode:** brugeren skifter selv kode under Indstillinger → Generelt
  (kræver den nuværende kode).
* **Deaktivér / aktivér:** en deaktiveret bruger mister *straks* adgangen til
  alle data (databasens `inbase_is_member()` kræver en aktiv profil), kontoen
  spærres i Supabase Auth (kan hverken logge på eller forny sin session), og
  et åbent IN-BASE logger selv brugeren ud inden for et minut. Historikken
  bevares. Foretræk deaktivering frem for sletning.
* **Skift rolle:** Administrator ↔ Bruger. Ændres en brugers rolle, mens
  vedkommende er logget på, logges brugeren ud og skal logge på igen.
* **Slet:** sletter Auth-kontoen og profilen. Navnet bevares i tidslinjerne.

Man kan ikke deaktivere, slette eller ændre rolle på sig selv, og der skal
altid være mindst én **aktiv** administrator (tjekkes af Edge Functions og af
en trigger i databasen).

## 8. Afprøvning med to brugerprofiler

1. Pc/Windows-bruger A: start IN-BASE, log på som administratoren.
2. Opret brugeren `TEST.BRUGER` (rolle Bruger) med en midlertidig kode.
3. Pc/Windows-bruger B (med sin egen `%APPDATA%\IN-BASE\.env`): log på med
   `test.bruger` og den midlertidige kode → vælg ny kode.
4. A opretter en offboardingsag. B ser den (listerne opdateres automatisk
   inden for et minut) og markerer en opgave udført.
5. A og B åbner samme sag; A gemmer først, derefter B → B får "ændret af …",
   og intet overskrives.
6. B kan ikke se *Brugere*/*Data & sikkerhed* og får afslag, hvis B forsøger
   at ændre opsætning – afslaget kommer fra databasen, ikke kun fra knapperne.
7. B opretter en indmelding i **Ønsker & Udvikling**; A sætter status *Til
   vurdering* og tildeler en ansvarlig; B ser ændringen i historikken.
8. A deaktiverer `TEST.BRUGER` → B logges ud inden for et minut og kan ikke
   logge på igen. Slet eller deaktivér test.bruger, når afprøvningen er færdig.

Samme pc, to profiler: start én IN-BASE, log ud (sidebar), log på som den anden.

## 9. Gamle lokale data (JSON)

De gamle JSON-data overføres ikke og er afviklet (værktøjet til det er fjernet
efter brug). Ligger der stadig gamle filer på en pc, slettes de manuelt efter
jeres slettepolitik: `Data\*.json`, `Data\Backup\` og `Lokal\Offline\`.

JSON-tilstanden (`INBASE_BACKEND=json`) er kun til udvikling og tests. Den har
ingen standardbruger; den første administrator oprettes med
`python tools/opret_json_administrator.py BRUGERNAVN "Navn"`.

## 10. Nulstil databasen (kun hvis nødvendigt, fx efter en testperiode)

`reset/nulstil_forretningsdata.sql` tømmer alle IN-BASE-forretningstabeller
(sager, personer, ansættelser, opgaver, rykkere, tidslinjer, skabeloner,
indstillinger, områder, indmeldinger i Ønsker & Udvikling med kommentarer og
historik) og `integration_probe`, men IKKE skemaet, de faste stillinger,
brugerprofiler eller `auth`. Den kører kun, hvis bekræftelseslinjen øverst i
filen aktiveres i samme kørsel. Kør bagefter `015_seed_standarder.sql` for at
få standarderne tilbage. Programmet kan ikke kalde nulstillingen. **Tjek i
Dashboardet, at du er i det rigtige projekt, før du kører den.**

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
Installeren lægger `%APPDATA%\IN-BASE\.env` på plads, hvis den mangler (se
afsnit 6); den indlejres ikke i .exe-filen. Logs skrives i `%LOCALAPPDATA%\IN-BASE`.

## 12. Test

| Kommando | Kræver | Dækker |
|---|---|---|
| `python -m unittest discover -s tests -t .` | intet | domæne, services (inkl. Ønsker & Udvikling og brugernavnsregler), JSON, konfiguration, mapping, Auth-service (mock), brugerflade (offscreen) |
| `python tools/lokal_testdatabase.py` + `set INBASE_LOKAL_PGRST_URL=http://127.0.0.1:3999` + `python -m unittest tests.test_supabase_lokal` | Docker | repositories + SQL + RLS mod en lokal PostgreSQL/PostgREST: deaktivering, Ønsker & Udvikling uden om programmet, konvertering af gamle e-mail-konti (005), administratorregler i SQL |
| `tests.test_supabase_e2e` (se filens docstring) | Docker + Supabase CLI (`supabase start` + `supabase functions serve`) | Auth-login med brugernavn, Edge Functions, oprettelse/nulstilling/deaktivering/sletning, to "pc'er" |

Den lokale testdatabase kører kun i Docker-containere på din pc – aldrig mod
Supabase-projektet. E2E-testen opretter og sletter konti og kører kun med
`INBASE_E2E_OPRET_BRUGERE=1`. Brug den mod en lokal `supabase start` eller et
separat testprojekt – aldrig mod produktionsdata.

## Kendte begrænsninger

* **Ingen offline:** uden forbindelse vises en fejl; intet gemmes lokalt.
* **Backup** tages af Supabase (afhænger af abonnement; gratis projekter har
  ingen automatisk backup og sættes på pause efter en uge uden aktivitet).
* **Tidszone:** tidspunkter vises i pc'ens lokale tid (forudsætter dansk tid).
* **Ingen selvbetjent "glemt kode":** en administrator nulstiller koden.
* **Login-aliasset** er afprøvet med en lokal stub, ikke mod Supabase Auth
  selv. Afviser Supabase Auth en dag `.invalid`-adresser ved oprettelse,
  skal domænet ændres samme tre steder (se "Sådan virker login") FØR der
  oprettes brugere – eksisterende konti skal så flyttes.
* **Deaktivering mens brugeren arbejder:** data lukkes med det samme, men
  programmet logger først brugeren ud ved næste kontrol (højst ca. et minut).
