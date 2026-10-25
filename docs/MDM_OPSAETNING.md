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

## Det får telefonen

| | |
|---|---|
| Synlige apps | Telefon og SMS (telefonens egne), Kontakter, Kamera, Ur, Lommeregner, Indstillinger, FL-UPDATE, FL-TMS samt eventuelle "Ekstra apps" |
| Skjult | Alt andet med et ikon: Play-butik, Chrome, YouTube, spil, Facebook, Temu … |
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

   007 skal være kørt først, og det er den allerede.
2. Styrings-appen ligger færdigbygget i `assets/mdm/inbase-klargoering.apk`. Den skal kun
   bygges igen, hvis koden i `android/` ændres: `.\scripts\byg_klargoering_apk.ps1`
   (kræver Android Studio).

## Klargør en telefon

1. **Telefoner (MDM) → + Ny telefon**. Skriv enhedsnavnet fra ERP (fx ISM589) og telefonnummeret.
2. Klargøringsvinduet åbner. Udfyld:
   - **Wi-Fi**: det netværk, pc'en er på. Telefon og pc skal være på samme net.
   - **FL-UPDATE** (påkrævet): vælg FL-UPDATE.apk på pc'en, eller angiv et https-link.
   - **Baggrundsbillede** (valgfrit): et JPG- eller PNG-billede på pc'en.

   - **Firma-mail (IMAP)**: sæt flueben for fastansatte med firma-mail.

   Indstillingerne huskes på pc'en til næste gang. Det gælder ikke Wi-Fi-koden.
3. Klik **Vis QR-kode**. Første gang spørger Windows Firewall. Vælg **Tillad** på private
   netværk.
4. Fabriksnulstil telefonen, tryk **6 gange** på velkomstskærmen og scan QR-koden.
5. Lad vinduet være åbent. Telefonen klargør sig selv og viser fremdriften. Når den er
   færdig, viser IN-BASE "✔ ISM589 er klargjort" med model, serienummer og IMEI.
6. Åbn FL-UPDATE på telefonen, og tillad den at **installere apps**. Så henter den FL-TMS.
   Det er det eneste trin i hånden, fordi Android ikke tillader, at det automatiseres.

En telefon klargøres igen ved at fabriksnulstille den og vælge **Klargør (QR-kode)…**.

**Fabriksnulstil en låst telefon.** Nulstilling er spærret både i Indstillinger og i
recovery, fordi Motorola fjerner punktet i recovery. Brug i stedet telefonens
nulstillingskode:
1. Find koden i IN-BASE under **Handling → Vis nulstillingskode**.
2. Åbn Telefon-appen på telefonen og tast `*#*#46227#*#*`. Det er I-N-B-A-S på tastaturet.
3. Indtast koden, og vælg **Fabriksnulstil telefonen**.

Telefoner, der er klargjort før nulstillingskoden blev indført (fx ISM321), kan kun
genskabes med Motorolas værktøj *Rescue and Smart Assistant* på pc'en
(<https://support.lenovo.com/rescue>). Brug funktionen *Rescue* til at installere telefonens
officielle software igen. Det sletter alt.

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

  Skjules en app, der skal bruges, så skriv pakkenavnet under **Ekstra apps** og klargør igen.

## Begrænsninger

- Der er ingen fjernstyring. En telefon kan ikke låses, spærres eller ændres på afstand. Nye
  regler kræver, at telefonen nulstilles og klargøres igen.
- Skjulte Google-apps (fx Play-butikken) opdateres ikke længere automatisk. Android-
  systemopdateringer kommer stadig.
- Låsen fjernes kun ved at nulstille med nulstillingskoden (`*#*#46227#*#*`). Koden ligger kun
  i IN-BASE og kan kun ses af administratorer.
