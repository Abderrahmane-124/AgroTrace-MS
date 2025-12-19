-- ========================================
-- Schéma PostgreSQL pour MS6 - RecoIrrigation
-- ========================================

-- Table des zones d'irrigation
CREATE TABLE IF NOT EXISTS zones (
    zone_id VARCHAR(50) PRIMARY KEY,
    plot_id VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    area_hectares DECIMAL(10, 4) NOT NULL CHECK (area_hectares > 0),
    
    -- Propriétés agronomiques
    soil_type VARCHAR(20) NOT NULL CHECK (soil_type IN ('sandy', 'loamy', 'clay', 'organic')),
    crop_type VARCHAR(100) NOT NULL,
    growth_stage VARCHAR(20) NOT NULL CHECK (growth_stage IN ('germination', 'vegetative', 'flowering', 'fruiting', 'maturation')),
    planting_date DATE,
    
    -- Équipement
    irrigation_type VARCHAR(20) NOT NULL CHECK (irrigation_type IN ('drip', 'sprinkler', 'furrow', 'flood')),
    flow_rate_lpm DECIMAL(10, 2) NOT NULL CHECK (flow_rate_lpm > 0),
    equipment_name VARCHAR(200) NOT NULL,
    water_source VARCHAR(200) NOT NULL,
    
    -- Coûts
    water_cost_per_m3 DECIMAL(6, 2) DEFAULT 1.50 CHECK (water_cost_per_m3 >= 0),
    
    -- État actuel
    last_irrigation TIMESTAMP,
    soil_moisture_current DECIMAL(5, 2) CHECK (soil_moisture_current BETWEEN 0 AND 100),
    
    -- Métadonnées
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    active BOOLEAN DEFAULT TRUE
);

-- Table des plans d'irrigation
CREATE TABLE IF NOT EXISTS irrigation_plans (
    plan_id SERIAL PRIMARY KEY,
    zone_id VARCHAR(50) NOT NULL REFERENCES zones(zone_id),
    plot_id VARCHAR(50) NOT NULL,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMP NOT NULL,
    
    -- Contexte agronomique (snapshot au moment de la création)
    soil_type VARCHAR(20) NOT NULL,
    crop_type VARCHAR(100) NOT NULL,
    growth_stage VARCHAR(20) NOT NULL,
    irrigation_type VARCHAR(20) NOT NULL,
    
    -- Métriques
    total_volume_liters DECIMAL(12, 2) NOT NULL CHECK (total_volume_liters >= 0),
    estimated_cost_eur DECIMAL(10, 2) CHECK (estimated_cost_eur >= 0),
    water_source VARCHAR(200),
    
    -- Métadonnées
    recommendation_source VARCHAR(100) NOT NULL,
    notes TEXT,
    can_reschedule BOOLEAN DEFAULT TRUE,
    
    -- Statut
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'cancelled', 'expired'))
);

-- Table des sessions d'irrigation
CREATE TABLE IF NOT EXISTS irrigation_sessions (
    session_id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES irrigation_plans(plan_id) ON DELETE CASCADE,
    zone_id VARCHAR(50) NOT NULL REFERENCES zones(zone_id),
    
    -- Planification
    scheduled_date DATE NOT NULL,
    scheduled_time TIME NOT NULL,
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    
    -- Volumes et débits
    planned_volume_liters DECIMAL(12, 2) NOT NULL CHECK (planned_volume_liters >= 0),
    actual_volume_liters DECIMAL(12, 2) CHECK (actual_volume_liters >= 0),
    flow_rate_lpm DECIMAL(10, 2) NOT NULL CHECK (flow_rate_lpm > 0),
    
    -- Équipement
    equipment VARCHAR(200) NOT NULL,
    
    -- Exécution
    status VARCHAR(20) DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'in_progress', 'completed', 'cancelled', 'failed')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- Feedback
    success_rate DECIMAL(5, 2) CHECK (success_rate BETWEEN 0 AND 100),
    operator_notes TEXT,
    
    -- Métadonnées
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table historique des recommandations MS5 (pour analyse)
CREATE TABLE IF NOT EXISTS recommendations_log (
    log_id SERIAL PRIMARY KEY,
    plot_id VARCHAR(50) NOT NULL,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Données recommandation
    recommendation_type VARCHAR(50) NOT NULL,
    priority VARCHAR(20) NOT NULL,
    action VARCHAR(100) NOT NULL,
    details TEXT,
    source VARCHAR(50) NOT NULL,
    
    -- Données contextuelles
    quantity DECIMAL(10, 2),
    unit VARCHAR(20),
    soil_moisture DECIMAL(5, 2),
    temperature DECIMAL(5, 2),
    
    -- Traitement
    processed BOOLEAN DEFAULT FALSE,
    plan_id INTEGER REFERENCES irrigation_plans(plan_id)
);

-- Index pour performance
CREATE INDEX IF NOT EXISTS idx_zones_plot ON zones(plot_id);
CREATE INDEX IF NOT EXISTS idx_zones_active ON zones(active) WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_plans_zone ON irrigation_plans(zone_id);
CREATE INDEX IF NOT EXISTS idx_plans_status ON irrigation_plans(status);
CREATE INDEX IF NOT EXISTS idx_plans_valid ON irrigation_plans(valid_until);

CREATE INDEX IF NOT EXISTS idx_sessions_plan ON irrigation_sessions(plan_id);
CREATE INDEX IF NOT EXISTS idx_sessions_zone ON irrigation_sessions(zone_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON irrigation_sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_date ON irrigation_sessions(scheduled_date);

CREATE INDEX IF NOT EXISTS idx_reco_log_plot ON recommendations_log(plot_id);
CREATE INDEX IF NOT EXISTS idx_reco_log_received ON recommendations_log(received_at);
CREATE INDEX IF NOT EXISTS idx_reco_log_processed ON recommendations_log(processed);

-- Vue pour statistiques par zone
CREATE OR REPLACE VIEW zone_statistics AS
SELECT 
    z.zone_id,
    z.name,
    z.plot_id,
    COUNT(DISTINCT ip.plan_id) as total_plans,
    COUNT(DISTINCT CASE WHEN ip.status = 'active' THEN ip.plan_id END) as active_plans,
    SUM(CASE WHEN is_session.status = 'completed' THEN is_session.actual_volume_liters ELSE 0 END) as total_water_used_liters,
    COUNT(CASE WHEN is_session.status = 'completed' THEN 1 END) as completed_sessions,
    COUNT(CASE WHEN is_session.status = 'failed' THEN 1 END) as failed_sessions,
    AVG(is_session.success_rate) as avg_success_rate,
    MAX(is_session.completed_at) as last_irrigation,
    z.soil_moisture_current
FROM zones z
LEFT JOIN irrigation_plans ip ON z.zone_id = ip.zone_id
LEFT JOIN irrigation_sessions is_session ON ip.plan_id = is_session.plan_id
GROUP BY z.zone_id, z.name, z.plot_id, z.soil_moisture_current;

-- Fonction pour mettre à jour updated_at automatiquement
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers pour updated_at
CREATE TRIGGER update_zones_updated_at
    BEFORE UPDATE ON zones
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sessions_updated_at
    BEFORE UPDATE ON irrigation_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ========================================
-- DONNÉES DE DÉMONSTRATION
-- ========================================

-- Zones exemple
INSERT INTO zones (zone_id, plot_id, name, area_hectares, soil_type, crop_type, growth_stage, 
                   irrigation_type, flow_rate_lpm, equipment_name, water_source, soil_moisture_current) VALUES
('ZONE-NORTH-01', 'PLOT-001', 'Parcelle Nord - Tomates', 2.5, 'loamy', 'Tomato', 'flowering', 
 'drip', 200.0, 'Système goutte-à-goutte Nord', 'Puits #1', 45.0),
 
('ZONE-SOUTH-01', 'PLOT-002', 'Parcelle Sud - Maïs', 5.0, 'clay', 'Corn', 'vegetative', 
 'sprinkler', 350.0, 'Asperseurs pivotants Sud', 'Réservoir principal', 38.0),
 
('ZONE-EAST-01', 'PLOT-003', 'Parcelle Est - Laitue', 1.2, 'sandy', 'Lettuce', 'vegetative', 
 'drip', 150.0, 'Goutte-à-goutte Est', 'Puits #2', 55.0)
ON CONFLICT (zone_id) DO NOTHING;

COMMIT;
