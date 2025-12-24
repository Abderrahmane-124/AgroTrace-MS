"""
Service Kafka pour consommer les événements et appliquer les règles
"""
import json
import logging
import os
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from typing import Dict, List
from rules_engine import rules_engine
from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_WATER_FORECAST,
    KAFKA_TOPIC_DISEASE_DETECTED,
    KAFKA_TOPIC_SENSOR_DATA,
    KAFKA_TOPIC_RECOMMENDATIONS,
    KAFKA_GROUP_ID
)

logger = logging.getLogger(__name__)

# Mapping des plot_id vers les zones MS6
# Les capteurs envoient des IDs numériques, MS6 attend PLOT-001, PLOT-002, PLOT-003
PLOT_ID_MAPPING = {
    # IDs numériques
    '1': 'PLOT-001',
    '2': 'PLOT-002', 
    '3': 'PLOT-003',
    '4': 'PLOT-001',  # cycle sur les zones
    '5': 'PLOT-002',
    # IDs avec préfixe
    'plot_1': 'PLOT-001',
    'plot_2': 'PLOT-002',
    'plot_3': 'PLOT-003',
    'plot-1': 'PLOT-001',
    'plot-2': 'PLOT-002',
    'plot-3': 'PLOT-003',
    # Zones MS6 directes
    'PLOT-001': 'PLOT-001',
    'PLOT-002': 'PLOT-002',
    'PLOT-003': 'PLOT-003',
}



class KafkaService:
    """Service de traitement des événements Kafka"""
    
    def _extract_crop_from_class(self, class_name: str) -> str:
        """
        Extrait le type de culture depuis le nom de classe de maladie.
        Ex: 'Apple___Apple_scab' -> 'Apple'
            'Tomato___Late_blight' -> 'Tomato'
        """
        if not class_name:
            return 'unknown'
        
        # Format standard: Plante___Maladie
        if '___' in class_name:
            return class_name.split('___')[0]
        
        # Format alternatif: Plante_Maladie
        parts = class_name.split('_')
        if parts:
            return parts[0]
        
        return class_name
    
    def _normalize_plot_id(self, plot_id) -> str:
        """
        Normalise un plot_id vers le format MS6 (PLOT-001, PLOT-002, PLOT-003).
        Permet la compatibilité entre les données capteurs et les zones d'irrigation.
        """
        if not plot_id:
            # Fallback vers PLOT-001 si pas de plot_id
            return 'PLOT-001'
        
        plot_id_str = str(plot_id).strip()
        
        # Vérifier le mapping direct
        if plot_id_str in PLOT_ID_MAPPING:
            return PLOT_ID_MAPPING[plot_id_str]
        
        # Essayer en minuscule
        if plot_id_str.lower() in PLOT_ID_MAPPING:
            return PLOT_ID_MAPPING[plot_id_str.lower()]
        
        # Si c'est un nombre, mapper cycliquement
        try:
            num = int(plot_id_str)
            zone_num = ((num - 1) % 3) + 1  # 1, 2, 3 cyclique
            return f'PLOT-00{zone_num}'
        except ValueError:
            pass
        
        # Fallback: retourner PLOT-001
        logger.warning(f"Plot ID inconnu '{plot_id}', mapping vers PLOT-001")
        return 'PLOT-001'
    
    def __init__(self):
        """Initialise les consumers et producer Kafka"""
        self.bootstrap_servers = KAFKA_BOOTSTRAP_SERVERS
        self.group_id = KAFKA_GROUP_ID
        
        # Producer pour les recommandations
        self.producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            acks='all',
            retries=3
        )
        
        logger.info(f"Producer Kafka initialisé: {self.bootstrap_servers}")
    
    def send_recommendation(self, recommendation: Dict):
        """
        Envoie une recommandation vers Kafka
        
        Args:
            recommendation: Dict de recommandation
        """
        try:
            plot_id = recommendation.get('plot_id', 'UNKNOWN')
            
            future = self.producer.send(
                KAFKA_TOPIC_RECOMMENDATIONS,
                key=plot_id,
                value=recommendation
            )
            
            # Attendre confirmation (synchrone pour fiabilité)
            record_metadata = future.get(timeout=10)
            
            logger.info(f"Recommandation envoyée: plot={plot_id}, "
                       f"type={recommendation['type']}, "
                       f"priority={recommendation['priority']}, "
                       f"partition={record_metadata.partition}")
        
        except KafkaError as e:
            logger.error(f"Erreur envoi Kafka: {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue envoi recommandation: {e}")
    
    def send_recommendations(self, recommendations: List[Dict]):
        """
        Envoie plusieurs recommandations
        
        Args:
            recommendations: Liste de recommandations
        """
        for rec in recommendations:
            self.send_recommendation(rec)
    
    def consume_water_forecast(self):
        """Consomme le topic water.forecast et applique règles d'irrigation"""
        consumer = KafkaConsumer(
            KAFKA_TOPIC_WATER_FORECAST,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=True
        )
        
        logger.info(f"Consumer démarré: {KAFKA_TOPIC_WATER_FORECAST}")
        
        try:
            for message in consumer:
                try:
                    data = message.value
                    logger.info(f"Reçu water.forecast: plot={data.get('plot_id')}")
                    
                    # Normaliser les noms de champs
                    raw_plot_id = data.get('plotId') or data.get('plot_id')
                    normalized_data = {
                        'plot_id': self._normalize_plot_id(raw_plot_id),
                        'soil_moisture': data.get('soilMoisture') or data.get('soil_moisture'),
                        'temperature': data.get('temperature'),
                        'humidity': data.get('humidity'),
                        'forecasted_needs': data.get('forecastedNeeds') or data.get('forecasted_needs')
                    }
                    
                    # Appliquer règles
                    recommendations = rules_engine.evaluate_water_forecast(normalized_data)
                    
                    # Envoyer recommandations
                    if recommendations:
                        logger.info(f"Génération de {len(recommendations)} recommandation(s) irrigation")
                        self.send_recommendations(recommendations)
                    else:
                        logger.debug(f"Aucune règle irrigation déclenchée pour plot {normalized_data['plot_id']}")
                
                except Exception as e:
                    logger.error(f"Erreur traitement water.forecast: {e}", exc_info=True)
        
        finally:
            consumer.close()
    
    def consume_disease_detected(self):
        """Consomme le topic disease.detected et applique règles de traitement"""
        consumer = KafkaConsumer(
            KAFKA_TOPIC_DISEASE_DETECTED,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=True
        )
        
        logger.info(f"Consumer démarré: {KAFKA_TOPIC_DISEASE_DETECTED}")
        
        try:
            for message in consumer:
                try:
                    data = message.value
                    
                    # MS3 produit: {image_path, detection_results: {predicted_class, confidence, is_diseased, ...}}
                    detection_results = data.get('detection_results', {})
                    
                    # Extraire plot_id depuis image_path (ex: "mixed_images/Apple___scab_1.jpg" -> "plot_001")
                    image_path = data.get('image_path', '')
                    # Utiliser le nom de fichier comme identifiant de plot temporaire
                    plot_id = data.get('plot_id') or data.get('plotId') or os.path.basename(image_path).split('.')[0] or 'unknown_plot'
                    
                    # Extraire le nom de maladie depuis predicted_class
                    disease_name = detection_results.get('predicted_class', data.get('disease_name') or data.get('diseaseName'))
                    confidence = detection_results.get('confidence', data.get('confidence'))
                    is_diseased = detection_results.get('is_diseased', False)
                    
                    logger.info(f"Reçu disease.detected: plot={plot_id}, "
                               f"disease={disease_name}, confidence={confidence}")
                    
                    # Si pas de maladie détectée (healthy), ignorer
                    if not is_diseased:
                        logger.debug(f"Plante saine détectée, pas de recommandation générée")
                        continue
                    
                    # Normaliser les noms de champs
                    normalized_data = {
                        'plot_id': plot_id,
                        'disease_name': disease_name,
                        'confidence': confidence,
                        'severity': data.get('severity') or ('HIGH' if confidence and confidence > 0.8 else 'MEDIUM'),
                        'crop_type': data.get('cropType') or data.get('crop_type') or self._extract_crop_from_class(disease_name)
                    }
                    
                    # Appliquer règles
                    recommendations = rules_engine.evaluate_disease_detection(normalized_data)
                    
                    # Envoyer recommandations
                    if recommendations:
                        logger.info(f"Génération de {len(recommendations)} recommandation(s) traitement")
                        self.send_recommendations(recommendations)
                    else:
                        logger.debug(f"Aucune règle maladie déclenchée pour plot {normalized_data['plot_id']}")
                
                except Exception as e:
                    logger.error(f"Erreur traitement disease.detected: {e}", exc_info=True)
        
        finally:
            consumer.close()
    
    def consume_sensor_data(self):
        """Consomme le topic sensor-data-processed et applique règles de sol"""
        consumer = KafkaConsumer(
            KAFKA_TOPIC_SENSOR_DATA,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=True
        )
        
        logger.info(f"Consumer démarré: {KAFKA_TOPIC_SENSOR_DATA}")
        
        try:
            for message in consumer:
                try:
                    data = message.value
                    logger.info(f"Reçu sensor-data: plot={data.get('plot_id')}")
                    
                    # Normaliser les noms de champs
                    raw_plot_id = data.get('plotId') or data.get('plot_id')
                    normalized_data = {
                        'plot_id': self._normalize_plot_id(raw_plot_id),
                        'soil_moisture': data.get('soilMoisture') or data.get('soil_moisture'),
                        'temperature': data.get('temperature'),
                        'humidity': data.get('humidity'),
                        'ph': data.get('ph'),
                        'nitrogen': data.get('nitrogen'),
                        'phosphorus': data.get('phosphorus'),
                        'potassium': data.get('potassium')
                    }
                    
                    # Appliquer règles
                    recommendations = rules_engine.evaluate_sensor_data(normalized_data)
                    
                    # Envoyer recommandations
                    if recommendations:
                        logger.info(f"Génération de {len(recommendations)} recommandation(s) sol/fertilisation")
                        self.send_recommendations(recommendations)
                    else:
                        logger.debug(f"Aucune règle sol déclenchée pour plot {normalized_data['plot_id']}")
                
                except Exception as e:
                    logger.error(f"Erreur traitement sensor-data: {e}", exc_info=True)
        
        finally:
            consumer.close()
    
    def close(self):
        """Ferme le producer"""
        if self.producer:
            self.producer.flush()
            self.producer.close()
            logger.info("Producer Kafka fermé")
