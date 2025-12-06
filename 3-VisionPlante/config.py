"""
Configuration du microservice MS3 - VisionPlante
Détection des maladies foliaires avec Abuzaid01/plant-disease-classifier
"""

import os

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_IMAGE_TOPIC = os.getenv("KAFKA_IMAGE_TOPIC", "image.uploaded")
KAFKA_DISEASE_TOPIC = os.getenv("KAFKA_DISEASE_TOPIC", "disease.detected")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "vision-plante-group")

# MinIO Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "False").lower() == "true"
MINIO_RAW_BUCKET = os.getenv("MINIO_RAW_BUCKET", "raw-uav-images")
MINIO_RESULTS_BUCKET = os.getenv("MINIO_RESULTS_BUCKET", "disease-detection-results")

# HuggingFace Model Configuration
MODEL_NAME = os.getenv("MODEL_NAME", "Abuzaid01/plant-disease-classifier")
MODEL_DEVICE = os.getenv("MODEL_DEVICE", "cpu")  # "cuda" si GPU disponible
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))

# Processing Configuration
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
IMAGE_FOLDER_PREFIX = os.getenv("IMAGE_FOLDER_PREFIX", "mixed_images/")
SUPPORTED_FORMATS = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']

# Auto-publish Configuration
AUTO_PUBLISH_ON_STARTUP = os.getenv("AUTO_PUBLISH_ON_STARTUP", "True").lower() == "true"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
