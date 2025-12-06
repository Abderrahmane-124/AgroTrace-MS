# Ingestion de Données Capteurs

## Description
Microservice qui consomme les données des capteurs depuis Kafka, les harmonise, les valide et les stocke dans TimescaleDB pour persistance et analyse ultérieure.

---

## Données en Entrée

### Source des Données
- **Système** : Apache Kafka
- **Topic** : `sensor-data` (configurable)
- **Groupe de consommateurs** : `ingestion-group` (configurable)
- **Format** : Messages JSON avec structure :
  ```json
  {
    "sensor_type": "nom_capteur",
    "timestamp": "ISO-8601",
    "data_index": numéro,
    "measurements": {...}
  }
  ```

### Configuration Kafka
- `KAFKA_BOOTSTRAP_SERVERS` : Adresse du broker Kafka (défaut: `localhost:9092`)
- `KAFKA_TOPIC` : Topic source (défaut: `sensor-data`)
- `KAFKA_GROUP_ID` : Groupe de consommateurs (défaut: `ingestion-group`)
- Mode de lecture : `latest` (nouveaux messages uniquement)
- Auto-commit activé avec intervalle de 1 seconde

### Configuration Base de Données
- `DB_HOST` : Hôte TimescaleDB (défaut: `localhost`)
- `DB_PORT` : Port (défaut: `5432`)
- `DB_NAME` : Nom de la base (défaut: `agrotrace`)
- `DB_USER` : Utilisateur (défaut: `agrotrace_user`)
- `DB_PASSWORD` : Mot de passe (défaut: `agrotrace_pass`)

---

## Traitement Interne

### 1. Harmonisation des Données
Normalise et uniformise les données reçues :

- **Normalisation des champs** : Conversion des clés en minuscules avec underscores
- **Gestion du timestamp** : Support de multiples formats (ISO-8601, datetime standard)
- **Conversion des types** : 
  - Valeurs nulles (`None`, `''`, `'N/A'`) standardisées
  - Conversion automatique en nombres quand possible
  - Nettoyage des unités (%, °C, °F)
- **Structure flexible** : Support de données avec ou sans sous-dictionnaire `measurements`

### 2. Validation des Données
Vérification de la cohérence et des plages de valeurs :

- **Type de capteur** : Présence obligatoire, max 100 caractères
- **Timestamp** : Format valide vérifié
- **Mesures** : Au moins une mesure présente
- **Plages spécifiques** :
  - Humidité : 0-100%
  - Température : -50 à 60°C
  - pH : 0-14
  - Humidité du sol : 0-100%

### 3. Persistance
- **Pool de connexions** : 1-10 connexions threadées vers TimescaleDB
- **Retry automatique** : 10 tentatives avec délai de 5 secondes
- **Transactions** : Commit après chaque insertion réussie, rollback en cas d'erreur
- **Gestion des erreurs** : Messages invalides loggés mais ne bloquent pas le flux

---

## Données en Sortie

### Destination
- **Système** : TimescaleDB (PostgreSQL avec extension time-series)
- **Table** : `sensor_data`
- **Type de table** : Hypertable (optimisée pour séries temporelles)

### Structure de la Table
```sql
sensor_data (
  id SERIAL,
  sensor_type VARCHAR(100),
  timestamp TIMESTAMPTZ,
  data_index INTEGER,
  measurements JSONB,
  created_at TIMESTAMPTZ
)
```

### Caractéristiques
- **Clé primaire composite** : `(timestamp, id)`
- **Index** :
  - `sensor_type` : Filtrage par type de capteur
  - `timestamp DESC` : Requêtes temporelles
- **Format JSONB** : Permet indexation et requêtes flexibles sur les mesures
- **Optimisation time-series** : Partitionnement automatique par TimescaleDB

### Données Stockées
- Type de capteur identifiant la source
- Timestamp au format `TIMESTAMPTZ` avec fuseau horaire
- Index de la donnée source (pour traçabilité)
- Mesures au format JSONB (clés normalisées, valeurs nettoyées)
- Date de création automatique

---

## Flux de Traitement

1. **Consommation** : Lecture des messages depuis Kafka (batch de 10 max)
2. **Harmonisation** : Normalisation des champs et conversion des types
3. **Validation** : Vérification de cohérence et plages de valeurs
4. **Stockage** : Insertion dans TimescaleDB avec transaction
5. **Confirmation** : Commit du message Kafka après stockage réussi

---

## Monitoring et Statistiques

### Métriques en Temps Réel
- Nombre de messages reçus
- Nombre de messages stockés avec succès
- Nombre d'erreurs de validation ou stockage
- Affichage périodique toutes les 30 secondes en cas d'inactivité

### Logs
- Confirmation d'envoi avec timestamp, type de capteur et offset
- Erreurs de validation avec détails
- Erreurs de stockage avec contexte

### Arrêt Gracieux
- Fermeture propre du consommateur Kafka
- Libération du pool de connexions TimescaleDB
- Affichage du bilan complet (reçus, stockés, erreurs)

---

## Initialisation de la Base

Le script `init_db.sql` crée automatiquement :
- Extension TimescaleDB
- Table `sensor_data` avec hypertable
- Index optimisés pour les requêtes temporelles et par type
- Table `sensor_data_processed` (utilisée par MS2-Prétraitement)
- Vue `sensor_data_comparison` pour comparaison brut/traité

---

## Dépendances

- `kafka-python` : Client Kafka Consumer
- `psycopg2-binary` : Driver PostgreSQL/TimescaleDB
- `python-dotenv` : Gestion des variables d'environnement
