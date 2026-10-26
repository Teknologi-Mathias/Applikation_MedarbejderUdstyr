# Telefoner (MDM): klargøring af driftstelefoner

IN-BASE klargør driftstelefoner (fx Motorola) direkte fra programmet med en
QR-kode. Det kræver hverken en server, Google Cloud eller en MDM-tjeneste.
Telefonen bliver låst til drift, og den registreres ved sit enhedsnavn fra
ERP (fx ISM589).

```
IN-BASE på pc'en (samme Wi-Fi)                    Telefon (fabriksnulstillet)
  QR-kode  ─────────────── scannes ──────────────►  kobler på Wi-Fi
  midlertidig server (port 8765) ◄── henter ─────  IN-BASE Klargøring (assets/mdm)
                                                    • bliver telefonens administrator
                                                    • skjuler alle apps undtagen basale
                                                    • sætter baggrund og låser den
                                                    • henter og installerer FL-UPDATE
                                                    • låser indstillinger
  gemmer model/serienr./IMEI i Supabase ◄─ melder tilbage
```

Serveren kører kun, mens klargøringsvinduet er åbent. Efter klargøringen er der
ingen trafik. Supabase får én række pr. telefon.

Telefonen gemmer sine regler. De lægges på igen, hver gang telefonen starter, og når
styrings-appen er opdateret. Firma-mail og Chrome kan slås til og fra bagefter uden
nulstilling (se "Ændringer på en klargjort telefon").

## Det får telefonen

| | |
|---|---|
| Synlige apps | Telefon og SMS (telefonens egne), Kontakter, Kamera, Ur, Lommeregner, Indstillinger, **IN-BASE indstillinger**, FL-UPDATE, FL-TMS samt eventuelle "Ekstra apps" |
| Skjult | Alt andet med et ikon: Play-butik, Chrome, YouTube, spil, Facebook, Temu … |
| Oplæsning slået fra | Googles talesyntese (TTS), TalkBack og *Vælg for at få læst op*. Oplæsere fra andre apps kan ikke aktiveres. |
| Internet | Flytilstand, mobildata/APN og privat DNS kan ikke ændres. Wi-Fi kan skiftes frit, og netværksindstillinger kan nulstilles. |
| Låst | Fabriksnulstilling, flere brugere, konti, nødstart (safe boot), udviklerindstillinger/USB-fejlfinding, USB-filoverførsel, SD-kort, certifikater, afinstallation og ændring af apps, baggrundsbillede |
| Låseskærm | Viser enhedsnavnet, fx ISM589 |
| FL-UPDATE | Installeres automatisk og kan ikke afinstalleres. |
| Firma-mail (valgfrit) | Gmail-appen bliver synlig, og der kan tilføjes en IMAP-konto. Google-konti er stadig spærret. |

FL-UPDATE vælges som APK-fil på pc'en. Telefonen henter den så fra IN-BASE under
klargøringen. Alternativt kan du angive et https-link. APK'en ændres ikke.

## Første gang

1. Kør i Supabase SQL Editor, i denne rækkefølge:
   1. `app/infrastructure/database/migrations/008_mdm_lokal_klargoering.sql`
   2. `app/infrastructure/database/migrations/009_mdm_nulstillingskode.sql`
   3. `app/infrastructure/database/migrations/012_mdm_mail_og_signering.sql` (efter 010 og 011)

   007 skal være kørt først, og det er den allerede.
2. Styrings-appen ligger færdigbygget i `assets/mdm/inbase-klargoering.apk` og følger med
   IN-BASE. Alle kan klargøre og opdatere telefoner fra deres egen pc uden at bygge noget.
   Den skal kun bygges igen, hvis koden i `android/` ændres (se "Byg styrings-appen").

## Byg styrings-appen

Kræver Android Studio og en IN-BASE-**administratorkonto**: `.\scripts\byg_klargoering_apk.ps1`

Telefonerne accepterer kun en ny version, hvis den er signeret med samme nøgle som den app,
de blev klargjort med. Nøglen ligger derfor i Supabase (tabellen `mdm_signing_key`, migrering
012), og kun administratorer kan læse den. Scriptet beder om dit IN-BASE-login, henter
nøglen til `android/signering/`, bygger og sletter nøglen igen. Den kommer aldrig i git.
Uden nøglen nægter Gradle at bygge.

- Første gang, efter migrering 012 er kørt, laver scriptet nøglen og gemmer den. Den kan
  ikke ændres eller slettes fra IN-BASE bagefter. En ny nøgle ville kræve, at alle telefoner
  nulstilles.
- Reservekoden til v1-telefoner gemmes sammen med nøglen, så alle administratorer bygger med
  samme reservekode.
- Den, der har nøglen og en telefons nulstillingskode, kan lægge en anden app på telefonen.
  Giv derfor kun administratorrollen til dem, der skal have den.

## Klargør en telefon

1. **Telefoner (MDM) → + Ny telefon**. Skriv enhedsnavnet fra ERP (fx ISM589) og telefonnummeret.
2. Klargøringsvinduet åbner. Udfyld:
   - **Wi-Fi**: det netværk, pc'en er på. Telefon og pc skal være på samme net.
   - **FL-UPDATE** (påkrævet): vælg FL-UPDATE.apk på pc'en, eller angiv et https-link.
   - **Baggrundsbillede** (valgfrit): et JPG- eller PNG-billede på pc'en.

   - **Firma-mail (IMAP)**: sæt flueben for fastansatte med firma-mail. Kan også slås til
     senere uden nulstilling.

   Indstillingerne huskes på pc'en til næste gang. Det gælder ikke Wi-Fi-koden.
3. Klik **Vis QR-kode**. Første gang spørger Windows Firewall. Vælg **Tillad** på private
   netværk.
4. Fabriksnulstil telefonen, tryk **6 gange** på velkomstskærmen og scan QR-koden.
5. Lad vinduet være åbent. Telefonen klargør sig selv og viser fremdriften. Når den er
   færdig, viser IN-BASE "✔ ISM589 er klargjort" med model, serienummer og IMEI.
6. Åbn FL-UPDATE på telefonen, og tillad den at **installere apps**. Så henter den FL-TMS.
   Det er det eneste trin i hånden, fordi Android ikke tillader, at det automatiseres.

En telefon klargøres igen ved at fabriksnulstille den og vælge **Klargør (QR-kode)…**.

## Ændringer på en klargjort telefon

Administrator-menuen åbnes med ikonet **IN-BASE indstillinger** på startskærmen eller med
`*#*#46227#*#*` i Telefon-appen. Det kræver IN-BASE Klargøring 4.0. Ældre telefoner skal
klargøres igen én gang. Menuen kræver altid en kode fra IN-BASE:

| Kode (IN-BASE → Handling) | Kan | Må gives til brugeren |
|---|---|---|
| Ændringskode (fx *Slå firma-mail til…*) | kun den ene handling på den ene telefon | ja |
| Supportkode (Chrome) | vise og skjule Chrome | ja |
| Nulstillingskode | alt, også opdatering og fabriksnulstilling | nej |

**Firma-mail ved forfremmelse.**
1. Vælg telefonen i IN-BASE → **Handling → Slå firma-mail til…**. IN-BASE viser en 6-cifret
   ændringskode.
2. Medarbejderen åbner **IN-BASE indstillinger**, indtaster koden og vælger
   **Brug ændringskode**. Det kan klares over telefonen. Gmail bliver synlig, og der kan
   tilføjes en IMAP-konto.
3. Svar **Ja** i IN-BASE, så listen viser, at telefonen har mail.

*Slå firma-mail fra…* skjuler Gmail igen og spærrer konti. Den IMAP-konto, der allerede er
tilføjet, kan telefonen ikke slette selv. Den bliver bare usynlig. Skal den helt væk, så
nulstil telefonen og klargør den igen.

**Anvend regler igen** i menuen lægger reglerne på med det samme. Det sker også automatisk,
når telefonen genstarter.

**Opdater styrings-appen uden nulstilling.**
1. En administrator bygger den nye version (se "Byg styrings-appen") og udgiver den med
   IN-BASE. Det kan ske fra en hvilken som helst pc.
2. IN-BASE → Telefoner → **Opdater telefoner…**. Vinduet viser pc'ens adresse og skal være
   åbent under opdateringen.
3. På telefonen (samme Wi-Fi): **IN-BASE indstillinger** → nulstillingskoden → ret adressen
   om nødvendigt → **Opdater appen fra IN-BASE**. Reglerne lægges på igen bagefter.

Når reglerne lægges på igen, skjules kun systemapps. FL-UPDATE, FL-TMS og andre apps, der er
installeret efter klargøringen, røres ikke.

## Fabriksnulstilling

**Fabriksnulstil en låst telefon.** Nulstilling er spærret både i Indstillinger og i
recovery, fordi Motorola fjerner punktet i recovery. Brug i stedet telefonens
nulstillingskode:
1. Find koden i IN-BASE under **Handling → Vis nulstillingskode**.
2. Åbn Telefon-appen på telefonen og tast `*#*#46227#*#*`. Det er I-N-B-A-S på tastaturet.
3. Indtast koden, og vælg **Fabriksnulstil telefonen**.

**Telefoner klargjort før nulstillingskoden (version 1, fx ISM321).** De kan hverken
nulstilles i recovery, med Rescue-værktøjet eller med fastboot (`Permission denied`). Opdatér
i stedet styrings-appen via Bluetooth, som ikke er spærret:
1. På pc'en: højreklik på `assets/mdm/inbase-klargoering.apk` (version 2) og vælg
   **Send til → Bluetooth-enhed**. Vælg telefonen. Den skal først parres via
   Indstillinger → Bluetooth på telefonen.
2. På telefonen: accepter filen. Tryk på den i notifikationen, tillad installation fra
   *Bluetooth*, og vælg **Opdater**.
3. Tast `*#*#46227#*#*` i Telefon-appen, og indtast **reservekoden** (IN-BASE → Handling →
   Vis nulstillingskode). Telefonen nulstilles.

Reservekoden ligger i `android/reservekode.txt` og `assets/mdm/reservekode.txt` (ikke i git).
Den virker kun på telefoner uden egen kode.

**Firma-mail.** Når telefonen er klargjort med "Firma-mail", gør medarbejderen sådan:
1. Åbn Gmail.
2. Vælg *Tilføj en e-mailadresse → Andet*.
3. Indtast firma-mailen, og vælg *Personlig (IMAP)*.
4. Udfyld IMAP- og SMTP-serveren fra jeres mailudbyder.

## Afprøvning på første testtelefon

- [ ] Opsætningsguiden henter styrings-appen fra pc'en.

  Gør den ikke det, så tjek Wi-Fi, firewall, og at netværket i Windows er sat som *Privat*.
- [ ] IN-BASE viser "klargjort" med model, serienummer og IMEI.
- [ ] Telefonen kan ringe og sende SMS. Telefon- og SMS-appen er ikke skjult.
- [ ] Play-butik, Chrome og spil er væk fra startskærmen og app-skuffen.
- [ ] Baggrundsbilledet er sat og kan ikke ændres.
- [ ] Fabriksnulstilling i Indstillinger er spærret.
- [ ] `*#*#46227#*#*` i Telefon-appen åbner IN-BASE-menuen, og den rigtige kode nulstiller telefonen.
- [ ] FL-UPDATE er installeret (IN-BASE viser "FL-UPDATE installeret") og henter FL-TMS, når
  den har fået lov til at installere apps.
- [ ] Med firma-mail: en IMAP-konto kan tilføjes i Gmail, men en Google-konto kan ikke.
- [ ] Ikonet **IN-BASE indstillinger** findes og åbner menuen.
- [ ] Flytilstand og mobildata kan ikke slås fra, heller ikke i hurtigindstillingerne (træk ned
  fra toppen). Wi-Fi kan stadig skiftes, og netværksindstillinger kan nulstilles.
- [ ] Talesyntese, TalkBack og *Vælg for at få læst op* findes ikke under
  Indstillinger → Hjælpefunktioner. Er der en Motorola-oplæser, så notér pakkenavnet.
- [ ] Uden mail: *Slå firma-mail til* med ændringskoden får Gmail frem. Efter genstart er den
  der stadig. *Slå firma-mail fra* skjuler den igen.
- [ ] **Opdater telefoner** med en ny build (højere `versionCode`): telefonen opdateres, og
  FL-UPDATE og FL-TMS er stadig synlige.

  Skjules en app, der skal bruges, så skriv pakkenavnet under **Ekstra apps** og klargør igen.

## Begrænsninger

- Der er ingen fjernstyring. En telefon kan ikke låses eller spærres på afstand. Ændringer
  sker med en kode i telefonens menu (firma-mail, Chrome), og nye regler kommer med en ny
  version af styrings-appen (**Opdater telefoner**). Telefoner med version 3 eller ældre skal
  nulstilles og klargøres igen én gang.
- Skjulte Google-apps (fx Play-butikken) opdateres ikke længere automatisk. Android-
  systemopdateringer kommer stadig.
- Låsen fjernes kun ved at nulstille med nulstillingskoden (`*#*#46227#*#*`). Koden ligger kun
  i IN-BASE og kan kun ses af administratorer.
