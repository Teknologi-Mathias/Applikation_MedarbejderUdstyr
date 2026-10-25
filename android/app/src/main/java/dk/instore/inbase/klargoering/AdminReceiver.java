package dk.instore.inbase.klargoering;

import android.app.admin.DeviceAdminReceiver;
import android.content.ComponentName;
import android.content.Context;

/** Device Owner-modtageren. Selve klargøringen sker i KlargoeringActivity. */
public class AdminReceiver extends DeviceAdminReceiver {
    public static ComponentName komponent(Context context) {
        return new ComponentName(context.getApplicationContext(), AdminReceiver.class);
    }
}
