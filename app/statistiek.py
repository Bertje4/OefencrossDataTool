"""
Statistiek voor de pagina "Tijden individuele atleet" en de atleten-suggesties
bij het invoeren. Enkel lezen; er wordt hier niets bewaard.

Alleen de EINDTIJD telt (geen tussentijden). Atleten die in een oefencross
slechts 1 ronde liepen hebben geen eindtijd en geven dus geen punt in de grafieken.
"""
from . import datastore as ds


def _sleutel(naam, voornaam):
    return (ds._norm_naam(naam), ds._norm_naam(voornaam))


def _eindtijden_per_atleet():
    """{sleutel: [(datum_iso, seconden, tijd_tekst), ...]} van oud naar nieuw."""
    uit = {}
    for e in ds.laad_alle_events():
        for d in e.get("deelnames", []):
            eind = ds.parse_tijd(d.get("eindtijd"))
            if eind is None:
                continue
            honderdsten = eind // ds.timedelta(milliseconds=10)
            uit.setdefault(_sleutel(d["naam"], d["voornaam"]), []).append(
                (e["datum"], honderdsten / 100.0, ds.format_tijd(eind))
            )
    return uit


def keuzelijst():
    """Alle atleten voor de keuzelijst, met het aantal eindtijden (alfabetisch)."""
    per_atleet = _eindtijden_per_atleet()
    rijen = []
    for a in ds.laad_atleten():
        rijen.append({
            "id": a["id"],
            "naam": a["naam"],
            "voornaam": a["voornaam"],
            "n": len(per_atleet.get(_sleutel(a["naam"], a["voornaam"]), [])),
        })
    rijen.sort(key=lambda r: (r["naam"].lower(), r["voornaam"].lower()))
    return rijen


def tijdreeksen(ids):
    """
    Tijdreeksen voor de gekozen atleet-id's. Lege/onbekende id's (vrije
    kleurplekken) komen als None terug, zodat de kleur per plek stabiel blijft.
    """
    per_atleet = _eindtijden_per_atleet()
    op_id = {a["id"]: a for a in ds.laad_atleten()}
    uit = []
    gezien = set()
    for i in ids:
        a = op_id.get(i)
        if a is None or i in gezien:
            uit.append(None)
            continue
        gezien.add(i)
        punten = per_atleet.get(_sleutel(a["naam"], a["voornaam"]), [])
        uit.append({
            "id": a["id"],
            "naam": a["naam"],
            "voornaam": a["voornaam"],
            "punten": [{"d": d, "s": s, "t": t} for d, s, t in punten],
        })
    return {"reeksen": uit}


def suggesties():
    """Lijst {naam, voornaam} van alle bekende atleten, voor de invoerformulieren."""
    return sorted(
        ({"naam": a["naam"], "voornaam": a["voornaam"]} for a in ds.laad_atleten()),
        key=lambda r: (r["naam"].lower(), r["voornaam"].lower()),
    )
