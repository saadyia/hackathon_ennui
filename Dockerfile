# Image de « ofk? » : API FastAPI + frontend statique + données pré-calculées (aucun build au démarrage).
# Construction : docker build -t ofk . && docker run -p 8000:8000 ofk
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Dépendances d'abord (couche mise en cache tant que requirements.txt ne change pas)
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

# Utilisateur non root ; backend/data doit rester inscriptible (SQLite, synchro de l'agenda, graphe reconstruit à chaud)
RUN useradd --create-home --uid 10001 ofk && chown -R ofk:ofk /app/backend/data
USER ofk

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/sante', timeout=4)" || exit 1

# 0.0.0.0 : joignable hors du conteneur ; PORT fourni par l'hébergeur ; --proxy-headers : HTTPS derrière le proxy de Render/Railway
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
