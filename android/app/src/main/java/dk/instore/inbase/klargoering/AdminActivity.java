package dk.instore.inbase.klargoering;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * Administrator-menu på telefonen (åbnes med *#*#46227#*#* i Telefon-appen).
 * Med telefonens nulstillingskode (se IN-BASE → Handling → Vis nulstillingskode)
 * kan telefonen fabriksnulstilles – også selvom nulstilling ellers er spærret.
 * Telefoner uden egen kode (klargjort med v1) bruger reservekoden (assets/mdm/reservekode.txt).
 *
 * Supportkoden (IN-BASE → Handling → Vis supportkode) må gives til brugeren: den kan
 * kun vise og skjule Chrome (uden Google-konto) – fx til fejlfinding eller for at hente
 * en app igen. Nulstillingskoden virker også her.
 */
public class AdminActivity extends Activity {
    static final String PREFS = "inbase";
    static final String KODE = "nulstillingskode";
    private static final String CHROME = "com.android.chrome";
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
        tekst.setText("Supportkode: vis eller skjul Chrome.\nNulstillingskode: fabriksnulstil "
                + "telefonen – ALT på telefonen slettes.");
        EditText kode = new EditText(this);
        kode.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        kode.setHint("Kode fra IN-BASE");
        Button visChrome = new Button(this);
        visChrome.setText("Vis Chrome");
        visChrome.setOnClickListener(v -> chrome(kode.getText().toString().trim(), tekst, true));
        Button skjulChrome = new Button(this);
        skjulChrome.setText("Skjul Chrome");
        skjulChrome.setOnClickListener(v -> chrome(kode.getText().toString().trim(), tekst, false));
        Button nulstil = new Button(this);
        nulstil.setText("Fabriksnulstil telefonen");
        nulstil.setOnClickListener(v -> kontroller(kode.getText().toString().trim(), tekst));
        Button luk = new Button(this);
        luk.setText("Luk");
        luk.setOnClickListener(v -> finish());
        rod.addView(titel);
        rod.addView(tekst);
        rod.addView(kode);
        rod.addView(visChrome);
        rod.addView(skjulChrome);
        rod.addView(nulstil);
        rod.addView(luk);
        setContentView(rod);
    }

    private String nulstillingskode() {
        String rigtig = getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KODE, "");
        // Telefon klargjort før nulstillingskoden fandtes: reservekoden fra IN-BASE gælder.
        return rigtig.isEmpty() ? getString(R.string.reservekode) : rigtig;
    }

    /** Samme beregning som supportkode() i app/domain/mdm_enhed.py. */
    static String supportkode(String nulstillingskode) {
        if (nulstillingskode.isEmpty()) return "";
        try {
            byte[] h = MessageDigest.getInstance("SHA-256")
                    .digest(("chrome:" + nulstillingskode).getBytes(StandardCharsets.UTF_8));
            long tal = ((h[0] & 0xffL) << 24) | ((h[1] & 0xffL) << 16) | ((h[2] & 0xffL) << 8)
                    | (h[3] & 0xffL);
            return String.format("%06d", tal % 1000000);
        } catch (Exception ex) {
            return "";
        }
    }

    private void forkert(TextView tekst) {
        forsoeg++;
        tekst.setText("Forkert kode (" + forsoeg + "/5).");
        if (forsoeg >= 5) finish();
    }

    private void chrome(String indtastet, TextView tekst, boolean vis) {
        String rigtig = nulstillingskode();
        if (rigtig.isEmpty() || indtastet.isEmpty()
                || !(indtastet.equals(supportkode(rigtig)) || indtastet.equals(rigtig))) {
            forkert(tekst);
            return;
        }
        DevicePolicyManager dpm = (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
        ComponentName admin = AdminReceiver.komponent(this);
        try {
            if (vis) {
                // Ingen login i Chrome – telefonen tillader i forvejen ikke Google-konti.
                Bundle politik = new Bundle();
                politik.putInt("BrowserSignin", 0);
                dpm.setApplicationRestrictions(admin, CHROME, politik);
            }
            dpm.setApplicationHidden(admin, CHROME, !vis);
            tekst.setText(vis ? "Chrome er nu synlig på startskærmen." : "Chrome er skjult igen.");
        } catch (Exception ex) {
            tekst.setText("Chrome kunne ikke ændres: " + ex.getMessage());
        }
    }

    private void kontroller(String indtastet, TextView tekst) {
        String rigtig = nulstillingskode();
        if (rigtig.isEmpty() || !rigtig.equals(indtastet)) {
            forkert(tekst);
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
