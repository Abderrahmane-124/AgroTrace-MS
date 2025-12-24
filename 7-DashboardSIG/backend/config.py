# ========================================
# Configuration du DashboardSIG Backend
# ========================================

import os

# PostGIS Database
POSTGIS_HOST = os.getenv("POSTGIS_HOST", "postgis")
POSTGIS_PORT = int(os.getenv("POSTGIS_PORT", 5432))
POSTGIS_DB = os.getenv("POSTGIS_DB", "agrotrace_sig")
POSTGIS_USER = os.getenv("POSTGIS_USER", "agrotrace_user")
POSTGIS_PASSWORD = os.getenv("POSTGIS_PASSWORD", "agrotrace_pass")

# Kafka
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-broker:9092")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "dashboard-sig-group")

# Topics to consume
KAFKA_TOPICS = [
    "sensor-data-processed",      # MS2: Données capteurs prétraitées
    "water.forecast",             # MS4: Prévisions hydriques
    "disease.detected",           # MS3: Détections de maladies
    "agro.recommendations"        # MS5: Recommandations agronomiques
]

# MS6 RecoIrrigation API
RECO_IRRIGATION_API_URL = os.getenv("RECO_IRRIGATION_API_URL", "http://reco-irrigation:8086")

# MinIO for images (public URL for browser access)
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL", "http://localhost:9000")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "agrotrace-images")

# API Settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8085))

# Database URL
DATABASE_URL = f"postgresql://{POSTGIS_USER}:{POSTGIS_PASSWORD}@{POSTGIS_HOST}:{POSTGIS_PORT}/{POSTGIS_DB}"
