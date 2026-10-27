"""Skabeloner, fælles indstillinger og præferencer i Supabase.

Skrivning sker pr. post: én skabelon, ét område eller én ændret indstilling
ad gangen – aldrig "upload alt". Rettighederne (kun administratorer ændrer
opsætning) håndhæves af RLS og RPC-funktionerne i databasen.
"""
from app.domain import skabelon as sk
from app.domain.historik import nu, nuvaerende_bruger
from app.repositories.supabase import mapping
from app.repositories.supabase.klient import hent_alle, kald


class SupabaseSkabelonRepository:
    """workflow_templates (+ opgaver og versioner), message_templates, notification_rules.

    Ingen implicitte standardskabeloner: de bevidste standarder oprettes af
    migrering 004_seed_standarder.sql.
    """

    def __init__(self, klient):
        self.klient = klient

    def hent_alle(self) -> dict:
        alle = {}
        for slags, tabel in mapping.SKABELON_TABELLER.items():
            raekker = hent_alle(
                lambda t=tabel, s=slags: self.klient.table(t).select(mapping.SKABELON_SELECT[s])
                .order("sort_order").order("name"),
                "hente skabeloner")
            alle[slags] = [mapping.skabelon_fra_raekke(slags, r) for r in raekker]
        return alle

    def gem(self, slags: str, skabelon: dict, placering: int) -> None:
        raekke = mapping.skabelon_til_raekke(slags, skabelon, placering)
        with kald("gemme skabelonen"):
            if slags == sk.SAG:
                self.klient.rpc("inbase_save_workflow_template", {"p_template": raekke}).execute()
            else:
                self.klient.table(mapping.SKABELON_TABELLER[slags]).upsert(
                    raekke, on_conflict="id").execute()

    def slet(self, slags: str, skabelon_id: str) -> None:
        """Arbejdsgange via RPC (modultjek, migrering 018); mails og påmindelser direkte
        (RLS: medlemmer). Sager beholder skabelonens navn og deres egne opgaver."""
        with kald("slette skabelonen"):
            if slags == sk.SAG:
                self.klient.rpc("inbase_delete_workflow_template",
                                {"p_id": skabelon_id}).execute()
            else:
                self.klient.table(mapping.SKABELON_TABELLER[slags]).delete().eq(
                    "id", skabelon_id).execute()


class SupabaseIndstillingRepository:
    """app_settings (nøgle -> JSON) + områder i areas."""

    def __init__(self, klient):
        self.klient = klient

    def _omraader(self) -> list[dict]:
        return hent_alle(lambda: self.klient.table("areas").select("id, name, active, sort_order")
                         .order("sort_order").order("name"), "hente områder")

    def hent(self) -> dict:
        raekker = hent_alle(lambda: self.klient.table("app_settings").select("key, value")
                            .order("key"), "hente indstillinger")
        data = {r["key"]: r["value"] for r in raekker}
        data[mapping.OMRAADER] = [o["name"] for o in self._omraader() if o["active"]]
        return data

    def gem(self, indstillinger: dict) -> None:
        """Gemmer kun de indstillinger, der er ændret."""
        nuvaerende = self.hent()
        aendrede = [
            {"key": noegle, "value": vaerdi, "updated_at": mapping.til_tidspunkt(nu()),
             "updated_by": nuvaerende_bruger()}
            for noegle, vaerdi in indstillinger.items()
            if noegle != mapping.OMRAADER and nuvaerende.get(noegle) != vaerdi
        ]
        with kald("gemme indstillingerne"):
            if aendrede:
                self.klient.table("app_settings").upsert(aendrede, on_conflict="key").execute()
            nye = list(indstillinger.get(mapping.OMRAADER, nuvaerende[mapping.OMRAADER]))
            if nye != nuvaerende[mapping.OMRAADER]:
                self._gem_omraader(nye)

    def _gem_omraader(self, navne: list[str]) -> None:
        # Områder slettes ikke (sager peger på dem) – de markeres inaktive.
        if navne:
            self.klient.table("areas").upsert(
                [{"name": navn, "sort_order": nr, "active": True} for nr, navn in enumerate(navne)],
                on_conflict="name").execute()
        fjernede = [o["id"] for o in self._omraader() if o["active"] and o["name"] not in navne]
        if fjernede:
            self.klient.table("areas").update({"active": False}).in_("id", fjernede).execute()


class SupabasePraeferenceRepository:
    """Tema og Windows-notifikationer på brugerens egen profil (user_profiles)."""

    def __init__(self, klient):
        self.klient = klient

    def hent(self, brugernavn: str) -> dict:
        if not brugernavn:
            return {}
        with kald("hente dine præferencer"):
            svar = (self.klient.table("user_profiles").select("theme, windows_notifications")
                    .eq("username", brugernavn).limit(1).execute())
        return mapping.praeference_fra_raekke(svar.data[0]) if svar.data else {}

    def gem(self, brugernavn: str, praeferencer: dict) -> None:
        with kald("gemme dine præferencer"):
            self.klient.table("user_profiles").update(
                mapping.praeference_til_raekke(praeferencer)).eq("username", brugernavn).execute()
