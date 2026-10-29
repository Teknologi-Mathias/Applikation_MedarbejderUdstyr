"""Offboarding: afvikling af fratrådte medarbejdere, udstyr og rykkere."""
from app.domain import skabelon as sk
from app.domain.offboarding import Medarbejder
from app.domain.opgave import Opgave, laes_iso_dato
from app.domain.rykker import Rykker
from app.repositories.fejl import ValideringsFejl
from app.services.sag_service import SagService


class OffboardingService(SagService):

    def valider(self, sag: Medarbejder) -> None:
        super().valider(sag)
        if not sag.loennr:
            raise ValideringsFejl("Lønnr. skal udfyldes for en fratrådt medarbejder.")
        if laes_iso_dato(sag.fratraedelsesdato) is None:
            raise ValideringsFejl("Sidste arbejdsdag er ugyldig.")
        if sag.email and not sk.gyldig_email(sag.email):
            raise ValideringsFejl("E-mailadressen ser ikke gyldig ud.")

    def ny_sag(self, data: dict) -> Medarbejder:
        """Opretter et (ikke gemt) sagsobjekt ud fra dialogens data."""
        return Medarbejder(
            data["loennr"], data["navn"], data["fratraedelsesdato"], data.get("kommentar", ""),
            status_manuel=data.get("status_manuel"),
            status_begrundelse=data.get("status_begrundelse", ""),
            email=data.get("email", ""), tracking_link=data.get("tracking_link", ""),
            person_id=data.get("person_id"),
        )

    def rediger(self, gammel: Medarbejder, data: dict) -> Medarbejder:
        ny = gammel.kopi()
        ny.loennr = data["loennr"]
        ny.navn = data["navn"]
        ny.flyt_fratraedelse(data["fratraedelsesdato"])
        ny.kommentar = data["kommentar"]
        ny.email = data["email"]
        ny.tracking_link = data["tracking_link"]
        ny.status_manuel = data["status_manuel"]
        ny.status_begrundelse = data["status_begrundelse"]
        return self.gem_aendret(gammel, ny)

    def marker_afleveret(self, sag: Medarbejder, opgave_ids) -> Medarbejder:
        """Statusprikken "Udstyr retur": de valgte udstyrsopgaver er afleveret
        (Udført), de øvrige ikke (Ikke startet) – i ét gem."""
        ny = sag.kopi()
        afleveret = set(opgave_ids)
        for opgave in ny.opgaver:
            if not opgave.udstyr or opgave.status == Opgave.UNDTAGET:
                continue
            maal = Opgave.UDFOERT if opgave.id in afleveret else Opgave.IKKE_STARTET
            if maal != opgave.status and not (maal == Opgave.IKKE_STARTET and
                                              opgave.status != Opgave.UDFOERT):
                if maal == Opgave.UDFOERT and ny.er_blokeret(opgave):
                    raise ValideringsFejl(f"'{opgave.navn}' kan ikke udføres endnu. "
                                          f"{ny.blokeringsaarsag(opgave)}.")
                opgave.saet_status(maal)
        return self.gem_aendret(sag, ny)

    ### ----- rykkere og returlabel ------------------------------------------

    def registrer_rykker(self, sag: Medarbejder, rykker: Rykker) -> Medarbejder:
        ny = sag.kopi()
        ny.rykkere.append(rykker)
        frist = laes_iso_dato(rykker.frist)
        ny.historik.tilfoej(
            f"{rykker.kategori} oprettet som kladde",
            f"Skabelon: {rykker.skabelon_navn} · Frist: "
            f"{frist.strftime('%d-%m-%Y') if frist else rykker.frist} · Til: {ny.email}",
            rykker.id, data={"type": "rykker_kladde"},
        )
        return self.gem_aendret(sag, ny, registrer=False)

    def marker_rykker_sendt(self, sag: Medarbejder, rykker_id: str) -> Medarbejder:
        ny = sag.kopi()
        rykker = ny.find_rykker(rykker_id)
        if rykker is None or rykker.sendt:
            raise ValideringsFejl("Rykkeren findes ikke eller er allerede markeret som sendt.")
        rykker.marker_sendt()
        ny.historik.tilfoej(f"{rykker.kategori} markeret som sendt", f"Emne: {rykker.emne}",
                            rykker.id, data={"type": "rykker_sendt"})
        return self.gem_aendret(sag, ny, registrer=False)

    def registrer_returlabel(self, sag: Medarbejder, link: str) -> Medarbejder:
        ny = sag.kopi()
        ny.tracking_link = (link or "").strip()
        ny.historik.tilfoej("Returlabel registreret som sendt", ny.tracking_link)
        return self.gem_aendret(sag, ny, registrer=False)
