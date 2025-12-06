FROM python:3.11-slim

WORKDIR /app

# Installation des dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copie et installation des dépendances Python avec index CPU optimisé
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.1.2 torchvision==0.16.2 \
    && pip install --no-cache-dir \
    kafka-python==2.0.2 \
    minio==7.2.0 \
    transformers==4.40.0 \
    huggingface_hub \
    Pillow==10.1.0 \
    numpy==1.24.3 \
    && rm -rf /root/.cache/pip

# Copie du code de l'application
COPY . .

# Commande par défaut
CMD ["python", "vision_plante.py"]
