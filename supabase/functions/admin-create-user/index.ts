// IN-BASE Edge Function: administratoren opretter en ny bruger.
//
// Kaldes fra IN-BASE (Indstillinger → Brugere → Opret bruger) med brugerens
// egen session. Opretter en RIGTIG Supabase Auth-konto (auth.users) og præcis
// én profil i public.user_profiles med samme UUID.
//
// Body: { username, display_name, role, password }
//   username   normaliseres (trim + STORE bogstaver) og skal være unikt.
//   password   er en MIDLERTIDIG kode – brugeren skal vælge sin egen ved første
//              log på (user_profiles.must_change_password = true).
// Auth-kontoen får brugernavnets interne login-alias som e-mail, bekræftet
// med det samme (email_confirm) – der sendes ingen mail, og aliaset vises aldrig.
//
// Konsistens:
// - Findes aliasset allerede i Auth UDEN profil (fx en tidligere afbrudt
//   oprettelse), genoptages oprettelsen på den konto (sikker gentagelse).
// - Fejler profilen efter en NY konto, slettes kontoen igen (oprydning).
import {
  adminKlient,
  BRUGERNAVN,
  BRUGERNAVN_REGEL,
  Fejl,
  haandter,
  kraevAdministrator,
  laesJson,
  loginAlias,
  normaliserBrugernavn,
  ROLLER,
  svar,
  validerKode,
} from "../_shared/admin.ts";

Deno.serve(haandter(async (req) => {
  const admin = adminKlient();
  const kalder = await kraevAdministrator(req, admin);
  const body = await laesJson(req);

  const username = normaliserBrugernavn(body.username);
  const displayName = String(body.display_name ?? "").trim().slice(0, 100) || username;
  const role = String(body.role ?? "");
  const password = String(body.password ?? "");

  if (!BRUGERNAVN.test(username)) throw new Fejl(422, BRUGERNAVN_REGEL);
  if (!(ROLLER as readonly string[]).includes(role)) throw new Fejl(422, "Ukendt rolle.");
  validerKode(password);
  const alias = loginAlias(username);

  // Brugernavnet skal være unikt (gemmes altid med store bogstaver; databasen
  // har desuden et unikt indeks på lower(username)).
  const { data: navne, error: navneFejl } = await admin
    .from("user_profiles").select("id").eq("username", username);
  if (navneFejl) throw new Fejl(500, "Brugernavnet kunne ikke kontrolleres.");
  if ((navne ?? []).length) throw new Fejl(409, `Brugernavnet '${username}' er optaget.`);

  // Findes der allerede en Auth-konto med login-aliasset?
  const { data: eksisterende, error: opslagFejl } = await admin
    .rpc("inbase_auth_user_id_by_email", { p_email: alias });
  if (opslagFejl) throw new Fejl(500, "Brugernavnet kunne ikke kontrolleres.");

  let brugerId: string;
  let nyKonto = false;
  if (eksisterende) {
    const { data: profil } = await admin
      .from("user_profiles").select("id").eq("id", eksisterende).maybeSingle();
    if (profil) throw new Fejl(409, `Brugernavnet '${username}' er optaget.`);
    // Konto uden profil: genoptag oprettelsen (ny midlertidig kode, ingen spærring).
    const { error } = await admin.auth.admin.updateUserById(String(eksisterende), {
      password,
      email_confirm: true,
      ban_duration: "none",
    });
    if (error) throw new Fejl(500, `Den eksisterende konto kunne ikke klargøres: ${error.message}`);
    brugerId = String(eksisterende);
  } else {
    const { data, error } = await admin.auth.admin.createUser({
      email: alias,
      password,
      email_confirm: true, // internt alias: ingen bekræftelsesmail
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
    role,
    active: true,
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
  return svar(200, { ok: true, user: { id: brugerId, username, role } });
}));
