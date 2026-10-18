# ACKO Oefencross Database

## Mappenindeling op je server
Twee aparte datasets naast elkaar, onder één parent:

```
/mnt/Vijver/APPS/OefencrossTool/
├── DataBase/     <- ALLE DATA (dit kloon/back-up je zelf)
│   ├── atleten.json
│   ├── oefencrossen/      <- 1 leesbaar JSON-bestand per oefencross (2026-09-06.json, ...)
│   ├── verslagen/         <- bijgevoegde bestanden
│   └── verwijderd/        <- kopieën van verwijderde oefencrossen/atleten (ontstaat vanzelf)
└── Config/       <- AL de rest: code, HTML, CSS, Dockerfile, docker-compose.yml, deze uitleg
    ├── Dockerfile
    ├── docker-compose.yml
    ├── run.py
    ├── requirements.txt
    └── app/
        ├── __init__.py, datastore.py, ranking.py, pdf.py
        ├── static/stijl.css          <- kleuren/lettertype/lay-out
        └── templates/*.html          <- de pagina's zelf
```
De applicatie schrijft **nooit** iets in `Config`; alles wat je invoert komt
uitsluitend in `DataBase` terecht. Gaat de tool ooit stuk, dan staat alles nog
gewoon als leesbare tekstbestanden in `DataBase`.

## Installatie (eenmalig)
1. Maak in TrueNAS de datasets aan: `Vijver/APPS/OefencrossTool`, en daaronder
   `DataBase` en `Config`.
2. Zet de inhoud van de meegeleverde map `Config/` in de dataset **Config**.
   De inhoud van `DataBase/` (enkel een lege `atleten.json` en twee lege mappen)
   mag je in de dataset **DataBase** zetten; laat je die leeg, dan maakt de
   tool alles zelf aan bij de eerste start.
3. **Portainer → Images → Build a new image**
   - Name: `acko-oefencross:latest`
   - Kies **Web editor** en plak de volledige inhoud van `Dockerfile` erin.
   - Klik **Build the image**. (Dit is maar één keer nodig; er zit enkel Python
     en de libraries in, geen code.)
4. **Portainer → Stacks → Add stack**
   - Name: `acko-oefencross`
   - Build method: **Web editor**, plak de inhoud van `docker-compose.yml`.
   - Controleer de twee paden onder `volumes:` (pas aan als jouw pool/dataset
     anders heet) en verander `SECRET_KEY` naar iets willekeurigs.
   - Klik **Deploy the stack**.
5. Test: `http://<server-ip>:8420`

## De UI of code aanpassen
De map `Config` wordt in de container gemount (alleen-lezen), dus **je hoeft de
image nooit opnieuw te bouwen**:
1. Pas een bestand aan in `Config/app/templates/` (HTML) of
   `Config/app/static/stijl.css` (kleuren, lettertype, lay-out).
2. Portainer → Containers → `acko_oefencross` → **Restart**.
3. Ververs de pagina in je browser (Ctrl+F5, zodat ook de CSS vers geladen wordt).

Alleen als je een extra Python-library nodig hebt (`requirements.txt` /
`Dockerfile` wijzigen), moet je stap 3 van de installatie herhalen.

## Login
Enkel wie data wil **invoegen, wijzigen of verwijderen** (oefencross, seizoen,
of "Alle atleten") krijgt een inlogscherm. Gewone bezoekers kunnen de Home-
pagina, de Volledige Ranking en alle print/PDF-pagina's bekijken en downloaden
zonder in te loggen — er staat dus geen "Inloggen"-knop in de menubalk; die
verschijnt vanzelf zodra iemand op bv. "Oefencross invoegen" klikt.

Er is 1 gedeeld wachtwoord voor alle leden (`APP_WACHTWOORD` in
`docker-compose.yml`), geen aparte account per lid. Wil je dat liever wel (bv.
per lid intrekbare toegang), laat het weten.

Omdat de tool via een **iframe** op een andere domeinnaam (je WordPress-site)
draait, is de sessie-cookie ingesteld als `SameSite=None; Secure`. Dat vereist
HTTPS (via Proxymanager) — zonder HTTPS zal inloggen niet blijven "plakken".
Sommige browsers (vooral Safari/iOS met "Voorkom sitedoorschakeling") blokkeren
cookies in iframes soms alsnog; werkt inloggen in het iframe niet, probeer de
tool dan eens rechtstreeks te openen (`https://oefencross.jouwdomein.be`,
buiten WordPress om) om te zien of het probleem bij de browserinstelling ligt.

## Reverse proxy## Reverse proxy en WordPress
In **Proxymanager**: nieuwe proxy host, bv. `oefencross.jouwdomein.be` →
`<server-ip>:8420`, met SSL via Let's Encrypt. Daarna op de WordPress-pagina
(Custom HTML-blok):
```html
<iframe src="https://oefencross.jouwdomein.be"
        style="width:100%; min-height:900px; border:0;" loading="lazy"></iframe>
```

## Rechten
De container draait als root, dus bestanden in `DataBase` zijn eigendom van
root. Leest of synct een ander proces/gebruiker die map (bv. je Google
Drive-kloon), geef die dan leesrechten via de ACL van de dataset.

## Lokaal uittesten (zonder Docker)
```bash
cd OefencrossTool/Config
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py        # -> http://localhost:8420
```
Zonder omgevingsvariabele gebruikt de tool automatisch de zustermap
`../DataBase`. Met `OEFENCROSS_DATA_DIR=/ander/pad` kan je een ander pad kiezen.

## Wat werkt er?
- **Login enkel om data te wijzigen**: gewone bezoekers kunnen alles bekijken/downloaden zonder in te loggen. Enkel oefencross/seizoen invoegen of wijzigen, verwijderen en "Alle atleten" vragen het gedeelde wachtwoord (zie hieronder)
Alle datums worden getoond als **dd/mm/jjjj** (in de bestanden zelf staan ze als jjjj-mm-dd).
- **Home**: All-Time Ranking (top 5, op basis van de eindtijd, mannen/vrouwen apart) met "vanaf:"-filter (= alleen oefencrossen vanaf die datum; kiezen of typen), en de knoppen Volledige Ranking, Oefencross Invoegen / Wijzigen / Printen, Seizoensoverzicht Invoegen / Printen. De titel en "🏠 Home" (menubalk) brengen je overal terug naar de homepagina
- **Volledige Ranking**: dezelfde ranking als op Home, maar dan de volledige lijst in plaats van top 5. Publiek, geen login nodig
- **Oefencross invoegen/wijzigen**: Ronde 1 / Ronde 2 / Eindtijd; ontbrekende waarde wordt automatisch berekend; wie maar 1 ronde liep komt onderaan
- **Tijdformaat**: altijd korter dan een uur, dus `mm:ss` of met honderdsten `mm:ss:hh` (bv. `12:34` of `12:34:56`; `12:34.56` mag ook)
- **Oefencross verwijderen**: knop bij "Wijzigen" en op de printpagina, met bevestiging. Het bestand wordt niet gewist maar verplaatst naar `DataBase/verwijderd/oefencrossen/`
- **Nieuwe/onvolledige atleten** worden herkend (popup 3, met "Nee, later aanvullen"); geslacht/geboortedatum mag leeg blijven en wordt bij de volgende invoer opnieuw gevraagd
- **Alle atleten**: overzicht, filter "enkel onvolledig", zoeken, rechtstreeks bewerken en **atleet verwijderen**. Dat verwijdert enkel de atleet uit `atleten.json` (kopie in `DataBase/verwijderd/atleten.json`); de wedstrijdresultaten blijven onaangeroerd. Tot je de atleet opnieuw toevoegt, staat die in de uitslagen onder "Geslacht nog niet gekend" en telt hij niet mee in de rankings
- **Print Oefencross** (scherm + PDF, A4 liggend), volgens het sjabloon: "#ste oefencross" + Grote Prijs, en per rij Ranking, Naam, Voornaam (+ kroontje bij een PR gelopen op die dag), #ste deelname, Ronde 1 / R1 PR, Ronde 2 / R2 PR, Eindtijd / Eind PR (met de datum waarop die gelopen werd). Eerst Vrouwen, dan Mannen. PR = beste tijd tot en met die oefencross
- **Seizoensoverzicht invoegen**: bulk-invoer **november–oktober** (per maand "tussen" + "eind"). Datums = automatisch de **eerste zondag van de maand**; met **"Datums aanpassen"** kan je uitzonderingen invullen (moet in de juiste maand én het juiste jaar van het seizoen vallen). Bestaat er al een oefencross op die datum, dan blijven Grote Prijs/opmerkingen/verslag behouden en worden deelnemers samengevoegd (zelfde naam = overschreven). Optioneel veld: "De hoeveelste oefencross was November (dit seizoen)?" — vul je dat in (bv. 482), dan telt de tool voor de rest van dat seizoen automatisch verder (december = 483, ...) voor de "#ste oefencross" op de printpagina, ook als nog niet alle 40 jaar in de database staat. Laat je dat leeg, dan telt de tool zelf op basis van de positie in de database (kan te laag uitvallen zolang niet alles is ingevoerd)
- **Print Seizoensoverzicht** (scherm + PDF, A4 liggend): maandgrid, PR's fluogeel

### Let op
- "#ste oefencross" en "#ste deelname" tellen de oefencrossen **die in de database staan**. Zolang niet alle 40 jaar ingevoerd zijn, kunnen die nummers dus te laag zijn; ze kloppen vanzelf zodra alles erin staat.
- Verwijder je een oefencross, dan schuiven de nummers van de latere oefencrossen op.

## Nog te bouwen
- Toegangscontrole (wie mag invoeren/wijzigen)
