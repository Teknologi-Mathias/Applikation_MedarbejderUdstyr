# Medarbejderafvikling

Holder styr på fratrådte medarbejdere og om deres udstyr (tøj, telefon,
tankkort m.m.) er sendt retur til hovedkontoret.

## Struktur

```
main.py                     Starter programmet
app/
  __init__.py               VERSION
  stier.py                  Alle stier (Data-mappe, assets) – ét sted
  medarbejder.py            Medarbejder-modellen: status, udstyr, JSON
  data_manager.py           Læser/skriver JSON-filerne sikkert
  ui/
    theme.py                Farver og stylesheet
    hjaelpere.py            Små byggeklodser: knapper, kort, datoer
    widgets.py              Tabel-hjælpere (sortering, farvede piller)
    diagrammer.py           Donut- og søjlediagram
    medarbejder_dialog.py   Opret/rediger medarbejder inkl. udstyr
    medarbejder_side.py     Side med søgning + tabel (Hovedside og Arkiv)
    dashboard_side.py       Dashboardet
    hovedvindue.py          Vinduet: sidebar, sider og alle handlinger
assets/                     Ikoner (pakkes med i .exe)
```

Ny type udstyr tilføjes ét sted: `Medarbejder.UDSTYR` i `app/medarbejder.py`.

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
