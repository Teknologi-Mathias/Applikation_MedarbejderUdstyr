"""Fejltyper fra datalaget. UI'en fanger dem og viser beskeden til brugeren."""


class DataFejl(Exception):
    """Data kan ikke læses eller skrives (fx ødelagt JSON eller manglende adgang)."""


class KonfliktFejl(DataFejl):
    """Posten er ændret af en anden, siden den blev hentet (optimistisk låsning)."""


class OfflineFejl(DataFejl):
    """Handlingen kræver forbindelse til den centrale datakilde."""


class SessionUdloebetFejl(DataFejl):
    """Sessionen er udløbet, eller brugerens adgang er lukket – brugeren skal logge på igen."""


class KompatibilitetsFejl(DataFejl):
    """Klienten og databasens skema passer ikke sammen (migrering mangler)."""


class ValideringsFejl(ValueError):
    """Input overholder ikke forretningsreglerne (vises direkte for brugeren)."""


class ForkertLoginFejl(Exception):
    """Brugernavn eller adgangskode er forkert (ikke en datafejl)."""
