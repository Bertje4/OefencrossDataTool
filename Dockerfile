# BASIS-IMAGE: bevat enkel Python + de libraries (Flask, WeasyPrint, gunicorn).
# De applicatiecode zelf zit NIET in de image maar wordt bij het opstarten
# gemount vanuit de map Config; de data vanuit de map DataBase (zie
# docker-compose.yml). Daardoor kan je HTML/CSS/code aanpassen zonder de image
# opnieuw te bouwen, en heeft deze Dockerfile geen build-context (COPY) nodig,
# zodat je hem gewoon in Portainer kan plakken (Images -> Build a new image -> Web editor).
FROM python:3.11-slim

# WeasyPrint (PDF-generatie) heeft systeemlibraries nodig (Pango/Cairo).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Zelfde versies als in requirements.txt
RUN pip install --no-cache-dir Flask==3.1.3 weasyprint==70.0 gunicorn==23.0.0

ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
EXPOSE 8420

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8420", "--timeout", "60", "run:app"]
