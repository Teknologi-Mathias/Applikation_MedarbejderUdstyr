// IN-BASE Edge Function: administratoren opretter en ny bruger.
//
// Kaldes fra IN-BASE (Indstillinger → Brugere → Opret bruger) med brugerens
// egen session. Opretter en RIGTIG Supabase Auth-konto (auth.users) og præcis
// én profil i public.user_profiles med samme UUID.
//
// Body: { email, username, display_name, role, password }
//   password er en MIDLERTIDIG kode – brugeren skal vælge sin egen ved første
//   log på (user_profiles.must_change_password = true).
//
// Konsistens:
// - Findes e-mailen allerede i Auth UDEN profil (fx en tidligere afbrudt
//   oprettelse), genoptages oprettelsen på den konto (sikker gentagelse).
// - Fejler profilen efter en NY konto, slettes kontoen igen (oprydning).
import {
  adminKlient,
  BRUGERNAVN,
  EMAIL,
  Fejl,
  haandter,
  kraevAdministrator,
  laesJson,
  ROLLER,
  svar,
  validerKode,
} from "../_shared/admin.ts";

Deno.serve(haandter(async (req) => {
  const admin = adminKlient();
  const kalder = await kraevAdministrator(req, admin);
  const body = await laesJson(req);

  const email = String(body.email ?? "").trim().toLowerCase();
  const username = String(body.username ?? "").trim();
  const displayName = String(body.display_name ?? "").trim().slice(0, 100) || username;
  const role = String(body.role ?? "");
  const password = String(body.password ?? "");

  if (!EMAIL.test(email)) throw new Fejl(422, "Ugyldig e-mailadresse.");
  if (!BRUGERNAVN.test(username)) {
    throw new Fejl(422, "Brugernavnet skal være 2-40 tegn: bogstaver, tal, punktum, - eller _.");
  }
  if (!(ROLLER as readonly string[]).includes(role)) throw new Fejl(422, "Ukendt rolle.");
  validerKode(password);

  // Brugernavnet skal være unikt (uden forskel på store/små bogstaver).
  const { data: navne, error: navneFejl } = await admin
    .from("user_profiles").select("username").ilike("username", username);
  if (navneFejl) throw new Fejl(500, "Brugernavnet kunne ikke kontrolleres.");
  if ((navne ?? []).some((p) => String(p.username).toLowerCase() === username.toLowerCase())) {
    throw new Fejl(409, `Brugernavnet '${username}' er optaget.`);
  }

  // Findes der allerede en Auth-konto med e-mailen?
  const { data: eksisterende, error: opslagFejl } = await admin
    .rpc("inbase_auth_user_id_by_email", { p_email: email });
  if (opslagFejl) throw new Fejl(500, "E-mailen kunne ikke kontrolleres.");

  let brugerId: string;
  let nyKonto = false;
  if (eksisterende) {
    const { data: profil } = await admin
      .from("user_profiles").select("id").eq("id", eksisterende).maybeSingle();
    if (profil) throw new Fejl(409, "Der findes allerede en IN-BASE-bruger med denne e-mail.");
    // Konto uden profil: genoptag oprettelsen (ny midlertidig kode, bekræftet e-mail).
    const { error } = await admin.auth.admin.updateUserById(String(eksisterende), {
      password,
      email_confirm: true,
    });
    if (error) throw new Fejl(500, `Den eksisterende konto kunne ikke klargøres: ${error.message}`);
    brugerId = String(eksisterende);
  } else {
    const { data, error } = await admin.auth.admin.createUser({
      email,
      password,
      email_confirm: true, // administratoren står inde for adressen; ingen bekræftelsesmail
      app_metadata: { inbase: true },
    });
    if (error || !data.user) {
      const status = error?.status && error.status < 500 ? 422 : 500;
      throw new Fejl(status, `Kontoen kunne ikke oprettes: ${error?.message ?? "ukendt fejl"}`);
    }
    brugerId = data.user.id;
    nyKonto = true;
  }

  const { error: profilFejl } = await admin.from("user_profiles").insert({
    id: brugerId,
    username,
    display_name: displayName,
    email,
    role,
    must_change_password: true,
  });
  if (profilFejl) {
    if (nyKonto) {
      const { error: oprydning } = await admin.auth.admin.deleteUser(brugerId);
      if (oprydning) {
        console.error(`Oprydning af konto ${brugerId} mislykkedes:`, oprydning);
        throw new Fejl(500, "Profilen kunne ikke oprettes, og kontoen kunne ikke ryddes op. " +
          "Prøv igen – oprettelsen genoptages på den samme konto.");
      }
    }
    if (profilFejl.code === "23505") throw new Fejl(409, `Brugernavnet '${username}' er optaget.`);
    throw new Fejl(500, `Profilen kunne ikke oprettes: ${profilFejl.message}`);
  }

  console.log(`IN-BASE: bruger ${username} (${brugerId}, ${role}) oprettet af ${kalder.id}`);
  return svar(200, { ok: true, user: { id: brugerId, email, username, role } });
}));
