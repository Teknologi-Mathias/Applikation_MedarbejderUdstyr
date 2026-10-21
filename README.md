# Medarbejderafvikling

Holder styr på fratrådte medarbejdere via afviklingssager: hver medarbejder
får opgaver (fx "Modtag telefon", "Luk systemadgange") med ansvarlig, frist og
status. Medarbejderens status beregnes ud fra opgaverne.

## Struktur

```
main.py                     Starter programmet
app/
  __init__.py               VERSION
  stier.py                  Alle stier (Data-mappe, assets) – ét sted
  medarbejder.py            Medarbejder + beregnet status, konvertering af gamle data
  opgave.py                 Én opgave: ansvarlig, frist, status, begrundelse
  skabeloner.py             Skabeloner -> opgaver (Data/skabeloner.json)
  alarmer.py                Regler for Action Center, Dagsoversigt, notifikationer
  data_manager.py           Læser/skriver JSON-filerne sikkert
  ui/
    theme.py                Farver og stylesheet
    hjaelpere.py            Små byggeklodser: knapper, kort, datoer
    widgets.py              Tabel-hjælpere (sortering, farvede piller)
    diagrammer.py           Donut- og søjlediagram
    medarbejder_dialog.py   Opret/rediger stamdata, skabelon og manuel status
    sag_dialog.py           Afviklingssagen: opgaveliste og fremdrift
    opgave_dialog.py        Rediger/undtag/slet én opgave
    medarbejder_side.py     Side med søgning + tabel (Hovedside og Arkiv)
    dashboard_side.py       Dashboard med Action Center og Dagsoversigt
    notifikationer.py       Ikon ved uret + Windows-notifikationer
    hovedvindue.py          Vinduet: sidebar, sider og alle handlinger
assets/                     Ikoner (pakkes med i .exe)
```

## Skabeloner

Opgaverne i en ny sag kommer fra `Data/skabeloner.json` (oprettes automatisk
første gang). Ret opgaver, ansvarlige og frister dér; `frist_dage` er antal
dage efter sidste arbejdsdag. Slet filen for at få standardskabelonerne igen.

## Status

- Alle obligatoriske opgaver udført/undtaget -> **Afviklet**
- Mindst én opgave i gang, afventer eller udført -> **Delvist afleveret**
- Ellers -> **Afventer Udstyr**

Status kan låses manuelt under *Rediger*, men kun med en begrundelse.

## Data

- **Udvikling:** `Data/` i projektmappen.
- **Færdig .exe:** `Data/` ved siden af programfilen, fx
  `C:\MedarbejderUdstyr\Data`. Første gang kopieres evt. data fra den gamle
  placering i `%APPDATA%\MedarbejderUdstyr\Data`.

Læg programmet i en mappe brugerne kan skrive i (fx `C:\MedarbejderUdstyr`),
**ikke** i `C:\Program Files`.

## Byg

```
pyinstaller MedarbejderUdstyr.spec
```
