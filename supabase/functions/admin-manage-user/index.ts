// IN-BASE Edge Function: administratoren administrerer en anden brugers konto.
//
// Body: { action: "reset_password", user_id, password }
//         -> ny midlertidig kode; brugeren skal vælge sin egen ved næste log på.
//       { action: "set_active", user_id, active }
//         -> deaktiverer/aktiverer. En deaktiveret profil har straks ingen
//            adgang til data (RLS, migrering 005), og kontoen spærres i
//            Supabase Auth, så den hverken kan logge på eller forny sin session.
//       { action: "set_role", user_id, role }
//         -> ændrer rollen (Administrator/Bruger).
//       { action: "delete", user_id }
//         -> sletter Auth-kontoen (profilen slettes med, cascade). Navnet
//            bevares i tidslinjerne.
// Man kan ikke deaktivere, slette eller ændre rolle på sig selv. Den sidste
// aktive administrator beskyttes her OG af en trigger i databasen.
import {
  adminKlient,
  Fejl,
  haandter,
  kraevAdministrator,
  laesJson,
  ROLLER,
  SPAERRET,
  svar,
  UUID,
  validerKode,
} from "../_shared/admin.ts";

// Databasens trigger (IB422) og andre fejl ved opdatering af profilen.
function profilFejl(fejl: { code?: string; message: string }): Fejl {
  return fejl.code === "IB422" ? new Fejl(409, fejl.message)
    : new Fejl(500, `Profilen kunne ikke opdateres: ${fejl.message}`);
}

Deno.serve(haandter(async (req) => {
  const admin = adminKlient();
  const kalder = await kraevAdministrator(req, admin);
  const body = await laesJson(req);
  const handling = String(body.action ?? "");
  const brugerId = String(body.user_id ?? "");
  if (!UUID.test(brugerId)) throw new Fejl(422, "Ugyldigt bruger-id.");

  const { data: profil, error: opslagFejl } = await admin
    .from("user_profiles").select("id, username, role, active").eq("id", brugerId).maybeSingle();
  if (opslagFejl) throw new Fejl(500, "Brugeren kunne ikke slås op.");
  if (!profil) throw new Fejl(404, "Brugeren findes ikke længere.");
  const sigSelv = brugerId === kalder.id;

  if (handling === "reset_password") {
    const kode = String(body.password ?? "");
    validerKode(kode);
    const { error } = await admin.auth.admin.updateUserById(brugerId, { password: kode });
    if (error) throw new Fejl(500, `Koden kunne ikke ændres: ${error.message}`);
    const { error: flagFejl } = await admin
      .from("user_profiles").update({ must_change_password: true }).eq("id", brugerId);
    if (flagFejl) throw new Fejl(500, "Koden er ændret, men kravet om ny kode kunne ikke sættes.");
    console.log(`IN-BASE: kode nulstillet for ${profil.username} af ${kalder.id}`);
    return svar(200, { ok: true });
  }

  if (handling === "set_active") {
    if (typeof body.active !== "boolean") throw new Fejl(422, "active skal være true eller false.");
    const aktiv = body.active;
    if (sigSelv && !aktiv) throw new Fejl(422, "Du kan ikke deaktivere den bruger, du er logget ind med.");
    // Profilen først: den lukker adgangen til data med det samme (og triggeren
    // afviser at deaktivere den sidste aktive administrator).
    const { error } = await admin.from("user_profiles").update({ active: aktiv }).eq("id", brugerId);
    if (error) throw profilFejl(error);
    const { error: spaerreFejl } = await admin.auth.admin.updateUserById(brugerId, {
      ban_duration: aktiv ? "none" : SPAERRET,
    });
    if (spaerreFejl) {
      throw new Fejl(500, aktiv
        ? `Profilen er aktiveret, men spærringen i Supabase Auth kunne ikke fjernes: ${spaerreFejl.message}`
        : `Profilen er deaktiveret (ingen adgang til data), men kontoen kunne ikke spærres i Supabase Auth: ${spaerreFejl.message}`);
    }
    console.log(`IN-BASE: bruger ${profil.username} ${aktiv ? "aktiveret" : "deaktiveret"} af ${kalder.id}`);
    return svar(200, { ok: true });
  }

  if (handling === "set_role") {
    const rolle = String(body.role ?? "");
    if (!(ROLLER as readonly string[]).includes(rolle)) throw new Fejl(422, "Ukendt rolle.");
    if (sigSelv) throw new Fejl(422, "Du kan ikke ændre din egen rolle.");
    const { error } = await admin.from("user_profiles").update({ role: rolle }).eq("id", brugerId);
    if (error) throw profilFejl(error);
    console.log(`IN-BASE: ${profil.username} har nu rollen ${rolle} (ændret af ${kalder.id})`);
    return svar(200, { ok: true });
  }

  if (handling === "delete") {
    if (sigSelv) throw new Fejl(422, "Du kan ikke slette den bruger, du er logget ind med.");
    if (profil.role === "Administrator" && profil.active) {
      const { count, error } = await admin.from("user_profiles")
        .select("id", { count: "exact", head: true })
        .eq("role", "Administrator").eq("active", true);
      if (error) throw new Fejl(500, "Antallet af administratorer kunne ikke kontrolleres.");
      if ((count ?? 0) <= 1) throw new Fejl(409, "Der skal altid være mindst én aktiv administrator.");
    }
    const { error } = await admin.auth.admin.deleteUser(brugerId);
    if (error) throw new Fejl(500, `Brugeren kunne ikke slettes: ${error.message}`);
    console.log(`IN-BASE: bruger ${profil.username} slettet af ${kalder.id}`);
    return svar(200, { ok: true });
  }

  throw new Fejl(422, "Ukendt handling.");
}));
