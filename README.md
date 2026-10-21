# IN-BASE

**Interne processer, samlet ét sted.**
Et fælles sted til opfølgning, automatisering, dokumentation og sammenhæng
mellem virksomhedens eksisterende systemer.

Første modul er **medarbejderafvikling**: hver fratrådt medarbejder får en
afviklingssag med opgaver (fx "Modtag telefon", "Er lukket i NAV?"),
rykkere og en tidslinje over hele forløbet.

## Struktur

```
main.py                     Starter programmet
app/
  __init__.py               Navn, slogan og VERSION
  stier.py                  Alle stier (Data-mappe, backup, assets) – ét sted
  medarbejder.py            Medarbejder + beregnet status, konvertering af gamle data
  opgave.py                 Én opgave: ansvarlig, frist, status, udstyr
  rykker.py                 Én rykker: kladde oprettet / sendt
  historik.py               Tidslinjen (kun tilføjelser, hash-kæde)
  skabeloner.py             Sags-, mail- og påmindelsesskabeloner, variabler, validering
  alarmer.py                Regler for Action Center, Dagsoversigt og påmindelser
  datasikkerhed.py          Backup, test af backup, gendannelse, slettepolitik
  brugere.py                Brugerkartotek, roller og log på (BETA)
  session.py                Hvem er logget ind lige nu
  indstillinger.py          Data/indstillinger.json
  data_manager.py           Læser/skriver JSON-filerne sikkert
  ui/
    theme.py                Farver og stylesheet
    hjaelpere.py            Små byggeklodser: knapper, kort, datoer, piller
    widgets.py              Tabel-hjælpere (sortering, farvede piller)
    diagrammer.py           Donut- og søjlediagram
    hovedvindue.py          Vinduet: sidebar, sider og alle handlinger
    dashboard_side.py       Dashboard med Action Center og Dagsoversigt
    medarbejder_side.py     Side med søgning + tabel (Hovedside og Arkiv)
    skabelon_side.py        Siden Skabeloner (tre faner)
    skabelon_dialoger.py    Editorer til skabeloner med forhåndsvisning
    data_side.py            Siden Data & sikkerhed
    bruger_side.py          Siden Brugerkartotek (kun administratorer)
    login_dialog.py         Log på-skærmen
    medarbejder_dialog.py   Opret/rediger stamdata, e-mail, skabelon, manuel status
    sag_dialog.py           Afviklingssagen: opgaver og tidslinje
    opgave_dialog.py        Rediger/undtag/slet én opgave
    rykker_dialog.py        Opret rykker -> kladde i mailprogrammet (mailto:)
    notifikationer.py       Ikon ved uret + Windows-notifikationer
assets/                     Ikoner (pakkes med i .exe)
```

## Brugere og roller (BETA)

Programmet åbner først efter log på. Første gang findes kun brugeren
**admin / admin** – skift koden under *Brugerkartotek*.

- **Administrator:** alt, inkl. Brugerkartotek, Data & sikkerhed, redigering
  af skabeloner og permanent sletning i arkivet.
- **Bruger:** sager, rykkere, tidslinjer og arkiv; kan se skabeloner.

Brugerne gemmes i `Data/brugere.json` (kode som saltet PBKDF2-hash). Filen
kan dog læses og ændres af alle med adgang til datamappen, så løsningen er
**ikke sikker** – brug ikke private adgangskoder. Tidslinjen registrerer den
bruger, der er logget ind.

## Tema

Mørkt, blødt lilla tema bygget op om `#341539`. Alle farver ligger i
`FARVER` i `app/ui/theme.py`.

## Skabeloner

Redigeres på siden **Skabeloner** (gemmes i `Data/skabeloner.json`):

- **Udstyr ved oprettelse** – opgaver der oprettes for nye medarbejdere.
  `Frist (dage)` regnes fra sidste arbejdsdag. Opgaver med *Udstyr* udfyldt
  nævnes i rykkere som manglende udstyr.
- **Mails** – rykkere. Variabler: `{navn}`, `{fornavn}`, `{loennr}`, `{email}`,
  `{sidste_arbejdsdag}`, `{manglende_udstyr}`, `{frist}`, `{tracking_link}`.
  Kategorien styrer, hvilken skabelon der foreslås (1. rykker -> *Første
  påmindelse*, 2. -> *Anden rykker*, 3.+ -> *Sidste rykker*).
- **Påmindelser** – Windows-notifikationer knyttet til foruddefinerede regler
  (se `REGLER` i `app/skabeloner.py` og `paamindelser()` i `app/alarmer.py`).

Mangler en variabel en værdi (fx e-mail), kan beskeden ikke oprettes.

## Status

- Alle obligatoriske opgaver udført/undtaget -> **Afviklet**
- Mindst én opgave i gang, afventer eller udført -> **Delvist afleveret**
- Ellers -> **Afventer Udstyr**

Status kan låses manuelt under *Rediger*, men kun med en begrundelse.

## Rykkere

*Handling -> Opret rykker* åbner en kladde i standardmailprogrammet via
`mailto:`. Programmet kan ikke se, om mailen sendes, så rykkeren står som
*Kladde oprettet*, indtil den markeres som sendt (*Handling -> Marker rykker
som sendt*). Begge dele registreres i tidslinjen.

## Data og sikkerhed

- **Udvikling:** `Data/` i projektmappen. **Færdig .exe:** `Data/` ved siden af
  programfilen, fx `C:\IN-BASE\Data`. Miljøvariablen `INBASE_DATA` kan pege på
  en anden mappe.
- **Backup:** én automatisk backup om dagen (i `Data/Backup` eller en valgt
  mappe), testet straks efter. Gendannelse tager først en backup af de
  nuværende data.
- **Slettepolitik:** arkiverede sager kan slettes efter en valgt periode
  (standard 12 måneder – aftal perioden med HR).
- **Adgang:** styres af Windows-rettighederne på `Data`- og backupmappen.

Læg programmet i en mappe brugerne kan skrive i, **ikke** i `C:\Program Files`.

## Byg

```
pyinstaller MedarbejderUdstyr.spec
```
