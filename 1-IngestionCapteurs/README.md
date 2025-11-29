# Service d'Ingestion de Données Capteurs

Ce service récupère les données depuis l'API REST et les affiche en temps réel.

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

Modifiez le fichier `.env` selon vos besoins.

## Configuration

Le fichier `.env` contient les paramètres suivants:

- `API_ENDPOINT`: URL de l'API source (par défaut: http://localhost:8080/api/sensor-data)
- `FETCH_INTERVAL`: Intervalle de récupération en secondes (par défaut: 2)

## Utilisation

Lancer le service d'ingestion:
```bash
python ingestion.py
```

Le service va:
1. Se connecter à l'API REST
2. Récupérer les données périodiquement
3. Afficher les données formatées dans la console

Pour arrêter le service, appuyez sur `Ctrl+C`.

## Format des Données

Le service affiche les données reçues avec les informations suivantes:
- Type de capteur
- Timestamp
- Index des données
- Mesures détaillées

## Prérequis

Assurez-vous que:
- L'API REST est accessible à l'URL configurée
- Le simulateur de capteurs (dans `0-Simulateur-Capteurs`) est en cours d'exécution
