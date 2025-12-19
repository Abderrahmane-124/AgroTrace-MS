FROM python:3.11-slim

WORKDIR /app

# Installation dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copier requirements
COPY requirements.txt .

# Installer dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY config.py .
COPY rules_config.yaml .
COPY rules_engine.py .
COPY kafka_service.py .
COPY regles_agro.py .

# Lancer l'application
CMD ["python", "-u", "regles_agro.py"]
