package dk.instore.inbase.klargoering;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;

import java.util.concurrent.CountDownLatch;

/** Modtager resultatet af installationen af FL-UPDATE (PackageInstaller). */
public class InstallReceiver extends BroadcastReceiver {
    static volatile CountDownLatch venter;
    static volatile int status = PackageInstaller.STATUS_FAILURE;
    static volatile String besked = "";
    static volatile String pakke = "";

    @Override
    public void onReceive(Context context, Intent intent) {
        status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        besked = String.valueOf(intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE));
        String navn = intent.getStringExtra(PackageInstaller.EXTRA_PACKAGE_NAME);
        pakke = navn == null ? "" : navn;
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            // Bør ikke ske for en Device Owner – men vis i så fald bekræftelsen.
            Intent bekraeft = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (bekraeft != null) {
                bekraeft.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(bekraeft);
            }
            return;
        }
        CountDownLatch latch = venter;
        if (latch != null) latch.countDown();
    }
}
