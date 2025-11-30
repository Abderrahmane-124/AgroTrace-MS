import os
from dotenv import load_dotenv

load_dotenv()

KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'sensor-data')
KAFKA_GROUP_ID = os.getenv('KAFKA_GROUP_ID', 'ingestion-group')

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'agrotrace')
DB_USER = os.getenv('DB_USER', 'agrotrace_user')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'agrotrace_pass')
