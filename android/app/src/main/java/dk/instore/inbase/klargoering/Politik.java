package dk.instore.inbase.klargoering;

import android.Manifest;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PersistableBundle;
import android.os.UserManager;
import android.provider.MediaStore;
import android.provider.Telephony;
import android.telecom.TelecomManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Telefonens regler. Gemmes på telefonen ved klargøringen, så de kan ændres (mail, Chrome)
 * og lægges på igen ved hver opstart og app-opdatering – uden nulstilling og uden server.
 *
 * Alle trin kan køres igen og igen: de slår både til og fra (fx vises Gmail igen,
 * når mail slås til).
 */
class Politik {
    private static final String NOEGLE = "politik";

    private static final String[] BEGRAENSNINGER = {
            UserManager.DISALLOW_FACTORY_RESET,
            UserManager.DISALLOW_ADD_USER,
            UserManager.DISALLOW_MODIFY_ACCOUNTS,
            UserManager.DISALLOW_SAFE_BOOT,
            UserManager.DISALLOW_DEBUGGING_FEATURES,
            UserManager.DISALLOW_USB_FILE_TRANSFER,
            UserManager.DISALLOW_MOUNT_PHYSICAL_MEDIA,
            UserManager.DISALLOW_CONFIG_CREDENTIALS,
            UserManager.DISALLOW_APPS_CONTROL,
            UserManager.DISALLOW_UNINSTALL_APPS,
            UserManager.DISALLOW_SET_WALLPAPER,
            // Internettet må ikke kunne slås fra. Wi-Fi må skiftes, og netværk må nulstilles.
            UserManager.DISALLOW_AIRPLANE_MODE,
            UserManager.DISALLOW_CONFIG_MOBILE_NETWORKS,
            UserManager.DISALLOW_CONFIG_PRIVATE_DNS,
    };

    /** Apps, der altid må ses ud over Telefon, SMS, Indstillinger og startskærmen. */
    private static final String[] STANDARD_TILLADTE = {
            "com.google.android.contacts", "com.android.contacts",
            "com.google.android.deskclock", "com.android.deskclock",
            "com.google.android.calculator", "com.android.calculator2",
            "com.motorola.camera3", "com.motorola.camera2", "com.motorola.camera",
            "com.android.camera2", "com.google.android.GoogleCamera",
            // Nyere/billige Motorola (fx Moto G05, Moto E14 – Android Go): andre kamera-apps.
            // Kameraet findes også ud fra, hvad telefonen kan (kameraApps).
            "com.motorola.camera5", "com.motorola.cameraone", "com.android.camera",
            "com.google.android.apps.cameralite",
            // Galleri – ellers kan de billeder, kameraet tager, ikke ses.
            "com.google.android.apps.photos", "com.google.android.apps.photosgo",
            "com.motorola.gallery", "com.android.gallery3d",
    };

    /** Skjules altid, også uden ikon: oplæsning (talesyntese, TalkBack og Vælg for at få læst op). */
    private static final String[] ALTID_SKJULTE = {
            "com.google.android.tts",
            "com.google.android.marvin.talkback",
    };

    /** Kendte PDF-læsere – findes også, selv om de er skjult fra en ældre klargøring. */
    private static final String[] PDF_LAESERE = {
            "com.google.android.apps.pdfviewer", "com.google.android.apps.nbu.files",
    };

    private static final String GMAIL = "com.google.android.gm";
    static final String CHROME = "com.android.chrome";
    /** Sat fra admin-menuen: næste ændring af skærmlåsen er godkendt (AdminReceiver). */
    static final String SKAERMLAAS_AABEN = "skaermlaas_aaben";
    /** Første skærmlås er sat (standardmønsteret ved klargøringen – registreres ikke). */
    static final String SKAERMLAAS_SAT = "skaermlaas_sat";
    /** Seneste ændring af skærmlåsen uden kode (tidspunkt) og antallet af dem. */
    static final String SKAERMLAAS_AENDRET = "skaermlaas_aendret";
    static final String SKAERMLAAS_ANTAL = "skaermlaas_antal";

    private final JSONObject data;

    private Politik(JSONObject data) {
        this.data = data;
    }

    /** Fra QR-kodens ekstra-data (se Klargoering). */
    static Politik fraEkstra(PersistableBundle ekstra) throws Exception {
        JSONObject data = new JSONObject();
        for (String n : new String[]{"navn", "organisation", "kontakt", "tilladte", "server"}) {
            String v = ekstra.getString(n);
            data.put(n, v == null ? "" : v.trim());
        }
        data.put("mail", "1".equals(ekstra.getString("mail")));
        data.put("chrome", false);
        return new Politik(data);
    }

    /** null, hvis telefonen er klargjort med en version før de gemte regler (v3 og ældre). */
    static Politik hent(Context ctx) {
        String json = ctx.getSharedPreferences(AdminActivity.PREFS, Context.MODE_PRIVATE)
                .getString(NOEGLE, null);
        try {
            return json == null ? null : new Politik(new JSONObject(json));
        } catch (Exception ex) {
            return null;
        }
    }

    void gem(Context ctx) {
        ctx.getSharedPreferences(AdminActivity.PREFS, Context.MODE_PRIVATE).edit()
                .putString(NOEGLE, data.toString()).commit();
    }

    String s(String noegle) {
        return data.optString(noegle, "");
    }

    boolean mail() {
        return data.optBoolean("mail");
    }

    boolean chrome() {
        return data.optBoolean("chrome");
    }

    boolean skaermlaasAaben() {
        return data.optBoolean(SKAERMLAAS_AABEN);
    }

    /** Ændringer af skærmlåsen uden kode – tom, hvis der ingen er. */
    String skaermlaasAendringer() {
        int antal = data.optInt(SKAERMLAAS_ANTAL);
        return antal == 0 ? "" : "Skærmlåsen er ændret uden kode " + antal + " gang(e), senest "
                + s(SKAERMLAAS_AENDRET) + ". Standardmønsteret gælder måske ikke længere.";
    }

    /** Skærmlåsen er sat eller ændret (AdminReceiver). Godkendte ændringer registreres ikke. */
    void skaermlaasAendret(String tidspunkt) throws Exception {
        if (!data.optBoolean(SKAERMLAAS_SAT)) {
            data.put(SKAERMLAAS_SAT, true);           // standardmønsteret ved klargøringen
        } else if (skaermlaasAaben()) {
            data.put(SKAERMLAAS_AABEN, false);        // godkendt i admin-menuen
            data.put(SKAERMLAAS_ANTAL, 0);
        } else {
            data.put(SKAERMLAAS_AENDRET, tidspunkt);
            data.put(SKAERMLAAS_ANTAL, data.optInt(SKAERMLAAS_ANTAL) + 1);
        }
    }

    void saet(String noegle, Object vaerdi) throws Exception {
        data.put(noegle, vaerdi);
    }

    // ----- trin -----------------------------------------------------------------

    /** Lægger alle regler på igen (opstart, app-opdatering, admin-menuen). Returnerer fejlene. */
    List<String> anvend(Context ctx) {
        List<String> fejl = new ArrayList<>();
        try { rettigheder(ctx); } catch (Exception ex) { fejl.add("Rettigheder: " + ex.getMessage()); }
        try { skjulApps(ctx, false); } catch (Exception ex) { fejl.add("Apps: " + ex.getMessage()); }
        try { kamera(ctx); } catch (Exception ex) { fejl.add("Kamera: " + ex.getMessage()); }
        try { begraensninger(ctx); } catch (Exception ex) { fejl.add("Begrænsninger: " + ex.getMessage()); }
        try {
            Sporing.forbered(ctx, this);
            Sporing.nu(ctx);
        } catch (Exception ex) {
            fejl.add("Find telefon/oplåsning: " + ex.getMessage());
        }
        return fejl;
    }

    void rettigheder(Context ctx) {
        DevicePolicyManager dpm = dpm(ctx);
        ComponentName admin = AdminReceiver.komponent(ctx);
        // Placering kun til Find telefon (Sporing) – én position, når IN-BASE beder om det.
        for (String r : new String[]{Manifest.permission.READ_PHONE_STATE,
                Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION,
                Manifest.permission.ACCESS_BACKGROUND_LOCATION}) {
            dpm.setPermissionGrantState(admin, ctx.getPackageName(), r,
                    DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED);
        }
        String org = s("organisation");
        if (!org.isEmpty()) dpm.setOrganizationName(admin, org);
        String kontakt = s("kontakt");
        dpm.setDeviceOwnerLockScreenInfo(admin, (s("navn") + (org.isEmpty() ? "" : " · " + org)
                + (kontakt.isEmpty() ? "" : "\n" + kontakt)).trim());
        if (!kontakt.isEmpty()) {
            // Vises, når brugeren rammer en spærret funktion (fx nulstilling eller konti).
            dpm.setShortSupportMessage(admin, kontakt);
            dpm.setLongSupportMessage(admin, "Telefonen er en firmatelefon (" + s("navn") + "). "
                    + kontakt);
        }
        // Kun systemets egne tilgængelighedstjenester – ingen oplæsere fra andre apps.
        dpm.setPermittedAccessibilityServices(admin, new ArrayList<>());
    }

    /**
     * Viser de tilladte apps og skjuler resten. alle=true (klargøringen): alle apps med ikon.
     * alle=false (senere): kun systemapps – så FL-UPDATE og FL-TMS, der installeres efter
     * klargøringen, aldrig skjules. Returnerer de apps, der blev skjult nu.
     */
    JSONArray skjulApps(Context ctx, boolean alle) throws Exception {
        DevicePolicyManager dpm = dpm(ctx);
        ComponentName admin = AdminReceiver.komponent(ctx);
        PackageManager pm = ctx.getPackageManager();
        Set<String> tilladte = new HashSet<>();
        tilladte.add(ctx.getPackageName());
        tilladte.add("com.android.settings");
        Collections.addAll(tilladte, STANDARD_TILLADTE);
        if (mail()) tilladte.add(GMAIL);
        if (chrome()) {
            tilladte.add(CHROME);
            // Ingen login i Chrome – telefonen tillader i forvejen ikke Google-konti.
            Bundle chromePolitik = new Bundle();
            chromePolitik.putInt("BrowserSignin", 0);
            dpm.setApplicationRestrictions(admin, CHROME, chromePolitik);
        }
        for (String p : s("tilladte").split(",")) if (!p.trim().isEmpty()) tilladte.add(p.trim());
        // Galleriet må aldrig skjules – ellers kan billederne fra kameraet ikke ses.
        tilladte.addAll(gallerier(pm));
        // PDF-læseren må aldrig skjules – briefs fra Gmail og FL-TMS åbnes i den.
        for (String p : pdfLaesere(pm)) if (!CHROME.equals(p) || chrome()) tilladte.add(p);
        // Kameraet må aldrig skjules – FL-TMS tager billeder gennem det. Findes ud fra, hvad
        // telefonen kan, så også kamera-apps uden for STANDARD_TILLADTE (andre modeller) ses.
        tilladte.addAll(kameraApps(pm));
        TelecomManager tc = (TelecomManager) ctx.getSystemService(Context.TELECOM_SERVICE);
        if (tc != null && tc.getDefaultDialerPackage() != null) tilladte.add(tc.getDefaultDialerPackage());
        String sms = Telephony.Sms.getDefaultSmsPackage(ctx);
        if (sms != null) tilladte.add(sms);
        // Startskærmen må aldrig skjules.
        Intent hjem = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME);
        for (ResolveInfo r : pm.queryIntentActivities(hjem, PackageManager.MATCH_ALL)) {
            tilladte.add(r.activityInfo.packageName);
        }

        // Tilladte apps, der er skjult (fx Gmail fra før mail blev slået til), vises igen.
        for (String pakke : tilladte) {
            if (dpm.isApplicationHidden(admin, pakke)) dpm.setApplicationHidden(admin, pakke, false);
        }

        Set<String> skjult = new HashSet<>();
        Intent start = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        for (ResolveInfo r : pm.queryIntentActivities(start, PackageManager.MATCH_ALL)) {
            String pakke = r.activityInfo.packageName;
            if (tilladte.contains(pakke) || skjult.contains(pakke)) continue;
            boolean system = (r.activityInfo.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0;
            if ((alle || system) && dpm.setApplicationHidden(admin, pakke, true)) skjult.add(pakke);
        }
        for (String pakke : ALTID_SKJULTE) {
            // Returnerer false, hvis pakken ikke findes på telefonen.
            if (dpm.setApplicationHidden(admin, pakke, true)) skjult.add(pakke);
        }
        return new JSONArray(skjult);
    }

    /** Systemapps, der kan åbne en PDF (også skjulte), uden Chrome. */
    static Set<String> pdfLaesere(PackageManager pm) {
        Set<String> laesere = new HashSet<>();
        Intent pdf = new Intent(Intent.ACTION_VIEW)
                .setDataAndType(Uri.parse("content://dk.instore.inbase/brief.pdf"), "application/pdf");
        for (ResolveInfo r : pm.queryIntentActivities(pdf,
                PackageManager.MATCH_ALL | PackageManager.MATCH_UNINSTALLED_PACKAGES)) {
            boolean system = (r.activityInfo.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0;
            if (system && !CHROME.equals(r.activityInfo.packageName)) {
                laesere.add(r.activityInfo.packageName);
            }
        }
        for (String pakke : PDF_LAESERE) {
            try {
                pm.getApplicationInfo(pakke, PackageManager.MATCH_UNINSTALLED_PACKAGES);
                laesere.add(pakke);
            } catch (PackageManager.NameNotFoundException ex) {
                // Ikke på telefonen.
            }
        }
        return laesere;
    }

    /**
     * Systemapps, der kan tage billeder eller video (også skjulte fra en ældre klargøring).
     * Reserve: systemapps med "camera" i pakkenavnet – hvis en model ikke melder sig på
     * kamera-handlingerne, mens den er skjult. Kun apps med ikon skjules, så de øvrige er uden betydning.
     */
    static Set<String> kameraApps(PackageManager pm) {
        Set<String> kameraer = new HashSet<>();
        for (String handling : new String[]{MediaStore.ACTION_IMAGE_CAPTURE,
                MediaStore.ACTION_VIDEO_CAPTURE, MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA}) {
            for (ResolveInfo r : pm.queryIntentActivities(new Intent(handling),
                    PackageManager.MATCH_ALL | PackageManager.MATCH_UNINSTALLED_PACKAGES)) {
                if ((r.activityInfo.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0) {
                    kameraer.add(r.activityInfo.packageName);
                }
            }
        }
        for (ApplicationInfo a : pm.getInstalledApplications(PackageManager.MATCH_UNINSTALLED_PACKAGES)) {
            if ((a.flags & ApplicationInfo.FLAG_SYSTEM) != 0 && a.packageName.contains(".camera")) {
                kameraer.add(a.packageName);
            }
        }
        return kameraer;
    }

    /** Galleri-apps på telefonen (også skjulte fra en ældre klargøring), fx Motorola-galleriet. */
    static Set<String> gallerier(PackageManager pm) {
        Set<String> gallerier = new HashSet<>();
        Intent galleri = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_APP_GALLERY);
        for (ResolveInfo r : pm.queryIntentActivities(galleri,
                PackageManager.MATCH_ALL | PackageManager.MATCH_UNINSTALLED_PACKAGES)) {
            if ((r.activityInfo.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0) {
                gallerier.add(r.activityInfo.packageName);
            }
        }
        return gallerier;
    }

    /** Det, en app skal have for at tage billeder og se/vedhæfte dem (Android 10-15). */
    private static final Set<String> KAMERA_RETTIGHEDER = new HashSet<>(Arrays.asList(
            Manifest.permission.CAMERA,
            Manifest.permission.READ_MEDIA_IMAGES, Manifest.permission.READ_MEDIA_VIDEO,
            Manifest.permission.READ_EXTERNAL_STORAGE, Manifest.permission.WRITE_EXTERNAL_STORAGE));

    /**
     * Kamera og billeder skal altid virke – FL-TMS tager billeder gennem kameraet:
     * 1) kamera- og galleri-apps, der er skjult (fx fra klargøring med en ældre version), vises igen;
     * 2) apps installeret efter klargøringen (FL-TMS, FL-UPDATE, ekstra apps) får kamera- og
     *    billedrettighederne, de beder om – så et fejltryk på "Afvis" aldrig stopper kameraet.
     * Kører ved klargøring, opstart, app-opdatering og hver time (SporingJob), så også apps,
     * FL-UPDATE installerer senere, får kameraet uden genstart. Bruger ikke de gemte regler.
     */
    static void kamera(Context ctx) {
        DevicePolicyManager dpm = dpm(ctx);
        ComponentName admin = AdminReceiver.komponent(ctx);
        PackageManager pm = ctx.getPackageManager();
        Set<String> synlige = kameraApps(pm);
        synlige.addAll(gallerier(pm));
        for (String pakke : synlige) {
            if (dpm.isApplicationHidden(admin, pakke)) dpm.setApplicationHidden(admin, pakke, false);
        }
        for (PackageInfo p : pm.getInstalledPackages(PackageManager.GET_PERMISSIONS)) {
            if (p.applicationInfo == null || p.requestedPermissions == null
                    || (p.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0
                    || ctx.getPackageName().equals(p.packageName)) {
                continue;
            }
            for (String r : p.requestedPermissions) {
                if (KAMERA_RETTIGHEDER.contains(r)) {
                    dpm.setPermissionGrantState(admin, p.packageName, r,
                            DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED);
                }
            }
        }
    }

    void begraensninger(Context ctx) {
        DevicePolicyManager dpm = dpm(ctx);
        ComponentName admin = AdminReceiver.komponent(ctx);
        for (String b : BEGRAENSNINGER) {
            // Med firma-mail må der tilføjes en IMAP-konto i Gmail – men aldrig en Google-konto.
            if (mail() && UserManager.DISALLOW_MODIFY_ACCOUNTS.equals(b)) {
                dpm.clearUserRestriction(admin, b);
            } else {
                dpm.addUserRestriction(admin, b);
            }
        }
        dpm.setAccountManagementDisabled(admin, "com.google", true);
        skaermlaas(ctx, dpm, admin);
    }

    /**
     * Telefonen skal altid have en skærmlås (standardmønsteret tegnes ved klargøringen), så
     * den ikke kan fjernes. Android kan ikke forhindre, at mønsteret ændres – AdminReceiver
     * registrerer derfor ændringer, der ikke er godkendt i admin-menuen (SKAERMLAAS_AABEN).
     */
    private void skaermlaas(Context ctx, DevicePolicyManager dpm, ComponentName admin) {
        if (Build.VERSION.SDK_INT >= 31) {
            dpm.setRequiredPasswordComplexity(DevicePolicyManager.PASSWORD_COMPLEXITY_LOW);
        } else {
            dpm.setPasswordQuality(admin, DevicePolicyManager.PASSWORD_QUALITY_SOMETHING);
        }
    }

    private static DevicePolicyManager dpm(Context ctx) {
        return (DevicePolicyManager) ctx.getSystemService(Context.DEVICE_POLICY_SERVICE);
    }
}
