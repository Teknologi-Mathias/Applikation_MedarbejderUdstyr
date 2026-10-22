"""Fejltyper fra datalaget. UI'en fanger dem og viser beskeden til brugeren."""


class DataFejl(Exception):
    """Data kan ikke læses eller skrives (fx ødelagt JSON eller manglende adgang)."""


class KonfliktFejl(DataFejl):
    """Posten er ændret af en anden, siden den blev hentet (optimistisk låsning)."""


class OfflineFejl(DataFejl):
    """Handlingen kræver forbindelse til den centrale datakilde."""


class ValideringsFejl(ValueError):
    """Input overholder ikke forretningsreglerne (vises direkte for brugeren)."""
