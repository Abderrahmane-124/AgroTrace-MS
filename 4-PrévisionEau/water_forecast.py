"""
Microservice MS4 - PrévisionEau
Prévision du besoin en eau et du stress hydrique à court terme (1-7 jours)
Utilise Prophet pour la prévision de séries temporelles
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
from prophet import Prophet
import warnings

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

import config

# Supprimer les warnings de Prophet
warnings.filterwarnings('ignore')


class WaterForecastService:
    """
    Service de prévision du besoin en eau
    - Lit les données capteurs depuis TimescaleDB
    - Entraîne des modèles Prophet par type de capteur
    - Génère des prévisions de stress hydrique (1-7 jours)
    - Publie les prévisions dans Kafka et TimescaleDB
    """
    
    def __init__(self):
        self.kafka_bootstrap_servers = config.KAFKA_BOOTSTRAP_SERVERS
        self.kafka_sensor_topic = config.KAFKA_SENSOR_TOPIC
        self.kafka_forecast_topic = config.KAFKA_FORECAST_TOPIC
        self.kafka_group_id = config.KAFKA_GROUP_ID
        
        self.consumer = None
        self.producer = None
        self.db_pool = None
        
        # Modèles Prophet par type de capteur
        self.models = {}
        self.last_training_time = {}
        
        # Statistiques
        self.forecasts_generated = 0
        self.errors_count = 0
        
        print(f"💧 WaterForecast Service - Initialisation")
        print(f"   📊 Horizon de prévision: {config.FORECAST_HORIZON} jours")
        print(f"   🔄 Réentraînement: toutes les {config.RETRAINING_INTERVAL_HOURS}h")
    
    def init_database_pool(self):
        """Initialiser le pool de connexions TimescaleDB"""
        print(f"\n🔌 Connexion à TimescaleDB: {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
        
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.db_pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=10,
                    host=config.DB_HOST,
                    port=config.DB_PORT,
                    database=config.DB_NAME,
                    user=config.DB_USER,
                    password=config.DB_PASSWORD,
                    connect_timeout=10
                )
                print("✅ Connexion TimescaleDB établie")
                
                # Initialiser le schéma
                self._init_database_schema()
                return True
                
            except Exception as e:
                retry_count += 1
                print(f"✗ Tentative {retry_count}/{max_retries} - Erreur DB: {e}")
                if retry_count < max_retries:
                    print(f"  Nouvelle tentative dans 5 secondes...")
                    time.sleep(5)
        
        print("✗ Impossible de se connecter à TimescaleDB")
        return False
    
    def _init_database_schema(self):
        """Créer la table water_forecast si elle n'existe pas"""
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Table pour les prévisions d'eau
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS water_forecast (
                        id SERIAL,
                        forecast_date TIMESTAMPTZ NOT NULL,
                        target_date TIMESTAMPTZ NOT NULL,
                        sensor_type VARCHAR(100) NOT NULL,
                        
                        -- Prévisions
                        predicted_value FLOAT,
                        lower_bound FLOAT,
                        upper_bound FLOAT,
                        
                        -- Indicateurs de stress hydrique
                        water_stress_level VARCHAR(50),
                        water_stress_score FLOAT,
                        irrigation_recommended BOOLEAN DEFAULT FALSE,
                        
                        -- Métadonnées
                        horizon_days INTEGER,
                        model_confidence FLOAT,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        
                        PRIMARY KEY (forecast_date, target_date, sensor_type)
                    );
                """)
                
                # Index
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_water_forecast_target_date 
                    ON water_forecast(target_date DESC);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_water_forecast_sensor_type 
                    ON water_forecast(sensor_type);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_water_forecast_stress_level 
                    ON water_forecast(water_stress_level);
                """)
                
                # Hypertable TimescaleDB
                cursor.execute("""
                    SELECT create_hypertable('water_forecast', 'forecast_date', 
                                            if_not_exists => TRUE);
                """)
                
                conn.commit()
                print("✅ Schéma water_forecast initialisé")
                
        except Exception as e:
            print(f"⚠️  Erreur initialisation schéma: {e}")
            conn.rollback()
        finally:
            self.db_pool.putconn(conn)
    
    def init_kafka(self):
        """Initialiser les connexions Kafka"""
        print(f"\n🔌 Connexion à Kafka: {self.kafka_bootstrap_servers}")
        
        try:
            # Consumer (optionnel - pour écouter les nouvelles données)
            self.consumer = KafkaConsumer(
                self.kafka_sensor_topic,
                bootstrap_servers=self.kafka_bootstrap_servers,
                group_id=self.kafka_group_id,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',
                enable_auto_commit=True,
                consumer_timeout_ms=1000
            )
            
            # Producer pour publier les prévisions
            self.producer = KafkaProducer(
                bootstrap_servers=self.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                retries=3
            )
            
            print("✅ Kafka initialisé")
            print(f"   📥 Consumer topic: {self.kafka_sensor_topic}")
            print(f"   📤 Producer topic: {self.kafka_forecast_topic}")
            
        except Exception as e:
            print(f"❌ Erreur connexion Kafka: {e}")
            raise
    
    def fetch_sensor_data(self, sensor_type: str, days: int = None) -> pd.DataFrame:
        """
        Récupérer les données historiques d'un capteur depuis TimescaleDB
        
        Args:
            sensor_type: Type de capteur (ex: 'Soil Moisture')
            days: Nombre de jours d'historique (défaut: TRAINING_WINDOW_DAYS)
        
        Returns:
            DataFrame avec colonnes ['ds', 'y'] pour Prophet
        """
        days = days or config.TRAINING_WINDOW_DAYS
        
        conn = self.db_pool.getconn()
        try:
            # Construire des filtres spécifiques selon le type de capteur
            if 'Humidity' in sensor_type or 'Moisture' in sensor_type:
                # Pour humidité/moisture, valeurs entre 0.1 et 100
                value_filter = "AND clean_value > 0.1 AND clean_value <= 100"
            elif 'Temperature' in sensor_type:
                # Pour température, valeurs réalistes
                value_filter = "AND clean_value > -50 AND clean_value < 60"
            elif 'pH' in sensor_type:
                # Pour pH
                value_filter = "AND clean_value > 0 AND clean_value <= 14"
            elif 'Light' in sensor_type or 'Intensity' in sensor_type:
                # Pour lumière
                value_filter = "AND clean_value > 0 AND clean_value < 100000"
            elif 'Voltage' in sensor_type:
                # Pour voltage
                value_filter = "AND clean_value > 0 AND clean_value < 50"
            elif 'TDS' in sensor_type:
                # Pour TDS
                value_filter = "AND clean_value > 0 AND clean_value < 5000"
            else:
                # Filtre général
                value_filter = "AND clean_value > 0.01"
            
            query = f"""
                SELECT 
                    timestamp as ds,
                    clean_value as y
                FROM sensor_data_processed
                WHERE sensor_type = %s
                    AND timestamp >= NOW() - INTERVAL '%s days'
                    AND clean_value IS NOT NULL
                    {value_filter}
                ORDER BY timestamp ASC
            """
            
            df = pd.read_sql_query(
                query,
                conn,
                params=(sensor_type, days)
            )
            
            # Retirer le timezone pour Prophet (ne supporte pas timezone-aware datetimes)
            if not df.empty and 'ds' in df.columns:
                df['ds'] = pd.to_datetime(df['ds']).dt.tz_localize(None)
                
                # Debug: afficher les statistiques des données
                if len(df) > 0:
                    print(f"   📊 Valeurs: min={df['y'].min():.2f}, max={df['y'].max():.2f}, mean={df['y'].mean():.2f}")
            
            return df
            
        except Exception as e:
            print(f"❌ Erreur récupération données {sensor_type}: {e}")
            return pd.DataFrame()
        finally:
            self.db_pool.putconn(conn)
    
    def train_prophet_model(self, sensor_type: str) -> Optional[Prophet]:
        """
        Entraîner un modèle Prophet pour un type de capteur
        
        Args:
            sensor_type: Type de capteur
        
        Returns:
            Modèle Prophet entraîné ou None si erreur
        """
        try:
            print(f"\n🤖 Entraînement modèle Prophet: {sensor_type}")
            
            # Récupérer les données
            df = self.fetch_sensor_data(sensor_type)
            
            if len(df) < config.MIN_DATA_POINTS:
                print(f"⚠️  Pas assez de données ({len(df)} < {config.MIN_DATA_POINTS})")
                return None
            
            print(f"   📊 {len(df)} points de données")
            
            # Créer et entraîner le modèle Prophet
            # Désactiver les logs de stan pour éviter les warnings
            import logging
            logging.getLogger('cmdstanpy').setLevel(logging.ERROR)
            logging.getLogger('prophet').setLevel(logging.ERROR)
            
            model = Prophet(
                daily_seasonality=True,
                weekly_seasonality=True,
                yearly_seasonality=False,
                changepoint_prior_scale=0.05,
                interval_width=0.95
                # Ne pas désactiver uncertainty_samples pour avoir yhat_lower/upper
            )
            
            model.fit(df)
            
            print(f"   ✅ Modèle entraîné")
            
            # Sauvegarder le modèle et l'heure d'entraînement
            self.models[sensor_type] = model
            self.last_training_time[sensor_type] = datetime.now()
            
            return model
            
        except Exception as e:
            print(f"❌ Erreur entraînement {sensor_type}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def should_retrain(self, sensor_type: str) -> bool:
        """Vérifier si le modèle doit être réentraîné"""
        if sensor_type not in self.models:
            return True
        
        if sensor_type not in self.last_training_time:
            return True
        
        elapsed = datetime.now() - self.last_training_time[sensor_type]
        return elapsed.total_seconds() > (config.RETRAINING_INTERVAL_HOURS * 3600)
    
    def generate_forecast(self, sensor_type: str, horizon_days: int = None) -> Optional[pd.DataFrame]:
        """
        Générer une prévision pour un capteur
        
        Args:
            sensor_type: Type de capteur
            horizon_days: Nombre de jours de prévision (défaut: FORECAST_HORIZON)
        
        Returns:
            DataFrame avec les prévisions ou None
        """
        horizon_days = horizon_days or config.FORECAST_HORIZON
        
        try:
            # Vérifier si réentraînement nécessaire
            if self.should_retrain(sensor_type):
                model = self.train_prophet_model(sensor_type)
                if model is None:
                    return None
            else:
                model = self.models[sensor_type]
            
            # Créer le dataframe de dates futures
            future = model.make_future_dataframe(periods=horizon_days, freq='D')
            
            # Générer les prévisions
            forecast = model.predict(future)
            
            # Filtrer uniquement les prévisions futures
            forecast = forecast[forecast['ds'] > datetime.now()]
            
            return forecast
            
        except Exception as e:
            print(f"❌ Erreur génération prévision {sensor_type}: {e}")
            return None
    
    def calculate_water_stress(self, soil_moisture: float, temperature: float = None, 
                               humidity: float = None) -> Tuple[str, float, bool]:
        """
        Calculer le niveau de stress hydrique
        
        Args:
            soil_moisture: Humidité du sol (%)
            temperature: Température (°C) - optionnel
            humidity: Humidité de l'air (%) - optionnel
        
        Returns:
            (niveau, score, irrigation_recommandée)
        """
        # Score basé principalement sur l'humidité du sol
        score = soil_moisture / 100.0
        
        # Ajustements selon température et humidité
        if temperature is not None:
            # Température élevée augmente le stress
            if temperature > 30:
                score *= 0.9
            elif temperature > 35:
                score *= 0.8
        
        if humidity is not None:
            # Humidité de l'air faible augmente le stress
            if humidity < 40:
                score *= 0.95
            elif humidity < 30:
                score *= 0.85
        
        # Déterminer le niveau de stress
        if score < (config.WATER_STRESS_THRESHOLD_LOW / 100.0):
            level = "HIGH_STRESS"
            irrigation_recommended = True
        elif score < (config.WATER_STRESS_THRESHOLD_MEDIUM / 100.0):
            level = "MEDIUM_STRESS"
            irrigation_recommended = True
        elif score > (config.WATER_STRESS_THRESHOLD_HIGH / 100.0):
            level = "OPTIMAL"
            irrigation_recommended = False
        else:
            level = "LOW_STRESS"
            irrigation_recommended = False
        
        return level, round(score, 4), irrigation_recommended
    
    def calculate_water_needs(self, forecasts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Calculer le besoin en eau agrégé pour chaque jour en combinant
        les prévisions de Soil Moisture, Temperature et Humidity
        
        Args:
            forecasts: Liste de toutes les prévisions
        
        Returns:
            Liste des besoins en eau par jour
        """
        print(f"\n{'='*70}")
        print(f"💧 CALCUL DU BESOIN EN EAU")
        print(f"{'='*70}")
        
        # Grouper les prévisions par date cible ET par type de capteur
        forecasts_by_date = {}
        for forecast in forecasts:
            target_date = forecast['target_date'][:10]  # Juste la date sans l'heure
            sensor_type = forecast['sensor_type']
            
            if target_date not in forecasts_by_date:
                forecasts_by_date[target_date] = {}
            
            # Prendre la première valeur de chaque type de capteur pour chaque date
            if sensor_type not in forecasts_by_date[target_date]:
                forecasts_by_date[target_date][sensor_type] = forecast['predicted_value']
        
        water_needs = []
        
        for target_date, sensor_values in sorted(forecasts_by_date.items()):
            # Extraire les valeurs
            soil_moisture = sensor_values.get('Soil Moisture', None)
            temperature = sensor_values.get('Environment Temperature') or sensor_values.get('Soil Temperature', None)
            humidity = sensor_values.get('Environment Humidity', None)
            
            # Valider et limiter les valeurs
            if soil_moisture is not None:
                soil_moisture = max(0, min(100, soil_moisture))  # Limiter à [0-100]
            
            if temperature is not None:
                temperature = max(-50, min(60, temperature))  # Limiter à [-50, 60]
            
            if humidity is not None:
                humidity = max(0, min(100, humidity))  # Limiter à [0-100]
            
            if soil_moisture is None:
                continue  # Besoin au minimum de l'humidité du sol
            
            # Calcul du besoin en eau (0-100, où 100 = besoin maximal)
            # Formule inverse : plus l'humidité du sol est faible, plus le besoin est élevé
            water_need_score = 0.0
            
            # Contribution de l'humidité du sol (60%)
            soil_contribution = (100 - soil_moisture) * config.WEIGHT_SOIL_MOISTURE
            water_need_score += soil_contribution
            
            # Contribution de la température (25%)
            if temperature is not None:
                # Température élevée augmente le besoin
                temp_factor = min(max((temperature - 15) / 30, 0), 1)  # Normaliser entre 15-45°C
                temp_contribution = temp_factor * 100 * config.WEIGHT_TEMPERATURE
                water_need_score += temp_contribution
            
            # Contribution de l'humidité de l'air (15%)
            if humidity is not None:
                # Humidité de l'air faible augmente le besoin
                humidity_factor = (100 - humidity) / 100
                humidity_contribution = humidity_factor * 100 * config.WEIGHT_HUMIDITY
                water_need_score += humidity_contribution
            
            # Déterminer le niveau de besoin
            if water_need_score > 70:
                need_level = "CRITICAL"
                irrigation_priority = "HIGH"
                irrigation_recommended = True
            elif water_need_score > 50:
                need_level = "HIGH"
                irrigation_priority = "MEDIUM"
                irrigation_recommended = True
            elif water_need_score > 30:
                need_level = "MODERATE"
                irrigation_priority = "LOW"
                irrigation_recommended = True
            else:
                need_level = "LOW"
                irrigation_priority = "NONE"
                irrigation_recommended = False
            
            # Calculer la quantité d'eau recommandée (mm/jour)
            # Formule simplifiée : basée sur le score de besoin
            water_amount_mm = round((water_need_score / 100) * 10, 2)  # Max 10mm/jour
            
            # Calculer l'horizon en jours
            from datetime import datetime as dt
            horizon_days = (dt.fromisoformat(target_date) - dt.now()).days + 1
            
            water_need_data = {
                'forecast_date': forecasts[0]['forecast_date'],
                'target_date': target_date,
                'water_need_score': round(water_need_score, 2),
                'need_level': need_level,
                'irrigation_recommended': irrigation_recommended,
                'irrigation_priority': irrigation_priority,
                'recommended_water_mm': water_amount_mm,
                'soil_moisture_percent': soil_moisture,
                'temperature_celsius': temperature,
                'humidity_percent': humidity,
                'horizon_days': horizon_days
            }
            
            water_needs.append(water_need_data)
            
            print(f"\n📅 {target_date}")
            print(f"   💧 Besoin en eau: {water_need_score:.1f}/100 ({need_level})")
            print(f"   🚿 Irrigation: {'OUI' if irrigation_recommended else 'NON'} (priorité: {irrigation_priority})")
            print(f"   💦 Quantité recommandée: {water_amount_mm} mm/jour")
            temp_str = f"{temperature:.1f}" if temperature is not None else "N/A"
            humidity_str = f"{humidity:.1f}" if humidity is not None else "N/A"
            print(f"   📊 Sol: {soil_moisture:.1f}%, Temp: {temp_str}°C, Humidité: {humidity_str}%")
        
        print(f"\n{'='*70}\n")
        
        return water_needs
    
    def generate_all_forecasts(self) -> List[Dict[str, Any]]:
        """
        Générer les prévisions pour tous les types de capteurs pertinents
        
        Returns:
            Liste des prévisions générées
        """
        print(f"\n{'='*70}")
        print(f"📊 GÉNÉRATION DES PRÉVISIONS")
        print(f"{'='*70}")
        
        all_forecasts = []
        forecast_date = datetime.now()
        
        # Capteurs pertinents pour l'irrigation
        sensor_types = config.SOIL_MOISTURE_SENSORS + config.TEMPERATURE_SENSORS + config.HUMIDITY_SENSORS
        sensor_types = list(set(sensor_types))  # Supprimer les doublons
        
        for sensor_type in sensor_types:
            print(f"\n🔮 Prévision: {sensor_type}")
            
            forecast_df = self.generate_forecast(sensor_type)
            
            if forecast_df is None or len(forecast_df) == 0:
                print(f"   ⚠️  Aucune prévision générée")
                continue
            
            # Traiter chaque jour de prévision
            for idx, row in forecast_df.iterrows():
                target_date = row['ds']
                predicted_value = row['yhat']
                
                # Gérer les bornes de confiance (peuvent ne pas exister)
                lower_bound = row.get('yhat_lower', predicted_value * 0.95)
                upper_bound = row.get('yhat_upper', predicted_value * 1.05)
                
                # Si les colonnes n'existent pas, utiliser des valeurs par défaut
                if pd.isna(lower_bound):
                    lower_bound = predicted_value * 0.95
                if pd.isna(upper_bound):
                    upper_bound = predicted_value * 1.05
                
                # Calculer l'horizon en jours
                horizon_days = (target_date - forecast_date).days
                
                if horizon_days <= 0 or horizon_days > config.FORECAST_HORIZON:
                    continue
                
                # Validation des valeurs prédites (éviter les aberrations)
                if predicted_value < -100 or predicted_value > 10000:
                    print(f"   ⚠️  Valeur aberrante ignorée: {predicted_value}")
                    continue
                
                # Calculer le stress hydrique (si c'est l'humidité du sol)
                if sensor_type in config.SOIL_MOISTURE_SENSORS:
                    stress_level, stress_score, irrigation_rec = self.calculate_water_stress(predicted_value)
                else:
                    stress_level = "N/A"
                    stress_score = 0.0
                    irrigation_rec = False
                
                # Confidence basée sur la largeur de l'intervalle
                interval_width = upper_bound - lower_bound
                model_confidence = max(0.0, min(1.0, 1.0 - (interval_width / 100.0)))
                
                forecast_data = {
                    'forecast_date': forecast_date.isoformat(),
                    'target_date': target_date.isoformat(),
                    'sensor_type': sensor_type,
                    'predicted_value': round(predicted_value, 2),
                    'lower_bound': round(lower_bound, 2),
                    'upper_bound': round(upper_bound, 2),
                    'water_stress_level': stress_level,
                    'water_stress_score': stress_score,
                    'irrigation_recommended': irrigation_rec,
                    'horizon_days': horizon_days,
                    'model_confidence': round(model_confidence, 4)
                }
                
                all_forecasts.append(forecast_data)
            
            print(f"   ✅ {len(forecast_df)} prévisions générées")
        
        print(f"\n{'='*70}")
        print(f"✅ Total: {len(all_forecasts)} prévisions générées")
        print(f"{'='*70}\n")
        
        # Calculer le besoin en eau agrégé
        water_needs = self.calculate_water_needs(all_forecasts)
        
        return all_forecasts, water_needs
    
    def save_forecasts_to_db(self, forecasts: List[Dict[str, Any]]) -> int:
        """
        Sauvegarder les prévisions dans TimescaleDB
        
        Args:
            forecasts: Liste des prévisions
        
        Returns:
            Nombre de prévisions sauvegardées
        """
        if not forecasts:
            return 0
        
        conn = self.db_pool.getconn()
        saved = 0
        
        try:
            with conn.cursor() as cursor:
                for forecast in forecasts:
                    try:
                        cursor.execute("""
                            INSERT INTO water_forecast (
                                forecast_date, target_date, sensor_type,
                                predicted_value, lower_bound, upper_bound,
                                water_stress_level, water_stress_score, irrigation_recommended,
                                horizon_days, model_confidence
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (forecast_date, target_date, sensor_type)
                            DO UPDATE SET
                                predicted_value = EXCLUDED.predicted_value,
                                lower_bound = EXCLUDED.lower_bound,
                                upper_bound = EXCLUDED.upper_bound,
                                water_stress_level = EXCLUDED.water_stress_level,
                                water_stress_score = EXCLUDED.water_stress_score,
                                irrigation_recommended = EXCLUDED.irrigation_recommended,
                                horizon_days = EXCLUDED.horizon_days,
                                model_confidence = EXCLUDED.model_confidence
                        """, (
                            forecast['forecast_date'],
                            forecast['target_date'],
                            forecast['sensor_type'],
                            forecast['predicted_value'],
                            forecast['lower_bound'],
                            forecast['upper_bound'],
                            forecast['water_stress_level'],
                            forecast['water_stress_score'],
                            forecast['irrigation_recommended'],
                            forecast['horizon_days'],
                            forecast['model_confidence']
                        ))
                        saved += 1
                    except Exception as e:
                        print(f"⚠️  Erreur sauvegarde: {e}")
                
                conn.commit()
            
            print(f"💾 {saved}/{len(forecasts)} prévisions sauvegardées dans TimescaleDB")
            return saved
            
        except Exception as e:
            print(f"❌ Erreur sauvegarde DB: {e}")
            conn.rollback()
            return 0
        finally:
            self.db_pool.putconn(conn)
    
    def publish_forecasts_to_kafka(self, forecasts: List[Dict[str, Any]]) -> int:
        """
        Publier les prévisions dans Kafka
        
        Args:
            forecasts: Liste des prévisions
        
        Returns:
            Nombre de prévisions publiées
        """
        if not forecasts:
            return 0
        
        published = 0
        
        try:
            for forecast in forecasts:
                future = self.producer.send(
                    self.kafka_forecast_topic,
                    value=forecast
                )
                future.get(timeout=5)
                published += 1
            
            self.producer.flush()
            print(f"📤 {published}/{len(forecasts)} prévisions publiées dans Kafka")
            return published
            
        except Exception as e:
            print(f"❌ Erreur publication Kafka: {e}")
            return published
    
    def publish_water_needs_to_kafka(self, water_needs: List[Dict[str, Any]]) -> int:
        """
        Publier les besoins en eau dans Kafka topic 'water.needs'
        
        Args:
            water_needs: Liste des besoins en eau
        
        Returns:
            Nombre de besoins publiés
        """
        if not water_needs or not self.producer:
            return 0
        
        published = 0
        water_needs_topic = 'water.needs'
        
        try:
            for need in water_needs:
                self.producer.send(water_needs_topic, value=need)
                published += 1
            
            self.producer.flush()
            print(f"💧 {published}/{len(water_needs)} besoins en eau publiés dans Kafka topic '{water_needs_topic}'")
            return published
            
        except Exception as e:
            print(f"❌ Erreur publication besoins en eau Kafka: {e}")
            return published
    
    def run(self):
        """Boucle principale du service"""
        print(f"\n{'='*70}")
        print(f"💧 WATERFORECAST SERVICE - DÉMARRAGE")
        print(f"{'='*70}")
        
        # Initialisation
        if not self.init_database_pool():
            print("❌ Impossible de démarrer sans connexion DB")
            return
        
        self.init_kafka()
        
        print(f"\n✅ Service initialisé")
        print(f"📊 Génération de prévisions toutes les {config.PUBLISH_INTERVAL_MINUTES} minutes")
        print(f"{'='*70}\n")
        
        last_forecast_time = datetime.now() - timedelta(hours=1)  # Forcer première exécution
        
        try:
            while True:
                # Vérifier si c'est le moment de générer des prévisions
                elapsed = datetime.now() - last_forecast_time
                
                if elapsed.total_seconds() >= (config.PUBLISH_INTERVAL_MINUTES * 60):
                    # Générer les prévisions
                    forecasts, water_needs = self.generate_all_forecasts()
                    
                    if forecasts:
                        # Sauvegarder dans TimescaleDB
                        self.save_forecasts_to_db(forecasts)
                        
                        # Publier dans Kafka
                        self.publish_forecasts_to_kafka(forecasts)
                        
                        self.forecasts_generated += len(forecasts)
                    
                    # Publier les besoins en eau dans un topic séparé
                    if water_needs:
                        self.publish_water_needs_to_kafka(water_needs)
                    
                    last_forecast_time = datetime.now()
                    
                    # Afficher les statistiques
                    self.print_stats()
                
                # Pause
                time.sleep(60)  # Vérifier toutes les minutes
                
        except KeyboardInterrupt:
            print(f"\n\n⚠️  Arrêt demandé par l'utilisateur")
        except Exception as e:
            print(f"\n❌ Erreur fatale: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.shutdown()
    
    def print_stats(self):
        """Afficher les statistiques"""
        print(f"\n{'='*70}")
        print(f"📊 STATISTIQUES - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        print(f"  Prévisions générées: {self.forecasts_generated}")
        print(f"  Modèles entraînés: {len(self.models)}")
        print(f"  Erreurs: {self.errors_count}")
        
        if self.last_training_time:
            print(f"\n  Derniers entraînements:")
            for sensor_type, train_time in self.last_training_time.items():
                elapsed = datetime.now() - train_time
                print(f"    • {sensor_type}: il y a {elapsed.seconds // 60}min")
        
        print(f"{'='*70}\n")
    
    def shutdown(self):
        """Fermer les connexions proprement"""
        print(f"\n{'='*70}")
        print(f"🛑 ARRÊT DU SERVICE")
        print(f"{'='*70}")
        
        self.print_stats()
        
        if self.consumer:
            self.consumer.close()
            print("✅ Consumer Kafka fermé")
        
        if self.producer:
            self.producer.flush()
            self.producer.close()
            print("✅ Producer Kafka fermé")
        
        if self.db_pool:
            self.db_pool.closeall()
            print("✅ Connexions DB fermées")
        
        print(f"{'='*70}\n")


def main():
    """Point d'entrée du service"""
    service = WaterForecastService()
    service.run()


if __name__ == "__main__":
    main()
