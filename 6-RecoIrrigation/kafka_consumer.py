"""
Service Kafka pour consommer les recommandations MS5
"""
import json
import logging
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from threading import Thread
from typing import Dict, Optional, List
from datetime import datetime
from collections import deque
from models import RecommendationInput
from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_RECOMMENDATIONS,
    KAFKA_GROUP_ID
)

logger = logging.getLogger(__name__)


class RecommendationCache:
    """Cache en mémoire des dernières recommandations par plot"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.recommendations: Dict[str, deque] = {}
    
    def add(self, plot_id: str, recommendation: RecommendationInput):
        """Ajoute une recommandation au cache"""
        if plot_id not in self.recommendations:
            self.recommendations[plot_id] = deque(maxlen=20)  # Max 20 par plot
        
        self.recommendations[plot_id].append(recommendation)
        logger.debug(f"Recommandation ajoutée au cache: plot={plot_id}, action={recommendation.action}")
    
    def get_latest(self, plot_id: str, type_filter: str = None) -> Optional[RecommendationInput]:
        """
        Récupère la dernière recommandation pour un plot
        
        Args:
            plot_id: ID de la parcelle
            type_filter: Filtrer par type (ex: 'IRRIGATION')
        
        Returns:
            Dernière recommandation ou None
        """
        if plot_id not in self.recommendations:
            return None
        
        # Parcourir de la plus récente à la plus ancienne
        for rec in reversed(self.recommendations[plot_id]):
            if type_filter is None or rec.type == type_filter:
                return rec
        
        return None
    
    def get_all(self, plot_id: str, type_filter: str = None) -> list:
        """Récupère toutes les recommandations pour un plot"""
        if plot_id not in self.recommendations:
            return []
        
        recs = list(self.recommendations[plot_id])
        
        if type_filter:
            recs = [r for r in recs if r.type == type_filter]
        
        return recs


class KafkaRecommendationConsumer:
    """Consumer Kafka pour les recommandations MS5"""
    
    def __init__(self):
        self.bootstrap_servers = KAFKA_BOOTSTRAP_SERVERS
        self.topic = KAFKA_TOPIC_RECOMMENDATIONS
        self.group_id = KAFKA_GROUP_ID
        self.consumer = None
        self.cache = RecommendationCache()
        self.running = False
        self.thread = None
    
    def start(self):
        """Démarre le consumer Kafka en thread séparé"""
        if self.running:
            logger.warning("Consumer déjà en cours d'exécution")
            return
        
        self.running = True
        self.thread = Thread(target=self._consume, daemon=True, name="KafkaConsumerThread")
        self.thread.start()
        logger.info(f"Consumer Kafka démarré: topic={self.topic}")
    
    def stop(self):
        """Arrête le consumer"""
        self.running = False
        if self.consumer:
            self.consumer.close()
        logger.info("Consumer Kafka arrêté")
    
    def _consume(self):
        """Boucle de consommation Kafka"""
        try:
            self.consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',  # Seulement nouvelles recommandations
                enable_auto_commit=True,
                consumer_timeout_ms=1000  # Timeout pour permettre arrêt propre
            )
            
            logger.info(f"Consumer connecté: {self.topic}")
            
            while self.running:
                try:
                    # Poll avec timeout court pour vérifier self.running
                    messages = self.consumer.poll(timeout_ms=1000)
                    
                    for topic_partition, records in messages.items():
                        for record in records:
                            self._process_recommendation(record.value)
                
                except Exception as e:
                    logger.error(f"Erreur traitement message: {e}", exc_info=True)
        
        except KafkaError as e:
            logger.error(f"Erreur connexion Kafka: {e}")
        finally:
            if self.consumer:
                self.consumer.close()
    
    def _process_recommendation(self, data: Dict):
        """
        Traite une recommandation reçue
        
        Args:
            data: Données JSON de la recommandation
        """
        try:
            # Parser en modèle Pydantic
            recommendation = RecommendationInput(
                plot_id=data.get('plot_id'),
                timestamp=datetime.fromisoformat(data.get('timestamp')),
                type=data.get('type'),
                priority=data.get('priority'),
                action=data.get('action'),
                details=data.get('details'),
                source=data.get('source'),
                quantity=data.get('quantity'),
                unit=data.get('unit'),
                soil_moisture=data.get('soil_moisture'),
                temperature=data.get('temperature')
            )
            
            # Ajouter au cache
            self.cache.add(recommendation.plot_id, recommendation)
            
            logger.info(f"Recommandation reçue: plot={recommendation.plot_id}, "
                       f"type={recommendation.type}, priority={recommendation.priority}")
        
        except Exception as e:
            logger.error(f"Erreur parsing recommandation: {e}", exc_info=True)
    
    def get_latest_irrigation_recommendation(self, plot_id: str) -> Optional[RecommendationInput]:
        """
        Récupère la dernière recommandation d'irrigation pour un plot
        
        Args:
            plot_id: ID de la parcelle
        
        Returns:
            Recommandation ou None
        """
        return self.cache.get_latest(plot_id, type_filter='IRRIGATION')
    
    def get_all_recommendations(self, plot_id: str) -> list:
        """Récupère toutes les recommandations pour un plot"""
        return self.cache.get_all(plot_id)


# Instance globale
kafka_consumer = KafkaRecommendationConsumer()


def get_latest_irrigation_recommendation(plot_id: str) -> Optional[Dict]:
    """
    Fonction helper pour récupérer la dernière recommandation d'irrigation.
    Wrapper autour de la méthode de l'instance kafka_consumer.
    
    Args:
        plot_id: ID de la parcelle
    
    Returns:
        Dictionnaire de la recommandation ou None
    """
    recommendation = kafka_consumer.get_latest_irrigation_recommendation(plot_id)
    if recommendation:
        return {
            "plot_id": recommendation.plot_id,
            "timestamp": recommendation.timestamp.isoformat(),
            "type": recommendation.type,
            "priority": recommendation.priority,
            "action": recommendation.action,
            "details": recommendation.details,
            "source": recommendation.source,
            "quantity": recommendation.quantity,
            "unit": recommendation.unit,
            "soil_moisture": recommendation.soil_moisture,
            "temperature": recommendation.temperature
        }
    return None
