# Simulateur de Capteurs IoT - AgroTrace

Ce simulateur lit les données des capteurs depuis le dossier `Dataset` et les envoie via REST API.

## Installation

1. Créer l'environnement virtuel :
```powershell
python -m venv venv
```

2. Activer l'environnement virtuel :
```powershell
.\venv\Scripts\Activate.ps1
```

3. Installer les dépendances :
```powershell
pip install -r requirements.txt
```

## Configuration

1. Copier le fichier `.env.example` vers `.env` :
```powershell
Copy-Item .env.example .env
```

2. Modifier le fichier `.env` pour configurer l'endpoint de l'API :
```
API_ENDPOINT=http://localhost:8080/api/sensor-data
SEND_INTERVAL=1
```

## Utilisation

Lancer le simulateur :
```powershell
python simulator.py
```

Le simulateur va :
- Charger tous les fichiers Excel du dossier `Dataset`
- Sélectionner aléatoirement un capteur et une ligne de données
- Transformer la ligne en JSON
- Envoyer les données via POST à l'API configurée
- Répéter toutes les 1 secondes (configurable)
- Éviter d'envoyer deux données successives du même fichier

Appuyez sur `Ctrl+C` pour arrêter le simulateur.

## Capteurs disponibles

Les fichiers suivants sont chargés depuis le dossier Dataset :
- Environment Humidity
- Environment Light Intensity
- Environment Temperature
- Soil Moisture
- Soil pH
- Soil Temperature
- Solar Panel Battery Voltage
- Water TDS

## Format des données envoyées

```json
{
  "sensor_type": "Environment Temperature",
  "timestamp": "2025-11-25T10:30:45.123456",
  "data_index": 42,
  "measurements": {
    "column1": "value1",
    "column2": "value2",
    ...
  }
}
```
