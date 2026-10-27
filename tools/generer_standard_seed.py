"""Genererer migrations/015_seed_standarder.sql ud fra programmets standarder.

(004 er den oprindelige udgave og ændres ikke længere – 015 køres efter 014,
så skabelonopgaverne kan have arbejdsspor.)

Standardskabelonerne (app/domain/skabelon.py) og standardområderne
(app/services/indstillinger_service.py) er de BEVIDSTE standarder, en ny
database starter med. De får faste UUID'er (uuid5), så filen er den samme
hver gang, og SQL'en kan køres igen uden dubletter (on conflict do nothing).

Kør efter en ændring af standarderne:
    python tools/generer_standard_seed.py
"""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain import skabelon as sk  # noqa: E402
from app.repositories.supabase import mapping  # noqa: E402
from app.services.indstillinger_service import STANDARD  # noqa: E402

NAVNERUM = uuid.UUID("6f1d3c52-6a0e-4d1b-9a7e-2c5b8f0e1a11")
MAAL = (Path(__file__).resolve().parents[1]
        / "app/infrastructure/database/migrations/015_seed_standarder.sql")
# Standarder fra før arbejdssporene (004): deaktiveres – slettes ikke.
UDGAAEDE = (("sager", "onboarding", "Onboarding – standard"),
            ("sager", "onboarding", "Onboarding – FM/DM"),
            # Arbejdssporene før det forenklede flow (deaktiveret af migrering 018).
            ("sager", "onboarding", "Onboarding – arbejdsspor"),
            ("sager", "onboarding", "Onboarding – arbejdsspor FM/DM"))


def _sql_json(data) -> str:
    return "'" + json.dumps(data, ensure_ascii=False, indent=1).replace("'", "''") + "'::jsonb"


def _indsaet(tabel: str, raekker: list[dict]) -> str:
    kolonner = ", ".join(raekker[0])
    return (f"insert into public.{tabel} ({kolonner})\n"
            f"select {kolonner} from jsonb_populate_recordset(null::public.{tabel},\n"
            f"{_sql_json(raekker)})\n"
            "on conflict do nothing;\n")


def generer() -> str:
    dele = [
        "-- IN-BASE 015: bevidste standarder (ingen forretningsdata). Køres EFTER 014.\n"
        "-- GENERERET af tools/generer_standard_seed.py – ret standarderne i Python og\n"
        "-- generér filen igen. Kan køres flere gange (on conflict do nothing).\n",
    ]
    omraader = [{"id": str(uuid.uuid5(NAVNERUM, f"area/{navn}")), "name": navn,
                 "sort_order": nr, "active": True}
                for nr, navn in enumerate(STANDARD["omraader"])]
    dele.append("-- Områder (Indstillinger → Organisation)\n" + _indsaet("areas", omraader))

    for slags, tabel in mapping.SKABELON_TABELLER.items():
        skabeloner, opgaver = [], []
        for nr, data in enumerate(sk._STANDARD[slags]):
            skabelon = sk.klargoer(dict(data, id=str(uuid.uuid5(
                NAVNERUM, f"{slags}/{data.get('proces', '')}/{data['navn']}"))), slags)
            skabelon["aendret_af"] = "standard"
            raekke = mapping.skabelon_til_raekke(slags, skabelon, nr)
            for opgave_nr, opgave in enumerate(raekke.pop("tasks", [])):
                opgaver.append({**opgave, "id": str(uuid.uuid5(
                    NAVNERUM, f"task/{raekke['id']}/{opgave_nr}")),
                    "template_id": raekke["id"], "sort_order": opgave_nr})
            raekke.pop("versions", None)
            raekke.setdefault("updated_by", "standard")
            raekke["updated_at"] = "2026-01-01T00:00:00+00:00"
            skabeloner.append(raekke)
        dele.append(f"-- {slags}\n" + _indsaet(tabel, skabeloner))
        if opgaver:
            dele.append(_indsaet("workflow_template_tasks", opgaver))
    udgaaede = ", ".join(f"'{uuid.uuid5(NAVNERUM, '/'.join(n))}'" for n in UDGAAEDE)
    dele.append("-- Onboarding-skabeloner fra før arbejdssporene: deaktiveres (slettes ikke)\n"
                f"update public.workflow_templates set active = false where id in ({udgaaede});\n")
    return "\n".join(dele)


if __name__ == "__main__":
    MAAL.write_text(generer(), encoding="utf-8")
    print(f"Skrevet: {MAAL}")
