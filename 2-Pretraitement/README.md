# Microservice 2 : Prétraitement des Données Capteurs

## 🎯 Rôle

Le microservice de prétraitement nettoie, normalise et enrichit les **données capteurs IoT** :
- Nettoyage des données
- Normalisation
- Détection d'anomalies
- Calcul de moyennes mobiles

> ⚠️ **Note** : Le traitement des images UAV est maintenant géré par **MS3 - VisionPlante**

## 📥 Entrées

**Source** : Kafka Topic `sensor-data`
- **Format** : JSON
- **Provenance** : MS1 (Ingestion Capteurs)
- **Fréquence** : Temps réel (push automatique)

**Exemple de message reçu** :
```json
{
  "sensor_type": "Temperature",
  "timestamp": "2025-12-02T10:30:00Z",
  "data_index": 42,
  "measurements": {
    "Temperature (°C)": 25.3
  }
}
```

## ⚙️ Traitement

### Pipeline Capteurs IoT

1. **Validation** : Vérification de la structure des données
2. **Extraction** : Récupération de la valeur principale
3. **Détection d'anomalies** :
   - Vérification des plages de valeurs attendues
   - Calcul du Z-score (si historique suffisant)
   - Seuil : Z-score > 3.0 = anomalie
4. **Nettoyage** :
   - Remplacement des anomalies par la moyenne mobile
   - Gestion des valeurs manquantes
5. **Normalisation** :
   - Min-Max scaling [0, 1]
   - Basé sur les plages définies par type de capteur
6. **Features** :
   - Calcul de moyenne mobile (fenêtre de 5 mesures)
7. **Score de qualité** :
   - 1.0 = excellente qualité
   - Pénalités pour anomalies et données manquantes

### Plages de valeurs normales :

| Capteur | Min | Max |
|---------|-----|-----|
| Temperature | -10°C | 50°C |
| Environment Humidity | 0% | 100% |
| Soil Moisture | 0% | 100% |
| Soil pH | 0 | 14 |
| Light Intensity | 0 lux | 100000 lux |

## 📤 Sorties

### 1. TimescaleDB : Table `sensor_data_processed`

**Structure** :
```sql
CREATE TABLE sensor_data_processed (
    id SERIAL PRIMARY KEY,
    sensor_type VARCHAR(100),
    timestamp TIMESTAMPTZ,
    raw_value FLOAT,              -- Valeur brute originale
    clean_value FLOAT,            -- Valeur nettoyée
    normalized_value FLOAT,       -- Valeur normalisée [0-1]
    moving_average FLOAT,         -- Moyenne mobile
    quality_score FLOAT,          -- Score de qualité [0-1]
    is_anomaly BOOLEAN,           -- Anomalie détectée ?
    missing_data_filled BOOLEAN,  -- Donnée manquante remplie ?
    processing_timestamp TIMESTAMPTZ,
    created_at TIMESTAMPTZ
);
```

**Pourquoi TimescaleDB ?**
- ✅ Stockage permanent (historique illimité)
- ✅ Requêtes SQL complexes et analytics
- ✅ Indexation automatique sur timestamp

### 2. Kafka Topic : `sensor-data-processed`

**Format de message publié** :
```json
{
  "sensor_type": "Temperature",
  "timestamp": "2025-12-02T10:30:00Z",
  "raw_value": 25.3,
  "clean_value": 25.3,
  "normalized_value": 0.5883,
  "moving_average": 25.45,
  "quality_score": 1.0,
  "is_anomaly": false,
  "missing_data_filled": false,
  "processing_timestamp": "2025-12-02T10:30:01Z"
}
```

**Pourquoi Kafka ?**
- ✅ Notification temps réel aux services suivants
- ✅ Architecture découplée (event-driven)
- ✅ Scalabilité horizontale

**Consommateurs** :
- MS3 : VisionPlante (corrélation avec images)
- MS4 : Prédiction (modèles ML)
- MS5 : Alertes (détection seuils)
- MS6 : Dashboard (visualisation temps réel)

## 🚀 Démarrage

### Via Docker Compose (recommandé)

```bash
# Démarrer tous les services
docker compose up -d

# Voir les logs du prétraitement
docker compose logs -f preprocessing

# Arrêter les services
docker compose down
```

### En développement local

```bash
cd 2-Pretraitement

# Installer les dépendances
pip install -r requirements.txt

# Configurer les variables d'environnement
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export KAFKA_INPUT_TOPIC=sensor-data
export KAFKA_OUTPUT_TOPIC=sensor-data-processed
export DB_HOST=localhost

# Lancer le service
python preprocessing.py
```

## 📊 Configuration

Variables d'environnement :

| Variable | Description | Défaut |
|----------|-------------|--------|
| `KAFKA_BOOTSTRAP_SERVERS` | Adresse Kafka | `localhost:9092` |
| `KAFKA_INPUT_TOPIC` | Topic d'entrée | `sensor-data` |
| `KAFKA_OUTPUT_TOPIC` | Topic de sortie | `sensor-data-processed` |
| `KAFKA_GROUP_ID` | Groupe consumer | `preprocessing-group` |
| `DB_HOST` | Hôte TimescaleDB | `localhost` |
| `DB_PORT` | Port TimescaleDB | `5432` |
| `DB_NAME` | Nom de la base | `agrotrace` |
| `DB_USER` | Utilisateur DB | `agrotrace_user` |
| `DB_PASSWORD` | Mot de passe DB | `agrotrace_pass` |
| `ANOMALY_THRESHOLD` | Seuil Z-score | `3.0` |
| `MOVING_AVERAGE_WINDOW` | Fenêtre moyenne | `5` |

## 📈 Statistiques

Le service affiche des statistiques toutes les 30 secondes :

```
==============================================================
  STATISTIQUES - 2025-12-02 10:30:00
==============================================================
  Messages reçus:     1000
  Messages traités:   985
  Anomalies détectées: 15
  Erreurs:            15
  Taux de succès:     98.50%
--------------------------------------------------------------
```

## 🔍 Exemples de requêtes

### Requêtes SQL sur TimescaleDB

```sql
-- Données des dernières 24h
SELECT * FROM sensor_data_processed
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;

-- Moyenne par type de capteur (dernière heure)
SELECT 
    sensor_type,
    AVG(normalized_value) as avg_norm,
    AVG(quality_score) as avg_quality,
    COUNT(*) as count
FROM sensor_data_processed
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY sensor_type;

-- Anomalies détectées
SELECT 
    sensor_type,
    timestamp,
    raw_value,
    clean_value
FROM sensor_data_processed
WHERE is_anomaly = true
ORDER BY timestamp DESC
LIMIT 100;

-- Évolution de la température (avec moyennes mobiles)
SELECT 
    time_bucket('5 minutes', timestamp) AS bucket,
    sensor_type,
    AVG(clean_value) as avg_value,
    AVG(moving_average) as avg_moving
FROM sensor_data_processed
WHERE sensor_type = 'Temperature'
  AND timestamp > NOW() - INTERVAL '2 hours'
GROUP BY bucket, sensor_type
ORDER BY bucket DESC;
```

## 🏗️ Architecture

```
┌─────────────────────┐
│  MS1: Ingestion     │
│  Capteurs           │
└──────────┬──────────┘
           │ Kafka: sensor-data (temps réel)
           ▼
┌─────────────────────┐
│  MS2: Prétraitement │
│                     │
│  Pipeline:          │
│  1. Validation      │
│  2. Extraction      │
│  3. Détection       │
│     anomalies       │
│  4. Nettoyage       │
│  5. Normalisation   │
│  6. Features        │
│  7. Qualité         │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌────────────┐  ┌──────────────────────┐
│TimescaleDB │  │ Kafka:               │
│.processed  │  │ sensor-data-processed│
└────────────┘  └──────────┬───────────┘
                           │
                           ▼
                 ┌─────────────────────┐
                 │ Services suivants:  │
                 │ - VisionPlante      │
                 │ - Prédiction        │
                 │ - Alertes           │
                 │ - Dashboard         │
                 └─────────────────────┘
```

## 🧪 Tests

```bash
# Vérifier que le service reçoit des données
docker compose logs preprocessing | grep "Messages reçus"

# Vérifier les anomalies détectées
docker compose logs preprocessing | grep "Anomalies détectées"

# Consulter les données dans TimescaleDB
docker compose exec timescaledb psql -U agrotrace_user -d agrotrace -c \
  "SELECT COUNT(*) FROM sensor_data_processed;"

# Vérifier les topics Kafka
docker compose exec kafka-broker kafka-topics.sh --list \
  --bootstrap-server localhost:9092
```

## 📝 Notes techniques

### Pourquoi lire depuis Kafka (et pas TimescaleDB) ?

1. **Temps réel** : Push automatique, latence < 1s
2. **Event-driven** : Architecture découplée
3. **Scalabilité** : Consumer groups pour parallélisation

### Pourquoi écrire dans les DEUX (TimescaleDB + Kafka) ?

1. **Kafka** : Notification temps réel aux services
2. **TimescaleDB** : Persistence long terme + analytics

### Algorithmes de prétraitement

- **Détection anomalies** : Z-score + plages de valeurs
- **Nettoyage** : Interpolation par moyenne mobile
- **Normalisation** : Min-Max scaling
- **Features** : Moyenne mobile sur fenêtre glissante

## 🔜 Évolutions futures

- [ ] Interpolation avancée (LSTM)
- [ ] Détection d'anomalies contextuelles
- [ ] Calcul d'indices supplémentaires (EVI, SAVI)
- [ ] API REST pour requêtes ad-hoc
- [ ] Support formats images supplémentaires (JPEG2000)
- [ ] Traitement multi-spectral avancé
