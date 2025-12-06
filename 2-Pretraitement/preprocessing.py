import json
import time
from datetime import datetime
from collections import deque
from typing import Dict, Any, Optional, List
import numpy as np
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import config

class SensorDataPreprocessor:
    """
    Microservice de prétraitement des données capteurs
    - Lit les données brutes depuis Kafka topic 'sensor-data'
    - Nettoie et normalise les données
    - Stocke dans TimescaleDB (sensor_data_processed)
    - Publie dans Kafka topic 'sensor-data-processed'
    """
    
    def __init__(self):
        self.kafka_bootstrap_servers = config.KAFKA_BOOTSTRAP_SERVERS
        self.kafka_input_topic = config.KAFKA_INPUT_TOPIC
        self.kafka_output_topic = config.KAFKA_OUTPUT_TOPIC
        self.kafka_group_id = config.KAFKA_GROUP_ID
        
        self.consumer = None
        self.producer = None
        self.db_pool = None
        
        # Statistiques
        self.received_count = 0
        self.processed_count = 0
        self.anomaly_count = 0
        self.error_count = 0
        
        # Historique pour calcul de moyennes mobiles (par sensor_type)
        self.history = {}
        
    def init_database_pool(self):
        """Initialise le pool de connexions PostgreSQL"""
        print(f"Connexion à TimescaleDB: {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
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
                print("✓ Connexion TimescaleDB établie")
                
                # Initialiser le schéma de la table processed
                self._init_database_schema()
                return True
            except Exception as e:
                retry_count += 1
                print(f"✗ Tentative {retry_count}/{max_retries} - Erreur DB: {e}")
                if retry_count < max_retries:
                    print(f"  Nouvelle tentative dans 5 secondes...")
                    time.sleep(5)
        
        print("✗ Impossible de se connecter à la base de données")
        return False
    
    def _init_database_schema(self):
        """Crée la table sensor_data_processed si elle n'existe pas"""
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Table pour les données prétraitées
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sensor_data_processed (
                        id SERIAL PRIMARY KEY,
                        sensor_type VARCHAR(100) NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL,
                        
                        -- Valeurs brutes (pour référence)
                        raw_value FLOAT,
                        
                        -- Valeurs nettoyées
                        clean_value FLOAT,
                        
                        -- Valeurs normalisées [0-1]
                        normalized_value FLOAT,
                        
                        -- Features calculées
                        moving_average FLOAT,
                        
                        -- Métadonnées de qualité
                        quality_score FLOAT,
                        is_anomaly BOOLEAN DEFAULT FALSE,
                        missing_data_filled BOOLEAN DEFAULT FALSE,
                        
                        -- Métadonnées
                        processing_timestamp TIMESTAMPTZ DEFAULT NOW(),
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Index pour optimiser les requêtes
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_processed_sensor_type 
                    ON sensor_data_processed(sensor_type);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_processed_timestamp 
                    ON sensor_data_processed(timestamp);
                """)
                
                # Convertir en hypertable si ce n'est pas déjà fait
                cursor.execute("""
                    SELECT create_hypertable('sensor_data_processed', 'timestamp', 
                                            if_not_exists => TRUE);
                """)
                
                conn.commit()
                print("✓ Schéma sensor_data_processed initialisé")
        except Exception as e:
            print(f"✗ Erreur initialisation schéma: {e}")
            conn.rollback()
        finally:
            self.db_pool.putconn(conn)
    
    def init_kafka_consumer(self):
        """Initialise le consumer Kafka"""
        print(f"Initialisation Kafka Consumer...")
        print(f"  Bootstrap servers: {self.kafka_bootstrap_servers}")
        print(f"  Topic: {self.kafka_input_topic}")
        print(f"  Group ID: {self.kafka_group_id}")
        
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.consumer = KafkaConsumer(
                    self.kafka_input_topic,
                    bootstrap_servers=self.kafka_bootstrap_servers,
                    group_id=self.kafka_group_id,
                    auto_offset_reset='earliest',
                    enable_auto_commit=True,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    consumer_timeout_ms=1000
                )
                print("✓ Kafka Consumer initialisé")
                return True
            except Exception as e:
                retry_count += 1
                print(f"✗ Tentative {retry_count}/{max_retries} - Erreur Kafka Consumer: {e}")
                if retry_count < max_retries:
                    print(f"  Nouvelle tentative dans 5 secondes...")
                    time.sleep(5)
        
        print("✗ Impossible de se connecter à Kafka (Consumer)")
        return False
    
    def init_kafka_producer(self):
        """Initialise le producer Kafka"""
        print(f"Initialisation Kafka Producer...")
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.producer = KafkaProducer(
                    bootstrap_servers=self.kafka_bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    acks='all',
                    retries=3
                )
                print(f"✓ Kafka Producer initialisé (topic: {self.kafka_output_topic})")
                return True
            except Exception as e:
                retry_count += 1
                print(f"✗ Tentative {retry_count}/{max_retries} - Erreur Kafka Producer: {e}")
                if retry_count < max_retries:
                    print(f"  Nouvelle tentative dans 5 secondes...")
                    time.sleep(5)
        
        print("✗ Impossible de se connecter à Kafka (Producer)")
        return False
    
    def preprocess_sensor_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Prétraite les données capteurs
        
        Pipeline:
        1. Validation
        2. Extraction de la valeur
        3. Détection d'anomalies
        4. Nettoyage (gestion valeurs manquantes)
        5. Normalisation
        6. Calcul de features (moyenne mobile)
        7. Calcul du score de qualité
        """
        try:
            sensor_type = raw_data.get('sensor_type')
            timestamp = raw_data.get('timestamp')
            measurements = raw_data.get('measurements', {})
            
            if not sensor_type or not timestamp:
                return None
            
            # Extraction de la valeur principale
            raw_value = self._extract_value(sensor_type, measurements)
            if raw_value is None:
                return None
            
            # Initialiser l'historique pour ce type de capteur
            if sensor_type not in self.history:
                self.history[sensor_type] = deque(maxlen=config.MOVING_AVERAGE_WINDOW)
            
            # Détection d'anomalies
            is_anomaly = self._detect_anomaly(sensor_type, raw_value)
            
            # Nettoyage: si anomalie, on peut interpoler ou ignorer
            clean_value = raw_value
            missing_data_filled = False
            
            if is_anomaly:
                self.anomaly_count += 1
                # Option 1: Utiliser la moyenne des valeurs récentes
                if len(self.history[sensor_type]) > 0:
                    clean_value = np.mean(list(self.history[sensor_type]))
                    missing_data_filled = True
                # Option 2: On pourrait aussi rejeter la valeur
                # return None
            
            # Normalisation [0-1] selon les ranges définis
            normalized_value = self._normalize_value(sensor_type, clean_value)
            
            # Calcul de la moyenne mobile
            self.history[sensor_type].append(clean_value)
            moving_average = np.mean(list(self.history[sensor_type]))
            
            # Score de qualité (1.0 = parfait, 0.0 = mauvais)
            quality_score = self._calculate_quality_score(
                is_anomaly, 
                missing_data_filled,
                len(self.history[sensor_type])
            )
            
            # Construction du résultat
            processed_data = {
                'sensor_type': sensor_type,
                'timestamp': timestamp,
                'raw_value': raw_value,
                'clean_value': clean_value,
                'normalized_value': normalized_value,
                'moving_average': moving_average,
                'quality_score': quality_score,
                'is_anomaly': is_anomaly,
                'missing_data_filled': missing_data_filled,
                'processing_timestamp': datetime.utcnow().isoformat()
            }
            
            return processed_data
            
        except Exception as e:
            print(f"✗ Erreur prétraitement: {e}")
            return None
    
    def _extract_value(self, sensor_type: str, measurements: Dict) -> Optional[float]:
        """Extrait la valeur principale selon le type de capteur"""
        try:
            if sensor_type == 'Temperature':
                return float(measurements.get('Temperature (°C)', 0))
            elif sensor_type == 'Environment Humidity':
                return float(measurements.get('Environment Humidity (%)', 0))
            elif sensor_type == 'Soil Moisture':
                return float(measurements.get('Soil Moisture (%)', 0))
            elif sensor_type == 'Soil pH':
                return float(measurements.get('Soil pH', 0))
            elif sensor_type == 'Light Intensity':
                return float(measurements.get('Light Intensity (lux)', 0))
            else:
                # Prendre la première valeur numérique disponible
                for key, value in measurements.items():
                    try:
                        return float(value)
                    except:
                        continue
            return None
        except Exception as e:
            print(f"✗ Erreur extraction valeur: {e}")
            return None
    
    def _detect_anomaly(self, sensor_type: str, value: float) -> bool:
        """
        Détecte les anomalies basées sur:
        1. Plages de valeurs attendues
        2. Z-score (si historique disponible)
        """
        # Vérifier les plages de valeurs
        if sensor_type in config.SENSOR_RANGES:
            range_config = config.SENSOR_RANGES[sensor_type]
            if value < range_config['min'] or value > range_config['max']:
                return True
        
        # Z-score si on a assez d'historique
        if sensor_type in self.history and len(self.history[sensor_type]) >= 3:
            values = list(self.history[sensor_type])
            mean = np.mean(values)
            std = np.std(values)
            
            if std > 0:
                z_score = abs((value - mean) / std)
                if z_score > config.ANOMALY_THRESHOLD:
                    return True
        
        return False
    
    def _normalize_value(self, sensor_type: str, value: float) -> float:
        """
        Normalise la valeur entre 0 et 1 selon les plages définies
        Formule: (value - min) / (max - min)
        """
        if sensor_type not in config.SENSOR_RANGES:
            return value  # Pas de normalisation si pas de range défini
        
        range_config = config.SENSOR_RANGES[sensor_type]
        min_val = range_config['min']
        max_val = range_config['max']
        
        # Clip la valeur dans la plage
        value = max(min_val, min(max_val, value))
        
        # Normalisation
        if max_val - min_val > 0:
            normalized = (value - min_val) / (max_val - min_val)
            return round(normalized, 4)
        
        return 0.0
    
    def _calculate_quality_score(self, is_anomaly: bool, missing_data_filled: bool, 
                                 history_size: int) -> float:
        """
        Calcule un score de qualité pour la donnée
        1.0 = excellente qualité
        0.0 = mauvaise qualité
        """
        score = 1.0
        
        # Pénalité pour anomalie
        if is_anomaly:
            score -= 0.3
        
        # Pénalité pour donnée manquante remplie
        if missing_data_filled:
            score -= 0.2
        
        # Bonus si on a un bon historique pour la moyenne mobile
        if history_size >= config.MOVING_AVERAGE_WINDOW:
            score += 0.1
        
        return max(0.0, min(1.0, round(score, 2)))
    
    def save_to_database(self, processed_data: Dict[str, Any]) -> bool:
        """Sauvegarde les données prétraitées dans TimescaleDB"""
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO sensor_data_processed (
                        sensor_type, timestamp, raw_value, clean_value, 
                        normalized_value, moving_average, quality_score,
                        is_anomaly, missing_data_filled
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    processed_data['sensor_type'],
                    processed_data['timestamp'],
                    processed_data['raw_value'],
                    processed_data['clean_value'],
                    processed_data['normalized_value'],
                    processed_data['moving_average'],
                    processed_data['quality_score'],
                    processed_data['is_anomaly'],
                    processed_data['missing_data_filled']
                ))
                conn.commit()
                return True
        except Exception as e:
            print(f"✗ Erreur sauvegarde DB: {e}")
            conn.rollback()
            return False
        finally:
            self.db_pool.putconn(conn)
    
    def publish_to_kafka(self, processed_data: Dict[str, Any]) -> bool:
        """Publie les données prétraitées dans Kafka"""
        try:
            self.producer.send(self.kafka_output_topic, value=processed_data)
            self.producer.flush()
            return True
        except Exception as e:
            print(f"✗ Erreur publication Kafka: {e}")
            return False
    
    def run(self):
        """Boucle principale du microservice"""
        print("\n" + "="*60)
        print("  MICROSERVICE DE PRÉTRAITEMENT - AgroTrace")
        print("="*60)
        
        # Initialisation
        if not self.init_database_pool():
            print("✗ Erreur initialisation base de données")
            return
        
        if not self.init_kafka_consumer():
            print("✗ Erreur initialisation Kafka Consumer")
            return
        
        if not self.init_kafka_producer():
            print("✗ Erreur initialisation Kafka Producer")
            return
        
        print("\n✓ Tous les services sont initialisés")
        print(f"✓ Écoute du topic Kafka: {self.kafka_input_topic}")
        print(f"✓ Publication vers topic: {self.kafka_output_topic}")
        print(f"✓ Stockage: TimescaleDB (sensor_data_processed)")
        print("\n" + "-"*60)
        print("En attente de messages...\n")
        
        last_stats_time = time.time()
        
        try:
            while True:
                try:
                    # === TRAITEMENT DES DONNÉES CAPTEURS ===
                    for message in self.consumer:
                        self.received_count += 1
                        raw_data = message.value
                        
                        # Prétraitement
                        processed_data = self.preprocess_sensor_data(raw_data)
                        
                        if processed_data:
                            # Sauvegarde dans TimescaleDB
                            db_success = self.save_to_database(processed_data)
                            
                            # Publication dans Kafka
                            kafka_success = self.publish_to_kafka(processed_data)
                            
                            if db_success and kafka_success:
                                self.processed_count += 1
                                
                                # Log périodique
                                if self.processed_count % 10 == 0:
                                    print(f"✓ [{datetime.now().strftime('%H:%M:%S')}] "
                                          f"{processed_data['sensor_type']}: "
                                          f"raw={processed_data['raw_value']:.2f} → "
                                          f"clean={processed_data['clean_value']:.2f} → "
                                          f"norm={processed_data['normalized_value']:.4f} "
                                          f"(quality={processed_data['quality_score']:.2f})")
                            else:
                                self.error_count += 1
                        else:
                            self.error_count += 1
                    
                    # Statistiques toutes les 30 secondes
                    if time.time() - last_stats_time >= 30:
                        self.print_stats()
                        last_stats_time = time.time()
                    
                    # Petite pause si pas de messages
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"✗ Erreur traitement message: {e}")
                    self.error_count += 1
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            print("\n\n⚠ Arrêt demandé par l'utilisateur")
        finally:
            self.cleanup()
    
    def print_stats(self):
        """Affiche les statistiques"""
        print("\n" + "="*60)
        print(f"  STATISTIQUES - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        print(f"  [SENSORS]")
        print(f"    Messages reçus:     {self.received_count}")
        print(f"    Messages traités:   {self.processed_count}")
        print(f"    Anomalies détectées: {self.anomaly_count}")
        if self.received_count > 0:
            success_rate = (self.processed_count / self.received_count) * 100
            print(f"    Taux de succès:     {success_rate:.2f}%")
        print(f"    Erreurs totales:    {self.error_count}")
        print("-"*60 + "\n")
    
    def cleanup(self):
        """Nettoyage des ressources"""
        print("\nNettoyage des ressources...")
        
        if self.consumer:
            self.consumer.close()
            print("✓ Kafka Consumer fermé")
        
        if self.producer:
            self.producer.close()
            print("✓ Kafka Producer fermé")
        
        if self.db_pool:
            self.db_pool.closeall()
            print("✓ Connexions DB fermées")
        
        self.print_stats()
        print("\n✓ Microservice arrêté proprement")


def main():
    """Point d'entrée du microservice"""
    preprocessor = SensorDataPreprocessor()
    preprocessor.run()


if __name__ == '__main__':
    main()
