"""Signeringsnøglen til IN-BASE Klargøring – ligger i Supabase, kun for administratorer.

Telefonerne accepterer kun en ny version af styrings-appen, hvis den er signeret
med samme nøgle som den, de blev klargjort med. Nøglen ligger derfor ét sted
(tabellen mdm_signing_key, migrering 012), så alle administratorer kan bygge appen
fra deres egen pc. Bruges af scripts\\byg_klargoering_apk.ps1:

    python tools/signeringsnoegle.py hent --keytool <sti til keytool.exe>
    python tools/signeringsnoegle.py ryd

hent: logger på med IN-BASE-brugernavn og adgangskode og skriver android/signering/
      (nøglefil + signering.properties) og android/reservekode.txt. Findes der endnu
      ingen nøgle, laves én med keytool og gemmes – det sker kun første gang.
ryd:  sletter android/signering/ igen, så nøglen ikke bliver liggende på pc'en.
"""
import argparse
import base64
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import admin_login                       # tools/admin_login.py (samme mappe)
from admin_login import Stop

ROD = Path(__file__).resolve().parents[1]

ANDROID = ROD / "android"
SIGNERING = ANDROID / "signering"
RESERVEKODE = ANDROID / "reservekode.txt"
NOEGLEFIL = "inbase-klargoering.p12"
ALIAS = "inbase"
TABEL = "mdm_signing_key"


def log_ind():
    return admin_login.log_ind("bygge styrings-appen")


def ny_noegle(keytool: str) -> dict:
    """Laver en ny nøgle (PKCS12, RSA 4096, 100 år) med en tilfældig adgangskode."""
    adgangskode = secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory() as mappe:
        fil = Path(mappe) / NOEGLEFIL
        subprocess.run([keytool, "-genkeypair", "-keystore", str(fil), "-storetype", "PKCS12",
                        "-storepass", adgangskode, "-keypass", adgangskode, "-alias", ALIAS,
                        "-keyalg", "RSA", "-keysize", "4096", "-validity", "36500",
                        "-dname", "CN=IN-BASE Klargoering"],
                       check=True, capture_output=True)
        data = fil.read_bytes()
    # Den eksisterende reservekode genbruges, så telefoner klargjort med v1 stadig kan nulstilles.
    reserve = (RESERVEKODE.read_text(encoding="utf-8").strip() if RESERVEKODE.is_file()
               else f"{secrets.randbelow(10**8):08d}")
    return {"keystore_base64": base64.b64encode(data).decode("ascii"),
            "store_password": adgangskode, "key_alias": ALIAS, "reserve_code": reserve}


def hent(keytool: str) -> None:
    klient = log_ind()
    raekker = klient.table(TABEL).select("*").execute().data
    if not raekker:
        print("Der findes ingen signeringsnøgle endnu – laver en ny og gemmer den i Supabase.")
        noegle = ny_noegle(keytool)
        try:
            klient.table(TABEL).insert(noegle).execute()
        except Exception:
            # En anden administrator kan have gemt en nøgle i mellemtiden – den gælder så.
            pass
        raekker = klient.table(TABEL).select("*").execute().data
        if not raekker:
            raise Stop("Nøglen kunne ikke gemmes i Supabase. Er migrering 012 kørt?")
    noegle = raekker[0]
    SIGNERING.mkdir(parents=True, exist_ok=True)
    (SIGNERING / NOEGLEFIL).write_bytes(base64.b64decode(noegle["keystore_base64"]))
    (SIGNERING / "signering.properties").write_text(
        f"storeFile={NOEGLEFIL}\nstorePassword={noegle['store_password']}\n"
        f"keyAlias={noegle['key_alias']}\nkeyPassword={noegle['store_password']}\n",
        encoding="utf-8")
    if noegle.get("reserve_code"):
        RESERVEKODE.write_text(noegle["reserve_code"], encoding="utf-8")
    print("Signeringsnøglen er hentet.")


def ryd() -> None:
    shutil.rmtree(SIGNERING, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("handling", choices=("hent", "ryd"))
    parser.add_argument("--keytool", default="keytool")
    args = parser.parse_args()
    try:
        hent(args.keytool) if args.handling == "hent" else ryd()
    except Stop as fejl:
        print(f"FEJL: {fejl}", file=sys.stderr)
        return 1
    except Exception as fejl:   # netværk, manglende konfiguration, keytool …
        print(f"FEJL: signeringsnøglen kunne ikke hentes ({fejl}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
