import pandas as pd
import json
import time
import random
from datetime import datetime
from pathlib import Path
from kafka import KafkaProducer
from kafka.errors import KafkaError
import config

class IoTSensorSimulatorKafka:
    def __init__(self):
        self.dataset_folder = Path(config.DATASET_FOLDER)
        self.kafka_bootstrap_servers = config.KAFKA_BOOTSTRAP_SERVERS
        self.kafka_topic = config.KAFKA_TOPIC
        self.send_interval = config.SEND_INTERVAL
        self.sensor_data = {}
        self.last_indices = {}
        self.producer = None
        
    def init_kafka_producer(self):
        """Initialise le producteur Kafka"""
        print(f"Connexion à Kafka: {self.kafka_bootstrap_servers}")
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.producer = KafkaProducer(
                    bootstrap_servers=self.kafka_bootstrap_servers.split(','),
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    key_serializer=lambda k: k.encode('utf-8') if k else None,
                    acks='all',  # Attendre la confirmation de tous les replicas
                    retries=3,
                    max_in_flight_requests_per_connection=1,
                    compression_type='gzip'
                )
                print("✓ Connexion Kafka établie")
                return True
            except Exception as e:
                retry_count += 1
                print(f"✗ Tentative {retry_count}/{max_retries} - Erreur: {e}")
                if retry_count < max_retries:
                    print(f"  Nouvelle tentative dans 5 secondes...")
                    time.sleep(5)
        
        print("✗ Impossible de se connecter à Kafka après plusieurs tentatives")
        return False
        
    def load_datasets(self):
        """Charge tous les fichiers Excel du dossier Dataset"""
        print(f"Chargement des fichiers depuis {self.dataset_folder}...")
        
        excel_files = list(self.dataset_folder.glob('*.xlsx'))
        
        if not excel_files:
            raise FileNotFoundError(f"Aucun fichier Excel trouvé dans {self.dataset_folder}")
        
        for file_path in excel_files:
            sensor_name = file_path.stem
            try:
                # Lire le fichier Excel
                df = pd.read_excel(file_path)
                
                # La première ligne contient les vrais en-têtes
                # Extraire les en-têtes de la première ligne
                headers = df.iloc[0].tolist()
                
                # Renommer les colonnes avec ces en-têtes
                df.columns = headers
                
                # Supprimer la première ligne (maintenant que les en-têtes sont définis)
                df = df.iloc[1:].reset_index(drop=True)
                
                self.sensor_data[sensor_name] = df
                self.last_indices[sensor_name] = -1
                print(f"✓ Chargé: {sensor_name} ({len(df)} lignes)")
            except Exception as e:
                print(f"✗ Erreur lors du chargement de {sensor_name}: {e}")
        
        print(f"\nTotal: {len(self.sensor_data)} capteurs chargés\n")
        
    def get_random_sensor_data(self):
        """Sélectionne aléatoirement un capteur et une ligne de données"""
        if not self.sensor_data:
            return None
        
        # Sélectionner un capteur aléatoire
        available_sensors = list(self.sensor_data.keys())
        
        # Éviter de sélectionner le même capteur deux fois de suite si possible
        if len(available_sensors) > 1:
            last_sensor = getattr(self, 'last_sensor', None)
            if last_sensor and last_sensor in available_sensors:
                available_sensors_filtered = [s for s in available_sensors if s != last_sensor]
                if available_sensors_filtered:
                    available_sensors = available_sensors_filtered
        
        sensor_name = random.choice(available_sensors)
        self.last_sensor = sensor_name
        
        df = self.sensor_data[sensor_name]
        
        # Sélectionner une ligne aléatoire
        available_indices = list(range(len(df)))
        last_idx = self.last_indices[sensor_name]
        
        if len(available_indices) > 1 and last_idx in available_indices:
            available_indices.remove(last_idx)
        
        random_index = random.choice(available_indices)
        self.last_indices[sensor_name] = random_index
        
        row = df.iloc[random_index]
        
        # Extraire les valeurs importantes
        # Les colonnes sont: Date & Time Created, Entry_id, Measurement Unit
        timestamp_col = df.columns[0]  # Date & Time Created
        entry_id_col = df.columns[1]   # Entry_id
        value_col = df.columns[2]      # Measurement Unit (valeur réelle)
        
        # Convertir la ligne en dictionnaire JSON
        data = {
            'sensor_type': sensor_name,
            'timestamp': datetime.now().isoformat(),
            'data_index': int(random_index),
            'original_timestamp': None,
            'entry_id': None,
            'value': None,
            'unit': None
        }
        
        # Extraire le timestamp original
        original_ts = row[timestamp_col]
        if pd.notna(original_ts):
            if isinstance(original_ts, (pd.Timestamp, datetime)):
                data['original_timestamp'] = original_ts.isoformat()
            else:
                data['original_timestamp'] = str(original_ts)
        
        # Extraire l'Entry_id
        entry_id = row[entry_id_col]
        if pd.notna(entry_id):
            try:
                data['entry_id'] = int(entry_id)
            except (ValueError, TypeError):
                data['entry_id'] = str(entry_id)
        
        # Extraire la valeur réelle (de la colonne Measurement Unit)
        measurement_value = row[value_col]
        if pd.notna(measurement_value):
            try:
                data['value'] = float(measurement_value)
            except (ValueError, TypeError):
                data['value'] = str(measurement_value)
        
        # Extraire l'unité depuis le nom de la colonne (ex: "Measurement Unit(Degree Celsius)")
        if 'Measurement Unit' in value_col:
            # Extraire l'unité entre parenthèses
            import re
            unit_match = re.search(r'\(([^)]+)\)', value_col)
            if unit_match:
                data['unit'] = unit_match.group(1)
            else:
                data['unit'] = value_col.replace('Measurement Unit', '').strip()
        else:
            data['unit'] = value_col
        
        return data
    
    def send_to_kafka(self, data):
        """Envoie les données vers Kafka"""
        try:
            # Utiliser le sensor_type comme clé pour le partitionnement
            key = data.get('sensor_type', 'unknown')
            
            # Envoyer le message
            future = self.producer.send(
                self.kafka_topic,
                key=key,
                value=data
            )
            
            # Attendre la confirmation (bloquant)
            record_metadata = future.get(timeout=10)
            
            print(f"✓ [{datetime.now().strftime('%H:%M:%S')}] Envoyé: {data['sensor_type']} "
                  f"→ Topic: {record_metadata.topic}, Partition: {record_metadata.partition}, "
                  f"Offset: {record_metadata.offset}")
            return True
            
        except KafkaError as e:
            print(f"✗ [{datetime.now().strftime('%H:%M:%S')}] Erreur Kafka: {e}")
            return False
        except Exception as e:
            print(f"✗ [{datetime.now().strftime('%H:%M:%S')}] Erreur: {e}")
            return False
    
    def run(self):
        """Lance le simulateur en boucle infinie"""
        print("="*70)
        print("SIMULATEUR DE CAPTEURS IoT - AgroTrace (Kafka Producer)")
        print("="*70)
        print(f"Kafka Bootstrap Servers: {self.kafka_bootstrap_servers}")
        print(f"Kafka Topic: {self.kafka_topic}")
        print(f"Intervalle d'envoi: {self.send_interval} seconde(s)")
        print("="*70)
        print("\nAppuyez sur Ctrl+C pour arrêter le simulateur\n")
        
        # Initialiser Kafka
        if not self.init_kafka_producer():
            print("Impossible de démarrer le simulateur sans connexion Kafka")
            return
        
        # Charger les datasets
        self.load_datasets()
        
        if not self.sensor_data:
            print("Aucune donnée chargée. Arrêt du simulateur.")
            return
        
        sent_count = 0
        error_count = 0
        
        try:
            while True:
                # Récupérer des données aléatoires
                data = self.get_random_sensor_data()
                
                if data:
                    # Envoyer les données vers Kafka
                    if self.send_to_kafka(data):
                        sent_count += 1
                    else:
                        error_count += 1
                    
                    # Afficher les statistiques toutes les 10 envois
                    if (sent_count + error_count) % 10 == 0:
                        print(f"\n--- Stats: {sent_count} envoyés, {error_count} erreurs ---\n")
                
                # Attendre avant le prochain envoi
                time.sleep(self.send_interval)
                
        except KeyboardInterrupt:
            print(f"\n\n{'='*70}")
            print("ARRÊT DU SIMULATEUR")
            print(f"{'='*70}")
            print(f"Total envoyés: {sent_count}")
            print(f"Total erreurs: {error_count}")
            print(f"{'='*70}\n")
        finally:
            if self.producer:
                print("Fermeture du producteur Kafka...")
                self.producer.flush()
                self.producer.close()
                print("✓ Producteur Kafka fermé")

def main():
    simulator = IoTSensorSimulatorKafka()
    simulator.run()

if __name__ == "__main__":
    main()
