package dk.instore.inbase.klargoering;

import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.UserManager;
import android.util.Base64;

import org.json.JSONObject;

import java.security.SecureRandom;

/**
 * Lås skærmlåsen op fra IN-BASE (glemt mønster) – via samme tjek som Find telefon (Sporing).
 *
 * Telefonen har en nulstillingsnøgle (setResetPasswordToken). Beder IN-BASE om oplåsning, sætter
 * telefonen skærmlåskoden fra IN-BASE som midlertidig PIN (resetPasswordWithToken), og brugeren
 * sætter standardmønsteret igen med "Skift skærmlås (godkendt)".
 *
 * Har telefonen allerede en skærmlås, når nøglen laves, aktiverer Android den først ved næste
 * oplåsning – derfor melder telefonen "klar" til IN-BASE (unlock_ready, migrering 025).
 * Nøglen ligger i device-protected storage (Sporing.de), så oplåsning også virker før første
 * oplåsning efter en genstart.
 */
final class LaasOp {
    private static final String NOEGLE = "laas_op_noegle";

    private LaasOp() {}

    /** Laver nøglen én gang (klargøring, opstart, app-opdatering) – aktiv eller ej. */
    static void forbered(Context ctx) {
        SharedPreferences de = Sporing.de(ctx);
        if (!de.getString(NOEGLE, "").isEmpty()) return;
        byte[] noegle = new byte[32];
        new SecureRandom().nextBytes(noegle);
        DevicePolicyManager dpm = ctx.getSystemService(DevicePolicyManager.class);
        ComponentName admin = AdminReceiver.komponent(ctx);
        if (dpm.setResetPasswordToken(admin, noegle)) {
            de.edit().putString(NOEGLE, Base64.encodeToString(noegle, Base64.NO_WRAP)).commit();
        }
    }

    static boolean klar(Context ctx) {
        try {
            return !Sporing.de(ctx).getString(NOEGLE, "").isEmpty()
                    && ctx.getSystemService(DevicePolicyManager.class)
                    .isResetPasswordTokenActive(AdminReceiver.komponent(ctx));
        } catch (Exception ex) {
            return false;
        }
    }

    /** Sætter skærmlåskoden som PIN. Svaret går til IN-BASE: {ok} eller {fejl}. */
    static JSONObject udfoer(Context ctx, String nulstillingskode) throws Exception {
        JSONObject svar = new JSONObject();
        String noegle = Sporing.de(ctx).getString(NOEGLE, "");
        if (noegle.isEmpty() || !klar(ctx)) {
            svar.put("ok", false);
            svar.put("fejl", "Telefonen er ikke klar – den skal låses op én gang efter opdateringen.");
            return svar;
        }
        // Nulstillingen skal ikke registreres som en ændring uden kode (AdminReceiver). Før første
        // oplåsning efter genstart kan reglerne ikke læses – så registreres den, og
        // "Skift skærmlås (godkendt)" nulstiller advarslen bagefter.
        if (ctx.getSystemService(UserManager.class).isUserUnlocked()) {
            Politik politik = Politik.hent(ctx);
            if (politik != null) {
                politik.saet(Politik.SKAERMLAAS_AABEN, true);
                politik.gem(ctx);
            }
        }
        String pin = AdminActivity.aendringskode(nulstillingskode, AdminActivity.SKAERMLAAS);
        try {
            boolean ok = ctx.getSystemService(DevicePolicyManager.class).resetPasswordWithToken(
                    AdminReceiver.komponent(ctx), pin, Base64.decode(noegle, Base64.NO_WRAP), 0);
            svar.put("ok", ok);
            if (!ok) svar.put("fejl", "Android afviste nulstillingen.");
        } catch (Exception ex) {
            svar.put("ok", false);
            svar.put("fejl", String.valueOf(ex.getMessage()));
        }
        return svar;
    }
}
