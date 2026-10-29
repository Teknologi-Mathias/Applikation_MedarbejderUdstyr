package dk.instore.inbase.klargoering;

import android.app.WallpaperManager;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.os.Build;
import android.os.PersistableBundle;
import android.telephony.TelephonyManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
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
 *   tilladte       ekstra pakker (kommasepareret), der må ses ud over Politik.STANDARD_TILLADTE
 *   organisation   vises på låseskærmen (valgfri)
 *   kontakt        fx "Kontakt din IT-administrator (…)" – låseskærm og ved spærrede funktioner
 *
 * Reglerne (apps, begrænsninger, låseskærm) ligger i Politik og gemmes på telefonen –
 * her køres de første gang. FL-UPDATE, baggrund og tilbagemelding sker kun ved klargøringen.
 *
 * Hvert trin fanger sine egne fejl: en fejl i ét trin stopper ikke resten.
 */
class Klargoering {
    private final Context ctx;
    private final PersistableBundle ekstra;
    private final Consumer<String> log;
    private final DevicePolicyManager dpm;
    private final ComponentName admin;
    private final JSONArray fejl = new JSONArray();
    private final JSONObject rapport = new JSONObject();
    private Politik politik;

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
        try {
            politik = Politik.fraEkstra(ekstra);
        } catch (Exception ex) {
            // Kan kun ske ved en programfejl – uden regler kan telefonen ikke klargøres.
            fejl.put("Regler: " + ex.getMessage());
            log.accept("  FEJL – " + ex.getMessage());
            return false;
        }
        // Reglerne gemmes, så de kan ændres og lægges på igen ved hver opstart.
        trin("Gemmer regler", () -> politik.gem(ctx));
        trin("Rettigheder", () -> politik.rettigheder(ctx));
        trin("Telefonoplysninger", this::oplysninger);
        if ("1".equals(e("baggrund"))) trin("Baggrundsbillede", this::baggrund);
        trin("Skjuler apps, der ikke skal bruges", this::skjulApps);
        trin("Henter og installerer FL-UPDATE", this::flUpdate);
        trin("Låser indstillinger", () -> politik.begraensninger(ctx));
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

    private void oplysninger() throws Exception {
        rapport.put("app_version", BuildConfig.VERSION_NAME);
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
        HttpURLConnection forb = Installer.aabn(e("server") + "/baggrund");
        try (InputStream ind = forb.getInputStream()) {
            WallpaperManager.getInstance(ctx).setStream(ind, null, true,
                    WallpaperManager.FLAG_SYSTEM | WallpaperManager.FLAG_LOCK);
        } finally {
            forb.disconnect();
        }
    }

    private void skjulApps() throws Exception {
        JSONArray skjult = politik.skjulApps(ctx, true);
        rapport.put("skjulte_apps", skjult);
        log.accept("  " + skjult.length() + " apps skjult");
        if (Politik.pdfLaesere(ctx.getPackageManager()).isEmpty()) {
            fejl.put("PDF: ingen PDF-læser på telefonen – briefs fra mail og FL-TMS kan ikke åbnes");
            log.accept("  ADVARSEL – ingen PDF-læser fundet");
        }
    }

    private void flUpdate() throws Exception {
        if (e("fl_update_url").isEmpty()) throw new Exception("intet link til FL-UPDATE i QR-koden");
        File apk = new File(ctx.getCacheDir(), "fl-update.apk");
        Installer.hent(e("fl_update_url"), apk);
        log.accept("  hentet (" + apk.length() / 1024 + " KB)");
        String pakke = Installer.installer(ctx, apk);
        if (!pakke.isEmpty()) dpm.setUninstallBlocked(admin, pakke, true);
        rapport.put("fl_update", pakke);
        log.accept("  installeret (" + pakke + ")");
        apk.delete();
    }

    private void meldTilbage() throws Exception {
        rapport.put("enhed_id", e("enhed_id"));
        rapport.put("fejl", fejl);
        byte[] data = rapport.toString().getBytes(StandardCharsets.UTF_8);
        Exception sidste = null;
        for (int forsoeg = 0; forsoeg < 3; forsoeg++) {
            try {
                HttpURLConnection forb = Installer.aabn(e("server") + "/api/klargjort");
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
}
