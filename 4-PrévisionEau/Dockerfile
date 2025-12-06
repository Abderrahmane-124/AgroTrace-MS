FROM python:3.10-slim

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers de requirements
COPY requirements.txt .

# Installer les dépendances système nécessaires pour Prophet
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY . .

# Variables d'environnement par défaut
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV DB_HOST=timescaledb
ENV DB_PORT=5432
ENV DB_NAME=agrotrace
ENV DB_USER=agrotrace_user
ENV DB_PASSWORD=agrotrace_pass

ENV FORECAST_HORIZON=7
ENV TRAINING_WINDOW_DAYS=30
ENV RETRAINING_INTERVAL_HOURS=6
ENV PUBLISH_INTERVAL_MINUTES=60

ENV PYTHONUNBUFFERED=1

# Commande de démarrage
CMD ["python", "-u", "water_forecast.py"]
