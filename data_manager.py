from pathlib import Path
import json

from medarbejder import Medarbejder


BASE_MAPPE = Path(__file__).resolve().parent
DATA_MAPPE = BASE_MAPPE / "Data"
AKTIVE_FIL = DATA_MAPPE / "medarbejdere.json"
ARKIV_FIL = DATA_MAPPE / "arkiv.json"


def _sikre_data_mappe():
    DATA_MAPPE.mkdir(parents=True, exist_ok=True)


def _hent_json(fil):
    _sikre_data_mappe()

    if not fil.exists():
        return []

    

    with fil.open("r", encoding="utf-8") as f:
        if f == "":
            return []
        else:
            return json.load(f)


def _gem_json(data, fil):
    _sikre_data_mappe()

    with fil.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def hent_medarbejdere():
    data = _hent_json(AKTIVE_FIL)

    medarbejdere = []

    for medarbejder_data in data:
        medarbejder = Medarbejder.fra_dict(medarbejder_data)
        medarbejdere.append(medarbejder)

    return medarbejdere


def gem_medarbejdere(medarbejdere):
    data = []

    for medarbejder in medarbejdere:
        data.append(medarbejder.til_dict())

    _gem_json(data, AKTIVE_FIL)


def hent_arkiv():
    data = _hent_json(ARKIV_FIL)

    medarbejdere = []

    for medarbejder_data in data:
        medarbejder = Medarbejder.fra_dict(medarbejder_data)
        medarbejdere.append(medarbejder)

    return medarbejdere


def arkiver_medarbejder(medarbejder):
    arkiv = _hent_json(ARKIV_FIL)
    data = _hent_json(AKTIVE_FIL)

    arkiv.append(medarbejder.til_dict())
    data.remove(medarbejder.til_dict())

    _gem_json(data, AKTIVE_FIL)
    _gem_json(arkiv, ARKIV_FIL)