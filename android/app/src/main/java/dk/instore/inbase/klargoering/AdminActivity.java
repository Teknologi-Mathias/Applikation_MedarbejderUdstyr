package dk.instore.inbase.klargoering;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.admin.DevicePolicyManager;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

/**
 * Administrator-menu på telefonen: ikonet "IN-BASE indstillinger" eller *#*#46227#*#* i Telefon-appen.
 *
 * Koder fra IN-BASE (Telefoner → Handling):
 *   nulstillingskode  alt herunder + fabriksnulstilling og opdatering af appen fra IN-BASE.
 *                     Telefoner uden egen kode (klargjort med v1) bruger reservekoden
 *                     (assets/mdm/reservekode.txt).
 *   supportkode       må gives til brugeren: kan kun vise og skjule Chrome (uden Google-konto).
 *   skærmlåskode      (v6+) godkender én ændring af skærmlåsen (ændringskode "skaermlaas").
 *                     Ændringer uden kode registreres og vises øverst i menuen.
 *   ændringskode      én kode pr. telefon og handling, fx "slå firma-mail til". Telefonen
 *                     kan se på koden, hvilken handling den gælder.
 *   masterkode        (v5+) gælder som nulstillingskode på alle telefoner – også når telefonens
 *                     egen kode er væk. Kun hashen ligger i appen (android/masterkode.txt).
 *
 * Kodernes beregning (aendringskode) er den samme som i app/domain/mdm_enhed.py.
 */
public class AdminActivity extends Activity {
    static final String PREFS = "inbase";
    static final String KODE = "nulstillingskode";
    static final String MAIL_TIL = "mail:til";
    static final String MAIL_FRA = "mail:fra";
    static final String SKAERMLAAS = "skaermlaas";
    private static final String GAMMEL = "Telefonen er klargjort med en ældre version af IN-BASE "
            + "Klargøring og kan ikke ændres herfra. Fabriksnulstil og klargør den igen fra IN-BASE.";
    private int forsoeg = 0;
    private TextView tekst;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        LinearLayout rod = new LinearLayout(this);
        rod.setOrientation(LinearLayout.VERTICAL);
        rod.setPadding(48, 96, 48, 48);
        TextView titel = new TextView(this);
        titel.setTextSize(22);
        titel.setText("IN-BASE – administrator");
        tekst = new TextView(this);
        tekst.setPadding(0, 24, 0, 24);
        tekst.setText("Indtast koden fra IN-BASE og vælg handlingen.\n"
                + "Ændringskode: fx slå firma-mail til eller fra.\n"
                + "Supportkode: vis eller skjul Chrome.\n"
                + "Skærmlåskode: skift skærmlåsen godkendt (nulstiller advarslen).\n"
                + "Nulstillingskode: alt – også opdatering og fabriksnulstilling.");
        EditText kode = new EditText(this);
        kode.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        kode.setHint("Kode fra IN-BASE");
        Politik politik = Politik.hent(this);
        EditText server = new EditText(this);
        server.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        server.setHint("Pc'ens adresse, fx 192.168.1.20:8765");
        if (politik != null) server.setText(politik.s("server").replaceFirst("^http://", ""));

        rod.addView(titel);
        rod.addView(tekst);
        rod.addView(kode);
        knap(rod, "Brug ændringskode", () -> aendring(kode.getText().toString().trim()));
        knap(rod, "Vis Chrome", () -> chrome(kode.getText().toString().trim(), true));
        knap(rod, "Skjul Chrome", () -> chrome(kode.getText().toString().trim(), false));
        knap(rod, "Skift skærmlås (godkendt)", () -> skaermlaas(kode.getText().toString().trim()));
        knap(rod, "Anvend regler igen", this::anvendIgen);
        rod.addView(server);
        knap(rod, "Opdater appen fra IN-BASE", () -> opdater(kode.getText().toString().trim(),
                server.getText().toString().trim()));
        knap(rod, "Fabriksnulstil telefonen", () -> kontroller(kode.getText().toString().trim()));
        knap(rod, "Luk", this::finish);
        ScrollView rul = new ScrollView(this);
        rul.addView(rod);
        setContentView(rul);
        if (politik == null) {
            tekst.setText(GAMMEL);
        } else if (!politik.skaermlaasAendringer().isEmpty()) {
            tekst.setText(politik.skaermlaasAendringer() + "\n\n" + tekst.getText());
        }
    }

    private void knap(LinearLayout rod, String titel, Runnable handling) {
        Button knap = new Button(this);
        knap.setText(titel);
        knap.setOnClickListener(v -> handling.run());
        rod.addView(knap);
    }

    private String nulstillingskode() {
        String rigtig = getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KODE, "");
        // Telefon klargjort før nulstillingskoden fandtes: reservekoden fra IN-BASE gælder.
        return rigtig.isEmpty() ? getString(R.string.reservekode) : rigtig;
    }

    /** Telefonens nulstillingskode eller masterkoden. */
    private boolean erNulstillingskode(String indtastet) {
        if (indtastet.isEmpty()) return false;
        String rigtig = nulstillingskode();
        return (!rigtig.isEmpty() && rigtig.equals(indtastet)) || erMasterkode(indtastet);
    }

    private boolean erMasterkode(String indtastet) {
        try {
            byte[] h = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(
                    new PBEKeySpec(indtastet.toCharArray(),
                            "inbase-master".getBytes(StandardCharsets.UTF_8), 120000, 256))
                    .getEncoded();
            StringBuilder hex = new StringBuilder();
            for (byte b : h) hex.append(String.format("%02x", b));
            return MessageDigest.isEqual(hex.toString().getBytes(StandardCharsets.UTF_8),
                    getString(R.string.master_hash).getBytes(StandardCharsets.UTF_8));
        } catch (Exception ex) {
            return false;
        }
    }

    /** Samme beregning som aendringskode() i app/domain/mdm_enhed.py. */
    static String aendringskode(String nulstillingskode, String handling) {
        if (nulstillingskode.isEmpty()) return "";
        try {
            byte[] h = MessageDigest.getInstance("SHA-256")
                    .digest((handling + ":" + nulstillingskode).getBytes(StandardCharsets.UTF_8));
            long tal = ((h[0] & 0xffL) << 24) | ((h[1] & 0xffL) << 16) | ((h[2] & 0xffL) << 8)
                    | (h[3] & 0xffL);
            return String.format("%06d", tal % 1000000);
        } catch (Exception ex) {
            return "";
        }
    }

    private void forkert() {
        forsoeg++;
        tekst.setText("Forkert kode (" + forsoeg + "/5).");
        if (forsoeg >= 5) finish();
    }

    /** Gemmer en ændring i reglerne og lægger dem på igen. */
    private void aendr(String noegle, boolean vaerdi, String udfoert) {
        Politik politik = Politik.hent(this);
        if (politik == null) {
            tekst.setText(GAMMEL);
            return;
        }
        try {
            politik.saet(noegle, vaerdi);
            politik.gem(this);
            List<String> fejl = politik.anvend(this);
            tekst.setText(fejl.isEmpty() ? udfoert : udfoert + "\nMen: " + String.join("\n", fejl));
        } catch (Exception ex) {
            tekst.setText("Kunne ikke ændres: " + ex.getMessage());
        }
    }

    private void aendring(String indtastet) {
        String rigtig = nulstillingskode();
        if (!indtastet.isEmpty() && indtastet.equals(aendringskode(rigtig, MAIL_TIL))) {
            aendr("mail", true, "Firma-mail er slået til. Åbn Gmail → Tilføj en anden "
                    + "e-mailadresse → Andet, og log ind med firma-mailen (IMAP).");
        } else if (!indtastet.isEmpty() && indtastet.equals(aendringskode(rigtig, MAIL_FRA))) {
            aendr("mail", false, "Firma-mail er slået fra. Gmail er skjult.");
        } else {
            forkert();
        }
    }

    private void chrome(String indtastet, boolean vis) {
        String rigtig = nulstillingskode();
        if (indtastet.isEmpty() || !(indtastet.equals(aendringskode(rigtig, "chrome"))
                || erNulstillingskode(indtastet))) {
            forkert();
            return;
        }
        aendr("chrome", vis, vis ? "Chrome er nu synlig på startskærmen." : "Chrome er skjult igen.");
    }

    /**
     * Android kan ikke spærre for ændring af skærmlåsen, men en ændring uden kode registreres
     * (AdminReceiver). Skærmlåskoden (eller nulstillings-/masterkoden) godkender den næste
     * ændring – fx når standardmønsteret sættes igen – og nulstiller registreringen.
     */
    private void skaermlaas(String indtastet) {
        String rigtig = nulstillingskode();
        if (indtastet.isEmpty() || !(indtastet.equals(aendringskode(rigtig, SKAERMLAAS))
                || erNulstillingskode(indtastet))) {
            forkert();
            return;
        }
        aendr(Politik.SKAERMLAAS_AABEN, true, "Skift skærmlåsen nu, og tegn standardmønsteret. "
                + "Ændringen registreres som godkendt.");
        try {
            startActivity(new Intent(DevicePolicyManager.ACTION_SET_NEW_PASSWORD));
        } catch (Exception ex) {
            startActivity(new Intent(Settings.ACTION_SECURITY_SETTINGS));
        }
    }

    private void anvendIgen() {
        Politik politik = Politik.hent(this);
        if (politik == null) {
            tekst.setText(GAMMEL);
            return;
        }
        List<String> fejl = politik.anvend(this);
        tekst.setText(fejl.isEmpty() ? "Reglerne er lagt på igen." : String.join("\n", fejl));
    }

    /** Henter styrings-appen fra IN-BASE (Telefoner → Opdater telefoner) og installerer den. */
    private void opdater(String indtastet, String server) {
        if (!erNulstillingskode(indtastet)) {
            forkert();
            return;
        }
        if (server.isEmpty()) {
            tekst.setText("Skriv pc'ens adresse – den står i IN-BASE under Opdater telefoner.");
            return;
        }
        String adresse = (server.startsWith("http") ? server : "http://" + server)
                .replaceAll("/+$", "");
        tekst.setText("Henter appen fra " + adresse + " …");
        new Thread(() -> {
            try {
                File apk = new File(getCacheDir(), "inbase-klargoering.apk");
                Installer.hent(adresse + "/inbase-klargoering.apk", apk);
                Politik politik = Politik.hent(this);
                if (politik != null) {
                    politik.saet("server", adresse);
                    politik.gem(this);
                }
                runOnUiThread(() -> tekst.setText("Installerer – menuen lukker, når appen er "
                        + "opdateret. Reglerne lægges derefter på igen."));
                Installer.installer(this, apk);
                apk.delete();
                runOnUiThread(() -> tekst.setText("Appen er opdateret."));
            } catch (Exception ex) {
                runOnUiThread(() -> tekst.setText("Opdateringen mislykkedes: " + ex.getMessage()
                        + "\nEr pc'en på samme Wi-Fi, og er vinduet Opdater telefoner åbent?"));
            }
        }, "opdatering").start();
    }

    private void kontroller(String indtastet) {
        if (!erNulstillingskode(indtastet)) {
            forkert();
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
