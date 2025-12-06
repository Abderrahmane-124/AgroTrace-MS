# Prétraitement de Données Capteurs

## Description
Microservice qui consomme les données brutes depuis Kafka, applique un pipeline de prétraitement (nettoyage, normalisation, détection d'anomalies), puis stocke les données enrichies dans TimescaleDB et les republie dans Kafka pour les microservices en aval.

---

## Données en Entrée

### Source des Données
- **Système** : Apache Kafka
- **Topic source** : `sensor-data` (configurable via `KAFKA_INPUT_TOPIC`)
- **Groupe de consommateurs** : `preprocessing-group` (configurable)
- **Format** : Messages JSON avec structure :
  ```json
  {
    "sensor_type": "nom_capteur",
    "timestamp": "ISO-8601",
    "measurements": {
      "mesure1": valeur1,
      "mesure2": valeur2
    }
  }
  ```

### Configuration
**Kafka** :
- `KAFKA_BOOTSTRAP_SERVERS` : Adresse du broker (défaut: `localhost:9092`)
- `KAFKA_INPUT_TOPIC` : Topic d'entrée (défaut: `sensor-data`)
- `KAFKA_OUTPUT_TOPIC` : Topic de sortie (défaut: `sensor-data-processed`)
- `KAFKA_GROUP_ID` : Groupe de consommateurs (défaut: `preprocessing-group`)
- Mode de lecture : `earliest` (depuis le début)

**TimescaleDB** :
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

**Prétraitement** :
- `ANOMALY_THRESHOLD` : Seuil Z-score pour anomalies (défaut: `3.0`)
- `MOVING_AVERAGE_WINDOW` : Fenêtre pour moyennes mobiles (défaut: `5` mesures)

### Plages de Valeurs Normales
Définies pour chaque type de capteur :
- **Temperature** : -10°C à 50°C
- **Environment Humidity** : 0% à 100%
- **Soil Moisture** : 0% à 100%
- **Soil pH** : 0 à 14
- **Light Intensity** : 0 à 100000 lux

---

## Traitement Interne

### Pipeline de Prétraitement

#### 1. Validation
- Vérification de la présence du `sensor_type` et `timestamp`
- Validation de la structure des données

#### 2. Extraction de Valeur
Extraction de la mesure principale selon le type de capteur :
- Temperature → `Temperature (°C)`
- Environment Humidity → `Environment Humidity (%)`
- Soil Moisture → `Soil Moisture (%)`
- Soil pH → `Soil pH`
- Light Intensity → `Light Intensity (lux)`
- Autres → Première valeur numérique disponible

#### 3. Détection d'Anomalies
Deux méthodes combinées :
- **Plages de valeurs** : Vérification que la valeur est dans la plage attendue
- **Z-score** : Calcul de l'écart par rapport à l'historique (si ≥ 3 mesures)
  - Seuil configurable (défaut: 3.0)
  - Utilise moyenne et écart-type de l'historique

#### 4. Nettoyage
- **Valeurs anormales** : Remplacement par la moyenne des valeurs récentes
- **Flag** : `missing_data_filled = true` si interpolation effectuée

#### 5. Normalisation
- **Formule** : `(valeur - min) / (max - min)`
- **Résultat** : Valeur entre 0 et 1
- **Clipping** : Les valeurs hors plage sont ramenées aux bornes

#### 6. Calcul de Features
- **Moyenne mobile** : Calculée sur fenêtre glissante (défaut: 5 dernières valeurs)
- **Historique** : Maintenu en mémoire par type de capteur

#### 7. Score de Qualité
Calcul d'un score de 0.0 (mauvais) à 1.0 (excellent) :
- Base : 1.0
- Pénalité anomalie : -0.3
- Pénalité donnée interpolée : -0.2
- Bonus historique complet : +0.1

---

## Données en Sortie

### Destination 1 : TimescaleDB
- **Table** : `sensor_data_processed`
- **Type** : Hypertable (optimisée time-series)

#### Structure de la Table
```sql
sensor_data_processed (
  id SERIAL PRIMARY KEY,
  sensor_type VARCHAR(100),
  timestamp TIMESTAMPTZ,
  raw_value FLOAT,
  clean_value FLOAT,
  normalized_value FLOAT,
  moving_average FLOAT,
  quality_score FLOAT,
  is_anomaly BOOLEAN,
  missing_data_filled BOOLEAN,
  processing_timestamp TIMESTAMPTZ,
  created_at TIMESTAMPTZ
)
```

#### Index Créés
- `sensor_type` : Filtrage par type
- `timestamp` : Requêtes temporelles
- Hypertable TimescaleDB : Partitionnement automatique

### Destination 2 : Apache Kafka
- **Topic** : `sensor-data-processed` (configurable)
- **Format** : JSON enrichi

#### Structure des Messages Kafka
```json
{
  "sensor_type": "string",
  "timestamp": "ISO-8601",
  "raw_value": float,
  "clean_value": float,
  "normalized_value": float,
  "moving_average": float,
  "quality_score": float,
  "is_anomaly": boolean,
  "missing_data_filled": boolean,
  "processing_timestamp": "ISO-8601"
}
```

---

## Flux de Traitement

1. **Consommation** : Lecture message depuis `sensor-data`
2. **Validation** : Vérification structure et champs obligatoires
3. **Extraction** : Récupération valeur principale du capteur
4. **Détection anomalies** : Vérification plages + Z-score
5. **Nettoyage** : Interpolation si anomalie détectée
6. **Normalisation** : Mise à l'échelle [0-1]
7. **Features** : Calcul moyenne mobile
8. **Scoring** : Calcul score de qualité
9. **Double écriture** :
   - Stockage dans `sensor_data_processed` (TimescaleDB)
   - Publication dans `sensor-data-processed` (Kafka)

---

## Monitoring et Statistiques

### Métriques en Temps Réel
- **Messages reçus** : Total messages consommés
- **Messages traités** : Total traités avec succès
- **Anomalies détectées** : Compteur d'anomalies
- **Taux de succès** : Pourcentage de réussite
- **Erreurs** : Compteur d'échecs

### Logs
- Affichage tous les 10 messages traités avec détails :
  - Valeur brute → Valeur nettoyée → Valeur normalisée
  - Score de qualité
- Statistiques complètes toutes les 30 secondes

### Arrêt Gracieux
- Fermeture Consumer et Producer Kafka
- Libération pool connexions TimescaleDB
- Affichage bilan final complet

---

## Gestion de l'Historique

- **Structure** : File FIFO (deque) par type de capteur
- **Taille** : Limitée à `MOVING_AVERAGE_WINDOW` (défaut: 5)
- **Usage** :
  - Calcul de moyennes mobiles
  - Détection d'anomalies par Z-score
  - Interpolation en cas de valeur manquante

---

## Dépendances

- `kafka-python` : Client Kafka Consumer et Producer
- `psycopg2-binary` : Driver PostgreSQL/TimescaleDB
- `numpy` : Calculs statistiques (moyenne, écart-type, normalisation)
