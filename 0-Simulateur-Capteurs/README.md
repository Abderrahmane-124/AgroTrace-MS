# Simulateur de Capteurs IoT

## Description
Microservice qui simule des capteurs IoT agricoles en lisant des données historiques et en les envoyant vers Kafka pour traitement en temps réel.

---

## Données en Entrée

### Source des Données
- **Emplacement** : Dossier `Dataset/` local
- **Format** : Fichiers Excel (`.xlsx`)
- **Types de capteurs** :
  - Environment Humidity
  - Environment Light Intensity
  - Environment Temperature
  - Soil Moisture
  - Soil pH
  - Soil Temperature
  - Solar Panel Battery Voltage
  - Water TDS

### Configuration
Les paramètres sont définis via variables d'environnement ou valeurs par défaut :
- `KAFKA_BOOTSTRAP_SERVERS` : Adresse du broker Kafka (défaut: `localhost:9092`)
- `KAFKA_TOPIC` : Topic Kafka de destination (défaut: `sensor-data`)
- `SEND_INTERVAL` : Intervalle d'envoi en secondes (défaut: `2`)
- `DATASET_FOLDER` : Dossier contenant les fichiers Excel (défaut: `Dataset`)

---

## Traitement Interne

### 1. Initialisation
- Chargement de tous les fichiers Excel du dossier `Dataset/`
- Connexion au broker Kafka avec retry automatique (10 tentatives max)
- Configuration du producteur Kafka avec compression gzip et garantie de livraison

### 2. Sélection Aléatoire des Données
- Choix aléatoire d'un capteur parmi ceux disponibles
- Sélection aléatoire d'une ligne de données dans le fichier du capteur
- Évite de sélectionner deux fois de suite le même capteur ou la même ligne

### 3. Formatage des Données
Structure JSON créée pour chaque message :
```json
{
  "sensor_type": "nom_du_capteur",
  "timestamp": "ISO-8601",
  "data_index": numéro_ligne,
  "measurements": {
    "colonne1": valeur1,
    "colonne2": valeur2,
    ...
  }
}
```

### 4. Gestion des Types
- Conversion automatique des types pandas vers types Python natifs
- Traitement des valeurs nulles
- Conversion des dates en format ISO-8601
- Conversion des nombres en float

---

## Données en Sortie

### Destination
- **Système** : Apache Kafka
- **Topic** : `sensor-data` (configurable)
- **Clé de partitionnement** : `sensor_type`

### Configuration Kafka
- **Acknowledgment** : `all` (garantie de réception par tous les replicas)
- **Compression** : gzip
- **Retries** : 3 tentatives automatiques
- **Max in-flight requests** : 1 (garantit l'ordre des messages)

### Format de Sortie
Messages JSON encodés en UTF-8 contenant :
- Type de capteur
- Timestamp de génération
- Index de la donnée source
- Ensemble des mesures du capteur

### Métadonnées de Livraison
Chaque message envoyé retourne :
- Topic de destination
- Numéro de partition
- Offset dans la partition

---

## Cycle de Fonctionnement

1. **Démarrage** : Connexion Kafka + chargement des datasets
2. **Boucle infinie** :
   - Sélection aléatoire capteur/données
   - Formatage en JSON
   - Envoi vers Kafka
   - Attente de confirmation
   - Pause selon `SEND_INTERVAL`
3. **Arrêt gracieux** (Ctrl+C) : Flush des messages + fermeture du producteur

---

## Statistiques et Monitoring

Le simulateur affiche en temps réel :
- Confirmations d'envoi avec timestamp, partition et offset
- Compteur de messages envoyés et d'erreurs
- Statistiques cumulées tous les 10 messages
- Bilan final à l'arrêt du service

---

## Dépendances

- `pandas` : Lecture des fichiers Excel
- `openpyxl` : Support du format Excel
- `kafka-python` : Client Kafka Producer
- `python-dotenv` : Gestion des variables d'environnement
