-- Initialisation de la base de données AgroTrace pour TimescaleDB
-- Ce script crée la structure de base pour stocker les données des capteurs

-- Activer l'extension TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Table principale pour les données des capteurs
CREATE TABLE IF NOT EXISTS sensor_data (
    id SERIAL PRIMARY KEY,
    sensor_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    data_index INTEGER,
    measurements JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Créer un index sur sensor_type pour les requêtes de filtrage
CREATE INDEX IF NOT EXISTS idx_sensor_type ON sensor_data(sensor_type);

-- Créer un index sur timestamp pour les requêtes temporelles
CREATE INDEX IF NOT EXISTS idx_timestamp ON sensor_data(timestamp);

-- Convertir la table en hypertable TimescaleDB (optimisation time-series)
-- La partition se fait automatiquement par timestamp
SELECT create_hypertable('sensor_data', 'timestamp', if_not_exists => TRUE);

-- Créer une politique de rétention (optionnel - garde 1 an de données)
-- SELECT add_retention_policy('sensor_data', INTERVAL '1 year', if_not_exists => TRUE);

-- Créer une politique de compression (optionnel - compresse après 7 jours)
-- ALTER TABLE sensor_data SET (
--     timescaledb.compress,
--     timescaledb.compress_segmentby = 'sensor_type'
-- );
-- SELECT add_compression_policy('sensor_data', INTERVAL '7 days', if_not_exists => TRUE);

COMMENT ON TABLE sensor_data IS 'Données des capteurs agricoles avec optimisation time-series via TimescaleDB';
COMMENT ON COLUMN sensor_data.sensor_type IS 'Type de capteur (Environment Humidity, Temperature, Soil Moisture, pH, etc.)';
COMMENT ON COLUMN sensor_data.timestamp IS 'Horodatage de la mesure du capteur';
COMMENT ON COLUMN sensor_data.data_index IS 'Index de la donnée dans la source';
COMMENT ON COLUMN sensor_data.measurements IS 'Mesures du capteur au format JSONB (flexible, indexable)';
COMMENT ON COLUMN sensor_data.created_at IS 'Date d''insertion dans la base de données';
