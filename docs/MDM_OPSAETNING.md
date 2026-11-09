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
| Skærmlås | Kræves altid og kan ikke fjernes (v6+). Standardmønsteret tegnes ved klargøringen. Android kan ikke forhindre, at mønsteret ændres – ændringer uden skærmlåskode registreres og vises øverst i administrator-menuen. |
| PDF-læser | Telefonens egen PDF-læser skjules aldrig (v6+), så briefs fra Gmail og FL-TMS kan åbnes. Findes der ingen, melder klargøringen det som fejl. |
| FL-UPDATE | Installeres automatisk og kan ikke afinstalleres. |
| Installér apps (valgfrit) | Op til 10 andre APK-filer fra pc'en installeres på samme måde og kan ikke afinstalleres (v8.1+). |
| Firma-mail (valgfrit) | Gmail-appen bliver synlig, og der kan tilføjes en IMAP-konto. Google-konti er stadig spærret. |

FL-UPDATE vælges som APK-fil på pc'en. Telefonen henter den så fra IN-BASE under
klargøringen. Alternativt kan du angive et https-link. APK'en ændres ikke.

## Første gang

1. Kør i Supabase SQL Editor, i denne rækkefølge:
   1. `app/infrastructure/database/migrations/008_mdm_lokal_klargoering.sql`
   2. `app/infrastructure/database/migrations/009_mdm_nulstillingskode.sql`
   3. `app/infrastructure/database/migrations/012_mdm_mail_og_signering.sql` (efter 010 og 011)
   4. `app/infrastructure/database/migrations/013_mdm_arkiv.sql` (Arkiv under Telefoner)
   5. `app/infrastructure/database/migrations/024_mdm_find_telefon.sql` (Find telefon, efter 023)
   6. `app/infrastructure/database/migrations/025_mdm_laas_op.sql` (Lås skærmlåsen op)
   7. `app/infrastructure/database/migrations/026_mdm_app_opdatering.sql` (automatisk opdatering)

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
   - **Installér apps** (valgfrit): tryk **+ Tilføj APK…** for hver app, der skal installeres
     ud over FL-UPDATE. **Fjern** tager den af listen igen. Kræver IN-BASE Klargøring 8.1.
     Telefonen installerer dem efter FL-UPDATE. Fejler én app, installeres de andre alligevel,
     og IN-BASE viser bagefter, hvor mange der kom på. Er en app i forvejen på telefonen, så
     brug **Ekstra apps** (pakkenavnet) i stedet.

   - **Firma-mail (IMAP)**: sæt flueben for fastansatte med firma-mail. Kan også slås til
     senere uden nulstilling.

   Indstillingerne huskes på pc'en til næste gang. Det gælder ikke Wi-Fi-koden.
3. Klik **Vis QR-kode**. Første gang spørger Windows Firewall. Vælg **Tillad** på private
   netværk.
4. Fabriksnulstil telefonen, tryk **6 gange** på velkomstskærmen og scan QR-koden.
5. Lad vinduet være åbent. Telefonen klargør sig selv og viser fremdriften. Når den er
   færdig, viser IN-BASE "✔ ISM589 er klargjort" med model, serienummer og IMEI.
6. Åbn FL-UPDATE på telefonen, og tillad den at **installere apps**. Så henter den FL-TMS.
   Det kan Android ikke automatisere.
7. Sæt **standardmønsteret** som skærmlås (U: start øverst til venstre → ned → højre → op).
   Telefonen beder selv om en skærmlås. Den første lås registreres som standarden; en
   app kan ikke tegne mønsteret, så det er også et trin i hånden.

En telefon klargøres igen ved at fabriksnulstille den og vælge **Klargør (QR-kode)…**.

## Ændringer på en klargjort telefon

Administrator-menuen åbnes med ikonet **IN-BASE indstillinger** på startskærmen eller med
`*#*#46227#*#*` i Telefon-appen. Det kræver IN-BASE Klargøring 4.0. Ældre telefoner skal
klargøres igen én gang. Menuen kræver altid en kode fra IN-BASE:

| Kode (IN-BASE → Handling) | Kan | Må gives til brugeren |
|---|---|---|
| Ændringskode (fx *Slå firma-mail til…*) | kun den ene handling på den ene telefon | ja |
| Supportkode (Chrome) | vise og skjule Chrome | ja |
| Skærmlåskode (*Vis skærmlåskode…*, v6+) | skifte skærmlåsen godkendt og nulstille advarslen om ændringer. Er også den midlertidige PIN efter *Lås skærmlåsen op…* | kun ved support |
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

**Skærmlåsen ændret.** Står der øverst i menuen, at skærmlåsen er ændret uden kode, så
gælder standardmønsteret måske ikke længere. Sæt det igen med skærmlåskoden: **Skift
skærmlås (godkendt)** → tegn standardmønsteret. Advarslen nulstilles.

**Glemt mønster (telefonen er låst).** Kræver IN-BASE Klargøring 8.0 og migrering 025.
1. Vælg telefonen i IN-BASE → **Handling → Lås skærmlåsen op…**, og bekræft. IN-BASE viser
   den midlertidige PIN-kode. Det er skærmlåskoden.
2. Bed brugeren om at **tegne et forkert mønster** eller **sætte telefonen i laderen eller en
   pc**. Så tjekker telefonen med det samme, ellers inden for en time. Telefonen skal have
   mobildata eller et kendt Wi-Fi.
3. Når IN-BASE viser "✔ låst op", låser brugeren op med PIN-koden.
4. **IN-BASE indstillinger** → samme kode → **Skift skærmlås (godkendt)** → tegn
   standardmønsteret.

Telefonen kan kun låses op fra IN-BASE, når den har meldt **klar**. Det gør den efter én
almindelig oplåsning, når den er opdateret til 8.0. IN-BASE advarer, hvis den ikke er klar,
og admin-menuen på telefonen viser det også. Det virker også efter en genstart, hvor telefonen
ikke er låst op endnu. Pc'en låser ikke telefonen op over USB, for det tillader Android ikke.
Stikket får kun telefonen til at tjekke ind.

**Anvend regler igen** i menuen lægger reglerne på med det samme. Det sker også automatisk,
når telefonen genstarter.

**Opdater styrings-appen – automatisk (telefoner med 8.0 eller nyere).** Kræver migrering 026.
1. En administrator bygger den nye version (se "Byg styrings-appen"). Afprøv den på én
   testtelefon (manuelt, herunder).
2. IN-BASE → Telefoner → **Opdater telefoner…** → **Udgiv 8.x til alle telefoner**.
3. Hver telefon ser den nye version ved sit næste tjek: når den låses op, sættes i laderen,
   eller senest inden for en time. Den henter appen (ca. 2 MB, over Wi-Fi eller mobildata),
   tjekker kontrolsummen og installerer den selv. Der skal ingen kode eller pc i nærheden.
   Android installerer kun en app, der er signeret med jeres nøgle.
4. Kolonnen **App** på Telefoner og vinduet **Opdater telefoner** viser, hvor mange der er
   opdateret.

Trafik: ca. 2 MB pr. telefon pr. udgivelse, dvs. ca. 200 MB for 100 telefoner. Udgiv derfor
samlet, ikke hver build. Mislykkes en installation, prøver telefonen samme version igen efter
6 timer.

**Opdater styrings-appen – manuelt (ældre telefoner, én gang).** Telefoner med 7.0 eller
ældre kan ikke opdatere sig selv. De skal have 8.0 én gang på denne måde, og derefter
opdaterer de automatisk.
1. IN-BASE → Telefoner → **Opdater telefoner…**. Vinduet viser pc'ens adresse og skal være
   åbent under opdateringen.
2. På telefonen (samme Wi-Fi): **IN-BASE indstillinger** → nulstillingskoden eller
   **masterkoden** → ret adressen om nødvendigt → **Opdater appen fra IN-BASE**. Reglerne
   lægges på igen bagefter.

Masterkoden virker på alle telefoner fra version 5. Det er altså én kode til alle, ikke en ny
kode for hver telefon. Den står i `android/masterkode.txt` hos den, der bygger styrings-appen.

Når reglerne lægges på igen, skjules kun systemapps. FL-UPDATE, FL-TMS og andre apps, der er
installeret efter klargøringen, røres ikke.

## Find en bortkommen telefon

Kræver IN-BASE Klargøring 7.0 på telefonen (**Opdater telefoner**) og migrering 024.

1. Vælg telefonen i IN-BASE → **Handling → Find telefon…**.
2. Lad vinduet stå åbent, eller luk det og åbn det igen senere. Anmodningen står, til telefonen
   svarer.
3. Når positionen kommer, viser vinduet koordinater, nøjagtighed, tidspunkt og batteri. Vælg
   **Åbn i kort** eller **Kopiér link**.

Telefonen kan ikke kaldes fra IN-BASE. På mobildata deler den IP-adresse med operatørens
andre kunder, og Googles push-tjeneste bruges ikke. Telefonen spørger derfor selv IN-BASE
(Supabase), om dens position ønskes:

| Hvornår | Svartid |
|---|---|
| Telefonen låses op, eller nogen tegner et forkert mønster | få sekunder (højst ét tjek pr. 10 min) |
| Telefonen kommer på nettet igen eller genstartes | få sekunder |
| Ellers én gang i timen | op til ca. 1 time, længere i dyb dvale |

Hvert tjek er en lille forespørgsel på ca. 5 KB, i alt ca. 4 MB pr. telefon pr. måned.
Supabase får kun en skrivning, når telefonen svarer, og "Senest set" højst én gang i timen.
Kolonnen **Senest set** viser, at en telefon tjekker ind. Telefonens administrator-menu viser
det også.

Er placering slået fra, slår telefonen den til for at finde positionen og bagefter fra igen
(Android 11+). Positionen kommer fra GPS, ellers fra mobilmasten eller Wi-Fi. Telefonen gemmer
ingen historik, og IN-BASE gemmer kun det seneste svar.

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
- [ ] Skærmlåsen kan ikke sættes til *Ingen* eller *Stryg*. Ændres mønsteret i
  Indstillinger, viser administrator-menuen advarslen; *Skift skærmlås (godkendt)* nulstiller den.
- [ ] En PDF åbnes fra Gmail og fra FL-TMS. Notér PDF-læserens pakkenavn.
- [ ] **Find telefon** på en telefon med kun data og uden Wi-Fi: positionen kommer få sekunder
  efter, at telefonen låses op, og inden for ca. 1 time, når den ligger låst og urørt. Kolonnen
  **Senest set** opdateres. Gælder det også for en telefon, der er opdateret fra version 6
  (ikke klargjort på ny), efter en genstart?
- [ ] **Lås skærmlåsen op**: IN-BASE viser telefonen som klar efter én oplåsning. Skift mønsteret
  uden kode, lås telefonen, og vælg *Lås skærmlåsen op…*. PIN-koden virker få sekunder efter et
  forkert mønster. Gentag ved at sætte telefonen i en pc, og efter en genstart uden oplåsning.
- [ ] **Automatisk opdatering**: byg en version med højere `versionCode`, og vælg *Udgiv til alle
  telefoner*. En testtelefon med 8.0 installerer den selv inden for en time, også på kun
  mobildata, og kolonnen **App** viser den nye version.

  Skjules en app, der skal bruges, så skriv pakkenavnet under **Ekstra apps** og klargør igen.

## Begrænsninger

- De eneste fjernhandlinger er **Find telefon** og **Lås skærmlåsen op**, og telefonen svarer
  først ved sit næste tjek (se "Find en bortkommen telefon"). En telefon kan ikke låses eller
  spærres på afstand. Ændringer
  sker med en kode i telefonens menu (firma-mail, Chrome), og nye regler kommer med en ny
  version af styrings-appen (**Opdater telefoner**). Fra 8.0 installerer telefonerne den selv. Telefoner med version 3 eller ældre skal
  nulstilles og klargøres igen én gang.
- Skjulte Google-apps (fx Play-butikken) opdateres ikke længere automatisk. Android-
  systemopdateringer kommer stadig.
- Skærmlåsen kan ikke spærres for ændring (Android har ingen regel til det) og kan ikke
  sættes af appen. Ændringer registreres kun på telefonen – IN-BASE får ikke besked.
- Låsen fjernes kun ved at nulstille med nulstillingskoden (`*#*#46227#*#*`). Koden ligger kun
  i IN-BASE og kan kun ses af administratorer. Et glemt mønster erstattes med en PIN med
  **Lås skærmlåsen op…** (v8+).
- Nulstilles skærmlåsen før første oplåsning efter en genstart, registreres det som en ændring
  uden kode. *Skift skærmlås (godkendt)* nulstiller advarslen.
