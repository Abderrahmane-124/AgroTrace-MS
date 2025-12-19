"""
Configuration centralisée pour MS5 - RèglesAgro
"""
import os

# ====================================
# KAFKA CONFIGURATION
# ====================================
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')

# Topics consommés
KAFKA_TOPIC_WATER_FORECAST = os.getenv('KAFKA_TOPIC_WATER_FORECAST', 'water.forecast')
KAFKA_TOPIC_DISEASE_DETECTED = os.getenv('KAFKA_TOPIC_DISEASE_DETECTED', 'disease.detected')
KAFKA_TOPIC_SENSOR_DATA = os.getenv('KAFKA_TOPIC_SENSOR_DATA', 'sensor-data-processed')

# Topic produit
KAFKA_TOPIC_RECOMMENDATIONS = os.getenv('KAFKA_TOPIC_RECOMMENDATIONS', 'agro.recommendations')

# Consumer group
KAFKA_GROUP_ID = os.getenv('KAFKA_GROUP_ID', 'regles-agro-group')

# ====================================
# POSTGRESQL CONFIGURATION
# ====================================
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'regles_agro')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'agro_user')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'agro_password')

# Connection string
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# ====================================
# RULES ENGINE CONFIGURATION
# ====================================
RULES_CONFIG_FILE = os.getenv('RULES_CONFIG_FILE', 'rules_config.yaml')

# Priorités des recommandations
PRIORITY_LEVELS = {
    'URGENT': 4,
    'HIGH': 3,
    'MEDIUM': 2,
    'LOW': 1
}

# ====================================
# LOGGING
# ====================================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
