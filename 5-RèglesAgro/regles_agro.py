"""
Point d'entrée principal du microservice MS5 - RèglesAgro
Lance les consumers Kafka en parallèle
"""
import logging
import sys
from threading import Thread
from kafka_service import KafkaService
from config import LOG_LEVEL

# Configuration logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Fonction principale"""
    logger.info("=" * 60)
    logger.info("MS5 - RèglesAgro - Moteur de Règles Agronomiques")
    logger.info("=" * 60)
    
    # Initialiser le service Kafka
    kafka_service = KafkaService()
    
    # Créer les threads pour les 3 consumers
    threads = [
        Thread(
            target=kafka_service.consume_water_forecast,
            name="Consumer-WaterForecast",
            daemon=True
        ),
        Thread(
            target=kafka_service.consume_disease_detected,
            name="Consumer-DiseaseDetected",
            daemon=True
        ),
        Thread(
            target=kafka_service.consume_sensor_data,
            name="Consumer-SensorData",
            daemon=True
        )
    ]
    
    # Démarrer tous les consumers
    logger.info("Démarrage des consumers Kafka...")
    for thread in threads:
        thread.start()
        logger.info(f"Thread démarré: {thread.name}")
    
    logger.info("Tous les consumers sont actifs. En attente d'événements...")
    
    # Attendre que les threads se terminent (jamais en mode normal)
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur (Ctrl+C)")
    finally:
        kafka_service.close()
        logger.info("Service arrêté proprement")


if __name__ == "__main__":
    main()
