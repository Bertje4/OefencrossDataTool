"""
Start de Oefencross-tool lokaal (of via WSGI/Gunicorn in productie).

Lokaal testen:
    python run.py
Productie (op je eigen server, achter je Proxymanager reverse proxy):
    gunicorn -w 2 -b 127.0.0.1:8420 "run:app"
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8420, debug=True)
