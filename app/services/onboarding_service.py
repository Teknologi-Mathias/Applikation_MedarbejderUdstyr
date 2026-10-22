"""Onboarding: fra kandidat til aktiv medarbejder.

Status følger milepælene (se app/domain/onboarding.py). En manuel status, der
springer over manglende krav, er en kritisk overstyring: den kræver
begrundelse og registreres i tidslinjen med de manglende opgaver.
Annullering kræver begrundelse og flytter forløbet til arkivet.
"""
from app.domain import skabelon as sk
from app.domain.onboarding import OnboardingForloeb
from app.domain.opgave import laes_iso_dato
from app.repositories.fejl import ValideringsFejl
from app.services.sag_service import SagService


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
        )

    def rediger(self, gammel: OnboardingForloeb, data: dict) -> OnboardingForloeb:
        ny = gammel.kopi()
        for felt in ("navn", "loennr", "stilling", "omraade", "ansaettelsesdato",
                     "foerste_arbejdsdag", "email", "ansvarlig", "kommentar"):
            setattr(ny, felt, data.get(felt, getattr(ny, felt)))
        return self.gem_aendret(gammel, ny)

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
