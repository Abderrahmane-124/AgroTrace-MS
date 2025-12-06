import os

# Configuration Kafka
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_INPUT_TOPIC = os.getenv('KAFKA_INPUT_TOPIC', 'sensor-data')
KAFKA_OUTPUT_TOPIC = os.getenv('KAFKA_OUTPUT_TOPIC', 'sensor-data-processed')
KAFKA_GROUP_ID = os.getenv('KAFKA_GROUP_ID', 'preprocessing-group')

# Configuration TimescaleDB
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_NAME = os.getenv('DB_NAME', 'agrotrace')
DB_USER = os.getenv('DB_USER', 'agrotrace_user')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'agrotrace_pass')

# Configuration du prétraitement
# Seuils pour la détection d'anomalies (Z-score)
ANOMALY_THRESHOLD = float(os.getenv('ANOMALY_THRESHOLD', '3.0'))

# Fenêtre pour les moyennes mobiles (en nombre de mesures)
MOVING_AVERAGE_WINDOW = int(os.getenv('MOVING_AVERAGE_WINDOW', '5'))

# Plages de valeurs normales pour chaque type de capteur
SENSOR_RANGES = {
    'Temperature': {'min': -10.0, 'max': 50.0},
    'Environment Humidity': {'min': 0.0, 'max': 100.0},
    'Soil Moisture': {'min': 0.0, 'max': 100.0},
    'Soil pH': {'min': 0.0, 'max': 14.0},
    'Light Intensity': {'min': 0.0, 'max': 100000.0},
}
