import os
from dotenv import load_dotenv

load_dotenv()

KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'sensor-data')
SEND_INTERVAL = int(os.getenv('SEND_INTERVAL', 2))
DATASET_FOLDER = 'Dataset'
