"""
Zet gerenderde HTML om naar een downloadbare PDF (WeasyPrint).

De stylesheet wordt rechtstreeks in de HTML gezet (css_inline), omdat WeasyPrint
bij een HTML-string geen "/static/stijl.css" kan ophalen. De paginagrootte
(A4 liggend) staat in stijl.css onder @page.
"""
import os
from flask import Response

STIJL_PAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "stijl.css")


def lees_stijl():
    with open(STIJL_PAD, "r", encoding="utf-8") as f:
        return f.read()


def html_naar_pdf_response(html_string, bestandsnaam):
    from weasyprint import HTML  # lazy import: enkel nodig waar echt PDF's gemaakt worden
    pdf_bytes = HTML(string=html_string).write_pdf()
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename={bestandsnaam}"},
    )
