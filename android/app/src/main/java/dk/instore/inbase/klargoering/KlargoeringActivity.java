package dk.instore.inbase.klargoering;

import android.app.Activity;
import android.app.admin.DevicePolicyManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PersistableBundle;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/**
 * Sidste trin i opsætningsguiden. Viser fremdriften, mens Klargoering arbejder.
 * Returnerer ALTID RESULT_OK – ellers afbryder Android opsætningen og nulstiller telefonen.
 */
public class KlargoeringActivity extends Activity {
    private TextView log;
    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        LinearLayout rod = new LinearLayout(this);
        rod.setOrientation(LinearLayout.VERTICAL);
        rod.setPadding(48, 96, 48, 48);
        TextView titel = new TextView(this);
        titel.setText("IN-BASE klargør telefonen …");
        titel.setTextSize(22);
        titel.setGravity(Gravity.START);
        log = new TextView(this);
        log.setTextSize(15);
        log.setPadding(0, 32, 0, 0);
        ScrollView rul = new ScrollView(this);
        rul.addView(log);
        rod.addView(titel);
        rod.addView(rul);
        setContentView(rod);

        PersistableBundle ekstra = getIntent().getParcelableExtra(
                DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE);
        Klargoering klargoering = new Klargoering(this, ekstra, this::skriv);
        new Thread(() -> {
            boolean ok = klargoering.koer();
            skriv(ok ? "\nFærdig. Telefonen er klar til drift." :
                    "\nFærdig med fejl – se ovenfor. Telefonen er låst, men tjek den i IN-BASE.");
            ui.postDelayed(() -> {
                setResult(RESULT_OK);
                finish();
            }, ok ? 3000 : 10000);
        }, "klargoering").start();
    }

    private void skriv(String linje) {
        ui.post(() -> log.append(linje + "\n"));
    }

    @Override
    public void onBackPressed() {
        // Klargøringen må ikke afbrydes.
    }
}
