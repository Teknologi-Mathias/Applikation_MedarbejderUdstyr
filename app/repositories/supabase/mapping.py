"""Oversættelse mellem domænet og Supabase-tabellerne – samlet ét sted.

Domænet serialiserer sig selv til dicts (Sag.til_dict / fra_dict, skabelon-
dicts). Her oversættes de dicts til tabelrækker og tilbage via FELTKORT:
(domænenøgle, kolonne, konvertering). Kolonnenavne, datoer, tidspunkter og
UUID'er håndteres derfor kun her.

Nyt felt i en sag/opgave/skabelon:
  1. Ny migrering: alter table ... add column ... (app/infrastructure/database/migrations/).
  2. Én linje i det relevante feltkort nedenfor.
RPC-funktionerne (003) udleder selv kolonnelisten, så de skal ikke ændres.

Tidspunkter: domænet bruger lokal tid uden tidszone ("2026-10-22T14:03:00").
De gemmes som timestamptz og læses tilbage til samme lokale streng, så
tidslinjens hash-kæde forbliver intakt (forudsætter samme tidszone på
pc'erne – Danmark).
"""
import uuid
from dataclasses import asdict
from datetime import datetime

from app.domain import indmelding as im
from app.domain import skabelon as sk
from app.domain.indmelding import Aendring, Indmelding, Kommentar
from app.domain.mdm_enhed import MdmEnhed
from app.domain.opdatering import Udgivelse
from app.domain.opgave import laes_iso_dato
from app.repositories.fejl import ValideringsFejl

# ---------------------------------------------------------------------------
# Værdier
# ---------------------------------------------------------------------------


def til_tidspunkt(tekst) -> str | None:
    """Lokal tid ("2026-10-22T14:03:00") -> ISO med tidszone, til timestamptz."""
    if not tekst:
        return None
    try:
        tid = datetime.fromisoformat(str(tekst))
    except ValueError:
        return None
    if tid.tzinfo is None:
        tid = tid.astimezone()      # fortolkes som lokal tid
    return tid.isoformat()


def fra_tidspunkt(vaerdi) -> str:
    """timestamptz fra databasen -> lokal tid uden tidszone (domænets format)."""
    if not vaerdi:
        return ""
    tid = datetime.fromisoformat(str(vaerdi).replace("Z", "+00:00"))
    if tid.tzinfo is not None:
        tid = tid.astimezone().replace(tzinfo=None)
    return tid.isoformat(timespec="seconds")


def til_dato(tekst) -> str | None:
    dato = laes_iso_dato(tekst) if tekst else None
    return dato.isoformat() if dato else None


def fra_dato(vaerdi) -> str:
    return str(vaerdi)[:10] if vaerdi else ""


def til_uuid(vaerdi) -> str | None:
    try:
        return str(uuid.UUID(str(vaerdi)))
    except (ValueError, TypeError):
        return None


def til_heltal(vaerdi) -> int:
    try:
        return int(float(str(vaerdi).strip() or 0))
    except ValueError as fejl:
        raise ValideringsFejl(f"'{vaerdi}' er ikke et helt tal.") from fejl


def _tekst_ind(v):
    return str(v or "")


def _tekst_ud(v):
    return v or ""


# konvertering: (til database, fra database)
TEKST = (_tekst_ind, _tekst_ud)
VALGFRI_TEKST = (lambda v: str(v).strip() or None if v else None, _tekst_ud)
BOOL = (bool, bool)
HELTAL = (til_heltal, lambda v: int(v or 0))
DATO = (til_dato, fra_dato)
TIDSPUNKT = (til_tidspunkt, fra_tidspunkt)
ID = (til_uuid, lambda v: str(v) if v else "")
JSON = (lambda v: v or None, lambda v: v)
LISTE = (lambda v: list(v or []), lambda v: list(v or []))
OBJEKT = (lambda v: dict(v or {}), lambda v: dict(v or {}))


def _til_raekke(data: dict, feltkort) -> dict:
    return {kolonne: konv[0](data.get(noegle)) for noegle, kolonne, konv in feltkort}


def _fra_raekke(raekke: dict, feltkort) -> dict:
    return {noegle: konv[1](raekke.get(kolonne)) for noegle, kolonne, konv in feltkort}


# ---------------------------------------------------------------------------
# Sager
# ---------------------------------------------------------------------------

SAG_FELTER = (
    ("id", "id", ID),
    ("proces", "process", TEKST),
    ("status", "status", TEKST),
    ("status_manuel", "status_manual", BOOL),
    ("status_begrundelse", "status_reason", TEKST),
    ("ansvarlig", "responsible", TEKST),
    ("kommentar", "comment", TEKST),
    ("tracking_link", "tracking_link", TEKST),
    ("oprettet", "created_at", TIDSPUNKT),
    ("arkiveret", "archived_on", DATO),
    ("behov", "needs", OBJEKT),
)
PERSON_FELTER = (
    ("person_id", "id", ID),
    ("navn", "full_name", TEKST),
    ("email", "email", VALGFRI_TEKST),
)
ANSAETTELSE_FELTER = (
    ("loennr", "payroll_number", VALGFRI_TEKST),
    ("stilling", "position_code", VALGFRI_TEKST),
    ("omraade", "area_name", VALGFRI_TEKST),
    ("ansaettelsesdato", "employment_date", DATO),
    ("foerste_arbejdsdag", "first_work_day", DATO),
    ("fratraedelsesdato", "termination_date", DATO),
)
OPGAVE_FELTER = (
    ("id", "id", ID),
    ("navn", "name", TEKST),
    ("beskrivelse", "description", TEKST),
    ("ansvarlig", "responsible", TEKST),
    ("frist", "due_date", DATO),
    ("status", "status", TEKST),
    ("obligatorisk", "mandatory", BOOL),
    ("begrundelse", "reason", TEKST),
    ("naeste_handling", "next_action", TEKST),
    ("udstyr", "equipment", TEKST),
    ("milepael", "milestone", TEKST),
    ("afsluttet", "completed_at", TIDSPUNKT),
    ("noegle", "task_key", TEKST),
    ("spor", "track", TEKST),
    ("afdeling", "department", TEKST),
    ("afhaenger_af", "depends_on", LISTE),
    ("betingelse", "condition", TEKST),
    ("planlagt", "planned_at", TIDSPUNKT),
)
RYKKER_FELTER = (
    ("id", "id", ID),
    ("skabelon_navn", "template_name", TEKST),
    ("kategori", "category", TEKST),
    ("emne", "subject", TEKST),
    ("frist", "due_date", DATO),
    ("oprettet", "created_at", TIDSPUNKT),
    ("oprettet_af", "created_by", TEKST),
    ("sendt", "sent_at", TIDSPUNKT),
    ("sendt_af", "sent_by", TEKST),
)
HAENDELSE_FELTER = (
    ("tid", "occurred_at", TIDSPUNKT),
    ("bruger", "actor", TEKST),
    ("handling", "action", TEKST),
    ("kommentar", "comment", TEKST),
    ("reference", "reference", TEKST),
    ("data", "data", JSON),
    ("hash", "hash", (lambda v: v or None, _tekst_ud)),
)

# Én forespørgsel henter sagen med alle dens rækker (PostgREST-embedding).
SAG_SELECT = (
    "*, people(*), "
    "employment_records(*, positions(code), areas(name)), "
    "case_tasks(*), case_reminders(*), audit_events(*)"
)


def _kraev_id(vaerdi, hvad: str) -> str:
    gyldig = til_uuid(vaerdi)
    if gyldig is None:
        raise ValideringsFejl(f"{hvad} har et ugyldigt id ({vaerdi!r}).")
    return gyldig


def sag_til_raekker(sag) -> dict:
    """Sagen som tabelrækker (fuld udgave – se rpc_payload for ændringerne)."""
    data = sag.til_dict()
    sagsraekke = _til_raekke(data, SAG_FELTER)
    sagsraekke["id"] = _kraev_id(data["id"], "Sagen")
    skabelon = data.get("skabelon") or {}
    sagsraekke["template_id"] = til_uuid(skabelon.get("id"))
    sagsraekke["template_name"] = str(skabelon.get("navn") or "")
    sagsraekke["template_version"] = (
        til_heltal(skabelon["version"]) if skabelon.get("version") not in (None, "") else None
    )
    person = _til_raekke(data, PERSON_FELTER)
    person["id"] = _kraev_id(data["person_id"], "Personen")
    opgaver = []
    for nr, opgave in enumerate(data.get("opgaver") or []):
        raekke = _til_raekke(opgave, OPGAVE_FELTER)
        raekke["id"] = _kraev_id(opgave.get("id"), f"Opgaven '{opgave.get('navn')}'")
        raekke["sort_order"] = nr
        opgaver.append(raekke)
    rykkere = []
    for nr, rykker in enumerate(data.get("rykkere") or []):
        raekke = _til_raekke(rykker, RYKKER_FELTER)
        raekke["id"] = _kraev_id(rykker.get("id"), "Rykkeren")
        raekke["created_at"] = raekke["created_at"] or til_tidspunkt(datetime.now().isoformat())
        raekke["sort_order"] = nr
        rykkere.append(raekke)
    haendelser = []
    for nr, haendelse in enumerate(data.get("historik") or []):
        raekke = _til_raekke(haendelse, HAENDELSE_FELTER)
        raekke["sequence"] = nr
        raekke["occurred_at"] = raekke["occurred_at"] or til_tidspunkt(datetime.now().isoformat())
        haendelser.append(raekke)
    return {
        "case": sagsraekke,
        "person": person,
        "employment": _til_raekke(data, ANSAETTELSE_FELTER),
        "tasks": opgaver,
        "reminders": rykkere,
        "events": haendelser,
    }


def rpc_payload(ny: dict, forrige: dict | None) -> dict:
    """Det, der sendes til inbase_save_case: kun det ændrede, hvis forrige kendes.

    forrige = rækkerne fra sidste hentning/gemning af SAMME version. Kendes
    den ikke, sendes alle opgaver/rykkere (replace) – stadig kun for denne sag.
    """
    payload = {"case": ny["case"], "person": ny["person"], "employment": ny["employment"]}
    for noegle, prefix in (("tasks", "tasks"), ("reminders", "reminders")):
        if forrige is None:
            payload[f"{prefix}_upsert"] = ny[noegle]
            payload[f"{prefix}_delete"] = []
            payload[f"{prefix}_replace"] = True
            continue
        gamle = {r["id"]: r for r in forrige[noegle]}
        nye_ids = {r["id"] for r in ny[noegle]}
        payload[f"{prefix}_upsert"] = [r for r in ny[noegle] if gamle.get(r["id"]) != r]
        payload[f"{prefix}_delete"] = [i for i in gamle if i not in nye_ids]
        payload[f"{prefix}_replace"] = False
    start = len(forrige["events"]) if forrige is not None else 0
    payload["events"] = ny["events"][start:]
    return payload


def sag_fra_raekke(raekke: dict, sagstype):
    """En række fra SAG_SELECT -> domæneobjekt (via sagstypens fra_dict)."""
    ansaettelse = raekke.get("employment_records") or {}
    person = raekke.get("people") or {}
    data = _fra_raekke(raekke, SAG_FELTER)
    data.update(_fra_raekke({**ansaettelse,
                             "position_code": (ansaettelse.get("positions") or {}).get("code"),
                             "area_name": (ansaettelse.get("areas") or {}).get("name")},
                            ANSAETTELSE_FELTER))
    data.update(_fra_raekke(person, PERSON_FELTER))
    data["version"] = int(raekke.get("version") or 0)
    data["opdateret"] = fra_tidspunkt(raekke.get("updated_at"))
    if raekke.get("template_id") or raekke.get("template_name"):
        data["skabelon"] = {"id": raekke.get("template_id") or "",
                            "navn": raekke.get("template_name") or "",
                            "version": raekke.get("template_version") or 1}
    data["opgaver"] = [
        _fra_raekke(r, OPGAVE_FELTER)
        for r in sorted(raekke.get("case_tasks") or [], key=lambda r: r.get("sort_order", 0))
    ]
    data["rykkere"] = [
        _fra_raekke(r, RYKKER_FELTER)
        for r in sorted(raekke.get("case_reminders") or [], key=lambda r: r.get("sort_order", 0))
    ]
    haendelser = []
    for r in sorted(raekke.get("audit_events") or [], key=lambda r: r["sequence"]):
        h = _fra_raekke(r, HAENDELSE_FELTER)
        if not h.get("data"):
            h.pop("data", None)
        haendelser.append(h)
    data["historik"] = haendelser
    return sagstype.fra_dict(data)


# ---------------------------------------------------------------------------
# Skabeloner
# ---------------------------------------------------------------------------

ARBEJDSGANG_FELTER = (
    ("id", "id", ID),
    ("proces", "process", TEKST),
    ("navn", "name", TEKST),
    ("beskrivelse", "description", TEKST),
    ("stillinger", "positions", LISTE),
    ("aktiv", "active", BOOL),
    ("version", "version", HELTAL),
)
ARBEJDSGANG_OPGAVE_FELTER = (
    ("navn", "name", TEKST),
    ("beskrivelse", "description", TEKST),
    ("ansvarlig", "responsible", TEKST),
    ("udstyr", "equipment", TEKST),
    ("milepael", "milestone", TEKST),
    ("frist_dage", "due_offset_days", HELTAL),
    ("obligatorisk", "mandatory", BOOL),
    ("noegle", "task_key", TEKST),
    ("spor", "track", TEKST),
    ("afdeling", "department", TEKST),
    ("afhaenger_af", "depends_on", LISTE),
    ("betingelse", "condition", TEKST),
)
MAIL_FELTER = (
    ("id", "id", ID),
    ("navn", "name", TEKST),
    ("kategori", "category", TEKST),
    ("tone", "tone", TEKST),
    ("frist_dage", "due_days", HELTAL),
    ("emne", "subject", TEKST),
    ("broedtekst", "body", TEKST),
    ("aktiv", "active", BOOL),
)
PAAMINDELSE_FELTER = (
    ("id", "id", ID),
    ("navn", "name", TEKST),
    ("regel", "rule", TEKST),
    ("dage", "days", HELTAL),
    ("gentag_dage", "repeat_days", HELTAL),
    ("titel", "title", TEKST),
    ("tekst", "body", TEKST),
    ("aktiv", "active", BOOL),
)
_AENDRET = (("aendret", "updated_at", TIDSPUNKT), ("aendret_af", "updated_by", TEKST))

SKABELON_TABELLER = {
    sk.SAG: "workflow_templates",
    sk.MAIL: "message_templates",
    sk.PAAMINDELSE: "notification_rules",
}
SKABELON_SELECT = {
    sk.SAG: "*, workflow_template_tasks(*), workflow_template_versions(*)",
    sk.MAIL: "*",
    sk.PAAMINDELSE: "*",
}
_SKABELON_FELTER = {sk.SAG: ARBEJDSGANG_FELTER, sk.MAIL: MAIL_FELTER,
                    sk.PAAMINDELSE: PAAMINDELSE_FELTER}


def skabelon_til_raekke(slags: str, skabelon: dict, placering: int) -> dict:
    raekke = _til_raekke(skabelon, _SKABELON_FELTER[slags])
    raekke["id"] = _kraev_id(skabelon.get("id"), f"Skabelonen '{skabelon.get('navn')}'")
    raekke["sort_order"] = int(placering)
    if slags == sk.SAG:
        raekke["tasks"] = [_til_raekke(o, ARBEJDSGANG_OPGAVE_FELTER)
                           for o in skabelon.get("opgaver") or []]
        raekke["versions"] = [
            {"version": til_heltal(v.get("version", 1)), "snapshot": v}
            for v in skabelon.get("versioner") or []
        ]
    else:
        raekke["updated_at"] = til_tidspunkt(skabelon.get("aendret")) or \
            til_tidspunkt(datetime.now().isoformat())
        raekke["updated_by"] = str(skabelon.get("aendret_af") or "")
    return raekke


def skabelon_fra_raekke(slags: str, raekke: dict) -> dict:
    data = _fra_raekke(raekke, _SKABELON_FELTER[slags] + _AENDRET)
    if slags == sk.SAG:
        data["opgaver"] = [
            _fra_raekke(o, ARBEJDSGANG_OPGAVE_FELTER)
            for o in sorted(raekke.get("workflow_template_tasks") or [],
                            key=lambda o: o.get("sort_order", 0))
        ]
        data["versioner"] = [
            v["snapshot"] for v in sorted(raekke.get("workflow_template_versions") or [],
                                          key=lambda v: v["version"])
        ]
    return sk.klargoer(data, slags)


# ---------------------------------------------------------------------------
# Indstillinger og brugere
# ---------------------------------------------------------------------------

# Nøgler i app_settings. "omraader" ligger i tabellen areas.
OMRAADER = "omraader"


# Supabase Auth logger på med e-mail. IN-BASE-brugere har derfor en intern,
# IKKE-leveringsbar adresse afledt af brugernavnet (".invalid" er reserveret
# og kan aldrig modtage post, RFC 2606). Aliaset vises aldrig og bruges aldrig
# til post. SAMME regel: inbase_login_alias() (migrering 005) og loginAlias()
# i supabase/functions/_shared/admin.ts. Ændres domænet, kan eksisterende
# konti ikke længere logge på.
LOGIN_ALIAS_DOMAENE = "brugere.in-base.invalid"


def login_alias(brugernavn: str) -> str:
    """Normaliseret brugernavn ("HAFRA") -> "hafra@brugere.in-base.invalid"."""
    return f"{brugernavn.strip().lower()}@{LOGIN_ALIAS_DOMAENE}"


def bruger_fra_profil(profil: dict) -> dict:
    """user_profiles-række -> brugerdict i samme format som JSON-brugerne."""
    return {
        "id": profil.get("id", ""),
        "brugernavn": profil.get("username", ""),
        "navn": profil.get("display_name") or profil.get("username", ""),
        "rolle": profil.get("role", ""),
        "aktiv": bool(profil.get("active", True)),
        "oprettet": fra_tidspunkt(profil.get("created_at")),
        "skal_skifte_kode": bool(profil.get("must_change_password")),
        # None = standardmodulerne (migrering 010); ellers en liste af moduler.
        "moduler": (list(profil["module_access"])
                    if profil.get("module_access") is not None else None),
        # Afdelinger brugeren er medlem af (migrering 014).
        "roller": list(profil.get("roles") or []),
        # Central opdatering (migrering 019): kanal og senest kørte klientversion.
        "kanal": profil.get("update_channel") or "stabil",
        "klient_version": profil.get("client_version") or "",
        "klient_set": fra_tidspunkt(profil.get("client_seen_at")),
    }


PRAEFERENCE_FELTER = (
    ("tema", "theme", TEKST),
    ("windows_notifikationer", "windows_notifications", BOOL),
)


def praeference_til_raekke(praef: dict) -> dict:
    return {kolonne: konv[0](praef[noegle])
            for noegle, kolonne, konv in PRAEFERENCE_FELTER if noegle in praef}


def praeference_fra_raekke(raekke: dict) -> dict:
    return _fra_raekke(raekke, PRAEFERENCE_FELTER)


# ---------------------------------------------------------------------------
# Ønsker & Udvikling (development_requests, migrering 006)
# ---------------------------------------------------------------------------

INDMELDING_FELTER = (
    ("id", "id", ID),
    ("nummer", "number", HELTAL),
    ("titel", "title", TEKST),
    ("kategori", "category", TEKST),
    ("beskrivelse", "description", TEKST),
    ("problem", "current_behavior", TEKST),
    ("oensket_resultat", "desired_outcome", TEKST),
    ("effekt", "business_impact", TEKST),
    ("supplerende", "additional_info", TEKST),
    ("status", "status", TEKST),
    ("prioritet", "priority", TEKST),
    ("indsender", "submitted_by_username", TEKST),
    ("ansvarlig", "assignee_username", TEKST),
    ("planlagt_version", "planned_version", TEKST),
    ("loesning", "resolution", TEKST),
    ("oprettet", "created_at", TIDSPUNKT),
    ("opdateret", "updated_at", TIDSPUNKT),
    ("version", "version", HELTAL),
)

# Domænefelt -> nøgle i RPC'ernes p_request/p_changes og i historikkens "field".
# Ansvarlig sendes som brugernavn ("assignee"); databasen slår brugeren op.
INDMELDING_RPC_NOEGLER = {
    **{noegle: kolonne for noegle, kolonne, _ in INDMELDING_FELTER
       if noegle in im.TEKSTFELTER + im.BEHANDLINGSFELTER},
    "ansvarlig": "assignee",
}
_FELT_FRA_RPC = {rpc: noegle for noegle, rpc in INDMELDING_RPC_NOEGLER.items()}


def indmelding_fra_raekke(raekke: dict) -> Indmelding:
    return Indmelding.fra_dict(_fra_raekke(raekke, INDMELDING_FELTER))


def indmelding_til_rpc(felter: dict) -> dict:
    """{"titel": ..., "ansvarlig": "HAFRA"} -> {"title": ..., "assignee": "HAFRA"}."""
    return {INDMELDING_RPC_NOEGLER[noegle]: str(vaerdi) for noegle, vaerdi in felter.items()}


def kommentar_fra_raekke(raekke: dict) -> Kommentar:
    return Kommentar(
        indmelding_id=str(raekke.get("request_id") or ""),
        forfatter=raekke.get("author_username") or "",
        tekst=raekke.get("body") or "",
        intern=bool(raekke.get("internal")),
        oprettet=fra_tidspunkt(raekke.get("created_at")),
        id=str(raekke.get("id") or ""),
    )


def aendring_fra_raekke(raekke: dict) -> Aendring:
    felt = raekke.get("field") or ""
    return Aendring(
        tidspunkt=fra_tidspunkt(raekke.get("occurred_at")),
        bruger=raekke.get("actor_username") or "",
        handling=raekke.get("action") or "",
        felt=_FELT_FRA_RPC.get(felt, felt),
        fra=raekke.get("old_value") or "",
        til=raekke.get("new_value") or "",
    )


# ---------------------------------------------------------------------------
# Telefoner (mdm_devices, migrering 007-013)
# ---------------------------------------------------------------------------

MDM_FELTER = (
    ("id", "id", ID),
    ("navn", "name", TEKST),
    ("telefonnummer", "phone_number", TEKST),
    ("note", "note", TEKST),
    ("status", "status", TEKST),
    ("producent", "manufacturer", TEKST),
    ("model", "model", TEKST),
    ("serienummer", "serial_number", TEKST),
    ("imei", "imei", TEKST),
    ("android_version", "android_version", TEKST),
    ("klargjort", "provisioned_at", TIDSPUNKT),
    ("nulstillingskode", "reset_code", TEKST),
    ("mail", "mail", BOOL),
    ("arkiveret", "archived_at", TIDSPUNKT),
    ("oprettet_af", "created_by_username", TEKST),
    ("oprettet", "created_at", TIDSPUNKT),
    ("opdateret", "updated_at", TIDSPUNKT),
)
_MDM_KOLONNE = {noegle: (kolonne, konv) for noegle, kolonne, konv in MDM_FELTER}


def mdm_fra_raekke(raekke: dict) -> MdmEnhed:
    return MdmEnhed.fra_dict(_fra_raekke(raekke, MDM_FELTER))


def mdm_til_rpc(felter: dict) -> dict:
    """{"navn": "ISM589", "klargjort": "2026-..."} -> {"name": "ISM589", "provisioned_at": "...+01:00"}.
    Tomme tidspunkter sendes som null."""
    return {_MDM_KOLONNE[k][0]: _MDM_KOLONNE[k][1][0](v) for k, v in felter.items()}


# ---------------------------------------------------------------------------
# Udgivne versioner (app_releases, migrering 019)
# ---------------------------------------------------------------------------

UDGIVELSE_FELTER = (
    ("version", "version", TEKST),
    ("kanal", "channel", TEKST),
    ("sti", "storage_path", TEKST),
    ("sha256", "sha256", TEKST),
    ("stoerrelse", "size_bytes", HELTAL),
    ("min_skema", "min_schema", HELTAL),
    ("tvungen", "mandatory", BOOL),
    ("noter", "notes", TEKST),
    ("udrulning", "rollout_percent", HELTAL),
    ("trukket_tilbage", "withdrawn", BOOL),
    ("commit", "commit_hash", TEKST),
)


def udgivelse_fra_raekke(raekke: dict) -> Udgivelse:
    return Udgivelse(**_fra_raekke(raekke, UDGIVELSE_FELTER),
                     oprettet=fra_tidspunkt(raekke.get("created_at")),
                     oprettet_af=raekke.get("created_by") or "")


def udgivelse_til_raekke(udgivelse: Udgivelse) -> dict:
    return _til_raekke(asdict(udgivelse), UDGIVELSE_FELTER)
