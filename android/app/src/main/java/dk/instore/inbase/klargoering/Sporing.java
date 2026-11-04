package dk.instore.inbase.klargoering;

import android.annotation.SuppressLint;
import android.app.admin.DevicePolicyManager;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.BatteryManager;
import android.os.Build;
import android.os.CancellationSignal;
import android.os.Looper;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Find telefon og Lås skærmlåsen op (IN-BASE → Telefoner → Handling).
 *
 * Telefonen kan ikke kaldes udefra (mobilnettets fælles IP-adresse, ingen Google-push), så den
 * spørger selv IN-BASE's Supabase, om der er bedt om dens position eller en oplåsning:
 *   - når den låses op, eller nogen tegner et forkert mønster (AdminReceiver), højst hvert 10. min
 *   - når den sættes i laderen eller en pc (JOB_LADER), højst én gang i timen, mens den lader
 *   - én gang i timen (periodisk job, kun med net – Android samler det med andre opvågninger)
 *   - ved opstart og app-opdatering (Politik.anvend)
 * Er der bedt om positionen, slås placering kortvarigt til, og én position sendes. Er der bedt
 * om oplåsning, sætter LaasOp skærmlåskoden som PIN. Er en nyere styrings-app udgivet, henter og
 * installerer Selvopdatering den (migrering 026). Der spores ikke løbende.
 *
 * Tjekket er en anonym RPC (inbase_mdm_phone_checkin, migrering 024/025) med enhedsnavnet og
 * nøglen sha256("sporing:" + nulstillingskode) – samme som sporingsnoegle() i
 * app/domain/mdm_enhed.py. Det, tjekket bruger, ligger i device-protected storage (de()), så det
 * også virker før første oplåsning efter en genstart (fx når mønsteret er glemt).
 */
final class Sporing {
    static final int JOB_TIME = 4601;
    static final int JOB_NU = 4602;
    static final int JOB_LADER = 4603;
    static final String SENEST_SET = "sporing_senest_set";   // vises i admin-menuen
    private static final String SENEST = "sporing_senest";   // ms – pause mellem tjek ved oplåsning
    private static final String NAVN = "navn";
    private static final long INTERVAL_MIN = 60;
    private static final long PAUSE_MS = TimeUnit.MINUTES.toMillis(10);
    private static final long GPS_TIMEOUT_S = 45;
    private static final long NET_TIMEOUT_S = 20;

    private Sporing() {}

    /** Lager, der kan læses før første oplåsning efter genstart. */
    static SharedPreferences de(Context ctx) {
        return ctx.createDeviceProtectedStorageContext()
                .getSharedPreferences("inbase_de", Context.MODE_PRIVATE);
    }

    /**
     * Kopierer enhedsnavn og nulstillingskode til de(), laver oplåsningsnøglen og planlægger
     * tjekkene (klargøring, opstart, app-opdatering – altid efter oplåsning).
     */
    static void forbered(Context ctx, Politik politik) {
        de(ctx).edit()
                .putString(NAVN, politik.s("navn"))
                .putString(AdminActivity.KODE, ctx.getSharedPreferences(AdminActivity.PREFS,
                        Context.MODE_PRIVATE).getString(AdminActivity.KODE, ""))
                .commit();
        LaasOp.forbered(ctx);
        planlaeg(ctx);
    }

    /** Timetjekket og ladetjekket – lægges kun ind, hvis de ikke allerede findes. */
    static void planlaeg(Context ctx) {
        JobScheduler js = ctx.getSystemService(JobScheduler.class);
        if (js == null) return;
        if (js.getPendingJob(JOB_TIME) == null) {
            js.schedule(new JobInfo.Builder(JOB_TIME, new ComponentName(ctx, SporingJob.class))
                    .setPeriodic(TimeUnit.MINUTES.toMillis(INTERVAL_MIN))
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                    .setPersisted(true)
                    .build());
        }
        if (js.getPendingJob(JOB_LADER) == null) lader(ctx, false);
    }

    /**
     * Tjek, når telefonen sættes i laderen/pc'en. Engangsjob, der lægges ind igen efter hver
     * kørsel (SporingJob, efter jobFinished) med en times ventetid – så det kører med det samme
     * ved næste tilslutning, men kun hver time, mens telefonen lader.
     */
    static void lader(Context ctx, boolean efterKoersel) {
        JobScheduler js = ctx.getSystemService(JobScheduler.class);
        if (js == null) return;
        js.schedule(new JobInfo.Builder(JOB_LADER, new ComponentName(ctx, SporingJob.class))
                .setRequiresCharging(true)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setMinimumLatency(efterKoersel ? TimeUnit.MINUTES.toMillis(INTERVAL_MIN) : 0)
                .setPersisted(true)
                .build());
    }

    /** Et tjek så snart der er net (oplåsning, opstart). Venter selv, hvis telefonen er uden net. */
    static void nu(Context ctx) {
        JobScheduler js = ctx.getSystemService(JobScheduler.class);
        if (js == null) return;
        js.schedule(new JobInfo.Builder(JOB_NU, new ComponentName(ctx, SporingJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .build());
    }

    static String noegle(String nulstillingskode) throws Exception {
        byte[] h = MessageDigest.getInstance("SHA-256")
                .digest(("sporing:" + nulstillingskode).getBytes(StandardCharsets.UTF_8));
        StringBuilder hex = new StringBuilder();
        for (byte b : h) hex.append(String.format("%02x", b));
        return hex.toString();
    }

    /** Selve tjekket (kører i SporingJob's tråd). pause=true: springes over, hvis det er nyt. */
    static void tjek(Context ctx, boolean pause) throws Exception {
        SharedPreferences de = de(ctx);
        long nu = System.currentTimeMillis();
        if (pause && nu - de.getLong(SENEST, 0) < PAUSE_MS) return;
        String navn = de.getString(NAVN, "");
        String kode = de.getString(AdminActivity.KODE, "");
        String url = ctx.getString(R.string.supabase_url);
        // Klargjort før de gemte regler, uden egen kode eller endnu ikke forberedt – kan ikke findes.
        if (navn.isEmpty() || kode.isEmpty() || url.isEmpty()) return;
        String noegle = noegle(kode);
        JSONObject rapport = new JSONObject().put("laas_op_klar", LaasOp.klar(ctx))
                .put("version", BuildConfig.VERSION_NAME);
        JSONObject svar = kald(ctx, url, navn, noegle, null, rapport);
        de.edit().putLong(SENEST, nu).putString(SENEST_SET,
                new SimpleDateFormat("dd-MM-yyyy HH:mm", Locale.ROOT).format(new Date(nu))).apply();
        if (svar.optBoolean("laas_op")) {
            kald(ctx, url, navn, noegle, null,
                    new JSONObject().put("laas_op", LaasOp.udfoer(ctx, kode)));
        }
        if (svar.optBoolean("find")) {
            kald(ctx, url, navn, noegle, position(ctx), null);
        }
        // Sidst: installeres en ny version af denne app, lukkes processen undervejs.
        Selvopdatering.tjek(ctx, url, navn, noegle, svar.optJSONObject("app"));
    }

    private static JSONObject kald(Context ctx, String url, String navn, String noegle,
                                   JSONObject position, JSONObject rapport) throws Exception {
        JSONObject krop = new JSONObject();
        krop.put("p_name", navn);
        krop.put("p_key", noegle);
        krop.put("p_location", position == null ? JSONObject.NULL : position);
        krop.put("p_report", rapport == null ? JSONObject.NULL : rapport);
        return new JSONObject(rpc(ctx, url, "inbase_mdm_phone_checkin", krop));
    }

    /** Kalder en RPC i Supabase som anon og returnerer svaret (JSON som tekst). */
    static String rpc(Context ctx, String url, String funktion, JSONObject krop) throws Exception {
        String anon = ctx.getString(R.string.supabase_noegle);
        HttpURLConnection forb = Installer.aabn(url + "/rest/v1/rpc/" + funktion);
        try {
            forb.setRequestMethod("POST");
            forb.setDoOutput(true);
            forb.setRequestProperty("Content-Type", "application/json");
            forb.setRequestProperty("apikey", anon);
            // Ældre anon-nøgler er JWT'er og sendes også som Bearer; nye publishable-nøgler ikke.
            if (anon.startsWith("eyJ")) forb.setRequestProperty("Authorization", "Bearer " + anon);
            try (OutputStream ud = forb.getOutputStream()) {
                ud.write(krop.toString().getBytes(StandardCharsets.UTF_8));
            }
            int status = forb.getResponseCode();
            if (status / 100 != 2) throw new Exception("Supabase svarede " + status);
            try (InputStream ind = forb.getInputStream()) {
                ByteArrayOutputStream data = new ByteArrayOutputStream();
                byte[] buf = new byte[64 * 1024];
                for (int n; (n = ind.read(buf)) > 0; ) data.write(buf, 0, n);
                return data.toString("UTF-8");
            }
        } finally {
            forb.disconnect();
        }
    }

    /** Én position (eller en fejl) – placering slås til imens og tilbage bagefter. */
    @SuppressLint("MissingPermission")   // se enPosition
    private static JSONObject position(Context ctx) throws Exception {
        LocationManager lm = ctx.getSystemService(LocationManager.class);
        DevicePolicyManager dpm = ctx.getSystemService(DevicePolicyManager.class);
        ComponentName admin = AdminReceiver.komponent(ctx);
        boolean varTil = lm.isLocationEnabled();
        JSONObject svar = new JSONObject();
        try {
            if (!varTil && Build.VERSION.SDK_INT >= 30) dpm.setLocationEnabled(admin, true);
            Location l = null;
            if (lm.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                l = enPosition(lm, LocationManager.GPS_PROVIDER, GPS_TIMEOUT_S);
            }
            if (l == null && lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                l = enPosition(lm, LocationManager.NETWORK_PROVIDER, NET_TIMEOUT_S);
            }
            if (l == null) l = lm.getLastKnownLocation(LocationManager.GPS_PROVIDER);
            if (l == null) l = lm.getLastKnownLocation(LocationManager.NETWORK_PROVIDER);
            if (l == null) {
                svar.put("fejl", lm.isLocationEnabled() ? "Intet GPS- eller netværkssignal."
                        : "Placering er slået fra og kunne ikke slås til (kræver Android 11).");
            } else {
                svar.put("lat", l.getLatitude());
                svar.put("lng", l.getLongitude());
                if (l.hasAccuracy()) svar.put("noejagtighed", l.getAccuracy());
                svar.put("tid", new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.ROOT)
                        .format(new Date(l.getTime())));
            }
        } catch (SecurityException ex) {
            svar.put("fejl", "Ingen adgang til placering – vælg Anvend regler igen i admin-menuen.");
        } finally {
            if (!varTil && Build.VERSION.SDK_INT >= 30) dpm.setLocationEnabled(admin, false);
        }
        BatteryManager batteri = ctx.getSystemService(BatteryManager.class);
        if (batteri != null) {
            svar.put("batteri", batteri.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY));
        }
        return svar;
    }

    /**
     * Venter højst timeout sekunder på en frisk position fra én kilde. Rettigheden tildeler
     * appen selv som administrator (Politik.rettigheder); en SecurityException fanges i position().
     */
    @SuppressLint("MissingPermission")
    @SuppressWarnings("deprecation")   // requestSingleUpdate: kun på Android 10
    private static Location enPosition(LocationManager lm, String kilde, long timeout)
            throws InterruptedException {
        AtomicReference<Location> fundet = new AtomicReference<>();
        CountDownLatch klar = new CountDownLatch(1);
        CancellationSignal stop = new CancellationSignal();
        LocationListener lytter = l -> {
            fundet.set(l);
            klar.countDown();
        };
        if (Build.VERSION.SDK_INT >= 30) {
            lm.getCurrentLocation(kilde, stop, Runnable::run, lytter::onLocationChanged);
        } else {
            lm.requestSingleUpdate(kilde, lytter, Looper.getMainLooper());
        }
        if (!klar.await(timeout, TimeUnit.SECONDS)) {
            stop.cancel();
            if (Build.VERSION.SDK_INT < 30) lm.removeUpdates(lytter);
        }
        return fundet.get();
    }
}
