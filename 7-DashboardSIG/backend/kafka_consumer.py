# ========================================
# Kafka Consumer pour DashboardSIG
# ========================================

import json
import threading
from kafka import KafkaConsumer
from datetime import datetime
import random

from config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_GROUP_ID, KAFKA_TOPICS, MINIO_PUBLIC_URL, MINIO_BUCKET
from database import (
    update_parcel_status, add_water_forecast, 
    add_disease_detection, add_recommendation
)


class DashboardKafkaConsumer:
    """Consumer Kafka pour recevoir les mises à jour des autres microservices"""
    
    def __init__(self):
        self.consumer = None
        self.running = False
        self.thread = None
        # Mapping simple des capteurs aux parcelles (simulation)
        self.sensor_parcel_map = {}
    
    def start(self):
        """Démarre le consumer dans un thread séparé"""
        self.running = True
        self.thread = threading.Thread(target=self._consume_messages, daemon=True)
        self.thread.start()
        print(f"🎧 Kafka Consumer démarré - Topics: {KAFKA_TOPICS}")
    
    def stop(self):
        """Arrête le consumer"""
        self.running = False
        if self.consumer:
            self.consumer.close()
        print("🛑 Kafka Consumer arrêté")
    
    def _consume_messages(self):
        """Consomme les messages Kafka"""
        try:
            self.consumer = KafkaConsumer(
                *KAFKA_TOPICS,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=KAFKA_GROUP_ID,
                auto_offset_reset='latest',
                value_deserializer=lambda m: json.loads(m.decode('utf-8')) if m else None,
                consumer_timeout_ms=1000
            )
            
            while self.running:
                try:
                    # Poll avec timeout
                    messages = self.consumer.poll(timeout_ms=1000)
                    
                    for topic_partition, records in messages.items():
                        topic = topic_partition.topic
                        for record in records:
                            try:
                                self._process_message(topic, record.value)
                            except Exception as e:
                                print(f"⚠ Erreur traitement message: {e}")
                
                except Exception as e:
                    if self.running:
                        print(f"⚠ Erreur polling Kafka: {e}")
                        
        except Exception as e:
            print(f"❌ Erreur connexion Kafka: {e}")
    
    def _process_message(self, topic: str, message: dict):
        """Traite un message selon le topic"""
        if not message:
            return
            
        print(f"📨 Message reçu - Topic: {topic}")
        
        try:
            if topic == "sensor-data-processed":
                self._handle_sensor_data(message)
            elif topic == "water.forecast":
                self._handle_water_forecast(message)
            elif topic == "disease.detected":
                self._handle_disease_detection(message)
            elif topic == "agro.recommendations":
                self._handle_recommendation(message)
        except Exception as e:
            print(f"⚠ Erreur traitement {topic}: {e}")
    
    def _handle_sensor_data(self, data: dict):
        """Traite les données capteurs prétraitées"""
        # Assigner à une parcelle (1-5 pour démo)
        parcel_id = self._get_parcel_for_sensor(data.get('sensor_type', 'unknown'))
        
        status_data = {}
        
        sensor_type = data.get('sensor_type', '').lower()
        value = data.get('processed_value', data.get('value'))
        
        if 'moisture' in sensor_type or 'soil' in sensor_type:
            status_data['soil_moisture'] = float(value) if value else None
            # Calculer stress hydrique
            if value and float(value) < 30:
                status_data['water_stress_level'] = 100 - float(value)
                status_data['health_status'] = 'HIGH' if float(value) < 20 else 'MODERATE'
        elif 'temp' in sensor_type:
            status_data['temperature'] = float(value) if value else None
        elif 'humid' in sensor_type:
            status_data['humidity'] = float(value) if value else None
        
        if status_data and parcel_id:
            update_parcel_status(parcel_id, status_data)
            print(f"   ✓ Parcelle {parcel_id} mise à jour: {list(status_data.keys())}")
    
    def _handle_water_forecast(self, data: dict):
        """Traite les prévisions hydriques"""
        parcel_id = data.get('parcel_id', random.randint(1, 5))
        
        forecast_data = {
            'forecast_date': data.get('forecast_date', datetime.now().date()),
            'predicted_need': data.get('water_need_mm', data.get('predicted_need', 0)),
            'stress_level': data.get('stress_level', 'MODERATE'),
            'confidence': data.get('confidence', 0.8),
            'recommendation': data.get('recommendation', '')
        }
        
        add_water_forecast(parcel_id, forecast_data)
        
        # Mettre à jour le statut de la parcelle
        status_data = {
            'water_stress_level': data.get('stress_level_percent', 50),
            'health_status': forecast_data['stress_level']
        }
        update_parcel_status(parcel_id, status_data)
        
        print(f"   ✓ Prévision ajoutée pour parcelle {parcel_id}")
    
    def _build_image_url(self, image_path: str) -> str:
        """Construit l'URL complète MinIO pour une image"""
        if not image_path:
            return ""
        
        # Si c'est déjà une URL complète, la retourner telle quelle
        if image_path.startswith('http://') or image_path.startswith('https://'):
            return image_path
        
        # Nettoyer le chemin (enlever les slashes en trop au début)
        clean_path = image_path.lstrip('/')
        
        # Construire l'URL MinIO complète
        # Format: http://localhost:9000/bucket-name/path/to/image.jpg
        return f"{MINIO_PUBLIC_URL}/{MINIO_BUCKET}/{clean_path}"
    
    def _handle_disease_detection(self, data: dict):
        """Traite les détections de maladies"""
        import os
        
        # MS3 produit: {image_path, detection_results: {predicted_class, confidence, is_diseased, ...}}
        detection_results = data.get('detection_results', {})
        
        # Extraire le plot_id depuis image_path ou utiliser un ID aléatoire
        image_path = data.get('image_path', '')
        parcel_id = data.get('parcel_id') or random.randint(1, 5)
        
        # Extraire le nom de maladie depuis detection_results
        disease_name = (
            detection_results.get('predicted_class') or 
            data.get('disease_name') or 
            data.get('predicted_class') or 
            'Unknown'
        )
        
        # Extraire la confiance
        confidence = (
            detection_results.get('confidence') or 
            data.get('confidence') or 
            data.get('probability') or 
            0
        )
        
        # Vérifier si une maladie est réellement détectée
        is_diseased = detection_results.get('is_diseased', False)
        
        detection_data = {
            'disease_name': disease_name,
            'confidence': confidence,
            'treatment_recommendation': data.get('treatment', self._get_treatment_recommendation(disease_name)),
            'image_url': self._build_image_url(image_path)
        }
        
        # Ne traiter que si une maladie est détectée (pas healthy)
        if is_diseased or (confidence > 0.5 and 'healthy' not in disease_name.lower()):
            add_disease_detection(parcel_id, detection_data)
            
            # Mettre à jour le statut si confiance élevée
            if detection_data['confidence'] > 0.6:
                status_data = {
                    'disease_detected': detection_data['disease_name'],
                    'disease_confidence': detection_data['confidence'],
                    'health_status': 'HIGH' if detection_data['confidence'] > 0.8 else 'MODERATE'
                }
                update_parcel_status(parcel_id, status_data)
            
            print(f"   ✓ Maladie détectée sur parcelle {parcel_id}: {detection_data['disease_name']} ({confidence*100:.1f}%)")
        else:
            print(f"   ✓ Plante saine détectée: {disease_name}")
    
    def _get_treatment_recommendation(self, disease_name: str) -> str:
        """Génère une recommandation de traitement basique basée sur le nom de la maladie"""
        disease_lower = disease_name.lower()
        
        if 'scab' in disease_lower:
            return "Appliquer un fongicide à base de cuivre. Éliminer les feuilles infectées."
        elif 'rust' in disease_lower:
            return "Traiter avec un fongicide systémique. Améliorer la circulation d'air."
        elif 'blight' in disease_lower:
            return "Retirer les parties affectées. Appliquer un fongicide préventif."
        elif 'mold' in disease_lower or 'mildew' in disease_lower:
            return "Réduire l'humidité. Appliquer un traitement anti-fongique."
        elif 'spot' in disease_lower:
            return "Éliminer les feuilles touchées. Traitement fongicide recommandé."
        elif 'rot' in disease_lower:
            return "Améliorer le drainage. Retirer les parties pourries."
        else:
            return "Consulter un agronome pour un diagnostic précis."
    
    def _handle_recommendation(self, data: dict):
        """Traite les recommandations stratégiques"""
        parcel_id = data.get('parcel_id', random.randint(1, 5))
        
        rec_data = {
            'type': data.get('type', data.get('action_type', 'GENERAL')),
            'priority': data.get('priority', 'MEDIUM'),
            'action_code': data.get('action_code', ''),
            'description': data.get('description', data.get('recommendation', '')),
            'quantity': data.get('quantity'),
            'unit': data.get('unit'),
            'expires_at': None
        }
        
        add_recommendation(parcel_id, rec_data)
        
        # Mettre à jour la dernière recommandation
        update_parcel_status(parcel_id, {
            'recommendation': rec_data['description'][:500] if rec_data['description'] else None
        })
        
        print(f"   ✓ Recommandation ajoutée pour parcelle {parcel_id}")
    
    def _get_parcel_for_sensor(self, sensor_type: str) -> int:
        """Retourne l'ID de parcelle pour un type de capteur (simulation)"""
        # Simple hash pour distribuer les capteurs entre les parcelles
        if sensor_type not in self.sensor_parcel_map:
            self.sensor_parcel_map[sensor_type] = (hash(sensor_type) % 5) + 1
        return self.sensor_parcel_map[sensor_type]


# Instance globale
kafka_consumer = DashboardKafkaConsumer()
