package dk.instore.inbase.klargoering;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * Lægger de gemte regler på igen, når telefonen starter, og når denne app er opdateret.
 * Fanger fx apps, der dukker op efter en Android-opdatering, og nye regler i en ny app-version.
 */
public class OpstartReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        Politik politik = Politik.hent(context);
        if (politik == null) return;   // klargjort før de gemte regler (v3) – rør intet
        PendingResult svar = goAsync();
        new Thread(() -> {
            try {
                for (String fejl : politik.anvend(context)) Log.w("IN-BASE", fejl);
            } finally {
                svar.finish();
            }
        }, "regler").start();
    }
}
