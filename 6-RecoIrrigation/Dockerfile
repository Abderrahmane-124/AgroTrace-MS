# MS6 - RecoIrrigation
FROM python:3.11-slim

# Métadonnées
LABEL maintainer="AgroTrace"
LABEL description="MS6 - API de recommandations tactiques d'irrigation"

# Variables d'environnement Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Répertoire de travail
WORKDIR /app

# Installer les dépendances système (PostgreSQL client)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copier requirements et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY config.py .
COPY models.py .
COPY planner.py .
COPY kafka_consumer.py .
COPY database.py .
COPY main.py .

# Exposition du port API
EXPOSE 8086

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8086/health')" || exit 1

# Commande de démarrage
CMD ["python", "main.py"]
