package dk.instore.inbase.klargoering;

import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Hent og installér en APK uden at spørge brugeren (Device Owner) – FL-UPDATE og selvopdatering. */
class Installer {
    private Installer() {}

    static HttpURLConnection aabn(String adresse) throws Exception {
        HttpURLConnection forb = (HttpURLConnection) new URL(adresse).openConnection();
        forb.setConnectTimeout(15000);
        forb.setReadTimeout(60000);
        forb.setInstanceFollowRedirects(true);
        return forb;
    }

    static void hent(String adresse, File fil) throws Exception {
        HttpURLConnection forb = aabn(adresse);
        try (InputStream ind = forb.getInputStream(); OutputStream ud = new FileOutputStream(fil)) {
            kopier(ind, ud);
        } finally {
            forb.disconnect();
        }
    }

    /** Installerer apk og returnerer pakkenavnet. Opdateres denne app selv, lukkes den undervejs. */
    static String installer(Context ctx, File apk) throws Exception {
        PackageInstaller pi = ctx.getPackageManager().getPackageInstaller();
        int id = pi.createSession(new PackageInstaller.SessionParams(
                PackageInstaller.SessionParams.MODE_FULL_INSTALL));
        try (PackageInstaller.Session session = pi.openSession(id)) {
            try (OutputStream ud = session.openWrite("apk", 0, apk.length());
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
        return InstallReceiver.pakke;
    }

    static void kopier(InputStream ind, OutputStream ud) throws Exception {
        byte[] buf = new byte[64 * 1024];
        int n;
        while ((n = ind.read(buf)) > 0) ud.write(buf, 0, n);
    }
}
