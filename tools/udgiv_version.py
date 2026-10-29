"""Udgiv IN-BASE til den centrale opdatering – kun administratorer (migrering 019).

Normalt gøres det i programmet: IN-BASE → Indstillinger → Opdateringer (træk
installeren ind). Dette værktøj er reserven, med de samme regler
(app/services/opdatering_service.py):

    python tools/udgiv_version.py udgiv release/IN-BASE-Setup-v0.10.0.exe [--noter "..."] [--tvungen]
    python tools/udgiv_version.py frigiv 0.10.0 [--procent 100]
    python tools/udgiv_version.py tilbagetraek 0.10.0 [--fortryd]
    python tools/udgiv_version.py minimum 0.10.0
    python tools/udgiv_version.py status
    python tools/udgiv_version.py ryd [--behold 5]

udgiv:        kontrollerer installeren (navn, størrelse, version i exe-filen, kontrolsum,
              skemakrav) og udgiver den som PILOT – kun brugere med pilotkanal får den.
frigiv:       gør versionen STABIL for alle (eller en andel: --procent 25, så 50, så 100).
              På Supabase Free er udgående trafik begrænset – frigiv samlet, ikke hver build.
tilbagetraek: stopper versionen. Klienter, der allerede kører den, går tilbage til
              den nyeste gyldige version (app/domain/opdatering.py).
minimum:      ældre klienter skal opdatere, før de må arbejde videre.
status:       udgivelser og hvilken version hver bruger sidst kørte.
ryd:          sletter gamle installere fra Storage (aldrig den nyeste stabile).
"""
import argparse
import sys
from pathlib import Path

from admin_login import Stop, log_ind   # tools/admin_login.py (samme mappe)


def _version(tekst: str) -> str:
    from app import version_tupel
    try:
        version_tupel(tekst)
    except ValueError as fejl:
        raise Stop(str(fejl)) from fejl
    return tekst


def _service():
    from app.infrastructure import stier
    from app.repositories.supabase.opdatering_repository import SupabaseOpdateringRepository
    from app.services.opdatering_service import OpdateringService
    klient = log_ind("udgive versioner af IN-BASE")
    return OpdateringService(SupabaseOpdateringRepository(klient), stier.OPDATERING_MAPPE), klient


def status() -> None:
    from app.repositories.supabase.konto_repository import SupabaseKontoRepository
    service, klient = _service()
    krav = service.krav()
    print(f"Skemaversion {krav.skema}, mindste klient {krav.min_klient}\n")
    print(f"{'Version':<10}{'Kanal':<8}{'Andel':>6}  {'Status':<16}{'MB':>6}  Oprettet / commit")
    for u in service.udgivelser():
        tilstand = "TRUKKET TILBAGE" if u.trukket_tilbage else ("tvungen" if u.tvungen else "")
        print(f"{u.version:<10}{u.kanal:<8}{u.udrulning:>5}%  {tilstand:<16}"
              f"{u.stoerrelse / 1024 / 1024:>6.1f}  {u.oprettet[:16]} {u.commit}")
    print(f"\n{'Bruger':<16}{'Kanal':<8}{'Version':<10}Sidst set")
    for b in SupabaseKontoRepository(klient).alle_profiler():
        print(f"{b['brugernavn']:<16}{b.get('kanal', ''):<8}{b.get('klient_version') or '–':<10}"
              f"{(b.get('klient_set') or '')[:16]}")


def main() -> int:
    from app.repositories.fejl import ValideringsFejl
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    under = parser.add_subparsers(dest="handling", required=True)
    p = under.add_parser("udgiv")
    p.add_argument("installer", type=Path)
    p.add_argument("--noter", default="")
    p.add_argument("--tvungen", action="store_true")
    p = under.add_parser("frigiv")
    p.add_argument("version")
    p.add_argument("--procent", type=int, default=100)
    p = under.add_parser("tilbagetraek")
    p.add_argument("version")
    p.add_argument("--fortryd", action="store_true")
    p = under.add_parser("minimum")
    p.add_argument("version")
    under.add_parser("status")
    p = under.add_parser("ryd")
    p.add_argument("--behold", type=int, default=5)
    args = parser.parse_args()
    try:
        if args.handling in ("frigiv", "tilbagetraek", "minimum"):
            _version(args.version)                     # tjekkes før log på
        if args.handling == "udgiv" and not args.installer.is_file():
            raise Stop(f"Filen findes ikke: {args.installer}")
        if args.handling == "status":
            status()
            return 0
        service, _ = _service()
        if args.handling == "udgiv":
            pakke = service.kontroller_pakke(args.installer)
            for advarsel in pakke.advarsler:
                print(f"BEMÆRK: {advarsel}")
            print(f"Uploader {pakke.sti.name} ({pakke.stoerrelse / 1024 / 1024:.1f} MB) …")
            service.udgiv(pakke, args.noter, args.tvungen)
            print(f"Version {pakke.version} er udgivet til PILOT. Frigiv den i IN-BASE → "
                  f"Indstillinger → Opdateringer eller: udgiv_version.py frigiv {pakke.version}")
        elif args.handling == "frigiv":
            service.frigiv(args.version, args.procent)
            print(f"Version {args.version} er frigivet som STABIL til {args.procent} % af brugerne.")
        elif args.handling == "tilbagetraek":
            service.tilbagetraek(args.version, args.fortryd)
            print(f"Version {args.version} er {'gyldig igen' if args.fortryd else 'trukket tilbage'}.")
        elif args.handling == "minimum":
            service.saet_minimum(args.version)
            print(f"Klienter ældre end {args.version} skal nu opdatere, før de kan arbejde videre.")
        else:
            for linje in service.ryd(args.behold) or ["Intet at rydde."]:
                print(linje)
    except (Stop, ValideringsFejl) as fejl:
        print(f"FEJL: {fejl}", file=sys.stderr)
        return 1
    except Exception as fejl:   # netværk, rettigheder, manglende migrering 019 …
        print(f"FEJL: {fejl}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
