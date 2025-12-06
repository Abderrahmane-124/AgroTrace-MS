"""
Configuration du microservice MS4 - PrévisionEau
Prévision du besoin en eau et du stress hydrique avec Prophet
"""

import os

# Configuration Kafka
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_SENSOR_TOPIC = os.getenv('KAFKA_SENSOR_TOPIC', 'sensor-data-processed')
KAFKA_FORECAST_TOPIC = os.getenv('KAFKA_FORECAST_TOPIC', 'water.forecast')
KAFKA_GROUP_ID = os.getenv('KAFKA_GROUP_ID', 'water-forecast-group')

# Configuration TimescaleDB
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_NAME = os.getenv('DB_NAME', 'agrotrace')
DB_USER = os.getenv('DB_USER', 'agrotrace_user')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'agrotrace_pass')

# Configuration du modèle Prophet
FORECAST_HORIZON = int(os.getenv('FORECAST_HORIZON', '7'))  # Jours de prévision (1-7)
TRAINING_WINDOW_DAYS = int(os.getenv('TRAINING_WINDOW_DAYS', '30'))  # Fenêtre d'entraînement
MIN_DATA_POINTS = int(os.getenv('MIN_DATA_POINTS', '3'))  # Minimum de points pour entraîner (réduit de 10 à 3)
RETRAINING_INTERVAL_HOURS = int(os.getenv('RETRAINING_INTERVAL_HOURS', '6'))  # Réentraînement toutes les 6h

# Seuils de stress hydrique
WATER_STRESS_THRESHOLD_LOW = float(os.getenv('WATER_STRESS_THRESHOLD_LOW', '30.0'))  # Humidité < 30% = stress élevé
WATER_STRESS_THRESHOLD_MEDIUM = float(os.getenv('WATER_STRESS_THRESHOLD_MEDIUM', '50.0'))  # Humidité < 50% = stress moyen
WATER_STRESS_THRESHOLD_HIGH = float(os.getenv('WATER_STRESS_THRESHOLD_HIGH', '70.0'))  # Humidité > 70% = optimal

# Configuration des capteurs pour irrigation
# Les noms doivent correspondre exactement aux noms dans sensor_data_processed
SOIL_MOISTURE_SENSORS = ['Soil Moisture']
TEMPERATURE_SENSORS = ['Environment Temperature', 'Soil Temperature']
HUMIDITY_SENSORS = ['Environment Humidity']

# Coefficients de pondération pour le calcul du besoin en eau
WEIGHT_SOIL_MOISTURE = float(os.getenv('WEIGHT_SOIL_MOISTURE', '0.6'))  # 60%
WEIGHT_TEMPERATURE = float(os.getenv('WEIGHT_TEMPERATURE', '0.25'))  # 25%
WEIGHT_HUMIDITY = float(os.getenv('WEIGHT_HUMIDITY', '0.15'))  # 15%

# Configuration de publication
PUBLISH_INTERVAL_MINUTES = int(os.getenv('PUBLISH_INTERVAL_MINUTES', '60'))  # Publier toutes les heures
AGGREGATION_INTERVAL_MINUTES = int(os.getenv('AGGREGATION_INTERVAL_MINUTES', '30'))  # Agrégation toutes les 30min

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
