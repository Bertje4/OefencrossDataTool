import os
import secrets
import uuid
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, g, jsonify
from werkzeug.utils import secure_filename

from . import datastore as ds
from . import ranking
from . import pdf as pdf_hulp
from . import statistiek


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-sleutel-verander-dit-in-productie")
    ds.ensure_dirs()

    # -------------------------------------------------------------------
    # Login (1 gedeeld wachtwoord voor alle leden)
    # -------------------------------------------------------------------
    app.permanent_session_lifetime = timedelta(days=180)
    # SameSite=None + Secure is nodig omdat de tool via een IFRAME op WordPress
    # staat (een andere domeinnaam dan de WordPress-site zelf): zonder deze
    # instelling weigeren moderne browsers de sessie-cookie in dat iframe, en
    # zou je bij elke pagina opnieuw moeten inloggen. Vereist wel HTTPS
    # (via Proxymanager); voor lokaal testen over http kan je dit uitzetten
    # met de omgevingsvariabele OEFENCROSS_SECURE_COOKIE=0.
    app.config["SESSION_COOKIE_SAMESITE"] = "None"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("OEFENCROSS_SECURE_COOKIE", "1") != "0"

    APP_WACHTWOORD = os.environ.get("APP_WACHTWOORD", "verander-dit-wachtwoord")
    if APP_WACHTWOORD == "verander-dit-wachtwoord":
        app.logger.warning(
            "LET OP: APP_WACHTWOORD staat nog op de standaardwaarde. "
            "Zet een eigen omgevingsvariabele APP_WACHTWOORD."
        )

    @app.before_request
    def vereis_login():
        # Enkel routes die data toevoegen/wijzigen/verwijderen vragen een login.
        # Resultaten bekijken/downloaden (Home, Volledige Ranking, printen, PDF's,
        # bijgevoegde verslagen) blijft voor iedereen vrij toegankelijk.
        beveiligd = {
            "oefencross_nieuw", "oefencross_wijzigen", "oefencross_verwijderen",
            "seizoensoverzicht_nieuw",
            "atleten_overzicht", "atleten_aanvullen", "atleten_aanvullen_overslaan",
            "atleet_verwijderen",
        }
        if request.endpoint in beveiligd and not session.get("ingelogd"):
            return redirect(url_for("login", volgende=request.path))

    # Schrijfslot: elke POST (invoegen, wijzigen, verwijderen, aanvullen) wordt
    # van begin tot einde afgehandeld terwijl we het slot vasthouden, zodat twee
    # gelijktijdige invoeren elkaar nooit overschrijven.
    @app.before_request
    def neem_schrijfslot():
        if request.method == "POST":
            g._slot = ds.schrijflock()
            g._slot.__enter__()

    @app.teardown_request
    def geef_schrijfslot_vrij(_exc):
        slot = g.pop("_slot", None)
        if slot is not None:
            slot.__exit__(None, None, None)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        fout = None
        volgende = request.values.get("volgende") or url_for("home")
        if request.method == "POST":
            ingevoerd = request.form.get("wachtwoord", "")
            if secrets.compare_digest(ingevoerd, APP_WACHTWOORD):
                session.permanent = True
                session["ingelogd"] = True
                return redirect(request.form.get("volgende") or url_for("home"))
            fout = "Onjuist wachtwoord."
        return render_template("login.html", fout=fout, volgende=volgende)

    @app.route("/uitloggen", methods=["POST"])
    def uitloggen():
        session.clear()
        return redirect(url_for("login"))

    # Alle data worden getoond als dd/mm/jjjj; "1ste, 2de, 8ste, 12de, 482ste ..."
    app.jinja_env.filters["datum_nl"] = ds.datum_nl
    app.jinja_env.filters["ordinaal"] = ds.ordinaal

    # -------------------------------------------------------------------
    # Home / All-Time Ranking
    # -------------------------------------------------------------------
    @app.route("/")
    def home():
        vanaf_tekst = (request.args.get("vanaf") or "").strip()
        vanaf_iso = None
        if vanaf_tekst:
            try:
                vanaf_iso = ds.parse_datum_invoer(vanaf_tekst)
            except ValueError as e:
                flash(f"Oei, er ging iets mis: {e}", "fout")
        rankings = ranking.all_time_ranking(vanaf_datum=vanaf_iso, top=5)
        return render_template(
            "home.html",
            rankings=rankings,
            datums=ds.lijst_datums(),
            vanaf_tekst=vanaf_tekst if vanaf_iso else "",
            seizoenen=ds.lijst_seizoenen(),
        )

    # -------------------------------------------------------------------
    # Volledige Ranking (zelfde als de top-5 op Home, maar dan alles)
    # -------------------------------------------------------------------
    @app.route("/ranking")
    def volledige_ranking():
        vanaf_tekst = (request.args.get("vanaf") or "").strip()
        vanaf_iso = None
        if vanaf_tekst:
            try:
                vanaf_iso = ds.parse_datum_invoer(vanaf_tekst)
            except ValueError as e:
                flash(f"Oei, er ging iets mis: {e}", "fout")
        rankings = ranking.all_time_ranking(vanaf_datum=vanaf_iso, top=None)
        return render_template(
            "ranking_volledig.html",
            rankings=rankings,
            datums=ds.lijst_datums(),
            vanaf_tekst=vanaf_tekst if vanaf_iso else "",
        )

    # -------------------------------------------------------------------
    # Oefencross invoegen (nieuw) / wijzigen (bestaand) - zelfde formulier
    # -------------------------------------------------------------------
    @app.route("/oefencross/nieuw", methods=["GET", "POST"])
    def oefencross_nieuw():
        return _oefencross_formulier(datum_str=None)

    @app.route("/oefencross/<datum_str>/wijzigen", methods=["GET", "POST"])
    def oefencross_wijzigen(datum_str):
        return _oefencross_formulier(datum_str=datum_str)

    def _oefencross_formulier(datum_str):
        bestaand_event = ds.laad_event(datum_str) if datum_str else None

        if request.method == "GET":
            return render_template(
                "oefencross_formulier.html",
                event=bestaand_event,
                datums=ds.lijst_datums(),
                bewerken=datum_str is not None,
                atleten_suggesties=statistiek.suggesties(),
            )

        # --- POST: formulier verwerken ---
        form_datum = request.form.get("datum", "").strip()
        if not form_datum:
            flash("Oei, er ging iets mis: datum is verplicht.", "fout")
            return redirect(request.url)

        grote_prijs = request.form.get("grote_prijs", "").strip() or None
        opmerkingen = request.form.get("opmerkingen", "").strip()

        namen = request.form.getlist("naam[]")
        voornamen = request.form.getlist("voornaam[]")
        ronde1s = request.form.getlist("ronde1[]")
        ronde2s = request.form.getlist("ronde2[]")
        eindtijden = request.form.getlist("eindtijd[]")

        atleten = ds.laad_atleten()
        deelnames = []
        onvolledige_atleten = []

        for naam, voornaam, r1, r2, eind in zip(namen, voornamen, ronde1s, ronde2s, eindtijden):
            naam, voornaam = naam.strip(), voornaam.strip()
            if not naam or not voornaam:
                continue
            try:
                r1c, r2c, eindc = ds.bereken_ontbrekende_tijd(r1, r2, eind)
            except ValueError as e:
                flash(f"Oei, er ging iets mis bij {voornaam} {naam}: {e}", "fout")
                return redirect(request.url)

            atleet, is_nieuw, onvolledig = ds.voeg_atleet_toe_indien_nieuw(atleten, naam, voornaam)
            if onvolledig:
                onvolledige_atleten.append(atleet)
            # Gebruik steeds de spelling uit de atletenlijst ("janssens" -> "Janssens")
            naam, voornaam = atleet["naam"], atleet["voornaam"]

            deelnames.append({
                "naam": naam, "voornaam": voornaam,
                "ronde1": r1c, "ronde2": r2c, "eindtijd": eindc,
            })

        if not deelnames:
            flash("Oei, er ging iets mis: geen enkele deelnemer met naam en voornaam ingevuld.", "fout")
            return redirect(request.url)

        # Bestaand verslag-bestand behouden tenzij een nieuw bestand is gekozen
        verslag_pad = bestaand_event.get("verslag_bestand") if bestaand_event else None
        upload = request.files.get("verslag")
        if upload and upload.filename:
            veilige_naam = f"{form_datum}_{uuid.uuid4().hex[:8]}_{secure_filename(upload.filename) or 'verslag'}"
            upload.save(os.path.join(ds.VERSLAGEN_DIR, veilige_naam))
            verslag_pad = veilige_naam

        event = {
            "datum": form_datum,
            "seizoen": ds.bepaal_seizoen(form_datum),
            "volgnummer": bestaand_event.get("volgnummer") if bestaand_event else None,
            "grote_prijs": grote_prijs,
            "opmerkingen": opmerkingen,
            "verslag_bestand": verslag_pad,
            "deelnames": deelnames,
        }
        ds.bewaar_event(event)
        ds.bewaar_atleten(atleten)

        if onvolledige_atleten:
            # popup 3: vraag ontbrekende gegevens aan van nieuwe/onvolledige atleten
            session["onvolledige_ids"] = [a["id"] for a in onvolledige_atleten]
            session["na_aanvullen"] = {"soort": "event", "waarde": form_datum}
            return redirect(url_for("atleten_aanvullen"))

        flash("Succesvol opgeslagen.", "succes")
        return redirect(url_for("oefencross_print", datum_str=form_datum))

    # -------------------------------------------------------------------
    # Seizoensoverzicht invoegen (bulk-invoer over een heel seizoen)
    # -------------------------------------------------------------------
    @app.route("/seizoensoverzicht/nieuw", methods=["GET", "POST"])
    def seizoensoverzicht_nieuw():
        if request.method == "GET":
            return render_template("seizoensoverzicht_formulier.html", maanden=ds.MAAND_VOLGORDE, atleten_suggesties=statistiek.suggesties())

        startjaar = request.form.get("startjaar", "").strip()
        if not startjaar.isdigit():
            flash("Oei, er ging iets mis: geef een geldig startjaar op (bv. 2026).", "fout")
            return redirect(request.url)
        seizoen_str = f"{startjaar}-{int(startjaar) + 1}"

        # Optioneel: het "officiële" volgnummer van de eerste oefencross van dit
        # seizoen (de eerste maand in ds.MAAND_VOLGORDE). Van daaruit telt de
        # tool voor elke volgende maand automatisch verder (+1 per maand), zodat
        # "#ste oefencross" op de printpagina klopt met je papieren telling, ook
        # als (nog) niet alle 40 jaar in de database staan.
        start_volgnummer_tekst = request.form.get("start_volgnummer", "").strip()
        start_volgnummer = None
        if start_volgnummer_tekst:
            if not start_volgnummer_tekst.isdigit():
                flash("Oei, er ging iets mis: het volgnummer moet een getal zijn.", "fout")
                return redirect(request.url)
            start_volgnummer = int(start_volgnummer_tekst)
        volgnummer_per_maand = {
            code: (start_volgnummer + i if start_volgnummer is not None else None)
            for i, (code, _label, _nr) in enumerate(ds.MAAND_VOLGORDE)
        }

        namen = request.form.getlist("naam[]")
        voornamen = request.form.getlist("voornaam[]")

        # Per maand: 1 datum (geldt voor alle deelnemers van die maand).
        # Standaard de eerste zondag van de maand; het formulier stuurt een
        # andere datum mee als de gebruiker de "override" gebruikte.
        maand_datums = {}
        for code, _label, _nr in ds.MAAND_VOLGORDE:
            waarde = request.form.get(f"datum_{code}", "").strip()
            if not waarde:
                waarde = ds.eerste_zondag(seizoen_str, code)
            try:
                maand_datums[code] = ds.datum_voor_maand(seizoen_str, code, waarde)
            except ValueError as e:
                flash(f"Oei, er ging iets mis: {e}", "fout")
                return redirect(request.url)

        atleten = ds.laad_atleten()
        onvolledige_atleten = []
        # per maand_code: lijst van nieuwe/bijgewerkte deelnames voor die maand
        deelnames_per_maand = {code: [] for code in maand_datums}

        for i, (naam, voornaam) in enumerate(zip(namen, voornamen)):
            naam, voornaam = naam.strip(), voornaam.strip()
            if not naam or not voornaam:
                continue

            atleet_heeft_data = False
            rij_resultaten = {}
            for code, _label, _nr in ds.MAAND_VOLGORDE:
                tussen = request.form.getlist(f"tussen_{code}[]")[i] if request.form.getlist(f"tussen_{code}[]") else ""
                eind = request.form.getlist(f"eind_{code}[]")[i] if request.form.getlist(f"eind_{code}[]") else ""
                if not tussen.strip() and not eind.strip():
                    continue
                try:
                    r1c, r2c, eindc = ds.bereken_ontbrekende_tijd(tussen, None, eind)
                except ValueError as e:
                    flash(f"Oei, er ging iets mis bij {voornaam} {naam}: {e}", "fout")
                    return redirect(request.url)
                rij_resultaten[code] = {
                    "naam": naam, "voornaam": voornaam,
                    "ronde1": r1c, "ronde2": r2c, "eindtijd": eindc,
                }
                atleet_heeft_data = True

            if not atleet_heeft_data:
                continue

            atleet, is_nieuw, onvolledig = ds.voeg_atleet_toe_indien_nieuw(atleten, naam, voornaam)
            if onvolledig:
                onvolledige_atleten.append(atleet)
            for code, resultaat in rij_resultaten.items():
                resultaat["naam"], resultaat["voornaam"] = atleet["naam"], atleet["voornaam"]
                deelnames_per_maand[code].append(resultaat)

        if not any(deelnames_per_maand.values()):
            flash("Oei, er ging iets mis: geen enkele tijd ingevuld voor een deelnemer.", "fout")
            return redirect(request.url)

        for code, nieuwe_deelnames in deelnames_per_maand.items():
            if not nieuwe_deelnames:
                continue
            datum_str = maand_datums[code]
            bestaand = ds.laad_event(datum_str)
            if bestaand:
                bestaand["deelnames"] = ds.merge_deelnames(bestaand["deelnames"], nieuwe_deelnames)
                if volgnummer_per_maand[code] is not None:
                    bestaand["volgnummer"] = volgnummer_per_maand[code]
                ds.bewaar_event(bestaand)
            else:
                ds.bewaar_event({
                    "datum": datum_str,
                    "seizoen": ds.bepaal_seizoen(datum_str),
                    "volgnummer": volgnummer_per_maand[code],
                    "grote_prijs": None,
                    "opmerkingen": "",
                    "verslag_bestand": None,
                    "deelnames": nieuwe_deelnames,
                })

        ds.bewaar_atleten(atleten)

        if onvolledige_atleten:
            session["onvolledige_ids"] = [a["id"] for a in onvolledige_atleten]
            session["na_aanvullen"] = {"soort": "seizoen", "waarde": seizoen_str}
            return redirect(url_for("atleten_aanvullen"))

        flash("Succesvol opgeslagen.", "succes")
        return redirect(url_for("seizoensoverzicht_print", seizoen_str=seizoen_str))

    # -------------------------------------------------------------------
    # Popup 3: ontbrekende atleetgegevens aanvullen
    # -------------------------------------------------------------------
    # -------------------------------------------------------------------
    # Tijden individuele atleet (publiek, enkel lezen)
    # -------------------------------------------------------------------
    @app.route("/atleten/tijden")
    def atleet_tijden():
        return render_template("atleet_tijden.html", keuzes=statistiek.keuzelijst())

    @app.route("/atleten/tijden/data")
    def atleet_tijden_data():
        ids = [i for i in request.args.get("a", "").split(",")]
        return jsonify(statistiek.tijdreeksen(ids[:5]))

    @app.route("/atleten/aanvullen", methods=["GET", "POST"])
    def atleten_aanvullen():
        ids = session.get("onvolledige_ids", [])
        atleten = ds.laad_atleten()

        if request.method == "POST":
            for a in atleten:
                if a["id"] in ids:
                    geslacht = request.form.get(f"geslacht_{a['id']}", "").strip().lower() or None
                    geboortedatum = request.form.get(f"geboortedatum_{a['id']}", "").strip() or None
                    ds.vul_atleet_aan(atleten, a["id"], geslacht, geboortedatum)
            ds.bewaar_atleten(atleten)
            flash("Succesvol opgeslagen.", "succes")
            return _na_aanvullen_doorsturen()

        onvolledige = [a for a in atleten if a["id"] in ids]
        return render_template("atleten_aanvullen.html", atleten=onvolledige)

    def _na_aanvullen_doorsturen():
        doel = session.pop("na_aanvullen", None)
        session.pop("onvolledige_ids", None)
        if doel and doel["soort"] == "event":
            return redirect(url_for("oefencross_print", datum_str=doel["waarde"]))
        if doel and doel["soort"] == "seizoen":
            return redirect(url_for("seizoensoverzicht_print", seizoen_str=doel["waarde"]))
        return redirect(url_for("home"))

    @app.route("/atleten/aanvullen/overslaan", methods=["POST"])
    def atleten_aanvullen_overslaan():
        """Popup 3, antwoord "nee": de resultaten zijn al opgeslagen, niets aanvullen."""
        flash("Succesvol opgeslagen.", "succes")
        return _na_aanvullen_doorsturen()

    # -------------------------------------------------------------------
    # Verwijderen (oefencross / atleet)
    # -------------------------------------------------------------------
    @app.route("/oefencross/<datum_str>/verwijderen", methods=["POST"])
    def oefencross_verwijderen(datum_str):
        if ds.verwijder_event(datum_str):
            flash(f"De oefencross van {ds.datum_nl(datum_str)} is verwijderd.", "succes")
        else:
            flash("Oei, er ging iets mis: deze oefencross bestaat niet (meer).", "fout")
        return redirect(url_for("home"))

    @app.route("/atleten/<atleet_id>/verwijderen", methods=["POST"])
    def atleet_verwijderen(atleet_id):
        atleten = ds.laad_atleten()
        weg = ds.verwijder_atleet(atleten, atleet_id)
        if weg:
            ds.bewaar_atleten(atleten)
            flash(f"{weg['voornaam']} {weg['naam']} is uit de atletenlijst verwijderd. "
                  f"De wedstrijdresultaten zijn onaangetast gebleven.", "succes")
        else:
            flash("Oei, er ging iets mis: deze atleet bestaat niet (meer).", "fout")
        return redirect(url_for("atleten_overzicht",
                                filter=request.args.get("filter", "alle"),
                                zoek=request.args.get("zoek", "")))

    # -------------------------------------------------------------------
    # Alle atleten - overzicht + filter op "onvolledig" + rechtstreeks aanvullen
    # -------------------------------------------------------------------
    @app.route("/atleten", methods=["GET", "POST"])
    def atleten_overzicht():
        atleten = ds.laad_atleten()

        if request.method == "POST":
            for a in atleten:
                geslacht_key = f"geslacht_{a['id']}"
                geboortedatum_key = f"geboortedatum_{a['id']}"
                if geslacht_key in request.form or geboortedatum_key in request.form:
                    geslacht = request.form.get(geslacht_key, "").strip().lower() or None
                    geboortedatum = request.form.get(geboortedatum_key, "").strip() or None
                    if geslacht:
                        a["geslacht"] = geslacht
                    if geboortedatum:
                        a["geboortedatum"] = geboortedatum
            ds.bewaar_atleten(atleten)
            flash("Succesvol opgeslagen.", "succes")
            return redirect(url_for("atleten_overzicht", filter=request.args.get("filter", "alle")))

        filter_param = request.args.get("filter", "alle")
        zoek = (request.args.get("zoek") or "").strip().lower()

        def is_onvolledig(a):
            return not a.get("geslacht") or not a.get("geboortedatum")

        weergave = atleten
        if filter_param == "onvolledig":
            weergave = [a for a in weergave if is_onvolledig(a)]
        if zoek:
            weergave = [a for a in weergave if zoek in a["naam"].lower() or zoek in a["voornaam"].lower()]
        weergave = sorted(weergave, key=lambda a: (a["naam"].lower(), a["voornaam"].lower()))

        return render_template(
            "atleten_overzicht.html",
            atleten=weergave,
            filter_param=filter_param,
            zoek=zoek,
            totaal_onvolledig=sum(1 for a in atleten if is_onvolledig(a)),
            is_onvolledig=is_onvolledig,
        )

    # -------------------------------------------------------------------
    # Print Oefencross
    # -------------------------------------------------------------------
    @app.route("/oefencross/<datum_str>/print")
    def oefencross_print(datum_str):
        data = ranking.event_ranking_met_pr(datum_str)
        if data is None:
            flash("Deze oefencross bestaat niet.", "fout")
            return redirect(url_for("home"))
        return render_template("print_oefencross.html", data=data)

    @app.route("/oefencross/<datum_str>/print.pdf")
    def oefencross_print_pdf(datum_str):
        data = ranking.event_ranking_met_pr(datum_str)
        if data is None:
            flash("Deze oefencross bestaat niet.", "fout")
            return redirect(url_for("home"))
        html = render_template("print_oefencross.html", data=data, pdf_modus=True, css_inline=pdf_hulp.lees_stijl())
        from .pdf import html_naar_pdf_response
        return html_naar_pdf_response(html, f"oefencross_{datum_str}.pdf")

    @app.route("/verslagen/<path:bestandsnaam>")
    def verslag_download(bestandsnaam):
        return send_from_directory(ds.VERSLAGEN_DIR, bestandsnaam)

    # -------------------------------------------------------------------
    # Print Seizoensoverzicht
    # -------------------------------------------------------------------
    @app.route("/seizoensoverzicht/<seizoen_str>/print")
    def seizoensoverzicht_print(seizoen_str):
        data = ranking.season_overzicht(seizoen_str)
        if data is None:
            flash("Voor dit seizoen bestaat nog geen enkele oefencross.", "fout")
            return redirect(url_for("home"))
        return render_template("print_seizoensoverzicht.html", data=data)

    @app.route("/seizoensoverzicht/<seizoen_str>/print.pdf")
    def seizoensoverzicht_print_pdf(seizoen_str):
        data = ranking.season_overzicht(seizoen_str)
        if data is None:
            flash("Voor dit seizoen bestaat nog geen enkele oefencross.", "fout")
            return redirect(url_for("home"))
        html = render_template("print_seizoensoverzicht.html", data=data, pdf_modus=True, css_inline=pdf_hulp.lees_stijl())
        from .pdf import html_naar_pdf_response
        return html_naar_pdf_response(html, f"seizoensoverzicht_{seizoen_str}.pdf")

    return app
