"""Forbered migrering af JSON-data til den relationelle model (001_initial_schema.sql).

Læser KUN – kildefilerne ændres aldrig og slettes ikke. Resultatet er én
JSON-fil pr. tabel (klar til import) og en valideringsrapport, der
sammenholder resultatet med de oprindelige data.

Kør:
    python -m app.infrastructure.database.migrering --data Data --ud migrering_ud

Id'er: sager beholder deres UUID. Afledte rækker (opgaver, hændelser,
rykkere, ansættelser) får deterministiske UUIDv5-id'er, så en gentaget
kørsel giver samme resultat og kan sammenlignes.

Adgangskoder migreres IKKE: brugerne oprettes i Supabase Auth (invitation),
og user_profiles kobles på auth.users.id ved import.
"""
import argparse
import json
import uuid
from collections import Counter
from pathlib import Path

from app.domain import skabelon as sk
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb
from app.infrastructure import stier
from app.repositories.json.json_fil import hent_json

NAVNERUM = uuid.UUID("6f1d3c52-6a0e-4d1b-9a7e-2c5b8f0e1a11")


def _uuid(*dele) -> str:
    return str(uuid.uuid5(NAVNERUM, "/".join(str(d) for d in dele)))


def _dato(tekst):
    return str(tekst)[:10] if tekst else None


class IkkeMigreretFejl(Exception):
    """Kildedata har endnu ikke stabile id'er (programmet er ikke startet efter opdateringen)."""


def _laes_sager(mappe: Path):
    sager = []
    for filnavn, sagstype, arkiv in (
        (stier.OFFBOARDING_AKTIVE, Medarbejder, False),
        (stier.OFFBOARDING_ARKIV, Medarbejder, True),
        (stier.ONBOARDING_AKTIVE, OnboardingForloeb, False),
        (stier.ONBOARDING_ARKIV, OnboardingForloeb, True),
    ):
        for post in hent_json(mappe / filnavn):
            if not isinstance(post, dict):
                continue
            if not (post.get("id") and post.get("person_id") and "historik" in post):
                raise IkkeMigreretFejl(
                    f"{filnavn} indeholder sager uden stabile id'er. Start IN-BASE én gang "
                    "(så migreres data efter en backup), og kør derefter dette værktøj."
                )
            sager.append((sagstype.fra_dict(post), arkiv, post))
    return sager


def byg_raekker(mappe: Path) -> dict:
    """Bygger rækker til alle tabeller ud fra datamappen."""
    raekker = {t: [] for t in (
        "areas", "positions", "people", "employment_records", "workflow_templates",
        "workflow_template_versions", "workflow_template_tasks", "message_templates",
        "notification_rules", "lifecycle_cases", "case_tasks", "case_reminders",
        "audit_events", "user_profiles",
    )}
    indstillinger = hent_json(mappe / stier.INDSTILLINGER, forventet=dict)
    omraader = set(indstillinger.get("omraader", []))
    sager = _laes_sager(mappe)
    omraader.update(s.omraade for s, _, _ in sager if getattr(s, "omraade", ""))
    for navn in sorted(omraader):
        raekker["areas"].append({"id": _uuid("area", navn), "name": navn, "active": True})
    for kode in OnboardingForloeb.STILLINGER:
        raekker["positions"].append({"id": _uuid("position", kode), "code": kode, "name": kode})

    # --- skabeloner (rå fil normaliseres i hukommelsen – filen skrives ikke) ---
    skabeloner = sk.normaliser_alle(hent_json(mappe / stier.SKABELONER, forventet=(list, dict)))
    for s in skabeloner[sk.SAG]:
        skabelon_id = _uuid("template", s["id"])
        raekker["workflow_templates"].append({
            "id": skabelon_id, "legacy_id": s["id"], "process": s["proces"], "name": s["navn"],
            "description": s.get("beskrivelse", ""), "positions": s.get("stillinger", []),
            "active": s["aktiv"], "version": s.get("version", 1),
            "updated_at": s.get("aendret"), "updated_by": s.get("aendret_af"),
        })
        for gammel in s.get("versioner", []):
            raekker["workflow_template_versions"].append({
                "template_id": skabelon_id, "version": gammel.get("version", 1), "snapshot": gammel,
            })
        for nr, o in enumerate(s["opgaver"]):
            raekker["workflow_template_tasks"].append({
                "id": _uuid("template_task", s["id"], nr), "template_id": skabelon_id,
                "sort_order": nr, "name": o["navn"], "description": o.get("beskrivelse", ""),
                "responsible": o.get("ansvarlig", ""), "equipment": o.get("udstyr", ""),
                "milestone": o.get("milepael", ""), "due_offset_days": int(o.get("frist_dage", 0)),
                "mandatory": bool(o.get("obligatorisk", True)),
            })
    for m in skabeloner[sk.MAIL]:
        raekker["message_templates"].append({
            "id": _uuid("message", m["id"]), "legacy_id": m["id"], "name": m["navn"],
            "category": m["kategori"], "tone": m["tone"], "due_days": m["frist_dage"],
            "subject": m["emne"], "body": m["broedtekst"], "active": m["aktiv"],
        })
    for p in skabeloner[sk.PAAMINDELSE]:
        raekker["notification_rules"].append({
            "id": _uuid("rule", p["id"]), "legacy_id": p["id"], "name": p["navn"],
            "rule": p["regel"], "days": p["dage"], "repeat_days": p.get("gentag_dage", 1),
            "title": p["titel"], "body": p["tekst"], "active": p["aktiv"],
        })
    skabelon_ider = {r["legacy_id"]: r["id"] for r in raekker["workflow_templates"]}

    # --- personer, ansættelser og sager ---
    personer = {}
    for sag, arkiveret, _ in sager:
        if sag.person_id not in personer:
            personer[sag.person_id] = {"id": sag.person_id, "full_name": sag.navn,
                                       "email": getattr(sag, "email", "") or None}
            raekker["people"].append(personer[sag.person_id])
        ansaettelse_id = _uuid("employment", sag.id)
        onboarding = isinstance(sag, OnboardingForloeb)
        raekker["employment_records"].append({
            "id": ansaettelse_id, "person_id": sag.person_id,
            "payroll_number": sag.loennr or None,
            "position_id": _uuid("position", sag.stilling) if onboarding and sag.stilling else None,
            "area_id": _uuid("area", sag.omraade) if onboarding and sag.omraade else None,
            "employment_date": _dato(sag.ansaettelsesdato) if onboarding else None,
            "first_work_day": _dato(sag.foerste_arbejdsdag) if onboarding else None,
            "termination_date": None if onboarding else _dato(sag.fratraedelsesdato),
        })
        raekker["lifecycle_cases"].append({
            "id": sag.id, "person_id": sag.person_id, "employment_record_id": ansaettelse_id,
            "process": sag.PROCES, "status": sag.status,
            "status_manual": sag.status_manuel is not None,
            "status_reason": sag.status_begrundelse, "responsible": sag.ansvarlig,
            "comment": sag.kommentar, "tracking_link": getattr(sag, "tracking_link", ""),
            "template_id": skabelon_ider.get(sag.skabelon.get("id")),
            "template_version": sag.skabelon.get("version"),
            "archived_on": _dato(sag.arkiveret) or (None if not arkiveret else _dato(sag.opdateret)),
            "created_at": sag.oprettet, "updated_at": sag.opdateret, "version": max(sag.version, 1),
        })
        for nr, o in enumerate(sag.opgaver):
            raekker["case_tasks"].append({
                "id": _uuid("task", sag.id, o.id), "case_id": sag.id, "legacy_id": o.id,
                "sort_order": nr, "name": o.navn, "description": o.beskrivelse,
                "responsible": o.ansvarlig, "due_date": _dato(o.frist), "status": o.status,
                "mandatory": o.obligatorisk, "reason": o.begrundelse,
                "next_action": o.naeste_handling, "equipment": o.udstyr,
                "milestone": o.milepael, "completed_at": o.afsluttet_tid or None,
            })
        for r in getattr(sag, "rykkere", []):
            raekker["case_reminders"].append({
                "id": _uuid("reminder", sag.id, r.id), "case_id": sag.id, "legacy_id": r.id,
                "template_name": r.skabelon_navn, "category": r.kategori, "subject": r.emne,
                "due_date": _dato(r.frist), "created_at": r.oprettet, "created_by": r.oprettet_af,
                "sent_at": r.sendt or None, "sent_by": r.sendt_af,
            })
        for nr, h in enumerate(sag.historik.haendelser()):
            raekker["audit_events"].append({
                "id": _uuid("event", sag.id, nr), "case_id": sag.id, "sequence": nr,
                "occurred_at": h.get("tid"), "actor": h.get("bruger", ""),
                "action": h.get("handling", ""), "comment": h.get("kommentar", ""),
                "reference": h.get("reference", ""), "data": h.get("data"), "hash": h.get("hash"),
            })

    for b in hent_json(mappe / stier.BRUGERE):
        if isinstance(b, dict) and b.get("brugernavn"):
            raekker["user_profiles"].append({
                "id": None,  # sættes til auth.users.id, når brugeren er oprettet i Supabase Auth
                "username": b["brugernavn"], "display_name": b.get("navn", ""),
                "role": b.get("rolle", "Bruger"),
            })
    return raekker


def valider(raekker: dict, mappe: Path) -> list[str]:
    """Sammenholder rækkerne med kildedata. Returnerer en liste af fejl (tom = OK)."""
    fejl = []
    sager = _laes_sager(mappe)
    if len(raekker["lifecycle_cases"]) != len(sager):
        fejl.append(f"Antal sager: {len(raekker['lifecycle_cases'])} ≠ kilde {len(sager)}")
    sag_ider = {r["id"] for r in raekker["lifecycle_cases"]}
    if len(sag_ider) != len(raekker["lifecycle_cases"]):
        fejl.append("Dublerede sags-id'er.")
    opgaver = Counter(r["case_id"] for r in raekker["case_tasks"])
    haendelser = Counter(r["case_id"] for r in raekker["audit_events"])
    rykkere = Counter(r["case_id"] for r in raekker["case_reminders"])
    for sag, _, _ in sager:
        if sag.id not in sag_ider:
            fejl.append(f"Sag mangler: {sag.navn} ({sag.id})")
        if opgaver[sag.id] != len(sag.opgaver):
            fejl.append(f"{sag.navn}: {opgaver[sag.id]} opgaver ≠ kilde {len(sag.opgaver)}")
        if haendelser[sag.id] != len(sag.historik):
            fejl.append(f"{sag.navn}: {haendelser[sag.id]} hændelser ≠ kilde {len(sag.historik)}")
        if rykkere[sag.id] != len(getattr(sag, "rykkere", [])):
            fejl.append(f"{sag.navn}: rykkere stemmer ikke")
        if sag.status not in type(sag).STATUSER:
            fejl.append(f"{sag.navn}: ugyldig status {sag.status!r}")
    personer = {r["id"] for r in raekker["people"]}
    for r in raekker["lifecycle_cases"]:
        if r["person_id"] not in personer:
            fejl.append(f"Sag {r['id']} peger på en ukendt person.")
    return fejl


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Forbered migrering af IN-BASE-data til SQL.")
    parser.add_argument("--data", type=Path, default=stier.CENTRAL_DATA_MAPPE)
    parser.add_argument("--ud", type=Path, required=True)
    args = parser.parse_args(argv)
    raekker = byg_raekker(args.data)
    fejl = valider(raekker, args.data)
    args.ud.mkdir(parents=True, exist_ok=True)
    for tabel, data in raekker.items():
        (args.ud / f"{tabel}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    rapport = {"antal": {t: len(r) for t, r in raekker.items()}, "fejl": fejl}
    (args.ud / "rapport.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    for tabel, antal in rapport["antal"].items():
        print(f"{tabel:28} {antal}")
    print("Validering:", "OK" if not fejl else f"{len(fejl)} fejl – se rapport.json")
    return 0 if not fejl else 1


if __name__ == "__main__":
    raise SystemExit(main())
