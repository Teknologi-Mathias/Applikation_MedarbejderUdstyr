"""Afvikling af de GAMLE lokale forretningsdata (JSON) efter skiftet til Supabase.

De gamle data migreres IKKE – IN-BASE starter forfra i Supabase. Dette
værktøj viser, hvilke filer der er gamle forretningsdata (persondata), og
sletter dem kun efter en udtrykkelig bekræftelse. Det rører aldrig
kildekode, %APPDATA%\\IN-BASE\\.env (ny konfiguration) eller logfiler.

    python tools/afvikl_gamle_data.py              # vis (ændrer intet)
    python tools/afvikl_gamle_data.py --slet       # slet efter bekræftelse
    python tools/afvikl_gamle_data.py --data X:\\delt\\IN-BASE\\Data   # anden datamappe

Kør det på hver pc, hvor IN-BASE har været brugt (og på et evt. netværksdrev).
Ønsker HR en sidste kopi, så tag den FØR sletning og opbevar den efter jeres
slettepolitik – ikke i projektmappen.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

ROD = Path(__file__).resolve().parents[1]

# Filer i en IN-BASE-datamappe og hvad de indeholder.
FORRETNINGSDATA = {
    "medarbejdere.json": "aktive offboardingsager (navne, lønnr., e-mail, tidslinje)",
    "arkiv.json": "arkiverede offboardingsager (persondata)",
    "onboarding.json": "aktive onboardingforløb (persondata)",
    "onboarding_arkiv.json": "arkiverede onboardingforløb (persondata)",
    "skabeloner.json": "gamle skabeloner (erstattes af 004_seed_standarder.sql)",
    "indstillinger.json": "gamle fælles indstillinger",
    "brugere.json": "gamle lokale konti med kode-hashes (erstattes af Supabase Auth)",
}
# Mapper med kopier af forretningsdata.
KOPIMAPPER = {
    "Backup": "sikkerhedskopier af ovenstående (samme persondata)",
    "Offline": "offline-kopi af datamappen (JSON-tilstandens offline-drift)",
}
# Lokale, tekniske filer (ikke forretningsdata). Kan slettes, men behøver ikke.
TEKNISK = {
    "notifikationslog.json": "hvilke påmindelser der er vist (sags-id'er)",
    "praeferencer.json": "tema/notifikationer pr. bruger (nu på profilen i Supabase)",
    "lagring.json": "online/offline-valg (kun JSON-tilstanden)",
    "Logs": "logfiler – teknisk; behold dem til fejlsøgning eller slet efter behov",
}


def kandidater(datamapper: list[Path], lokale: list[Path]) -> list[tuple[Path, str, bool]]:
    """[(sti, beskrivelse, er_forretningsdata)] for det, der findes."""
    fundet = []
    for mappe in datamapper:
        for navn, tekst in FORRETNINGSDATA.items():
            if (mappe / navn).exists():
                fundet.append((mappe / navn, tekst, True))
        for navn, tekst in KOPIMAPPER.items():
            if (mappe / navn).exists():
                fundet.append((mappe / navn, tekst, True))
        for korrupt in mappe.glob("*.korrupt-*.json"):
            fundet.append((korrupt, "kopi af en ødelagt datafil", True))
    for mappe in lokale:
        for navn in ("Offline",):
            if (mappe / navn).exists():
                fundet.append((mappe / navn, KOPIMAPPER[navn], True))
        for navn, tekst in TEKNISK.items():
            if (mappe / navn).exists():
                fundet.append((mappe / navn, tekst, False))
    return fundet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", action="append", default=[],
                        help="ekstra datamappe (fx på et netværksdrev)")
    parser.add_argument("--slet", action="store_true", help="slet forretningsdata efter bekræftelse")
    parser.add_argument("--ogsaa-teknisk", action="store_true",
                        help="slet også de tekniske lokale filer (ikke logfiler)")
    args = parser.parse_args()

    appdata = Path(os.environ.get("APPDATA", Path.home()))
    localappdata = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    datamapper = [ROD / "Data", appdata / "MedarbejderUdstyr" / "Data",
                  *[Path(d) for d in args.data]]
    lokale = [ROD / "Lokal", localappdata / "IN-BASE"]

    fundet = kandidater(datamapper, lokale)
    if not fundet:
        print("Ingen gamle IN-BASE-data fundet.")
        return 0
    print("Fundet:\n")
    for sti, tekst, forretning in fundet:
        print(f"  [{'FORRETNINGSDATA' if forretning else 'teknisk        '}] {sti}\n"
              f"      {tekst}")
    if not args.slet:
        print("\nIntet er ændret. Kør med --slet for at slette forretningsdataene.")
        return 0

    slettes = [(s, t) for s, t, f in fundet
               if f or (args.ogsaa_teknisk and s.name != "Logs")]
    print(f"\n{len(slettes)} filer/mapper slettes permanent.")
    if input("Skriv SLET for at fortsætte: ").strip() != "SLET":
        print("Afbrudt – intet er slettet.")
        return 1
    for sti, _ in slettes:
        if sti.is_dir():
            shutil.rmtree(sti)
        else:
            sti.unlink()
        print(f"  slettet: {sti}")
    for mappe in datamapper:
        if mappe.exists() and not any(mappe.iterdir()):
            mappe.rmdir()
    print("Færdig. Kildekode og %APPDATA%\\IN-BASE\\.env er ikke rørt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
