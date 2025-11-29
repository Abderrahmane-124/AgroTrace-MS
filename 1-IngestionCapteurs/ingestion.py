import requests
import time
import json
from datetime import datetime
import config

class SensorDataIngestion:
    def __init__(self):
        self.api_endpoint = config.API_ENDPOINT
        self.fetch_interval = config.FETCH_INTERVAL
        self.received_count = 0
        
    def fetch_data(self):
        """Récupère les données depuis l'API"""
        try:
            response = requests.get(
                self.api_endpoint,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                return data
            else:
                print(f"✗ [{datetime.now().strftime('%H:%M:%S')}] Erreur {response.status_code}: {response.text}")
                return None
                
        except requests.exceptions.ConnectionError:
            print(f"✗ [{datetime.now().strftime('%H:%M:%S')}] Connexion refusée à {self.api_endpoint}")
            return None
        except requests.exceptions.Timeout:
            print(f"✗ [{datetime.now().strftime('%H:%M:%S')}] Timeout lors de la récupération")
            return None
        except Exception as e:
            print(f"✗ [{datetime.now().strftime('%H:%M:%S')}] Erreur: {e}")
            return None
    
    def display_data(self, data):
        """Affiche les données reçues de manière formatée"""
        self.received_count += 1
        
        print(f"\n{'='*70}")
        print(f"📊 DONNÉES REÇUES #{self.received_count} - [{datetime.now().strftime('%H:%M:%S')}]")
        print(f"{'='*70}")
        
        if isinstance(data, dict):
            # Si c'est un seul objet de données
            self._display_single_sensor(data)
        elif isinstance(data, list):
            # Si c'est une liste de données
            print(f"Nombre d'éléments: {len(data)}")
            for idx, item in enumerate(data, 1):
                print(f"\n--- Élément {idx} ---")
                self._display_single_sensor(item)
        else:
            print(json.dumps(data, indent=2))
        
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
        print("SERVICE D'INGESTION DE DONNÉES CAPTEURS - AgroTrace")
        print("="*70)
        print(f"API Endpoint: {self.api_endpoint}")
        print(f"Intervalle de récupération: {self.fetch_interval} seconde(s)")
        print("="*70)
        print("\nAppuyez sur Ctrl+C pour arrêter le service\n")
        
        error_count = 0
        
        try:
            while True:
                # Récupérer les données
                data = self.fetch_data()
                
                if data:
                    # Afficher les données
                    self.display_data(data)
                else:
                    error_count += 1
                    
                    # Afficher un message d'erreur tous les 5 échecs
                    if error_count % 5 == 0:
                        print(f"\n⚠️  {error_count} tentatives échouées. Vérifiez que l'API est accessible.\n")
                
                # Attendre avant la prochaine récupération
                time.sleep(self.fetch_interval)
                
        except KeyboardInterrupt:
            print(f"\n\n{'='*70}")
            print("ARRÊT DU SERVICE D'INGESTION")
            print(f"{'='*70}")
            print(f"Total de données reçues: {self.received_count}")
            print(f"Total d'erreurs: {error_count}")
            print(f"{'='*70}\n")

def main():
    ingestion = SensorDataIngestion()
    ingestion.run()

if __name__ == "__main__":
    main()
