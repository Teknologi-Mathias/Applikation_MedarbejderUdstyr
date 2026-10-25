package dk.instore.inbase.klargoering;

import android.Manifest;
import android.app.PendingIntent;
import android.app.WallpaperManager;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Build;
import android.os.PersistableBundle;
import android.os.UserManager;
import android.provider.Telephony;
import android.telecom.TelecomManager;
import android.telephony.TelephonyManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

/**
 * Klargør telefonen til drift – uden server, kun med det IN-BASE har lagt i QR-koden.
 *
 * Ekstra-data fra QR-koden (PROVISIONING_ADMIN_EXTRAS_BUNDLE, alle tekst):
 *   server         http://<pc>:<port> – IN-BASE's midlertidige server under klargøringen
 *   token          engangskode, så kun den rigtige telefon kan melde tilbage
 *   enhed_id, navn telefonens id og ERP-enhedsnavn (fx ISM589)
 *   fl_update_url  hvor FL-UPDATE.apk hentes (mx.fl-it.net)
 *   baggrund       "1" = hent baggrundsbillede fra IN-BASE
 *   nulstillingskode  kode til administrator-menuen (*#*#46227#*#*) – fabriksnulstilling
 *   mail           "1" = firma-mail: Gmail-appen synlig, IMAP-konti tilladt, Google-konti spærret
 *   tilladte       ekstra pakker (kommasepareret), der må ses ud over STANDARD_TILLADTE
 *   organisation   vises på låseskærmen (valgfri)
 *
 * Hvert trin fanger sine egne fejl: en fejl i ét trin stopper ikke resten.
 */
class Klargoering {
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
    };

    /** Apps, der altid må ses ud over Telefon, SMS, Indstillinger og startskærmen. */
    private static final String[] STANDARD_TILLADTE = {
            "com.google.android.contacts", "com.android.contacts",
            "com.google.android.deskclock", "com.android.deskclock",
            "com.google.android.calculator", "com.android.calculator2",
            "com.motorola.camera3", "com.motorola.camera2", "com.motorola.camera",
            "com.android.camera2", "com.google.android.GoogleCamera",
    };

    private static final String GMAIL = "com.google.android.gm";

    private final Context ctx;
    private final PersistableBundle ekstra;
    private final Consumer<String> log;
    private final DevicePolicyManager dpm;
    private final ComponentName admin;
    private final JSONArray fejl = new JSONArray();
    private final JSONObject rapport = new JSONObject();

    Klargoering(Context ctx, PersistableBundle ekstra, Consumer<String> log) {
        this.ctx = ctx;
        this.ekstra = ekstra == null ? new PersistableBundle() : ekstra;
        this.log = log;
        this.dpm = (DevicePolicyManager) ctx.getSystemService(Context.DEVICE_POLICY_SERVICE);
        this.admin = AdminReceiver.komponent(ctx);
    }

    private String e(String noegle) {
        String v = ekstra.getString(noegle);
        return v == null ? "" : v.trim();
    }

    /** true hvis alt lykkedes. */
    boolean koer() {
        log.accept("Telefon: " + e("navn"));
        // Først: administrator-nøglen (*#*#46227#*#*), så telefonen altid kan nulstilles.
        trin("Nulstillingskode", () -> {
            if (e("nulstillingskode").isEmpty()) throw new Exception("ingen kode i QR-koden");
            ctx.getSharedPreferences(AdminActivity.PREFS, Context.MODE_PRIVATE).edit()
                    .putString(AdminActivity.KODE, e("nulstillingskode")).commit();
        });
        trin("Rettigheder", this::rettigheder);
        trin("Telefonoplysninger", this::oplysninger);
        if ("1".equals(e("baggrund"))) trin("Baggrundsbillede", this::baggrund);
        trin("Skjuler apps, der ikke skal bruges", this::skjulApps);
        trin("Henter og installerer FL-UPDATE", this::flUpdate);
        trin("Låser indstillinger", this::begraensninger);
        trin("Melder tilbage til IN-BASE", this::meldTilbage);
        return fejl.length() == 0;
    }

    private interface Trin { void koer() throws Exception; }

    private void trin(String navn, Trin trin) {
        log.accept("• " + navn + " …");
        try {
            trin.koer();
        } catch (Exception ex) {
            String tekst = navn + ": " + ex.getMessage();
            fejl.put(tekst);
            log.accept("  FEJL – " + ex.getMessage());
        }
    }

    // ----- trin -----------------------------------------------------------------

    private void rettigheder() {
        dpm.setPermissionGrantState(admin, ctx.getPackageName(), Manifest.permission.READ_PHONE_STATE,
                DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED);
        String org = e("organisation");
        if (!org.isEmpty()) dpm.setOrganizationName(admin, org);
        dpm.setDeviceOwnerLockScreenInfo(admin, (e("navn") + (org.isEmpty() ? "" : " · " + org)).trim());
    }

    private void oplysninger() throws Exception {
        rapport.put("producent", Build.MANUFACTURER);
        rapport.put("model", Build.MODEL);
        rapport.put("android_version", Build.VERSION.RELEASE);
        try {
            rapport.put("serienummer", Build.getSerial());
        } catch (SecurityException ex) {
            rapport.put("serienummer", "");
        }
        try {
            TelephonyManager tm = (TelephonyManager) ctx.getSystemService(Context.TELEPHONY_SERVICE);
            String imei = tm == null ? null : tm.getImei();
            rapport.put("imei", imei == null ? "" : imei);
        } catch (SecurityException | UnsupportedOperationException ex) {
            rapport.put("imei", "");
        }
    }

    private void baggrund() throws Exception {
        HttpURLConnection forb = aabn(e("server") + "/baggrund");
        try (InputStream ind = forb.getInputStream()) {
            WallpaperManager.getInstance(ctx).setStream(ind, null, true,
                    WallpaperManager.FLAG_SYSTEM | WallpaperManager.FLAG_LOCK);
        } finally {
            forb.disconnect();
        }
    }

    private void skjulApps() throws Exception {
        PackageManager pm = ctx.getPackageManager();
        Set<String> tilladte = new HashSet<>();
        tilladte.add(ctx.getPackageName());
        tilladte.add("com.android.settings");
        java.util.Collections.addAll(tilladte, STANDARD_TILLADTE);
        if (mail()) tilladte.add(GMAIL);
        for (String p : e("tilladte").split(",")) if (!p.trim().isEmpty()) tilladte.add(p.trim());
        TelecomManager tc = (TelecomManager) ctx.getSystemService(Context.TELECOM_SERVICE);
        if (tc != null && tc.getDefaultDialerPackage() != null) tilladte.add(tc.getDefaultDialerPackage());
        String sms = Telephony.Sms.getDefaultSmsPackage(ctx);
        if (sms != null) tilladte.add(sms);
        // Startskærmen må aldrig skjules.
        Intent hjem = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME);
        for (ResolveInfo r : pm.queryIntentActivities(hjem, PackageManager.MATCH_ALL)) {
            tilladte.add(r.activityInfo.packageName);
        }

        Intent start = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        List<ResolveInfo> apps = pm.queryIntentActivities(start, PackageManager.MATCH_ALL);
        Set<String> skjult = new HashSet<>();
        for (ResolveInfo r : apps) {
            String pakke = r.activityInfo.packageName;
            if (tilladte.contains(pakke) || skjult.contains(pakke)) continue;
            if (dpm.setApplicationHidden(admin, pakke, true)) skjult.add(pakke);
        }
        rapport.put("skjulte_apps", new JSONArray(skjult));
        log.accept("  " + skjult.size() + " apps skjult");
    }

    private void flUpdate() throws Exception {
        if (e("fl_update_url").isEmpty()) throw new Exception("intet link til FL-UPDATE i QR-koden");
        File apk = new File(ctx.getCacheDir(), "fl-update.apk");
        HttpURLConnection forb = aabn(e("fl_update_url"));
        try (InputStream ind = forb.getInputStream(); OutputStream ud = new FileOutputStream(apk)) {
            kopier(ind, ud);
        } finally {
            forb.disconnect();
        }
        log.accept("  hentet (" + apk.length() / 1024 + " KB)");

        PackageInstaller pi = ctx.getPackageManager().getPackageInstaller();
        int id = pi.createSession(new PackageInstaller.SessionParams(
                PackageInstaller.SessionParams.MODE_FULL_INSTALL));
        try (PackageInstaller.Session session = pi.openSession(id)) {
            try (OutputStream ud = session.openWrite("fl-update", 0, apk.length());
                 InputStream ind = new FileInputStream(apk)) {
                kopier(ind, ud);
                session.fsync(ud);
            }
            CountDownLatch venter = new CountDownLatch(1);
            InstallReceiver.venter = venter;
            Intent svar = new Intent(ctx, InstallReceiver.class);
            PendingIntent pend = PendingIntent.getBroadcast(ctx, id, svar,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE);
            session.commit(pend.getIntentSender());
            if (!venter.await(3, TimeUnit.MINUTES)) throw new Exception("installationen svarede ikke");
        }
        if (InstallReceiver.status != PackageInstaller.STATUS_SUCCESS) {
            throw new Exception("installation afvist: " + InstallReceiver.besked);
        }
        String pakke = InstallReceiver.pakke;
        if (!pakke.isEmpty()) dpm.setUninstallBlocked(admin, pakke, true);
        rapport.put("fl_update", pakke);
        log.accept("  installeret (" + pakke + ")");
        apk.delete();
    }

    private void begraensninger() {
        for (String b : BEGRAENSNINGER) {
            // Med firma-mail må der tilføjes en IMAP-konto i Gmail – men aldrig en Google-konto.
            if (mail() && UserManager.DISALLOW_MODIFY_ACCOUNTS.equals(b)) continue;
            dpm.addUserRestriction(admin, b);
        }
        if (mail()) dpm.setAccountManagementDisabled(admin, "com.google", true);
    }

    private boolean mail() {
        return "1".equals(e("mail"));
    }

    private void meldTilbage() throws Exception {
        rapport.put("enhed_id", e("enhed_id"));
        rapport.put("fejl", fejl);
        byte[] data = rapport.toString().getBytes(StandardCharsets.UTF_8);
        Exception sidste = null;
        for (int forsoeg = 0; forsoeg < 3; forsoeg++) {
            try {
                HttpURLConnection forb = aabn(e("server") + "/api/klargjort");
                forb.setRequestMethod("POST");
                forb.setDoOutput(true);
                forb.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                forb.setRequestProperty("X-Inbase-Token", e("token"));
                try (OutputStream ud = forb.getOutputStream()) {
                    ud.write(data);
                }
                int kode = forb.getResponseCode();
                forb.disconnect();
                if (kode == 200) return;
                sidste = new Exception("IN-BASE svarede " + kode);
            } catch (Exception ex) {
                sidste = ex;
            }
            Thread.sleep(3000);
        }
        throw new Exception("IN-BASE kunne ikke nås (" + sidste.getMessage() +
                "). Er pc'en på samme Wi-Fi, og er QR-vinduet stadig åbent?");
    }

    // ----- hjælpere --------------------------------------------------------------

    private static HttpURLConnection aabn(String adresse) throws Exception {
        HttpURLConnection forb = (HttpURLConnection) new URL(adresse).openConnection();
        forb.setConnectTimeout(15000);
        forb.setReadTimeout(60000);
        forb.setInstanceFollowRedirects(true);
        return forb;
    }

    private static void kopier(InputStream ind, OutputStream ud) throws Exception {
        byte[] buf = new byte[64 * 1024];
        int n;
        while ((n = ind.read(buf)) > 0) ud.write(buf, 0, n);
    }
}
