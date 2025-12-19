"""
Configuration centralisée pour MS6 - RecoIrrigation
"""
import os

# ====================================
# API CONFIGURATION
# ====================================
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', '8086'))
API_TITLE = "MS6 - RecoIrrigation API"
API_VERSION = "1.0.0"
API_DESCRIPTION = "API de recommandations d'irrigation personnalisées"

# ====================================
# KAFKA CONFIGURATION
# ====================================
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_TOPIC_RECOMMENDATIONS = os.getenv('KAFKA_TOPIC_RECOMMENDATIONS', 'agro.recommendations')
KAFKA_GROUP_ID = os.getenv('KAFKA_GROUP_ID', 'reco-irrigation-group')

# ====================================
# POSTGRESQL CONFIGURATION
# ====================================
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'reco_irrigation')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'irrigation_user')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'irrigation_password')

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# ====================================
# IRRIGATION DEFAULTS
# ====================================
DEFAULT_FLOW_RATE_LPM = float(os.getenv('DEFAULT_FLOW_RATE_LPM', '200'))  # Litres par minute
DEFAULT_SESSION_MAX_MINUTES = int(os.getenv('DEFAULT_SESSION_MAX_MINUTES', '120'))  # 2h max par session
EARLY_MORNING_START = os.getenv('EARLY_MORNING_START', '06:00')
EVENING_START = os.getenv('EVENING_START', '18:00')

# Efficacité selon type d'irrigation (%)
IRRIGATION_EFFICIENCY = {
    'drip': 0.90,          # Goutte-à-goutte: 90% efficacité
    'sprinkler': 0.75,     # Aspersion: 75%
    'furrow': 0.60,        # Sillon: 60%
    'flood': 0.50          # Submersion: 50%
}

# Capacité rétention eau selon type de sol (mm/m)
SOIL_WATER_RETENTION = {
    'sandy': 80,           # Sol sableux: faible rétention
    'loamy': 170,          # Sol limoneux: moyenne
    'clay': 250,           # Sol argileux: forte
    'organic': 200         # Sol organique: bonne
}

# ====================================
# LOGGING
# ====================================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
