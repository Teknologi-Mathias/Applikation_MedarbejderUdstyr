package dk.instore.inbase.klargoering;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Åbner administrator-menuen, når der tastes *#*#46227#*#* (I-N-B-A-S) i Telefon-appen. */
public class HemmeligKodeReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        Intent aabn = new Intent(context, AdminActivity.class);
        aabn.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(aabn);
    }
}
