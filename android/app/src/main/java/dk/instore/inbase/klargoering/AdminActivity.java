package dk.instore.inbase.klargoering;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.admin.DevicePolicyManager;
import android.content.Context;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * Administrator-menu på telefonen (åbnes med *#*#46227#*#* i Telefon-appen).
 * Med telefonens nulstillingskode (se IN-BASE → Handling → Vis nulstillingskode)
 * kan telefonen fabriksnulstilles – også selvom nulstilling ellers er spærret.
 */
public class AdminActivity extends Activity {
    static final String PREFS = "inbase";
    static final String KODE = "nulstillingskode";
    private int forsoeg = 0;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        LinearLayout rod = new LinearLayout(this);
        rod.setOrientation(LinearLayout.VERTICAL);
        rod.setPadding(48, 96, 48, 48);
        TextView titel = new TextView(this);
        titel.setTextSize(22);
        titel.setText("IN-BASE – administrator");
        TextView tekst = new TextView(this);
        tekst.setPadding(0, 24, 0, 24);
        tekst.setText("Indtast telefonens nulstillingskode fra IN-BASE for at fabriksnulstille "
                + "telefonen. ALT på telefonen slettes.");
        EditText kode = new EditText(this);
        kode.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        kode.setHint("Nulstillingskode");
        Button nulstil = new Button(this);
        nulstil.setText("Fabriksnulstil telefonen");
        Button luk = new Button(this);
        luk.setText("Luk");
        luk.setOnClickListener(v -> finish());
        nulstil.setOnClickListener(v -> kontroller(kode.getText().toString().trim(), tekst));
        rod.addView(titel);
        rod.addView(tekst);
        rod.addView(kode);
        rod.addView(nulstil);
        rod.addView(luk);
        setContentView(rod);
    }

    private void kontroller(String indtastet, TextView tekst) {
        String rigtig = getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KODE, "");
        if (rigtig.isEmpty() || !rigtig.equals(indtastet)) {
            forsoeg++;
            tekst.setText("Forkert kode (" + forsoeg + "/5).");
            if (forsoeg >= 5) finish();
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle("Fabriksnulstil?")
                .setMessage("Alt på telefonen slettes, og den skal klargøres igen fra IN-BASE.")
                .setPositiveButton("Nulstil", (d, w) -> nulstil())
                .setNegativeButton("Annuller", null)
                .show();
    }

    private void nulstil() {
        DevicePolicyManager dpm = (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
        if (Build.VERSION.SDK_INT >= 34) {
            dpm.wipeDevice(0);
        } else {
            dpm.wipeData(0);
        }
    }
}
