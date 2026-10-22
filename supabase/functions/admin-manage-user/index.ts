// IN-BASE Edge Function: administratoren nulstiller kode for eller sletter en bruger.
//
// Body: { action: "reset_password", user_id, password }
//         -> ny midlertidig kode; brugeren skal vælge sin egen ved næste log på.
//       { action: "delete", user_id }
//         -> sletter Auth-kontoen (profilen slettes med, cascade). Navnet
//            bevares i tidslinjerne. Man kan ikke slette sig selv eller den
//            sidste administrator (tjekkes her OG af en trigger i databasen).
import {
  adminKlient,
  Fejl,
  haandter,
  kraevAdministrator,
  laesJson,
  svar,
  UUID,
  validerKode,
} from "../_shared/admin.ts";

Deno.serve(haandter(async (req) => {
  const admin = adminKlient();
  const kalder = await kraevAdministrator(req, admin);
  const body = await laesJson(req);
  const handling = String(body.action ?? "");
  const brugerId = String(body.user_id ?? "");
  if (!UUID.test(brugerId)) throw new Fejl(422, "Ugyldigt bruger-id.");

  const { data: profil, error: profilFejl } = await admin
    .from("user_profiles").select("id, username, role").eq("id", brugerId).maybeSingle();
  if (profilFejl) throw new Fejl(500, "Brugeren kunne ikke slås op.");
  if (!profil) throw new Fejl(404, "Brugeren findes ikke længere.");

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

  if (handling === "delete") {
    if (brugerId === kalder.id) {
      throw new Fejl(422, "Du kan ikke slette den bruger, du er logget ind med.");
    }
    if (profil.role === "Administrator") {
      const { count, error } = await admin.from("user_profiles")
        .select("id", { count: "exact", head: true }).eq("role", "Administrator");
      if (error) throw new Fejl(500, "Antallet af administratorer kunne ikke kontrolleres.");
      if ((count ?? 0) <= 1) throw new Fejl(409, "Der skal altid være mindst én administrator.");
    }
    const { error } = await admin.auth.admin.deleteUser(brugerId);
    if (error) throw new Fejl(500, `Brugeren kunne ikke slettes: ${error.message}`);
    console.log(`IN-BASE: bruger ${profil.username} slettet af ${kalder.id}`);
    return svar(200, { ok: true });
  }

  throw new Fejl(422, "Ukendt handling.");
}));
