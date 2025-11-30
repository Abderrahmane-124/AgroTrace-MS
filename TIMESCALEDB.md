# TimescaleDB - Stockage des Données Capteurs

## Vue d'ensemble

TimescaleDB est utilisé dans le projet AgroTrace pour stocker les données des capteurs agricoles avec optimisation time-series. C'est une extension de PostgreSQL spécialisée dans le stockage et l'analyse de données temporelles à grande échelle.

## Architecture

```
┌──────────────────┐      ┌─────────────┐      ┌──────────────────┐
│   Simulateur     │─────>│    Kafka    │─────>│   Ingestion      │
│   (Producer)     │      │  (Broker)   │      │   (Consumer)     │
└──────────────────┘      └─────────────┘      └────────┬─────────┘
                                                         │
                                                         │ Harmonisation
                                                         │ + Validation
                                                         ▼
                                                ┌──────────────────┐
                                                │   TimescaleDB    │
                                                │  (PostgreSQL)    │
                                                └──────────────────┘
```

## Configuration

### Dans docker-compose.yml

```yaml
timescaledb:
  image: timescale/timescaledb:latest-pg16
  container_name: agrotrace-timescaledb
  environment:
    POSTGRES_DB: agrotrace
    POSTGRES_USER: agrotrace_user
    POSTGRES_PASSWORD: agrotrace_pass
  ports:
    - "5432:5432"
  volumes:
    - timescaledb_data:/var/lib/postgresql/data
```

### Connexion depuis le microservice

- **Host**: `timescaledb` (nom du service Docker)
- **Port**: `5432`
- **Database**: `agrotrace`
- **User**: `agrotrace_user`
- **Password**: `agrotrace_pass`

## Schéma de la base de données

### Table principale : `sensor_data`

Cette table est une **hypertable** TimescaleDB optimisée pour les time-series.

```sql
CREATE TABLE sensor_data (
    id SERIAL PRIMARY KEY,
    sensor_type VARCHAR(100) NOT NULL,    -- Type de capteur
    timestamp TIMESTAMPTZ NOT NULL,       -- Horodatage de la mesure
    data_index INTEGER,                    -- Index de la donnée
    measurements JSONB NOT NULL,           -- Mesures au format JSON
    created_at TIMESTAMPTZ DEFAULT NOW()   -- Date d'insertion
);
```

### Index créés

- `idx_sensor_type` : Index sur le type de capteur pour les requêtes de filtrage
- `idx_timestamp` : Index sur le timestamp pour les requêtes temporelles
- Hypertable automatique : Partitionnement par timestamp

### Types de capteurs supportés

- **Environment Humidity** : Humidité environnementale (0-100%)
- **Temperature** : Température (-50 à 60°C)
- **Soil Moisture** : Humidité du sol (0-100%)
- **pH** : Niveau de pH (0-14)
- Et autres types selon les besoins

## Pipeline de traitement des données

### 1. Réception depuis Kafka

Le microservice `1-IngestionCapteurs` consomme les messages du topic `sensor-data`.

### 2. Harmonisation

La fonction `harmonize_data()` normalise les données :

- **Noms de champs** : Conversion en lowercase avec underscores
- **Types de données** : Conversion automatique string → float
- **Unités** : Nettoyage des unités (%, °C, °F)
- **Timestamp** : Normalisation en format ISO 8601
- **Valeurs manquantes** : Gestion de None, '', 'N/A'

**Exemple :**
```python
# Données brutes
{
    "sensor_type": "Temperature",
    "timestamp": "2025-11-30 14:30:00",
    "measurements": {
        "Temperature Value": "25.5°C",
        "Location": "Greenhouse A"
    }
}

# Après harmonisation
{
    "sensor_type": "Temperature",
    "timestamp": "2025-11-30T14:30:00",
    "measurements": {
        "temperature_value": 25.5,
        "location": "Greenhouse A"
    }
}
```

### 3. Validation

La fonction `validate_data()` vérifie la cohérence :

- **Type de capteur** : Présence et longueur < 100 caractères
- **Timestamp** : Format valide (ISO 8601)
- **Structure des mesures** : Format dictionnaire avec au moins une mesure
- **Plages de valeurs** :
  - Humidité : 0-100%
  - Température : -50 à 60°C
  - pH : 0-14
  - Humidité du sol : 0-100%

**Données invalides** : Rejetées avec message d'erreur dans les logs

### 4. Stockage

Insertion dans TimescaleDB avec gestion transactionnelle :

```sql
INSERT INTO sensor_data (sensor_type, timestamp, data_index, measurements)
VALUES ('Temperature', '2025-11-30T14:30:00', 42, '{"temperature_value": 25.5}')
```

## Fonctionnalités TimescaleDB utilisées

### Hypertable

Conversion automatique de la table en hypertable pour optimisation time-series :

```sql
SELECT create_hypertable('sensor_data', 'timestamp', if_not_exists => TRUE);
```

**Avantages** :
- Partitionnement automatique par temps
- Requêtes temporelles ultra-rapides
- Optimisation de l'espace disque

### Type JSONB

Les mesures sont stockées en JSONB pour :
- **Flexibilité** : Structure variable selon le capteur
- **Performance** : Indexation et requêtes sur les champs JSON
- **Requêtes** : Filtrage et agrégation sur les mesures

**Exemple de requête :**
```sql
-- Température moyenne par capteur
SELECT 
    sensor_type,
    AVG((measurements->>'temperature_value')::float) as avg_temp
FROM sensor_data
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY sensor_type;
```

## Connexion et pool de connexions

### Pool ThreadedConnectionPool

Le microservice utilise un pool de connexions psycopg2 :

```python
self.db_pool = psycopg2.pool.ThreadedConnectionPool(
    minconn=1,      # Minimum 1 connexion
    maxconn=10,     # Maximum 10 connexions
    host=config.DB_HOST,
    port=config.DB_PORT,
    database=config.DB_NAME,
    user=config.DB_USER,
    password=config.DB_PASSWORD
)
```

**Avantages** :
- Réutilisation des connexions
- Performance optimale
- Gestion automatique des connexions

## Initialisation de la base de données

### Script SQL : `init_db.sql`

Exécuté automatiquement au démarrage du microservice :

1. Active l'extension TimescaleDB
2. Crée la table `sensor_data`
3. Crée les index
4. Convertit en hypertable

### Exécution manuelle

Si besoin d'exécuter manuellement :

```bash
# Copier le script dans le conteneur
docker cp 1-IngestionCapteurs/init_db.sql agrotrace-timescaledb:/tmp/

# Se connecter au conteneur
docker exec -it agrotrace-timescaledb psql -U agrotrace_user -d agrotrace

# Exécuter le script
\i /tmp/init_db.sql
```

## Requêtes utiles

### Consulter les données récentes

```sql
-- 100 dernières mesures
SELECT * FROM sensor_data 
ORDER BY timestamp DESC 
LIMIT 100;
```

### Statistiques par type de capteur

```sql
SELECT 
    sensor_type,
    COUNT(*) as total_mesures,
    MIN(timestamp) as premiere_mesure,
    MAX(timestamp) as derniere_mesure
FROM sensor_data
GROUP BY sensor_type;
```

### Données d'un capteur spécifique

```sql
SELECT 
    timestamp,
    measurements
FROM sensor_data
WHERE sensor_type = 'Temperature'
AND timestamp > NOW() - INTERVAL '1 hour'
ORDER BY timestamp DESC;
```

### Mesures avec filtres sur JSONB

```sql
-- Températures supérieures à 30°C
SELECT 
    timestamp,
    sensor_type,
    (measurements->>'temperature_value')::float as temperature
FROM sensor_data
WHERE (measurements->>'temperature_value')::float > 30
ORDER BY timestamp DESC;
```

## Monitoring et maintenance

### Vérifier la santé de la base

```sql
-- Taille de la base de données
SELECT pg_size_pretty(pg_database_size('agrotrace'));

-- Nombre de lignes par hypertable
SELECT * FROM timescaledb_information.hypertables;

-- Chunks créés (partitions automatiques)
SELECT * FROM timescaledb_information.chunks 
WHERE hypertable_name = 'sensor_data';
```

### Logs du conteneur

```bash
# Voir les logs en temps réel
docker logs -f agrotrace-timescaledb

# Dernières 100 lignes
docker logs --tail 100 agrotrace-timescaledb
```

### Backup de la base

```bash
# Export complet
docker exec agrotrace-timescaledb pg_dump -U agrotrace_user agrotrace > backup.sql

# Restauration
docker exec -i agrotrace-timescaledb psql -U agrotrace_user agrotrace < backup.sql
```

## Optimisations futures (optionnelles)

### Politique de rétention

Supprimer automatiquement les données anciennes :

```sql
SELECT add_retention_policy('sensor_data', INTERVAL '1 year');
```

### Compression automatique

Compresser les données après 7 jours :

```sql
ALTER TABLE sensor_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'sensor_type'
);

SELECT add_compression_policy('sensor_data', INTERVAL '7 days');
```

### Agrégations continues

Pré-calculer des moyennes horaires/journalières :

```sql
CREATE MATERIALIZED VIEW sensor_data_hourly
WITH (timescaledb.continuous) AS
SELECT 
    sensor_type,
    time_bucket('1 hour', timestamp) AS bucket,
    AVG((measurements->>'temperature_value')::float) as avg_temp,
    COUNT(*) as measurements_count
FROM sensor_data
GROUP BY sensor_type, bucket;
```

## Résolution de problèmes

### Le microservice ne se connecte pas

1. Vérifier que TimescaleDB est démarré :
   ```bash
   docker ps | grep timescaledb
   ```

2. Vérifier les logs :
   ```bash
   docker logs agrotrace-timescaledb
   ```

3. Tester la connexion manuellement :
   ```bash
   docker exec -it agrotrace-timescaledb psql -U agrotrace_user -d agrotrace
   ```

### Erreur "table does not exist"

Exécuter manuellement le script `init_db.sql` (voir section Initialisation).

### Performances lentes

1. Vérifier les index :
   ```sql
   \d sensor_data
   ```

2. Analyser les requêtes lentes :
   ```sql
   SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;
   ```

3. Vérifier la mémoire du conteneur :
   ```bash
   docker stats agrotrace-timescaledb
   ```

## Références

- [Documentation TimescaleDB](https://docs.timescale.com/)
- [PostgreSQL JSONB](https://www.postgresql.org/docs/current/datatype-json.html)
- [psycopg2 Connection Pool](https://www.psycopg.org/docs/pool.html)
