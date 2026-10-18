"""
Ranking- en PR-logica.

Regels (uit de schets):
- Rankings zijn gebaseerd op de eindtijd, en apart voor mannen en vrouwen.
- Wie maar 1 van de 2 rondes liep, komt onderaan de ranking te staan,
  onderling gerankt op basis van die ene rondetijd.
- Een PR ("Persoonlijk Record") wordt per atleet en per meetpunt
  (Ronde 1 / Ronde 2 / Eindtijd) bijgehouden: de laagste tijd tot en met
  een bepaalde oefencross.
"""
from . import datastore as ds


def _k(naam, voornaam):
    """Genormaliseerde sleutel: 'janssens ' en 'Janssens' zijn dezelfde persoon."""
    return (ds._norm_naam(naam), ds._norm_naam(voornaam))


def _atleet_lookup(atleten):
    return {_k(a["naam"], a["voornaam"]): a for a in atleten}


def _geslacht_van(lookup, naam, voornaam):
    a = lookup.get(_k(naam, voornaam))
    return a["geslacht"] if a else None


# ---------------------------------------------------------------------------
# Home: All-Time Ranking
# ---------------------------------------------------------------------------

def all_time_ranking(vanaf_datum=None, top=5):
    """
    {'vrouwen': [...], 'mannen': [...]}: per geslacht de top-N beste eindtijden
    (1 rij per atleet: diens snelste eindtijd, met de tussentijd en datum van
    dezelfde loop), gerekend over alle oefencrossen VANAF vanaf_datum (ISO) tot nu.
    Atleten die enkel 1 ronde liepen komen onderaan, gerankt op die rondetijd.
    top=None geeft de VOLLEDIGE ranking terug (voor de pagina "Volledige Ranking").
    """
    lookup = _atleet_lookup(ds.laad_atleten())
    events = ds.laad_alle_events()
    if vanaf_datum:
        events = [e for e in events if e["datum"] >= vanaf_datum]

    volledig = {}   # sleutel -> dict(_tijd, tussen, datum, naam, voornaam)
    enkel = {}

    for e in events:
        for d in e.get("deelnames", []):
            sleutel = _k(d["naam"], d["voornaam"])
            r1 = ds.parse_tijd(d.get("ronde1"))
            r2 = ds.parse_tijd(d.get("ronde2"))
            eind = ds.parse_tijd(d.get("eindtijd"))
            basis = {"naam": d["naam"], "voornaam": d["voornaam"], "datum": e["datum"]}

            if eind is not None:
                if sleutel not in volledig or eind < volledig[sleutel]["_tijd"]:
                    volledig[sleutel] = dict(basis, _tijd=eind, tussen=ds.format_tijd(r1), eind=ds.format_tijd(eind))
            else:
                een_ronde = r1 if r1 is not None else r2
                if een_ronde is not None:
                    if sleutel not in enkel or een_ronde < enkel[sleutel]["_tijd"]:
                        enkel[sleutel] = dict(basis, _tijd=een_ronde, tussen=ds.format_tijd(een_ronde), eind=None)

    # wie ooit een volledige loop had, staat enkel in de "volledig"-lijst
    for sleutel in list(enkel):
        if sleutel in volledig:
            del enkel[sleutel]

    def bouw(bron, is_volledig):
        rijen = []
        for sleutel, r in bron.items():
            rijen.append(dict(r, geslacht=_geslacht_van(lookup, r["naam"], r["voornaam"]), volledig=is_volledig))
        rijen.sort(key=lambda r: r["_tijd"])
        return rijen

    v_rijen, e_rijen = bouw(volledig, True), bouw(enkel, False)
    resultaat = {}
    for label, code in (("vrouwen", "v"), ("mannen", "m")):
        rijen = [r for r in v_rijen if r["geslacht"] == code] + [r for r in e_rijen if r["geslacht"] == code]
        for i, r in enumerate(rijen, start=1):
            r["rank"] = i
        resultaat[label] = rijen if top is None else rijen[:top]
    return resultaat


# ---------------------------------------------------------------------------
# PR-stand
# ---------------------------------------------------------------------------

def pr_stand(events, tot_index):
    """
    Beste tijd per (atleet, veld) over events[0:tot_index], samen met de datum
    waarop die gelopen werd: {(naam, voornaam, veld): (timedelta, datum)}.
    Bij gelijke tijden geldt de eerst gelopen datum.
    """
    pr = {}
    for e in events[:tot_index]:
        for d in e.get("deelnames", []):
            for veld in ("ronde1", "ronde2", "eindtijd"):
                t = ds.parse_tijd(d.get(veld))
                if t is None:
                    continue
                key = _k(d["naam"], d["voornaam"]) + (veld,)
                if key not in pr or t < pr[key][0]:
                    pr[key] = (t, e["datum"])
    return pr


def _sorteer_groep(rijen):
    """Volledige loopsters/lopers (eindtijd) eerst op eindtijd; wie 1 ronde liep onderaan."""
    volledig = sorted([r for r in rijen if r["volledig"]], key=lambda r: r["_sleutel"])
    enkel = sorted([r for r in rijen if not r["volledig"]], key=lambda r: r["_sleutel"])
    for i, r in enumerate(volledig + enkel, start=1):
        r["rank"] = i
    return volledig + enkel


# ---------------------------------------------------------------------------
# Print Oefencross
# ---------------------------------------------------------------------------

def event_ranking_met_pr(datum_str):
    """
    Alles wat het printsjabloon "Print Oefencross" nodig heeft:
    - nummer: "#ste oefencross" (de hoeveelste oefencross in de database)
    - per deelnemer: ranking, "#ste deelname", tijden, PR-tijden (tot en met deze
      oefencross), de datum waarop de eind-PR gelopen werd, en of er deze dag
      een nieuw PR gelopen werd (-> kroontje achter de voornaam).
    """
    events = ds.laad_alle_events()
    idx = next((i for i, e in enumerate(events) if e["datum"] == datum_str), None)
    if idx is None:
        return None
    event = events[idx]
    voor = pr_stand(events, idx)        # PR-stand vóór deze oefencross
    tot_en_met = pr_stand(events, idx + 1)   # PR-stand na deze oefencross
    lookup = _atleet_lookup(ds.laad_atleten())

    # aantal deelnames per atleet tot en met deze oefencross
    aantal = {}
    for e in events[: idx + 1]:
        for sleutel in {_k(d["naam"], d["voornaam"]) for d in e.get("deelnames", [])}:
            aantal[sleutel] = aantal.get(sleutel, 0) + 1

    def nieuw_pr(sleutel, veld, tijd):
        if tijd is None:
            return False
        eerder = voor.get(sleutel + (veld,))
        return eerder is None or tijd < eerder[0]

    def pr_tijd(sleutel, veld):
        stand = tot_en_met.get(sleutel + (veld,))
        return ds.format_tijd(stand[0]) if stand else None

    rijen = []
    for d in event.get("deelnames", []):
        sleutel = _k(d["naam"], d["voornaam"])
        r1 = ds.parse_tijd(d.get("ronde1"))
        r2 = ds.parse_tijd(d.get("ronde2"))
        eind = ds.parse_tijd(d.get("eindtijd"))
        eind_stand = tot_en_met.get(sleutel + ("eindtijd",))
        flags = (nieuw_pr(sleutel, "ronde1", r1), nieuw_pr(sleutel, "ronde2", r2), nieuw_pr(sleutel, "eindtijd", eind))
        rijen.append({
            "naam": d["naam"], "voornaam": d["voornaam"],
            "geslacht": _geslacht_van(lookup, d["naam"], d["voornaam"]),
            "deelname": aantal.get(sleutel, 1),
            "ronde1": ds.format_tijd(r1), "r1_nieuw_pr": flags[0], "r1_pr": pr_tijd(sleutel, "ronde1"),
            "ronde2": ds.format_tijd(r2), "r2_nieuw_pr": flags[1], "r2_pr": pr_tijd(sleutel, "ronde2"),
            "eindtijd": ds.format_tijd(eind), "eind_nieuw_pr": flags[2],
            "eind_pr": ds.format_tijd(eind_stand[0]) if eind_stand else None,
            "eind_pr_datum": eind_stand[1] if eind_stand else None,
            "kroon": any(flags),
            "volledig": eind is not None,
            "_sleutel": eind if eind is not None else (r1 if r1 is not None else r2),
        })

    resultaat = {}
    for label, code in (("vrouwen", "v"), ("mannen", "m")):
        resultaat[label] = _sorteer_groep([r for r in rijen if r["geslacht"] == code])
    # Geslacht nog niet gekend: nooit stilzwijgend uit de uitslag laten verdwijnen
    resultaat["onbekend"] = _sorteer_groep([r for r in rijen if r["geslacht"] not in ("v", "m")])

    return {
        "nummer": event.get("volgnummer") or (idx + 1),
        "datum": event["datum"],
        "grote_prijs": event.get("grote_prijs"),
        "seizoen": ds.bepaal_seizoen(event["datum"]),
        "rankings": resultaat,
    }


# ---------------------------------------------------------------------------
# Print Seizoensoverzicht
# ---------------------------------------------------------------------------

def season_overzicht(seizoen_str):
    """
    Maandgrid: per atleet (mannen/vrouwen apart), voor elke maand van het seizoen
    de tussentijd (ronde 1) en eindtijd, met per cel een markering als dat op dat
    moment een nieuw persoonlijk record (PR) was.
    """
    alle_events = ds.laad_alle_events()
    lookup = _atleet_lookup(ds.laad_atleten())

    idxs = [i for i, e in enumerate(alle_events) if ds.bepaal_seizoen(e["datum"]) == seizoen_str]
    if not idxs:
        return None

    per_atleet = {}
    for idx in idxs:
        event = alle_events[idx]
        maand_code = ds.maand_code_van_datum(event["datum"])
        voor = pr_stand(alle_events, idx)

        for d in event.get("deelnames", []):
            sleutel = _k(d["naam"], d["voornaam"])
            r1 = ds.parse_tijd(d.get("ronde1"))
            eind = ds.parse_tijd(d.get("eindtijd"))

            def is_pr(veld, tijd):
                if tijd is None:
                    return False
                eerder = voor.get(sleutel + (veld,))
                return eerder is None or tijd < eerder[0]

            rij = per_atleet.setdefault(sleutel, {"naam": d["naam"], "voornaam": d["voornaam"], "maanden": {}})
            rij["maanden"][maand_code] = {
                "tussen": ds.format_tijd(r1), "tussen_pr": is_pr("ronde1", r1),
                "eind": ds.format_tijd(eind), "eind_pr": is_pr("eindtijd", eind),
                "datum": event["datum"],
            }

    rijen = [dict(r, geslacht=_geslacht_van(lookup, r["naam"], r["voornaam"])) for r in per_atleet.values()]

    def alfabetisch(lijst):
        return sorted(lijst, key=lambda r: (r["naam"].lower(), r["voornaam"].lower()))

    return {
        "seizoen": seizoen_str,
        "maanden": ds.MAAND_VOLGORDE,
        "rankings": {
            "vrouwen": alfabetisch([r for r in rijen if r["geslacht"] == "v"]),
            "mannen": alfabetisch([r for r in rijen if r["geslacht"] == "m"]),
            "onbekend": alfabetisch([r for r in rijen if r["geslacht"] not in ("v", "m")]),
        },
    }
