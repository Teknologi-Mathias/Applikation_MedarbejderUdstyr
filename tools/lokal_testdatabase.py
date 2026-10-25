"""Starter en LOKAL, midlertidig testdatabase i Docker (aldrig Supabase-projektet).

    python tools/lokal_testdatabase.py          # (gen)opret og start
    python tools/lokal_testdatabase.py --stop   # fjern containerne igen

Opretter PostgreSQL 15 + PostgREST (samme REST-lag som Supabase), kører
tests/sql/supabase_stub.sql, alle migreringer (001, 002, ...) – med en konto i
det gamle e-mail-format (tests/sql/foer_005_gammel_konto.sql) lige før 005 –
tests/sql/test_hjaelpere.sql og SQL-testen tests/sql/test_admin_regler.sql.
Derefter kan integrationstesten køres:

    set INBASE_LOKAL_PGRST_URL=http://127.0.0.1:3999
    python -m unittest tests.test_supabase_lokal

Kræver Docker Desktop. Data i containerne er fiktive og slettes med --stop.
"""
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROD = Path(__file__).resolve().parents[1]
MIGRERINGER = ROD / "app/infrastructure/database/migrations"
NET, DB, API = "inbase-net", "inbase-sqltest", "inbase-postgrest"
PORT = 3999
# Kun til den lokale container – ikke en hemmelighed for noget rigtigt system.
JWT_HEMMELIGHED = "lokal-test-hemmelighed-kun-til-docker-0123456789"


def docker(*args, input_tekst=None, tjek=True):
    return subprocess.run(["docker", *args], input=input_tekst, text=True, encoding="utf-8",
                          capture_output=True, check=tjek)


def stop():
    for navn in (API, DB):
        docker("rm", "-f", navn, tjek=False)
    docker("network", "rm", NET, tjek=False)


def psql_fil(fil: Path):
    svar = docker("exec", "-i", DB, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-q",
                  input_tekst=fil.read_text(encoding="utf-8"), tjek=False)
    if svar.returncode:
        raise SystemExit(f"Fejl i {fil.name}:\n{svar.stderr}")
    print(f"  ✓ {fil.relative_to(ROD)}")


def start():
    stop()
    docker("network", "create", NET)
    docker("run", "-d", "--name", DB, "--network", NET,
           "-e", "POSTGRES_PASSWORD=lokaltest", "postgres:15-alpine")
    for _ in range(60):
        if docker("exec", DB, "pg_isready", "-U", "postgres", tjek=False).returncode == 0:
            break
        time.sleep(1)
    time.sleep(2)
    print("Kører SQL:")
    psql_fil(ROD / "tests/sql/supabase_stub.sql")
    for fil in sorted(MIGRERINGER.glob("0*.sql")):
        if fil.name.startswith("005"):
            psql_fil(ROD / "tests/sql/foer_005_gammel_konto.sql")   # afprøver konverteringen
        psql_fil(fil)
    psql_fil(ROD / "tests/sql/test_hjaelpere.sql")
    psql_fil(ROD / "tests/sql/test_admin_regler.sql")   # fejler ved brudt regel
    docker("run", "-d", "--name", API, "--network", NET, "-p", f"127.0.0.1:{PORT}:3000",
           "-e", f"PGRST_DB_URI=postgres://authenticator:lokaltest@{DB}:5432/postgres",
           "-e", "PGRST_DB_SCHEMAS=public", "-e", "PGRST_DB_ANON_ROLE=anon",
           "-e", f"PGRST_JWT_SECRET={JWT_HEMMELIGHED}", "postgrest/postgrest:v12.2.3")
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=2)
        except urllib.error.HTTPError:
            break           # svarer (401 for anonyme) = kører
        except OSError:
            time.sleep(1)
    print(f"\nKlar. Kør:\n  set INBASE_LOKAL_PGRST_URL=http://127.0.0.1:{PORT}\n"
          "  python -m unittest tests.test_supabase_lokal -v")


if __name__ == "__main__":
    stop() if "--stop" in sys.argv else start()
