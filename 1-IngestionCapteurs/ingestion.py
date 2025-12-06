import json
import time
from datetime import datetime
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import config

class SensorDataIngestionKafka:
    def __init__(self):
        self.kafka_bootstrap_servers = config.KAFKA_BOOTSTRAP_SERVERS
        self.kafka_topic = config.KAFKA_TOPIC
        self.kafka_group_id = config.KAFKA_GROUP_ID
        self.received_count = 0
        self.stored_count = 0
        self.error_count = 0
        self.consumer = None
        self.db_pool = None
        
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
                
                # Initialiser le schéma de base de données
                self._init_database_schema()
                return True
            except Exception as e:
                retry_count += 1
                print(f"✗ Tentative {retry_count}/{max_retries} - Erreur DB: {e}")
                if retry_count < max_retries:
                    print(f"  Nouvelle tentative dans 5 secondes...")
                    time.sleep(5)
        
        print("✗ Impossible de se connecter à TimescaleDB après plusieurs tentatives")
        return False
    
    def _init_database_schema(self):
        """Initialise le schéma de la base de données"""
        conn = None
        try:
            conn = self.db_pool.getconn()
            cursor = conn.cursor()
            
            # Vérifier si la table existe déjà
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'sensor_data'
                );
            """)
            table_exists = cursor.fetchone()[0]
            
            if table_exists:
                print("✓ Table sensor_data existe déjà")
            else:
                print("⚠ Table sensor_data n'existe pas, tentative de création...")
                try:
                    with open('init_db.sql', 'r', encoding='utf-8') as f:
                        sql_script = f.read()
                        cursor.execute(sql_script)
                    print("✓ Schéma de base de données créé")
                except FileNotFoundError:
                    print("⚠ Fichier init_db.sql non trouvé - la table devrait être créée via docker-entrypoint-initdb.d")
            
            conn.commit()
            cursor.close()
        except Exception as e:
            print(f"⚠ Erreur lors de la vérification du schéma: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                self.db_pool.putconn(conn)
        
    def init_kafka_consumer(self):
        """Initialise le consommateur Kafka"""
        print(f"Connexion à Kafka: {self.kafka_bootstrap_servers}")
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.consumer = KafkaConsumer(
                    self.kafka_topic,
                    bootstrap_servers=self.kafka_bootstrap_servers.split(','),
                    group_id=self.kafka_group_id,
                    auto_offset_reset='latest',  # Commencer par les nouveaux messages
                    enable_auto_commit=True,
                    auto_commit_interval_ms=1000,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    key_deserializer=lambda k: k.decode('utf-8') if k else None,
                    consumer_timeout_ms=1000,  # Timeout pour permettre les interruptions
                    max_poll_records=10,
                    session_timeout_ms=30000,
                    heartbeat_interval_ms=10000
                )
                print("✓ Connexion Kafka établie")
                print(f"✓ Abonnement au topic: {self.kafka_topic}")
                print(f"✓ Groupe de consommateurs: {self.kafka_group_id}")
                return True
            except Exception as e:
                retry_count += 1
                print(f"✗ Tentative {retry_count}/{max_retries} - Erreur: {e}")
                if retry_count < max_retries:
                    print(f"  Nouvelle tentative dans 5 secondes...")
                    time.sleep(5)
        
        print("✗ Impossible de se connecter à Kafka après plusieurs tentatives")
        return False
    
    def harmonize_data(self, raw_data):
        """
        Harmonise les données du capteur pour assurer cohérence et structure uniforme
        - Normalise les noms de champs
        - Gère les valeurs manquantes
        - Convertit les types de données
        - Assure un format de timestamp ISO 8601
        """
        harmonized = {
            'sensor_type': None,
            'timestamp': None,
            'data_index': None,
            'measurements': {}
        }
        
        # 1. Extraire et normaliser le type de capteur
        if 'sensor_type' in raw_data:
            harmonized['sensor_type'] = str(raw_data['sensor_type']).strip()
        
        # 2. Normaliser le timestamp (ISO 8601)
        if 'timestamp' in raw_data:
            timestamp_value = raw_data['timestamp']
            try:
                # Si c'est déjà un objet datetime
                if isinstance(timestamp_value, datetime):
                    harmonized['timestamp'] = timestamp_value.isoformat()
                # Si c'est une chaîne, essayer de la parser
                elif isinstance(timestamp_value, str):
                    # Essayer plusieurs formats
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                        try:
                            dt = datetime.strptime(timestamp_value, fmt)
                            harmonized['timestamp'] = dt.isoformat()
                            break
                        except ValueError:
                            continue
                    # Si aucun format ne correspond, garder tel quel
                    if not harmonized['timestamp']:
                        harmonized['timestamp'] = timestamp_value
                else:
                    harmonized['timestamp'] = str(timestamp_value)
            except Exception as e:
                print(f"⚠ Erreur lors de la normalisation du timestamp: {e}")
                harmonized['timestamp'] = str(timestamp_value)
        else:
            # Si pas de timestamp, utiliser l'heure actuelle
            harmonized['timestamp'] = datetime.now().isoformat()
        
        # 3. Extraire l'index
        if 'data_index' in raw_data:
            try:
                harmonized['data_index'] = int(raw_data['data_index'])
            except (ValueError, TypeError):
                harmonized['data_index'] = None
        
        # 4. Extraire et nettoyer les mesures
        # NOUVEAU FORMAT: avec 'value', 'unit', 'entry_id', 'original_timestamp'
        if 'value' in raw_data:
            # Format mis à jour depuis le simulateur
            sensor_type = harmonized['sensor_type'] or 'unknown'
            
            # Ajouter la valeur principale avec une clé basée sur le sensor_type
            if raw_data['value'] is not None:
                try:
                    harmonized['measurements']['value'] = float(raw_data['value'])
                except (ValueError, TypeError):
                    harmonized['measurements']['value'] = raw_data['value']
            
            # Ajouter l'unité si disponible
            if 'unit' in raw_data and raw_data['unit']:
                harmonized['measurements']['unit'] = str(raw_data['unit'])
            
            # Ajouter l'entry_id si disponible
            if 'entry_id' in raw_data and raw_data['entry_id'] is not None:
                try:
                    harmonized['measurements']['entry_id'] = int(raw_data['entry_id'])
                except (ValueError, TypeError):
                    harmonized['measurements']['entry_id'] = str(raw_data['entry_id'])
            
            # Ajouter le timestamp original si disponible
            if 'original_timestamp' in raw_data and raw_data['original_timestamp']:
                harmonized['measurements']['original_timestamp'] = str(raw_data['original_timestamp'])
        
        # ANCIEN FORMAT: avec sous-dictionnaire 'measurements'
        elif 'measurements' in raw_data:
            measurements = raw_data['measurements']
            if isinstance(measurements, dict):
                for key, value in measurements.items():
                    # Normaliser la clé (lowercase, underscores)
                    normalized_key = key.lower().replace(' ', '_').replace('-', '_')
                    
                    # Nettoyer la valeur
                    if value is None or value == '' or value == 'N/A':
                        harmonized['measurements'][normalized_key] = None
                    else:
                        # Essayer de convertir en nombre si possible
                        try:
                            if isinstance(value, str):
                                # Enlever les unités et caractères non numériques
                                clean_value = value.replace('%', '').replace('°C', '').replace('°F', '').strip()
                                harmonized['measurements'][normalized_key] = float(clean_value)
                            else:
                                harmonized['measurements'][normalized_key] = float(value)
                        except (ValueError, TypeError):
                            # Si conversion impossible, garder tel quel
                            harmonized['measurements'][normalized_key] = str(value)
        else:
            # Si pas de sous-dictionnaire measurements ni de 'value', tout mettre dedans sauf les champs connus
            for key, value in raw_data.items():
                if key not in ['sensor_type', 'timestamp', 'data_index']:
                    normalized_key = key.lower().replace(' ', '_').replace('-', '_')
                    
                    if value is None or value == '' or value == 'N/A':
                        harmonized['measurements'][normalized_key] = None
                    else:
                        try:
                            if isinstance(value, str):
                                clean_value = value.replace('%', '').replace('°C', '').replace('°F', '').strip()
                                harmonized['measurements'][normalized_key] = float(clean_value)
                            else:
                                harmonized['measurements'][normalized_key] = float(value)
                        except (ValueError, TypeError):
                            harmonized['measurements'][normalized_key] = str(value)
        
        return harmonized
    
    def validate_data(self, harmonized_data):
        """
        Vérifie la cohérence des données harmonisées
        Retourne (is_valid, error_message)
        """
        errors = []
        
        # 1. Vérifier le type de capteur
        if not harmonized_data['sensor_type']:
            errors.append("Type de capteur manquant")
        elif len(harmonized_data['sensor_type']) > 100:
            errors.append("Type de capteur trop long (max 100 caractères)")
        
        # 2. Vérifier le timestamp
        if not harmonized_data['timestamp']:
            errors.append("Timestamp manquant")
        else:
            # Essayer de parser pour vérifier la validité
            try:
                if 'T' in harmonized_data['timestamp']:
                    datetime.fromisoformat(harmonized_data['timestamp'].replace('Z', '+00:00'))
                else:
                    datetime.strptime(harmonized_data['timestamp'], '%Y-%m-%d %H:%M:%S')
            except (ValueError, AttributeError) as e:
                errors.append(f"Format de timestamp invalide: {e}")
        
        # 3. Vérifier la structure des mesures
        if not harmonized_data['measurements']:
            errors.append("Aucune mesure disponible")
        elif not isinstance(harmonized_data['measurements'], dict):
            errors.append("Format de mesures invalide (doit être un dictionnaire)")
        
        # 4. Vérifier les valeurs numériques des mesures
        for key, value in harmonized_data['measurements'].items():
            if value is not None:
                # Vérifier les plages de valeurs selon le type de capteur
                if 'humidity' in key.lower():
                    try:
                        val = float(value)
                        if val < 0 or val > 100:
                            errors.append(f"Humidité hors plage (0-100%): {key}={val}")
                    except (ValueError, TypeError):
                        pass  # Pas numérique, déjà géré dans harmonization
                
                elif 'temperature' in key.lower():
                    try:
                        val = float(value)
                        if val < -50 or val > 60:
                            errors.append(f"Température hors plage (-50 à 60°C): {key}={val}")
                    except (ValueError, TypeError):
                        pass
                
                elif 'ph' in key.lower():
                    try:
                        val = float(value)
                        if val < 0 or val > 14:
                            errors.append(f"pH hors plage (0-14): {key}={val}")
                    except (ValueError, TypeError):
                        pass
                
                elif 'moisture' in key.lower():
                    try:
                        val = float(value)
                        if val < 0 or val > 100:
                            errors.append(f"Humidité du sol hors plage (0-100%): {key}={val}")
                    except (ValueError, TypeError):
                        pass
        
        # Retourner le résultat de validation
        if errors:
            return False, "; ".join(errors)
        return True, None
    
    def store_data(self, message):
        """
        Stocke les données dans TimescaleDB après harmonisation et validation
        """
        conn = None
        try:
            # 1. Extraire les données brutes
            raw_data = message.value
            
            # 2. Harmoniser les données
            harmonized_data = self.harmonize_data(raw_data)
            
            # 3. Valider les données
            is_valid, error_message = self.validate_data(harmonized_data)
            
            if not is_valid:
                self.error_count += 1
                print(f"✗ Données invalides (offset {message.offset}): {error_message}")
                return False
            
            # 4. Stocker dans TimescaleDB
            conn = self.db_pool.getconn()
            cursor = conn.cursor()
            
            # Convertir le timestamp en objet datetime si c'est une chaîne
            if isinstance(harmonized_data['timestamp'], str):
                try:
                    timestamp_obj = datetime.fromisoformat(harmonized_data['timestamp'].replace('Z', '+00:00'))
                except:
                    timestamp_obj = datetime.now()
            else:
                timestamp_obj = harmonized_data['timestamp']
            
            insert_query = """
                INSERT INTO sensor_data (sensor_type, timestamp, data_index, measurements)
                VALUES (%s, %s, %s, %s)
            """
            
            cursor.execute(insert_query, (
                harmonized_data['sensor_type'],
                timestamp_obj,
                harmonized_data['data_index'],
                json.dumps(harmonized_data['measurements'])
            ))
            
            conn.commit()
            cursor.close()
            
            self.stored_count += 1
            self.received_count += 1
            
            # Afficher un message de succès concis
            print(f"✓ [{datetime.now().strftime('%H:%M:%S')}] "
                  f"Stocké: {harmonized_data['sensor_type']} "
                  f"(offset {message.offset}) "
                  f"[Total: {self.stored_count}]")
            
            return True
            
        except Exception as e:
            self.error_count += 1
            print(f"✗ Erreur de stockage (offset {message.offset}): {e}")
            print(f"   Données: sensor_type={harmonized_data.get('sensor_type')}, timestamp={harmonized_data.get('timestamp')}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self.db_pool.putconn(conn)
    
    def display_data(self, message):
        """Affiche les données reçues de manière formatée"""
        self.received_count += 1
        
        data = message.value
        
        print(f"\n{'='*70}")
        print(f"📊 DONNÉES REÇUES #{self.received_count} - [{datetime.now().strftime('%H:%M:%S')}]")
        print(f"{'='*70}")
        print(f"📍 Topic: {message.topic}")
        print(f"📍 Partition: {message.partition}")
        print(f"📍 Offset: {message.offset}")
        print(f"📍 Key: {message.key}")
        print(f"{'-'*70}")
        
        self._display_single_sensor(data)
        
        print(f"{'='*70}\n")
    
    def _display_single_sensor(self, data):
        """Affiche les données d'un seul capteur"""
        if 'sensor_type' in data:
            print(f"🔹 Type de capteur: {data['sensor_type']}")
        
        if 'timestamp' in data:
            print(f"🕐 Timestamp: {data['timestamp']}")
        
        if 'data_index' in data:
            print(f"📍 Index: {data['data_index']}")
        
        if 'measurements' in data:
            print(f"\n📈 Mesures:")
            for key, value in data['measurements'].items():
                if value is not None:
                    print(f"   • {key}: {value}")
                else:
                    print(f"   • {key}: N/A")
        else:
            # Afficher toutes les autres clés
            print(f"\n📋 Données brutes:")
            for key, value in data.items():
                if key not in ['sensor_type', 'timestamp', 'data_index']:
                    print(f"   • {key}: {value}")
    
    def run(self):
        """Lance le service d'ingestion en boucle"""
        print("="*70)
        print("SERVICE D'INGESTION DE DONNÉES CAPTEURS - AgroTrace (Kafka Consumer)")
        print("="*70)
        print(f"Kafka Bootstrap Servers: {self.kafka_bootstrap_servers}")
        print(f"Kafka Topic: {self.kafka_topic}")
        print(f"Groupe de consommateurs: {self.kafka_group_id}")
        print(f"TimescaleDB: {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
        print("="*70)
        print("\nAppuyez sur Ctrl+C pour arrêter le service\n")
        
        # Initialiser TimescaleDB
        if not self.init_database_pool():
            print("Impossible de démarrer le service sans connexion à la base de données")
            return
        
        # Initialiser Kafka Consumer
        if not self.init_kafka_consumer():
            print("Impossible de démarrer le service sans connexion Kafka")
            return
        
        no_message_count = 0
        
        try:
            print("🔄 En attente de messages...\n")
            
            while True:
                try:
                    # Récupérer les messages (avec timeout pour permettre KeyboardInterrupt)
                    messages = self.consumer.poll(timeout_ms=1000)
                    
                    if messages:
                        no_message_count = 0
                        for topic_partition, records in messages.items():
                            for message in records:
                                try:
                                    # Stocker les données (harmonisation + validation + insertion)
                                    self.store_data(message)
                                except Exception as e:
                                    self.error_count += 1
                                    print(f"✗ Erreur lors du traitement du message: {e}")
                    else:
                        no_message_count += 1
                        # Afficher un message d'attente toutes les 30 secondes
                        if no_message_count % 30 == 0:
                            print(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] En attente de nouveaux messages... "
                                  f"(stockés: {self.stored_count}, erreurs: {self.error_count})")
                    
                except KafkaError as e:
                    self.error_count += 1
                    print(f"✗ Erreur Kafka: {e}")
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            print(f"\n\n{'='*70}")
            print("ARRÊT DU SERVICE D'INGESTION")
            print(f"{'='*70}")
            print(f"Total de messages reçus: {self.received_count}")
            print(f"Total de messages stockés: {self.stored_count}")
            print(f"Total d'erreurs: {self.error_count}")
            print(f"{'='*70}\n")
        finally:
            if self.consumer:
                print("Fermeture du consommateur Kafka...")
                self.consumer.close()
                print("✓ Consommateur Kafka fermé")
            if self.db_pool:
                print("Fermeture du pool de connexions TimescaleDB...")
                self.db_pool.closeall()
                print("✓ Pool TimescaleDB fermé")

def main():
    ingestion = SensorDataIngestionKafka()
    ingestion.run()

if __name__ == "__main__":
    main()
