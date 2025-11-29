import pandas as pd
import requests
import json
import time
import random
import os
from datetime import datetime
from pathlib import Path
import config

class IoTSensorSimulator:
    def __init__(self):
        self.dataset_folder = Path(config.DATASET_FOLDER)
        self.api_endpoint = config.API_ENDPOINT
        self.send_interval = config.SEND_INTERVAL
        self.sensor_data = {}
        self.last_indices = {}
        
    def load_datasets(self):
        """Charge tous les fichiers Excel du dossier Dataset"""
        print(f"Chargement des fichiers depuis {self.dataset_folder}...")
        
        excel_files = list(self.dataset_folder.glob('*.xlsx'))
        
        if not excel_files:
            raise FileNotFoundError(f"Aucun fichier Excel trouvé dans {self.dataset_folder}")
        
        for file_path in excel_files:
            sensor_name = file_path.stem
            try:
                df = pd.read_excel(file_path)
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
            # Filtrer le dernier capteur utilisé
            last_sensor = getattr(self, 'last_sensor', None)
            if last_sensor and last_sensor in available_sensors:
                available_sensors_filtered = [s for s in available_sensors if s != last_sensor]
                if available_sensors_filtered:
                    available_sensors = available_sensors_filtered
        
        sensor_name = random.choice(available_sensors)
        self.last_sensor = sensor_name
        
        df = self.sensor_data[sensor_name]
        
        # Sélectionner une ligne aléatoire (éviter la répétition immédiate)
        available_indices = list(range(len(df)))
        last_idx = self.last_indices[sensor_name]
        
        if len(available_indices) > 1 and last_idx in available_indices:
            available_indices.remove(last_idx)
        
        random_index = random.choice(available_indices)
        self.last_indices[sensor_name] = random_index
        
        row = df.iloc[random_index]
        
        # Convertir la ligne en dictionnaire JSON
        data = {
            'sensor_type': sensor_name,
            'timestamp': datetime.now().isoformat(),
            'data_index': int(random_index),
            'measurements': {}
        }
        
        # Ajouter toutes les colonnes comme mesures
        for column in df.columns:
            value = row[column]
            # Convertir les types pandas en types Python natifs
            if pd.isna(value):
                data['measurements'][column] = None
            elif isinstance(value, (pd.Timestamp, datetime)):
                data['measurements'][column] = value.isoformat()
            elif isinstance(value, (int, float)):
                data['measurements'][column] = float(value) if not pd.isna(value) else None
            else:
                data['measurements'][column] = str(value)
        
        return data
    
    def send_data(self, data):
        """Envoie les données à l'API REST"""
        try:
            response = requests.post(
                self.api_endpoint,
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                print(f"✓ [{datetime.now().strftime('%H:%M:%S')}] Envoyé: {data['sensor_type']}")
                return True
            else:
                print(f"✗ [{datetime.now().strftime('%H:%M:%S')}] Erreur {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.ConnectionError:
            print(f"✗ [{datetime.now().strftime('%H:%M:%S')}] Connexion refusée à {self.api_endpoint}")
            return False
        except requests.exceptions.Timeout:
            print(f"✗ [{datetime.now().strftime('%H:%M:%S')}] Timeout lors de l'envoi")
            return False
        except Exception as e:
            print(f"✗ [{datetime.now().strftime('%H:%M:%S')}] Erreur: {e}")
            return False
    
    def run(self):
        """Lance le simulateur en boucle infinie"""
        print("="*60)
        print("SIMULATEUR DE CAPTEURS IoT - AgroTrace")
        print("="*60)
        print(f"API Endpoint: {self.api_endpoint}")
        print(f"Intervalle d'envoi: {self.send_interval} seconde(s)")
        print("="*60)
        print("\nAppuyez sur Ctrl+C pour arrêter le simulateur\n")
        
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
                    # Envoyer les données
                    if self.send_data(data):
                        sent_count += 1
                    else:
                        error_count += 1
                    
                    # Afficher les statistiques toutes les 10 envois
                    if (sent_count + error_count) % 10 == 0:
                        print(f"\n--- Stats: {sent_count} envoyés, {error_count} erreurs ---\n")
                
                # Attendre avant le prochain envoi
                time.sleep(self.send_interval)
                
        except KeyboardInterrupt:
            print(f"\n\n{'='*60}")
            print("ARRÊT DU SIMULATEUR")
            print(f"{'='*60}")
            print(f"Total envoyés: {sent_count}")
            print(f"Total erreurs: {error_count}")
            print(f"{'='*60}\n")

def main():
    simulator = IoTSensorSimulator()
    simulator.run()

if __name__ == "__main__":
    main()
