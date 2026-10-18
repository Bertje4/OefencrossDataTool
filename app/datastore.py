"""
Data-laag voor de Oefencross-tool.

Alle "echte" data leeft als leesbare JSON-bestanden onder DATA_DIR (de map
"DataBase"), volledig los van de applicatiecode (de map "Config"). Zo kan je
enkel DataBase kopiëren/back-uppen, en is de data altijd leesbaar met een
teksteditor, ook als de tool zelf stuk is.

Bestandsstructuur van DataBase:
    atleten.json                  -> centrale atletenlijst
    oefencrossen/<datum>.json     -> 1 bestand per oefencross (datum = YYYY-MM-DD)
    verslagen/<...>               -> bijgevoegde bestanden (PDF/Word/...)
"""
import json
import os
import re
import uuid
from datetime import datetime, date, timedelta

# BASE_DIR = de map met de code (bij jou: .../OefencrossTool/Config)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# De data staat bewust NIET in de codemap, maar in een aparte, gelijkwaardige map.
# - In Docker: OEFENCROSS_DATA_DIR=/data (gemount vanaf .../OefencrossTool/DataBase)
# - Zonder Docker: standaard de zustermap "DataBase" naast de codemap, dus
#   .../OefencrossTool/Config  ->  .../OefencrossTool/DataBase
DATA_DIR = os.environ.get("OEFENCROSS_DATA_DIR") or os.path.join(
    os.path.dirname(BASE_DIR), "DataBase"
)
ATLETEN_FILE = os.path.join(DATA_DIR, "atleten.json")
OEFENCROSS_DIR = os.path.join(DATA_DIR, "oefencrossen")
VERSLAGEN_DIR = os.path.join(DATA_DIR, "verslagen")
# Verwijderde oefencrossen/atleten worden niet definitief gewist maar hierheen
# verplaatst, zodat een vergissing altijd te herstellen is.
VERWIJDERD_DIR = os.path.join(DATA_DIR, "verwijderd")

# Tijden zijn altijd korter dan een uur: "mm:ss" of, met honderdsten, "mm:ss:hh"
# (ook "mm:ss.hh" wordt aanvaard). Honderdsten moeten steeds 2 cijfers zijn.
TIME_RE = re.compile(r"^(\d{1,3}):([0-5]\d)(?:[:.](\d{2}))?$")


def ensure_dirs():
    os.makedirs(OEFENCROSS_DIR, exist_ok=True)
    os.makedirs(VERSLAGEN_DIR, exist_ok=True)
    if not os.path.exists(ATLETEN_FILE):
        _write_json(ATLETEN_FILE, [])


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return default
        return json.loads(content)


def _write_json(path, data):
    # Schrijf eerst naar een tijdelijk bestand en hernoem dan (atomisch),
    # zodat een crash tijdens het schrijven nooit een halfgeschreven/
    # corrupt bestand achterlaat.
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Tijd-helpers
# ---------------------------------------------------------------------------

def parse_tijd(waarde):
    """
    'mm:ss' of 'mm:ss:hh' (hh = honderdsten) -> timedelta. None/lege string -> None.
    Voorbeelden: '12:34' = 12 min 34 s, '12:34:56' = 12 min 34 s en 56 honderdsten.
    """
    if waarde is None:
        return None
    waarde = str(waarde).strip()
    if waarde == "":
        return None
    m = TIME_RE.match(waarde)
    if not m:
        raise ValueError(
            f"Ongeldig tijdformaat: '{waarde}' (verwacht mm:ss of mm:ss:hh, bv. 12:34 of 12:34:56)"
        )
    minuten, seconden, honderdsten = m.groups()
    return timedelta(
        minutes=int(minuten), seconds=int(seconden),
        milliseconds=int(honderdsten or 0) * 10,
    )


def format_tijd(td):
    """
    timedelta -> 'mm:ss' (of 'mm:ss:hh' als er honderdsten zijn).
    Alles wordt in gehele honderdsten gerekend om afrondingsfoutjes te vermijden.
    """
    if td is None:
        return None
    honderdsten_totaal = td // timedelta(milliseconds=10)
    if honderdsten_totaal < 0:
        raise ValueError("Negatieve tijd is ongeldig (is de eindtijd korter dan Ronde 1?)")
    seconden_totaal, hh = divmod(honderdsten_totaal, 100)
    mm, ss = divmod(seconden_totaal, 60)
    if hh:
        return f"{mm:02d}:{ss:02d}:{hh:02d}"
    return f"{mm:02d}:{ss:02d}"


def bereken_ontbrekende_tijd(ronde1, ronde2, eindtijd):
    """
    Vult de ontbrekende van de drie tijden aan op basis van de andere twee.
    Elke waarde is een string ('mm:ss' of 'mm:ss:hh') of None/"".
    Geeft (ronde1, ronde2, eindtijd) terug als strings (of None waar niet gekend/berekenbaar).
    """
    r1 = parse_tijd(ronde1)
    r2 = parse_tijd(ronde2)
    eind = parse_tijd(eindtijd)

    if r1 is not None and r2 is not None and eind is None:
        eind = r1 + r2
    elif r1 is not None and eind is not None and r2 is None:
        r2 = eind - r1
    elif r2 is not None and eind is not None and r1 is None:
        r1 = eind - r2
    # Als maar 1 van de 3 gekend is (of geen enkele), kan niets berekend worden;
    # dat is toegestaan (bv. iemand die maar 1 ronde liep).

    return format_tijd(r1), format_tijd(r2), format_tijd(eind)


def bepaal_seizoen(datum_str):
    """Seizoen loopt november t/m oktober. '2026-11-01' -> '2026-2027'."""
    d = datetime.strptime(datum_str, "%Y-%m-%d").date()
    if d.month >= 11:
        return f"{d.year}-{d.year + 1}"
    return f"{d.year - 1}-{d.year}"


# Volgorde van de maanden zoals in het Seizoensoverzicht (november t/m oktober)
MAAND_VOLGORDE = [
    ("nov", "November", 11), ("dec", "December", 12), ("jan", "Januari", 1),
    ("feb", "Februari", 2), ("mrt", "Maart", 3), ("apr", "April", 4),
    ("mei", "Mei", 5), ("jun", "Juni", 6), ("jul", "Juli", 7),
    ("aug", "Augustus", 8), ("sept", "September", 9), ("okt", "Oktober", 10),
]

# De eerste maand van het seizoen (nu: november). Vanaf deze maandnummer (of
# hoger) hoort een datum bij het STARTJAAR van het seizoen; alle maanden
# daarna (januari-oktober) horen bij startjaar + 1.
_START_MAAND_NR = MAAND_VOLGORDE[0][2]


def maand_code_van_datum(datum_str):
    maand_nr = datetime.strptime(datum_str, "%Y-%m-%d").month
    for code, _naam, nr in MAAND_VOLGORDE:
        if nr == maand_nr:
            return code
    return None


def seizoen_start_jaar(seizoen_str):
    return int(seizoen_str.split("-")[0])


def eerste_zondag(seizoen_str, maand_code):
    """
    Standaarddatum van de oefencross van een maand binnen een seizoen:
    de eerste zondag van die maand (november-december in het startjaar,
    januari-oktober in het jaar erna).
    """
    nr = dict((c, n) for c, _l, n in MAAND_VOLGORDE)[maand_code]
    start = seizoen_start_jaar(seizoen_str)
    jaar = start if nr >= _START_MAAND_NR else start + 1
    eerste = date(jaar, nr, 1)
    zondag = eerste + timedelta(days=(6 - eerste.weekday()) % 7)  # maandag=0 ... zondag=6
    return zondag.strftime("%Y-%m-%d")


def datum_voor_maand(seizoen_str, maand_code, dag_str):
    """
    Controleert dat een (eventueel overschreven) datum echt in de juiste maand
    EN het juiste jaar van het seizoen valt, en geeft ze terug als 'YYYY-MM-DD'.
    """
    try:
        d = datetime.strptime(dag_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"'{dag_str}' is geen geldige datum.")
    nr = dict((c, n) for c, _l, n in MAAND_VOLGORDE)[maand_code]
    start = seizoen_start_jaar(seizoen_str)
    verwacht_jaar = start if nr >= _START_MAAND_NR else start + 1
    if d.month != nr or d.year != verwacht_jaar:
        maandnaam = dict((c, l) for c, l, _n in MAAND_VOLGORDE)[maand_code]
        raise ValueError(
            f"De datum {dag_str} valt niet in {maandnaam} {verwacht_jaar} "
            f"(seizoen {seizoen_str})."
        )
    return d.strftime("%Y-%m-%d")


def lijst_seizoenen():
    """Alle seizoenen waarvoor minstens 1 oefencross bestaat, nieuwste eerst."""
    events = laad_alle_events()
    seizoenen = sorted({bepaal_seizoen(e["datum"]) for e in events}, reverse=True)
    return seizoenen


def merge_deelnames(bestaande_deelnames, nieuwe_deelnames):
    """
    Voegt nieuwe_deelnames toe aan bestaande_deelnames: een match op naam+voornaam
    wordt overschreven met de nieuwe waarden, een nieuwe naam wordt toegevoegd,
    en alles wat niet vermeld is in nieuwe_deelnames blijft ongewijzigd staan.
    Zo verlies je nooit resultaten die al rechtstreeks (individueel) waren ingevoerd.
    """
    resultaat = {(_norm_naam(d["naam"]), _norm_naam(d["voornaam"])): dict(d) for d in bestaande_deelnames}
    for d in nieuwe_deelnames:
        resultaat[(_norm_naam(d["naam"]), _norm_naam(d["voornaam"]))] = dict(d)
    return list(resultaat.values())


# ---------------------------------------------------------------------------
# Atleten
# ---------------------------------------------------------------------------

def _norm_naam(s):
    return re.sub(r"\s+", " ", s.strip()).lower()


def laad_atleten():
    return _read_json(ATLETEN_FILE, [])


def bewaar_atleten(atleten):
    _write_json(ATLETEN_FILE, atleten)


def vind_atleet(atleten, naam, voornaam):
    """Exacte match (hoofdletterongevoelig) op naam+voornaam. Geeft dict of None."""
    n, v = _norm_naam(naam), _norm_naam(voornaam)
    for a in atleten:
        if _norm_naam(a["naam"]) == n and _norm_naam(a["voornaam"]) == v:
            return a
    return None


def zoek_gelijkaardige_atleten(atleten, naam, voornaam, limiet=5):
    """
    Fuzzy-suggesties (typfout-detectie) op basis van naam+voornaam,
    voor het geval iemand per ongeluk een variant van een bestaande naam intikt.
    """
    import difflib
    doel = _norm_naam(f"{naam} {voornaam}")
    kandidaten = {
        _norm_naam(f"{a['naam']} {a['voornaam']}"): a for a in atleten
    }
    gelijkaardig = difflib.get_close_matches(doel, kandidaten.keys(), n=limiet, cutoff=0.72)
    return [kandidaten[k] for k in gelijkaardig]


def voeg_atleet_toe_indien_nieuw(atleten, naam, voornaam):
    """
    Geeft (atleet, is_nieuw, is_onvolledig) terug.
    Maakt een nieuwe atleet aan (zonder geslacht/geboortedatum) als naam+voornaam
    nog niet exact bestaat. Wijzigt 'atleten' in-place; caller is verantwoordelijk
    voor het bewaren.
    """
    bestaand = vind_atleet(atleten, naam, voornaam)
    if bestaand is not None:
        onvolledig = not bestaand.get("geslacht") or not bestaand.get("geboortedatum")
        return bestaand, False, onvolledig

    nieuw = {
        "id": str(uuid.uuid4()),
        "naam": naam.strip(),
        "voornaam": voornaam.strip(),
        "geslacht": None,
        "geboortedatum": None,
    }
    atleten.append(nieuw)
    return nieuw, True, True


def vul_atleet_aan(atleten, atleet_id, geslacht, geboortedatum):
    for a in atleten:
        if a["id"] == atleet_id:
            if geslacht:
                a["geslacht"] = geslacht
            if geboortedatum:
                a["geboortedatum"] = geboortedatum
            return a
    return None


# ---------------------------------------------------------------------------
# Oefencrossen
# ---------------------------------------------------------------------------

def _event_pad(datum_str):
    return os.path.join(OEFENCROSS_DIR, f"{datum_str}.json")


def event_bestaat(datum_str):
    return os.path.exists(_event_pad(datum_str))


def laad_event(datum_str):
    return _read_json(_event_pad(datum_str), None)


def bewaar_event(event):
    """event moet minstens 'datum' (YYYY-MM-DD) bevatten."""
    _write_json(_event_pad(event["datum"]), event)


def laad_alle_events():
    """Alle oefencrossen, gesorteerd van oud naar nieuw."""
    events = []
    if not os.path.isdir(OEFENCROSS_DIR):
        return events
    for naam in sorted(os.listdir(OEFENCROSS_DIR)):
        if naam.endswith(".json"):
            events.append(_read_json(os.path.join(OEFENCROSS_DIR, naam), None))
    events = [e for e in events if e]
    events.sort(key=lambda e: e["datum"])
    return events


def lijst_datums():
    """Voor de dropdown '<drop-down met alle oefencross data>' - nieuwste eerst."""
    events = laad_alle_events()
    return sorted((e["datum"] for e in events), reverse=True)


# ---------------------------------------------------------------------------
# Datums (weergave: dd/mm/jjjj, opslag: jjjj-mm-dd) en Nederlandse rangtelwoorden
# ---------------------------------------------------------------------------

def datum_nl(iso_str):
    """'2026-09-06' -> '06/09/2026'. Lege/ongeldige waarde -> ''."""
    if not iso_str:
        return ""
    try:
        return datetime.strptime(iso_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(iso_str)


def parse_datum_invoer(tekst):
    """Aanvaardt 'dd/mm/jjjj' (of dd-mm-jjjj / jjjj-mm-dd) en geeft 'jjjj-mm-dd'."""
    tekst = (tekst or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(tekst, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"'{tekst}' is geen geldige datum (verwacht dd/mm/jjjj).")


def ordinaal(n):
    """1 -> '1ste', 2 -> '2de', 8 -> '8ste', 12 -> '12de', 20 -> '20ste', 482 -> '482ste'."""
    n = int(n)
    return f"{n}{'ste' if n == 1 or n == 8 or n >= 20 else 'de'}"


# ---------------------------------------------------------------------------
# Verwijderen (met kopie in DataBase/verwijderd)
# ---------------------------------------------------------------------------

def verwijder_event(datum_str):
    """Verplaatst het oefencross-bestand naar verwijderd/oefencrossen/. True als het bestond."""
    pad = _event_pad(datum_str)
    if not os.path.exists(pad):
        return False
    doel_dir = os.path.join(VERWIJDERD_DIR, "oefencrossen")
    os.makedirs(doel_dir, exist_ok=True)
    stempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    os.replace(pad, os.path.join(doel_dir, f"{datum_str}__verwijderd-{stempel}.json"))
    return True


def verwijder_atleet(atleten, atleet_id):
    """
    Haalt enkel de atleet uit de atletenlijst (in-place; caller bewaart).
    De oefencross-resultaten worden NIET aangeraakt. Een kopie van het
    atleetrecord komt in verwijderd/atleten.json. Geeft het record terug (of None).
    """
    for i, a in enumerate(atleten):
        if a["id"] == atleet_id:
            weg = atleten.pop(i)
            os.makedirs(VERWIJDERD_DIR, exist_ok=True)
            log_pad = os.path.join(VERWIJDERD_DIR, "atleten.json")
            log = _read_json(log_pad, [])
            log.append(dict(weg, verwijderd_op=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            _write_json(log_pad, log)
            return weg
    return None
