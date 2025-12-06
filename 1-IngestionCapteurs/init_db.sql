-- Initialisation de la base de données AgroTrace pour TimescaleDB
-- Ce script crée la structure de base pour stocker les données des capteurs
-- Version: 2.0 - Supporte MS1 (Ingestion) et MS2 (Prétraitement)

-- Activer l'extension TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================================
-- TABLE 1: sensor_data (Utilisée par MS1 - IngestionCapteurs)
-- ============================================================================
-- Table principale pour les données des capteurs (format JSONB flexible)
CREATE TABLE IF NOT EXISTS sensor_data (
    id SERIAL,
    sensor_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    data_index INTEGER,
    measurements JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (timestamp, id)
);

-- Créer un index sur sensor_type pour les requêtes de filtrage
CREATE INDEX IF NOT EXISTS idx_sensor_type ON sensor_data(sensor_type);

-- Créer un index sur timestamp pour les requêtes temporelles
CREATE INDEX IF NOT EXISTS idx_timestamp ON sensor_data(timestamp DESC);

-- Convertir la table en hypertable TimescaleDB (optimisation time-series)
SELECT create_hypertable('sensor_data', 'timestamp', if_not_exists => TRUE);

COMMENT ON TABLE sensor_data IS 'Données des capteurs agricoles avec optimisation time-series via TimescaleDB (MS1 - Ingestion)';
COMMENT ON COLUMN sensor_data.sensor_type IS 'Type de capteur (Environment Humidity, Temperature, Soil Moisture, pH, etc.)';
COMMENT ON COLUMN sensor_data.timestamp IS 'Horodatage de la mesure du capteur';
COMMENT ON COLUMN sensor_data.data_index IS 'Index de la donnée dans la source';
COMMENT ON COLUMN sensor_data.measurements IS 'Mesures du capteur au format JSONB (flexible, indexable)';
COMMENT ON COLUMN sensor_data.created_at IS 'Date d''insertion dans la base de données';

-- ============================================================================
-- TABLE 2: sensor_data_processed (Utilisée par MS2 - Prétraitement)
-- ============================================================================
-- Table pour les données nettoyées, normalisées et enrichies
CREATE TABLE IF NOT EXISTS sensor_data_processed (
    id SERIAL,
    sensor_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    
    -- Valeurs brutes (pour référence)
    raw_value DOUBLE PRECISION,
    
    -- Valeurs nettoyées (anomalies corrigées)
    clean_value DOUBLE PRECISION,
    
    -- Valeurs normalisées [0-1]
    normalized_value DOUBLE PRECISION,
    
    -- Features calculées
    moving_average DOUBLE PRECISION,
    
    -- Métadonnées de qualité
    quality_score DOUBLE PRECISION DEFAULT 1.0,
    is_anomaly BOOLEAN DEFAULT FALSE,
    missing_data_filled BOOLEAN DEFAULT FALSE,
    
    -- Timestamps de traitement
    processing_timestamp TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Clé primaire composite
    PRIMARY KEY (timestamp, sensor_type, id)
);

-- Index pour optimiser les requêtes sur sensor_type
CREATE INDEX IF NOT EXISTS idx_processed_sensor_type ON sensor_data_processed(sensor_type);

-- Index pour les requêtes temporelles
CREATE INDEX IF NOT EXISTS idx_processed_timestamp ON sensor_data_processed(timestamp DESC);

-- Index pour filtrer par qualité
CREATE INDEX IF NOT EXISTS idx_processed_quality ON sensor_data_processed(quality_score);

-- Index pour filtrer les anomalies
CREATE INDEX IF NOT EXISTS idx_processed_anomaly ON sensor_data_processed(is_anomaly) WHERE is_anomaly = TRUE;

-- Index composite pour les requêtes courantes (sensor + temps)
CREATE INDEX IF NOT EXISTS idx_processed_sensor_time ON sensor_data_processed(sensor_type, timestamp DESC);

-- Convertir en hypertable TimescaleDB
SELECT create_hypertable('sensor_data_processed', 'timestamp', if_not_exists => TRUE);

COMMENT ON TABLE sensor_data_processed IS 'Données des capteurs prétraitées (nettoyées, normalisées, enrichies) par MS2 - Prétraitement';
COMMENT ON COLUMN sensor_data_processed.sensor_type IS 'Type de capteur traité';
COMMENT ON COLUMN sensor_data_processed.timestamp IS 'Horodatage de la mesure originale';
COMMENT ON COLUMN sensor_data_processed.raw_value IS 'Valeur brute originale avant traitement';
COMMENT ON COLUMN sensor_data_processed.clean_value IS 'Valeur après nettoyage (anomalies corrigées, valeurs manquantes remplies)';
COMMENT ON COLUMN sensor_data_processed.normalized_value IS 'Valeur normalisée entre 0 et 1 selon les plages définies';
COMMENT ON COLUMN sensor_data_processed.moving_average IS 'Moyenne mobile calculée sur une fenêtre glissante';
COMMENT ON COLUMN sensor_data_processed.quality_score IS 'Score de qualité de la donnée (0.0 = mauvais, 1.0 = excellent)';
COMMENT ON COLUMN sensor_data_processed.is_anomaly IS 'TRUE si une anomalie a été détectée dans la valeur brute';
COMMENT ON COLUMN sensor_data_processed.missing_data_filled IS 'TRUE si la valeur a été interpolée/remplie';
COMMENT ON COLUMN sensor_data_processed.processing_timestamp IS 'Date et heure du traitement par le microservice';

-- ============================================================================
-- POLITIQUES DE RÉTENTION ET COMPRESSION (Optionnel)
-- ============================================================================

-- Politique de rétention: garde 1 an de données brutes
-- SELECT add_retention_policy('sensor_data', INTERVAL '1 year', if_not_exists => TRUE);

-- Politique de rétention: garde 2 ans de données traitées (plus précieuses)
-- SELECT add_retention_policy('sensor_data_processed', INTERVAL '2 years', if_not_exists => TRUE);

-- Compression des données anciennes pour économiser l'espace
-- ALTER TABLE sensor_data SET (
--     timescaledb.compress,
--     timescaledb.compress_segmentby = 'sensor_type'
-- );
-- SELECT add_compression_policy('sensor_data', INTERVAL '7 days', if_not_exists => TRUE);

-- ALTER TABLE sensor_data_processed SET (
--     timescaledb.compress,
--     timescaledb.compress_segmentby = 'sensor_type'
-- );
-- SELECT add_compression_policy('sensor_data_processed', INTERVAL '30 days', if_not_exists => TRUE);

-- ============================================================================
-- VUE UTILITAIRE: Jointure entre données brutes et traitées
-- ============================================================================
CREATE OR REPLACE VIEW sensor_data_comparison AS
SELECT 
    r.sensor_type,
    r.timestamp,
    r.measurements->>'Temperature (°C)' AS raw_temperature,
    p.clean_value AS clean_temperature,
    p.normalized_value AS normalized_temperature,
    p.moving_average,
    p.quality_score,
    p.is_anomaly
FROM sensor_data r
LEFT JOIN sensor_data_processed p 
    ON r.sensor_type = p.sensor_type 
    AND r.timestamp = p.timestamp
ORDER BY r.timestamp DESC;

COMMENT ON VIEW sensor_data_comparison IS 'Vue pour comparer facilement les données brutes et traitées';
