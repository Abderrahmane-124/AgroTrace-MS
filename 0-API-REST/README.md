# API REST - AgroTrace

API REST développée avec FastAPI pour la réception et la distribution des données de capteurs IoT.

## Fonctionnalités

- **Réception de données** : Endpoint POST pour recevoir les données des capteurs
- **Distribution de données** : Endpoint GET pour distribuer les données aux consommateurs
- **Statistiques** : Suivi des données reçues et des types de capteurs
- **Buffer circulaire** : Stockage temporaire des dernières données
- **Documentation auto-générée** : Swagger UI et ReDoc

## Installation

1. Créer un environnement virtuel (optionnel mais recommandé):
```bash
python -m venv venv
.\venv\Scripts\activate
```

2. Installer les dépendances:
```bash
pip install -r requirements.txt
```

3. Configurer l'environnement:
```bash
cp .env.example .env
```

## Configuration

Le fichier `.env` contient les paramètres suivants:

- `HOST`: Adresse d'écoute (par défaut: 0.0.0.0)
- `PORT`: Port d'écoute (par défaut: 8080)
- `MAX_BUFFER_SIZE`: Taille maximale du buffer (par défaut: 100)

## Utilisation

Lancer le serveur API:
```bash
python main.py
```

Ou avec uvicorn directement:
```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

## Endpoints

### POST /api/sensor-data
Reçoit les données d'un capteur IoT.

**Body:**
```json
{
  "sensor_type": "temperature_sensor",
  "timestamp": "2024-01-01T12:00:00",
  "data_index": 42,
  "measurements": {
    "temperature": 25.5,
    "humidity": 60.2
  }
}
```

### GET /api/sensor-data?limit=1
Récupère les dernières données de capteurs.

**Paramètres:**
- `limit`: Nombre de données à récupérer (1-100, défaut: 1)

### GET /api/stats
Récupère les statistiques du service.

**Response:**
```json
{
  "total_received": 150,
  "buffer_size": 100,
  "buffer_max_size": 100,
  "sensors_types": {
    "temperature_sensor": 50,
    "humidity_sensor": 100
  },
  "uptime_seconds": 3600.5
}
```

### DELETE /api/sensor-data
Vide le buffer de données.

## Documentation Interactive

Une fois le serveur lancé, accédez à :

- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

## Architecture

```
Simulateur → POST → API REST (Buffer) → GET → Service Ingestion
```

1. Le simulateur envoie les données via POST
2. L'API stocke dans un buffer circulaire
3. Le service d'ingestion récupère via GET

## Logs

Le serveur affiche :
- Les informations de démarrage
- Les requêtes entrantes
- Les statistiques à l'arrêt
