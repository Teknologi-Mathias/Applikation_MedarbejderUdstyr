// Fælles kode for IN-BASE's administrator-Edge Functions.
//
// Sikkerhed:
// - Den privilegerede nøgle (service role / secret key) findes KUN i
//   servermiljøet og sendes aldrig tilbage til klienten.
// - Kalderens session valideres af Supabase Auth (auth.getUser(token)).
// - Rollen og om kontoen er aktiv afgøres af user_profiles i databasen –
//   aldrig af user_metadata eller af noget, klienten sender.
// - Adgangskoder logges aldrig.
import { createClient, type SupabaseClient, type User } from "npm:@supabase/supabase-js@2.49.4";

export const ROLLER = ["Administrator", "Bruger"] as const;
export const MIN_KODE = 8; // samme som SUPABASE_MIN_KODE_LAENGDE i app/services/auth_service.py
// Samme regel som app/domain/bruger.py og user_profiles_username_check (005).
export const BRUGERNAVN = /^(?!.*\.\.)[A-Z0-9](?:[A-Z0-9._-]{0,38}[A-Z0-9])$/;
export const BRUGERNAVN_REGEL = "Brugernavnet skal være 2-40 tegn: bogstaver (A-Z), tal, " +
  "punktum, - eller _ – og starte og slutte med et bogstav eller tal.";
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Internt, IKKE-leveringsbart login-alias (".invalid", RFC 2606). Samme regel
// som login_alias() i app/repositories/supabase/mapping.py og
// inbase_login_alias() i migrering 005. Aliaset sendes aldrig til klienten.
const ALIAS_DOMAENE = "brugere.in-base.invalid";
// Spærring i Supabase Auth for deaktiverede konti (~100 år).
export const SPAERRET = "876000h";

export function normaliserBrugernavn(tekst: unknown): string {
  return String(tekst ?? "").trim().toUpperCase();
}

export function loginAlias(brugernavn: string): string {
  return `${brugernavn.trim().toLowerCase()}@${ALIAS_DOMAENE}`;
}

export class Fejl extends Error {
  constructor(public status: number, besked: string) {
    super(besked);
  }
}

export function svar(status: number, indhold: Record<string, unknown>): Response {
  return new Response(JSON.stringify(indhold), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

/** Servernøglen: INBASE_SERVICE_KEY (sat af ejeren) eller Supabases egne. */
function serviceNoegle(): string {
  const eksplicit = Deno.env.get("INBASE_SERVICE_KEY");
  if (eksplicit) return eksplicit;
  const nye = Deno.env.get("SUPABASE_SECRET_KEYS"); // nye API-nøgler: {"default": "sb_secret_..."}
  if (nye) {
    try {
      const noegler = JSON.parse(nye) as Record<string, string>;
      const noegle = noegler.default ?? Object.values(noegler)[0];
      if (noegle) return noegle;
    } catch {
      // falder tilbage til den klassiske nøgle
    }
  }
  const klassisk = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (klassisk) return klassisk;
  throw new Fejl(500, "Serveren mangler sin service-nøgle. Se docs/SUPABASE_OPSAETNING.md.");
}

export function adminKlient(): SupabaseClient {
  const url = Deno.env.get("SUPABASE_URL");
  if (!url) throw new Fejl(500, "SUPABASE_URL mangler i servermiljøet.");
  return createClient(url, serviceNoegle(), {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

/** Kalderen skal være logget på OG være AKTIV Administrator i user_profiles. */
export async function kraevAdministrator(req: Request, admin: SupabaseClient): Promise<User> {
  const header = req.headers.get("Authorization") ?? "";
  const token = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  if (!token) throw new Fejl(401, "Du er ikke logget på.");
  const { data, error } = await admin.auth.getUser(token);
  if (error || !data.user) throw new Fejl(401, "Din session er ugyldig eller udløbet. Log på igen.");
  const { data: profil, error: profilFejl } = await admin
    .from("user_profiles").select("role, active").eq("id", data.user.id).maybeSingle();
  if (profilFejl) throw new Fejl(500, "Din rolle kunne ikke kontrolleres.");
  if (profil?.role !== "Administrator" || profil?.active !== true) {
    throw new Fejl(403, "Kun administratorer kan administrere brugere.");
  }
  return data.user;
}

export async function laesJson(req: Request): Promise<Record<string, unknown>> {
  try {
    const data = await req.json();
    if (data && typeof data === "object" && !Array.isArray(data)) return data;
  } catch {
    // ugyldig JSON
  }
  throw new Fejl(400, "Ugyldig forespørgsel.");
}

export function validerKode(kode: string): void {
  if (kode.length < MIN_KODE) {
    throw new Fejl(422, `Adgangskoden skal være mindst ${MIN_KODE} tegn.`);
  }
}

/** Fælles ramme: kun POST, typede fejl -> {ok:false,error}, alt andet logges. */
export function haandter(fn: (req: Request) => Promise<Response>) {
  return async (req: Request): Promise<Response> => {
    if (req.method !== "POST") return svar(405, { ok: false, error: "Kun POST er tilladt." });
    try {
      return await fn(req);
    } catch (e) {
      if (e instanceof Fejl) return svar(e.status, { ok: false, error: e.message });
      console.error("Uventet fejl:", e);
      return svar(500, { ok: false, error: "Uventet serverfejl. Se funktionens log." });
    }
  };
}
