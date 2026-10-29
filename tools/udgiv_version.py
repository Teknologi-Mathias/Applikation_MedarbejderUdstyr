"""Udgiv IN-BASE til den centrale opdatering – kun administratorer (migrering 019).

    python tools/udgiv_version.py udgiv release/IN-BASE-Setup-v0.10.0.exe [--noter "..."] [--tvungen]
    python tools/udgiv_version.py frigiv 0.10.0 [--procent 100]
    python tools/udgiv_version.py tilbagetraek 0.10.0 [--fortryd]
    python tools/udgiv_version.py minimum 0.10.0
    python tools/udgiv_version.py status
    python tools/udgiv_version.py ryd [--behold 5]

udgiv:        uploader installeren til Storage-bucketten "releases" og registrerer den
              som PILOT – kun brugere med pilotkanal (Indstillinger > Brugere) får den.
              Kontrolsum, størrelse og commit gemmes. Normalt via
              .\\scripts\\build_windows.ps1 -Udgiv.
frigiv:       gør versionen STABIL for alle (eller en andel: --procent 25, så 50, så 100).
              På Supabase Free er udgående trafik begrænset – frigiv samlet, ikke hver build.
tilbagetraek: stopper versionen. Klienter, der allerede kører den, går tilbage til
              den nyeste gyldige version (app/domain/opdatering.py).
minimum:      ældre klienter skal opdatere, før de må arbejde videre. Sæt det først,
              når den nye version er frigivet og virker.
status:       udgivelser og hvilken version hver bruger sidst kørte.
ryd:          sletter gamle installere fra Storage (aldrig den nyeste stabile).
"""
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

from admin_login import ROD, Stop, log_ind   # tools/admin_login.py (samme mappe)

MAKS_STOERRELSE = 50 * 1024 * 1024           # Supabase Free: højst 50 MB pr. fil
_FILNAVN = re.compile(r"^IN-BASE-Setup-v(\d+\.\d+\.\d+)\.exe$")


def _repo():
    from app.repositories.supabase.opdatering_repository import SupabaseOpdateringRepository
    return SupabaseOpdateringRepository(log_ind("udgive versioner af IN-BASE"))


def _commit() -> str:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROD, check=True,
                                capture_output=True, text=True).stdout.strip()
        aendret = subprocess.run(["git", "status", "--porcelain"], cwd=ROD, check=True,
                                 capture_output=True, text=True).stdout.strip()
        return commit + ("+ucommittet" if aendret else "")
    except (OSError, subprocess.CalledProcessError):
        return ""


def _version(tekst: str) -> str:
    from app import version_tupel
    try:
        version_tupel(tekst)
    except ValueError as fejl:
        raise Stop(str(fejl)) from fejl
    return tekst


def udgiv(fil: Path, noter: str, tvungen: bool) -> None:
    from app import KRAEVET_SKEMA
    from app.domain.opdatering import PILOT, Udgivelse

    match = _FILNAVN.match(fil.name)
    if not fil.is_file() or not match:
        raise Stop(f"Ikke en IN-BASE-installer: {fil} (forventet IN-BASE-Setup-v<version>.exe).")
    data = fil.read_bytes()
    if len(data) > MAKS_STOERRELSE:
        raise Stop(f"Installeren fylder {len(data) / 1024 / 1024:.1f} MB – højst 50 MB på Supabase "
                   "Free. Se 'Pakkestørrelse' i docs/RELEASE.md.")
    sha256 = hashlib.sha256(data).hexdigest()
    kontrol = fil.with_name(fil.name + ".sha256")
    if kontrol.is_file() and not kontrol.read_text(encoding="utf-8").lower().startswith(sha256):
        raise Stop(f"Kontrolsummen i {kontrol.name} passer ikke med installeren.")
    version = match.group(1)
    repo = _repo()
    if any(u.version == version for u in repo.udgivelser()):
        raise Stop(f"Version {version} er allerede udgivet. Ret versionsnummeret og byg igen.")
    udgivelse = Udgivelse(version=version, kanal=PILOT, sti=fil.name, sha256=sha256,
                          stoerrelse=len(data), min_skema=KRAEVET_SKEMA, tvungen=tvungen,
                          noter=noter.strip(), commit=_commit())
    print(f"Uploader {fil.name} ({len(data) / 1024 / 1024:.1f} MB) …")
    repo.upload(udgivelse.sti, data)
    try:
        repo.opret(udgivelse)
    except Exception:
        repo.slet_fil(udgivelse.sti)           # ingen fil uden registrering
        raise
    print(f"Version {version} er udgivet til PILOT (commit {udgivelse.commit or 'ukendt'}).")
    print(f"Når den er afprøvet:  python tools/udgiv_version.py frigiv {version}")


def frigiv(version: str, procent: int) -> None:
    from app.domain.opdatering import STABIL
    if not 0 < procent <= 100:
        raise Stop("--procent skal være mellem 1 og 100.")
    version = _version(version)                  # tjekkes før log på
    _repo().opdater(version, kanal=STABIL, udrulning=procent)
    print(f"Version {version} er frigivet som STABIL til {procent} % af brugerne.")


def tilbagetraek(version: str, fortryd: bool) -> None:
    version = _version(version)
    _repo().opdater(version, trukket_tilbage=not fortryd)
    print(f"Version {version} er {'gyldig igen' if fortryd else 'trukket tilbage'}.")


def minimum(version: str) -> None:
    version = _version(version)
    _repo().saet_minimum(version)
    print(f"Klienter ældre end {version} skal nu opdatere, før de kan arbejde videre.")


def status() -> None:
    from app.repositories.supabase.konto_repository import SupabaseKontoRepository
    repo = _repo()
    krav = repo.krav()
    print(f"Skemaversion {krav.get('schema_version')}, mindste klient "
          f"{krav.get('min_client_version')}\n")
    print(f"{'Version':<10}{'Kanal':<8}{'Andel':>6}  {'Status':<16}{'MB':>6}  Oprettet / commit")
    for u in sorted(repo.udgivelser(), key=lambda u: u.tupel, reverse=True):
        tilstand = "TRUKKET TILBAGE" if u.trukket_tilbage else ("tvungen" if u.tvungen else "")
        print(f"{u.version:<10}{u.kanal:<8}{u.udrulning:>5}%  {tilstand:<16}"
              f"{u.stoerrelse / 1024 / 1024:>6.1f}  {u.oprettet[:16]} {u.commit}")
    print(f"\n{'Bruger':<16}{'Kanal':<8}{'Version':<10}Sidst set")
    for b in SupabaseKontoRepository(repo.klient).alle_profiler():
        print(f"{b['brugernavn']:<16}{b.get('kanal', ''):<8}{b.get('klient_version') or '–':<10}"
              f"{(b.get('klient_set') or '')[:16]}")


def ryd(behold: int) -> None:
    from app.domain.opdatering import STABIL
    repo = _repo()
    alle = sorted(repo.udgivelser(), key=lambda u: u.tupel, reverse=True)
    stabile = [u for u in alle if u.kanal == STABIL and not u.trukket_tilbage]
    beskyt = {u.version for u in alle[:max(behold, 1)]} | {u.version for u in stabile[:1]}
    for u in alle:
        if u.version in beskyt:
            continue
        repo.slet_fil(u.sti)
        if u.trukket_tilbage:
            print(f"{u.version}: installeren er slettet (rækken bevares, så klienter ser tilbagetrækningen)")
        else:
            repo.slet(u.version)
            print(f"{u.version}: slettet")


def main() -> int:
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
        if args.handling == "udgiv":
            udgiv(args.installer, args.noter, args.tvungen)
        elif args.handling == "frigiv":
            frigiv(args.version, args.procent)
        elif args.handling == "tilbagetraek":
            tilbagetraek(args.version, args.fortryd)
        elif args.handling == "minimum":
            minimum(args.version)
        elif args.handling == "status":
            status()
        else:
            ryd(args.behold)
    except Stop as fejl:
        print(f"FEJL: {fejl}", file=sys.stderr)
        return 1
    except Exception as fejl:   # netværk, rettigheder, manglende migrering 019 …
        print(f"FEJL: {fejl}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
