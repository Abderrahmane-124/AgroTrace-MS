"""
Service Kafka pour consommer les événements et appliquer les règles
"""
import json
import logging
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


class KafkaService:
    """Service de traitement des événements Kafka"""
    
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
                    normalized_data = {
                        'plot_id': data.get('plotId') or data.get('plot_id'),
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
                    logger.info(f"Reçu disease.detected: plot={data.get('plot_id')}, "
                               f"disease={data.get('disease_name')}")
                    
                    # Normaliser les noms de champs
                    normalized_data = {
                        'plot_id': data.get('plotId') or data.get('plot_id'),
                        'disease_name': data.get('diseaseName') or data.get('disease_name'),
                        'confidence': data.get('confidence'),
                        'severity': data.get('severity'),
                        'crop_type': data.get('cropType') or data.get('crop_type')
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
                    normalized_data = {
                        'plot_id': data.get('plotId') or data.get('plot_id'),
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
