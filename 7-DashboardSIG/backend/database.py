# ========================================
# Connexion PostGIS et requêtes spatiales
# ========================================

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from config import (
    POSTGIS_HOST, POSTGIS_PORT, POSTGIS_DB, 
    POSTGIS_USER, POSTGIS_PASSWORD
)


class DatabaseManager:
    """Gestionnaire de connexion PostGIS avec pool de connexions"""
    
    _instance = None
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize_pool(self, min_conn=2, max_conn=10):
        """Initialise le pool de connexions"""
        if self._pool is None:
            try:
                self._pool = pool.ThreadedConnectionPool(
                    min_conn, max_conn,
                    host=POSTGIS_HOST,
                    port=POSTGIS_PORT,
                    database=POSTGIS_DB,
                    user=POSTGIS_USER,
                    password=POSTGIS_PASSWORD
                )
                print(f"✅ Pool PostGIS initialisé ({min_conn}-{max_conn} connexions)")
            except Exception as e:
                print(f"❌ Erreur initialisation pool: {e}")
                raise
    
    @contextmanager
    def get_connection(self):
        """Context manager pour obtenir une connexion du pool"""
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self._pool.putconn(conn)
    
    def close_pool(self):
        """Ferme le pool de connexions"""
        if self._pool:
            self._pool.closeall()
            print("🔌 Pool PostGIS fermé")


db_manager = DatabaseManager()


def init_database():
    """Initialise le schéma de base de données PostGIS"""
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            # Activer l'extension PostGIS
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            
            # Table des parcelles
            cur.execute("""
                CREATE TABLE IF NOT EXISTS parcels (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    culture_type VARCHAR(100),
                    area_hectares FLOAT DEFAULT 0,
                    geometry GEOMETRY(Polygon, 4326),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Table de l'état actuel des parcelles
            cur.execute("""
                CREATE TABLE IF NOT EXISTS parcel_status (
                    id SERIAL PRIMARY KEY,
                    parcel_id INTEGER REFERENCES parcels(id),
                    health_status VARCHAR(20) DEFAULT 'HEALTHY',
                    water_stress_level FLOAT DEFAULT 0,
                    soil_moisture FLOAT,
                    temperature FLOAT,
                    humidity FLOAT,
                    disease_detected VARCHAR(255),
                    disease_confidence FLOAT,
                    last_recommendation TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(parcel_id)
                );
            """)
            
            # Table des prévisions
            cur.execute("""
                CREATE TABLE IF NOT EXISTS water_forecasts (
                    id SERIAL PRIMARY KEY,
                    parcel_id INTEGER REFERENCES parcels(id),
                    forecast_date DATE NOT NULL,
                    predicted_need FLOAT,
                    stress_level VARCHAR(20),
                    confidence FLOAT,
                    recommendation TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Table des détections de maladies
            cur.execute("""
                CREATE TABLE IF NOT EXISTS disease_detections (
                    id SERIAL PRIMARY KEY,
                    parcel_id INTEGER REFERENCES parcels(id),
                    disease_name VARCHAR(255) NOT NULL,
                    confidence FLOAT,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    treatment_recommendation TEXT,
                    image_url TEXT,
                    resolved BOOLEAN DEFAULT FALSE
                );
            """)
            
            # Table des recommandations
            cur.execute("""
                CREATE TABLE IF NOT EXISTS recommendations (
                    id SERIAL PRIMARY KEY,
                    parcel_id INTEGER REFERENCES parcels(id),
                    type VARCHAR(50) NOT NULL,
                    priority VARCHAR(20) DEFAULT 'MEDIUM',
                    action_code VARCHAR(100),
                    description TEXT,
                    quantity FLOAT,
                    unit VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    completed BOOLEAN DEFAULT FALSE
                );
            """)
            
            # Index spatial
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_parcels_geometry 
                ON parcels USING GIST(geometry);
            """)
            
            # Insérer des parcelles de démonstration si vide
            cur.execute("SELECT COUNT(*) FROM parcels;")
            if cur.fetchone()[0] == 0:
                _insert_demo_data(cur)
            
            print("✅ Schéma PostGIS initialisé")


def _insert_demo_data(cursor):
    """Insère des données de démonstration"""
    # Parcelles de démonstration (coordonnées fictives au Maroc)
    demo_parcels = [
        ("Parcelle Nord - Blé", "Blé", 12.5, 
         "POLYGON((-7.62 33.58, -7.60 33.58, -7.60 33.56, -7.62 33.56, -7.62 33.58))"),
        ("Parcelle Est - Tomates", "Tomate", 8.3,
         "POLYGON((-7.58 33.57, -7.56 33.57, -7.56 33.55, -7.58 33.55, -7.58 33.57))"),
        ("Parcelle Sud - Maïs", "Maïs", 15.0,
         "POLYGON((-7.61 33.54, -7.59 33.54, -7.59 33.52, -7.61 33.52, -7.61 33.54))"),
        ("Parcelle Ouest - Oliviers", "Olivier", 20.0,
         "POLYGON((-7.65 33.56, -7.63 33.56, -7.63 33.54, -7.65 33.54, -7.65 33.56))"),
        ("Parcelle Centre - Agrumes", "Agrumes", 10.0,
         "POLYGON((-7.60 33.56, -7.58 33.56, -7.58 33.54, -7.60 33.54, -7.60 33.56))"),
    ]
    
    for name, culture, area, geom in demo_parcels:
        cursor.execute("""
            INSERT INTO parcels (name, culture_type, area_hectares, geometry)
            VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326))
            RETURNING id;
        """, (name, culture, area, geom))
        parcel_id = cursor.fetchone()[0]
        
        # État initial
        import random
        statuses = ['HEALTHY', 'LOW', 'MODERATE', 'HIGH', 'CRITICAL']
        cursor.execute("""
            INSERT INTO parcel_status 
            (parcel_id, health_status, water_stress_level, soil_moisture, temperature)
            VALUES (%s, %s, %s, %s, %s);
        """, (
            parcel_id,
            random.choice(statuses),
            random.uniform(0, 80),
            random.uniform(20, 70),
            random.uniform(15, 35)
        ))
    
    print("📊 Données de démonstration insérées")


def get_all_parcels() -> List[Dict[str, Any]]:
    """Récupère toutes les parcelles avec leur état"""
    with db_manager.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    p.id, p.name, p.culture_type, p.area_hectares,
                    ST_AsGeoJSON(p.geometry)::json as geometry,
                    COALESCE(ps.health_status, 'HEALTHY') as health_status,
                    COALESCE(ps.water_stress_level, 0) as water_stress_level,
                    ps.soil_moisture, ps.temperature,
                    ps.disease_detected, ps.disease_confidence,
                    ps.last_recommendation as recommendation,
                    COALESCE(ps.updated_at, p.created_at) as last_updated
                FROM parcels p
                LEFT JOIN parcel_status ps ON p.id = ps.parcel_id
                ORDER BY p.id;
            """)
            return cur.fetchall()


def get_parcel_detail(parcel_id: int) -> Optional[Dict[str, Any]]:
    """Récupère le détail d'une parcelle avec historique"""
    with db_manager.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Info parcelle
            cur.execute("""
                SELECT 
                    p.id, p.name, p.culture_type, p.area_hectares,
                    ST_AsGeoJSON(p.geometry)::json as geometry,
                    COALESCE(ps.health_status, 'HEALTHY') as health_status,
                    COALESCE(ps.water_stress_level, 0) as water_stress_level,
                    ps.soil_moisture, ps.temperature,
                    ps.disease_detected, ps.disease_confidence,
                    ps.last_recommendation as recommendation,
                    COALESCE(ps.updated_at, p.created_at) as last_updated
                FROM parcels p
                LEFT JOIN parcel_status ps ON p.id = ps.parcel_id
                WHERE p.id = %s;
            """, (parcel_id,))
            parcel = cur.fetchone()
            
            if not parcel:
                return None
            
            # Prévisions récentes
            cur.execute("""
                SELECT forecast_date, predicted_need, stress_level, 
                       confidence, recommendation
                FROM water_forecasts
                WHERE parcel_id = %s AND forecast_date >= CURRENT_DATE
                ORDER BY forecast_date
                LIMIT 7;
            """, (parcel_id,))
            parcel['forecasts'] = cur.fetchall()
            
            # Recommandations actives
            cur.execute("""
                SELECT type, priority, action_code, description, 
                       quantity, unit, created_at
                FROM recommendations
                WHERE parcel_id = %s AND completed = FALSE
                ORDER BY 
                    CASE priority 
                        WHEN 'CRITICAL' THEN 1 
                        WHEN 'HIGH' THEN 2 
                        WHEN 'MODERATE' THEN 3 
                        ELSE 4 
                    END
                LIMIT 10;
            """, (parcel_id,))
            parcel['recommendations'] = cur.fetchall()
            
            return parcel


def get_water_forecasts() -> List[Dict[str, Any]]:
    """Récupère les prévisions hydriques actuelles"""
    with db_manager.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    wf.id, wf.parcel_id, p.name as parcel_name,
                    wf.forecast_date, wf.predicted_need, wf.stress_level,
                    wf.confidence, wf.recommendation
                FROM water_forecasts wf
                JOIN parcels p ON wf.parcel_id = p.id
                WHERE wf.forecast_date >= CURRENT_DATE
                ORDER BY wf.forecast_date, wf.stress_level DESC;
            """)
            return cur.fetchall()


def get_disease_detections() -> List[Dict[str, Any]]:
    """Récupère les détections de maladies non résolues"""
    with db_manager.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    dd.id, dd.parcel_id, p.name as parcel_name,
                    dd.disease_name, dd.confidence, dd.detected_at,
                    dd.treatment_recommendation, dd.image_url
                FROM disease_detections dd
                JOIN parcels p ON dd.parcel_id = p.id
                WHERE dd.resolved = FALSE
                ORDER BY dd.detected_at DESC;
            """)
            return cur.fetchall()


def get_active_recommendations() -> List[Dict[str, Any]]:
    """Récupère les recommandations actives"""
    with db_manager.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    r.id, r.parcel_id, p.name as parcel_name,
                    r.type, r.priority, r.action_code, r.description,
                    r.quantity, r.unit, r.created_at, r.expires_at
                FROM recommendations r
                JOIN parcels p ON r.parcel_id = p.id
                WHERE r.completed = FALSE
                ORDER BY 
                    CASE r.priority 
                        WHEN 'CRITICAL' THEN 1 
                        WHEN 'HIGH' THEN 2 
                        WHEN 'MODERATE' THEN 3 
                        ELSE 4 
                    END,
                    r.created_at DESC;
            """)
            return cur.fetchall()


def get_dashboard_stats() -> Dict[str, Any]:
    """Récupère les statistiques du tableau de bord"""
    with db_manager.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_parcels,
                    COUNT(*) FILTER (WHERE ps.health_status = 'CRITICAL') as parcels_critical,
                    COUNT(*) FILTER (WHERE ps.health_status = 'HIGH') as parcels_high_stress,
                    COUNT(*) FILTER (WHERE ps.health_status = 'MODERATE') as parcels_moderate,
                    COUNT(*) FILTER (WHERE ps.health_status IN ('LOW', 'HEALTHY')) as parcels_healthy,
                    COALESCE(AVG(ps.soil_moisture), 0) as avg_soil_moisture,
                    COALESCE(AVG(ps.temperature), 0) as avg_temperature
                FROM parcels p
                LEFT JOIN parcel_status ps ON p.id = ps.parcel_id;
            """)
            stats = cur.fetchone()
            
            # Alertes maladies
            cur.execute("SELECT COUNT(*) FROM disease_detections WHERE resolved = FALSE;")
            stats['active_disease_alerts'] = cur.fetchone()[0]
            
            # Recommandations en attente
            cur.execute("SELECT COUNT(*) FROM recommendations WHERE completed = FALSE;")
            stats['pending_recommendations'] = cur.fetchone()[0]
            
            return stats


def update_parcel_status(parcel_id: int, data: Dict[str, Any]):
    """Met à jour l'état d'une parcelle"""
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO parcel_status 
                (parcel_id, health_status, water_stress_level, soil_moisture, 
                 temperature, humidity, disease_detected, disease_confidence,
                 last_recommendation, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (parcel_id) 
                DO UPDATE SET
                    health_status = COALESCE(EXCLUDED.health_status, parcel_status.health_status),
                    water_stress_level = COALESCE(EXCLUDED.water_stress_level, parcel_status.water_stress_level),
                    soil_moisture = COALESCE(EXCLUDED.soil_moisture, parcel_status.soil_moisture),
                    temperature = COALESCE(EXCLUDED.temperature, parcel_status.temperature),
                    humidity = COALESCE(EXCLUDED.humidity, parcel_status.humidity),
                    disease_detected = COALESCE(EXCLUDED.disease_detected, parcel_status.disease_detected),
                    disease_confidence = COALESCE(EXCLUDED.disease_confidence, parcel_status.disease_confidence),
                    last_recommendation = COALESCE(EXCLUDED.last_recommendation, parcel_status.last_recommendation),
                    updated_at = CURRENT_TIMESTAMP;
            """, (
                parcel_id,
                data.get('health_status'),
                data.get('water_stress_level'),
                data.get('soil_moisture'),
                data.get('temperature'),
                data.get('humidity'),
                data.get('disease_detected'),
                data.get('disease_confidence'),
                data.get('recommendation')
            ))


def add_water_forecast(parcel_id: int, data: Dict[str, Any]):
    """Ajoute une prévision hydrique"""
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO water_forecasts 
                (parcel_id, forecast_date, predicted_need, stress_level, 
                 confidence, recommendation)
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (
                parcel_id,
                data.get('forecast_date'),
                data.get('predicted_need'),
                data.get('stress_level'),
                data.get('confidence'),
                data.get('recommendation')
            ))


def add_disease_detection(parcel_id: int, data: Dict[str, Any]):
    """Ajoute une détection de maladie"""
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO disease_detections 
                (parcel_id, disease_name, confidence, treatment_recommendation, image_url)
                VALUES (%s, %s, %s, %s, %s);
            """, (
                parcel_id,
                data.get('disease_name'),
                data.get('confidence'),
                data.get('treatment_recommendation'),
                data.get('image_url')
            ))


def add_recommendation(parcel_id: int, data: Dict[str, Any]):
    """Ajoute une recommandation"""
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO recommendations 
                (parcel_id, type, priority, action_code, description, 
                 quantity, unit, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                parcel_id,
                data.get('type'),
                data.get('priority'),
                data.get('action_code'),
                data.get('description'),
                data.get('quantity'),
                data.get('unit'),
                data.get('expires_at')
            ))


def get_export_data(parcel_ids: Optional[List[int]] = None, 
                    start_date: Optional[datetime] = None,
                    end_date: Optional[datetime] = None) -> Dict[str, Any]:
    """Récupère les données pour export"""
    with db_manager.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Construire la requête parcelles
            query = """
                SELECT 
                    p.id, p.name, p.culture_type, p.area_hectares,
                    ps.health_status, ps.water_stress_level,
                    ps.soil_moisture, ps.temperature, ps.humidity,
                    ps.disease_detected, ps.updated_at
                FROM parcels p
                LEFT JOIN parcel_status ps ON p.id = ps.parcel_id
                WHERE 1=1
            """
            params = []
            
            if parcel_ids:
                query += " AND p.id = ANY(%s)"
                params.append(parcel_ids)
            
            cur.execute(query, params)
            parcels = cur.fetchall()
            
            # Recommandations
            rec_query = """
                SELECT r.*, p.name as parcel_name
                FROM recommendations r
                JOIN parcels p ON r.parcel_id = p.id
                WHERE r.completed = FALSE
            """
            if parcel_ids:
                rec_query += " AND r.parcel_id = ANY(%s)"
                cur.execute(rec_query, [parcel_ids])
            else:
                cur.execute(rec_query)
            recommendations = cur.fetchall()
            
            # Prévisions
            forecast_query = """
                SELECT wf.*, p.name as parcel_name
                FROM water_forecasts wf
                JOIN parcels p ON wf.parcel_id = p.id
                WHERE wf.forecast_date >= CURRENT_DATE
            """
            if parcel_ids:
                forecast_query += " AND wf.parcel_id = ANY(%s)"
                cur.execute(forecast_query, [parcel_ids])
            else:
                cur.execute(forecast_query)
            forecasts = cur.fetchall()
            
            return {
                'parcels': parcels,
                'recommendations': recommendations,
                'forecasts': forecasts,
                'generated_at': datetime.now().isoformat()
            }
