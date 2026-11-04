package dk.instore.inbase.klargoering;

import android.app.job.JobParameters;
import android.app.job.JobService;
import android.util.Log;

/**
 * Kører tjekket for Find telefon og Lås skærmlåsen op (Sporing) i en tråd – planlagt af
 * Sporing.planlaeg, Sporing.nu og Sporing.lader. Kører også før første oplåsning (directBootAware).
 */
public class SporingJob extends JobService {
    @Override
    public boolean onStartJob(JobParameters params) {
        int job = params.getJobId();
        new Thread(() -> {
            boolean igen = false;
            try {
                Sporing.tjek(this, job != Sporing.JOB_TIME);
            } catch (Exception ex) {
                Log.w("IN-BASE", "Tjek fra IN-BASE: " + ex.getMessage());
                igen = job == Sporing.JOB_NU;   // det timevise tjek kommer alligevel
            } finally {
                jobFinished(params, igen);
                // Først når jobbet er afsluttet – ellers stopper Android det kørende job.
                if (job == Sporing.JOB_LADER) Sporing.lader(this, true);
            }
        }, "sporing").start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }
}
