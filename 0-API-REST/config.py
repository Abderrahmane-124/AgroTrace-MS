import os
from dotenv import load_dotenv

load_dotenv()

# Configuration du serveur
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 8080))

# Taille maximale du buffer de données
MAX_BUFFER_SIZE = int(os.getenv('MAX_BUFFER_SIZE', 100))
