package dk.instore.inbase.klargoering;

import android.app.admin.DeviceAdminReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.UserHandle;
import android.os.UserManager;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** Device Owner-modtageren. Selve klargøringen sker i KlargoeringActivity. */
public class AdminReceiver extends DeviceAdminReceiver {
    public static ComponentName komponent(Context context) {
        return new ComponentName(context.getApplicationContext(), AdminReceiver.class);
    }

    /**
     * Skærmlåsen er sat eller ændret. Første gang er det standardmønsteret ved klargøringen;
     * senere registreres ændringer, som ikke er godkendt i admin-menuen (vises der).
     */
    @Override
    public void onPasswordChanged(Context context, Intent intent, UserHandle user) {
        // Før første oplåsning (LaasOp) kan reglerne ikke læses – ændringen registreres ikke.
        if (!context.getSystemService(UserManager.class).isUserUnlocked()) return;
        Politik politik = Politik.hent(context);
        if (politik == null) return;
        try {
            politik.skaermlaasAendret(new SimpleDateFormat("dd-MM-yyyy HH:mm", Locale.ROOT)
                    .format(new Date()));
            politik.gem(context);
        } catch (Exception ex) {
            // Registreringen er kun til information – telefonen virker uændret.
        }
    }

    /** Telefonen er låst op: Find telefon tjekker, om IN-BASE har bedt om positionen. */
    @Override
    public void onPasswordSucceeded(Context context, Intent intent, UserHandle user) {
        Sporing.nu(context);
    }

    /** Forkert mønster – fx en finder eller tyv. Tjekker også. */
    @Override
    public void onPasswordFailed(Context context, Intent intent, UserHandle user) {
        Sporing.nu(context);
    }
}
