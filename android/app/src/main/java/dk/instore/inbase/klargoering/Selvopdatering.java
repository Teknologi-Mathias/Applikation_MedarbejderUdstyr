package dk.instore.inbase.klargoering;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.UserManager;
import android.util.Base64;

import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.File;
import java.io.FileOutputStream;
import java.security.MessageDigest;
import java.util.concurrent.TimeUnit;

/**
 * Automatisk opdatering af denne app (IN-BASE → Telefoner → Opdater telefoner → Udgiv til alle
 * telefoner, migrering 026) – uden kode og uden pc i nærheden.
 *
 * Tjekket (Sporing) får den udgivne versionCode og kontrolsum. Er den nyere end denne app, hentes
 * appen med telefonens nøgle (inbase_mdm_phone_app), kontrolsummen tjekkes, og den installeres
 * stille (Device Owner). Android afviser en app med en anden signatur. Mislykkes det, prøves samme
 * version først igen efter 6 timer, så en fejl ikke giver trafik ved hvert tjek.
 */
final class Selvopdatering {
    private static final String FORSOEGT = "opdatering_forsoegt";   // "versionCode:ms"
    private static final long VENT_MS = TimeUnit.HOURS.toMillis(6);

    private Selvopdatering() {}

    static void tjek(Context ctx, String url, String navn, String noegle, JSONObject app)
            throws Exception {
        if (app == null) return;
        int version = app.optInt("version_code");
        if (version <= BuildConfig.VERSION_CODE) return;
        // Installation kræver, at telefonen har været låst op siden opstart.
        if (!ctx.getSystemService(UserManager.class).isUserUnlocked()) return;
        SharedPreferences de = Sporing.de(ctx);
        long nu = System.currentTimeMillis();
        String[] forsoegt = de.getString(FORSOEGT, "0:0").split(":");
        if (Integer.parseInt(forsoegt[0]) == version && nu - Long.parseLong(forsoegt[1]) < VENT_MS) {
            return;
        }
        de.edit().putString(FORSOEGT, version + ":" + nu).commit();

        Object svar = new JSONTokener(Sporing.rpc(ctx, url, "inbase_mdm_phone_app",
                new JSONObject().put("p_name", navn).put("p_key", noegle))).nextValue();
        if (!(svar instanceof String)) throw new Exception("ingen styrings-app udgivet");
        byte[] apk = Base64.decode((String) svar, Base64.DEFAULT);
        if (!hex(MessageDigest.getInstance("SHA-256").digest(apk)).equals(app.optString("sha256"))) {
            throw new Exception("kontrolsummen passer ikke");
        }
        File fil = new File(ctx.getCacheDir(), "inbase-klargoering-ny.apk");
        try {
            try (FileOutputStream ud = new FileOutputStream(fil)) {
                ud.write(apk);
            }
            Installer.installer(ctx, fil);   // processen lukkes undervejs; reglerne lægges på igen
        } finally {
            fil.delete();
        }
    }

    private static String hex(byte[] data) {
        StringBuilder tekst = new StringBuilder();
        for (byte b : data) tekst.append(String.format("%02x", b));
        return tekst.toString();
    }
}
