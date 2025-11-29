import os
from dotenv import load_dotenv

load_dotenv()

# Configuration de l'API
API_ENDPOINT = os.getenv('API_ENDPOINT', 'http://localhost:8080/api/sensor-data')

# Intervalle d'envoi des données (en secondes)
SEND_INTERVAL = int(os.getenv('SEND_INTERVAL', 1))

# Dossier contenant les fichiers de données
DATASET_FOLDER = 'Dataset'
