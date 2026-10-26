"""Onboarding: fra kandidat til aktiv medarbejder.

Status følger milepælene (se app/domain/onboarding.py). En manuel status, der
springer over manglende krav, er en kritisk overstyring: den kræver
begrundelse og registreres i tidslinjen med de manglende opgaver.
Annullering kræver begrundelse og flytter forløbet til arkivet.

HR's behov (app/domain/behov.py) gør betingede opgaver relevante eller ej
(workflow.synkroniser_betingelser). Oplæringsvagtens tidspunkt og booking
ligger på opgaven OPLAERING_BOOKET: tidspunktet er "planlagt", bookingen er
opgavens status – så et tidspunkt aldrig afslutter noget af sig selv.
"""
from datetime import datetime

from app.domain import skabelon as sk
from app.domain.behov import Behov
from app.domain.onboarding import OnboardingForloeb
from app.domain.opgave import Opgave, laes_iso_dato
from app.repositories.fejl import ValideringsFejl
from app.services import workflow
from app.services.sag_service import SagService

# Faste opgavenøgler fra standardskabelonen, som formularen arbejder på.
BEHOV_REGISTRERET = "behov_registreret"
OPLAERING_BOOKET = "oplaering_booket"

# Bookingstatus (formularen) <-> status på opgaven OPLAERING_BOOKET.
BOOKING = {
    "Ikke booket": Opgave.IKKE_STARTET,
    "Afventer bekræftelse": Opgave.AFVENTER,
    "Booket og bekræftet": Opgave.UDFOERT,
}


def booking_tekst(opgave: Opgave | None) -> str:
    if opgave is None:
        return ""
    return next((t for t, s in BOOKING.items() if s == opgave.status), opgave.status)


def opgave_med_noegle(sag, noegle: str) -> Opgave | None:
    return next((o for o in sag.opgaver if o.noegle == noegle), None)


class OnboardingService(SagService):

    def valider(self, sag: OnboardingForloeb) -> None:
        super().valider(sag)
        if sag.stilling not in OnboardingForloeb.STILLINGER:
            raise ValideringsFejl("Vælg en stilling: " + ", ".join(OnboardingForloeb.STILLINGER))
        for felt, navn in (("ansaettelsesdato", "Ansættelsesdato"),
                           ("foerste_arbejdsdag", "Første arbejdsdag")):
            vaerdi = getattr(sag, felt)
            if vaerdi and laes_iso_dato(vaerdi) is None:
                raise ValideringsFejl(f"{navn} er ugyldig.")
        if not sag.ansaettelsesdato:
            raise ValideringsFejl("Ansættelsesdato skal udfyldes.")
        if sag.email and not sk.gyldig_email(sag.email):
            raise ValideringsFejl("E-mailadressen ser ikke gyldig ud.")
        fejl = sag.behov.valider(sag.stilling)
        if fejl:
            raise ValideringsFejl(" ".join(fejl))
        for o in sag.opgaver:
            if o.planlagt and not _gyldigt_tidspunkt(o.planlagt):
                raise ValideringsFejl(f"'{o.navn}' har et ugyldigt planlagt tidspunkt.")

    def forbered_opgaver(self, sag: OnboardingForloeb, data: dict | None = None) -> None:
        """Formularens oplæring og "behov afklaret" + betingede opgaver efter behovet."""
        self._anvend_formular(sag, data or {})
        workflow.synkroniser_betingelser(sag, sag.behov)

    def ny_sag(self, data: dict) -> OnboardingForloeb:
        return OnboardingForloeb(
            data["navn"],
            loennr=data.get("loennr", ""),
            stilling=data.get("stilling", ""),
            omraade=data.get("omraade", ""),
            ansaettelsesdato=data.get("ansaettelsesdato", ""),
            foerste_arbejdsdag=data.get("foerste_arbejdsdag", ""),
            email=data.get("email", ""),
            ansvarlig=data.get("ansvarlig", ""),
            kommentar=data.get("kommentar", ""),
            behov=data.get("behov"),
        )

    def rediger(self, gammel: OnboardingForloeb, data: dict) -> OnboardingForloeb:
        """Gemmer formularen (stamdata, behov, oplæring) og opdaterer betingede opgaver."""
        ny = gammel.kopi()
        for felt in ("navn", "loennr", "stilling", "omraade", "ansaettelsesdato",
                     "foerste_arbejdsdag", "email", "ansvarlig", "kommentar"):
            setattr(ny, felt, data.get(felt, getattr(ny, felt)))
        if "behov" in data:
            ny.behov = Behov.fra_dict(data["behov"])
        self.forbered_opgaver(ny, data)
        return self.gem_aendret(gammel, ny)

    def _anvend_formular(self, sag: OnboardingForloeb, data: dict) -> None:
        """Oplæringsvagtens tidspunkt og booking + "behov afklaret" på opgaverne."""
        if data.get("behov_afklaret"):
            opgave = opgave_med_noegle(sag, BEHOV_REGISTRERET)
            if opgave is not None and not opgave.afsluttet:
                opgave.saet_status(Opgave.UDFOERT)
        booket = opgave_med_noegle(sag, OPLAERING_BOOKET)
        if booket is None:
            return
        if "oplaering_planlagt" in data:
            booket.planlagt = data["oplaering_planlagt"] or ""
        status = BOOKING.get(data.get("oplaering_booking") or "")
        if status and status != booket.status:
            if status != Opgave.IKKE_STARTET and sag.er_blokeret(booket):
                raise ValideringsFejl(f"Oplæringsvagten kan ikke bookes endnu. "
                                      f"{sag.blokeringsaarsag(booket)}.")
            booket.saet_status(status)

    def saet_manuel_status(self, sag, status, begrundelse):
        """Validerer onboarding-reglerne og registrerer kritiske overstyringer."""
        if status == OnboardingForloeb.STATUS_ANNULLERET:
            return self.annuller(sag, begrundelse)
        if status and sag.kraever_overstyring(status):
            if not (begrundelse or "").strip():
                raise ValideringsFejl(
                    f"'{status}' springer over krav, der ikke er opfyldt. "
                    "En begrundelse er påkrævet."
                )
            mangler = sag.mangler_for(status)
            ny = sag.kopi()
            ny.historik.tilfoej(
                f"Kritisk overstyring: status sat til {status}",
                f"{begrundelse.strip()} · Mangler: {', '.join(mangler) or 'intet'}",
                data={"type": "overstyring", "til": status, "mangler": mangler},
            )
            ny.status_manuel, ny.status_begrundelse = status, begrundelse.strip()
            return self.gem_aendret(sag, ny)
        return super().saet_manuel_status(sag, status, begrundelse)

    def annuller(self, sag: OnboardingForloeb, begrundelse: str) -> OnboardingForloeb:
        if not (begrundelse or "").strip():
            raise ValideringsFejl("Skriv hvorfor forløbet annulleres.")
        ny = sag.kopi()
        ny.status_manuel = OnboardingForloeb.STATUS_ANNULLERET
        ny.status_begrundelse = begrundelse.strip()
        ny.historik.tilfoej("Forløb annulleret", begrundelse.strip(),
                            data={"type": "annulleret"})
        gemt = self.gem_aendret(sag, ny, registrer=False)
        return self.arkiver(gemt, "Annulleret")


def _gyldigt_tidspunkt(tekst: str) -> bool:
    try:
        datetime.fromisoformat(tekst)
        return True
    except ValueError:
        return False
