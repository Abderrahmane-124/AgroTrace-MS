import os
from dotenv import load_dotenv

load_dotenv()

# Configuration de l'API source
API_ENDPOINT = os.getenv('API_ENDPOINT', 'http://localhost:8080/api/sensor-data')

# Intervalle de récupération des données (en secondes)
FETCH_INTERVAL = int(os.getenv('FETCH_INTERVAL', 2))
