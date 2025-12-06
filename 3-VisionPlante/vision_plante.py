"""
Microservice MS3 - VisionPlante
Détection des maladies foliaires avec le modèle Abuzaid01/plant-disease-classifier
- Lit les images depuis MinIO (raw-uav-images/mixed_images/)
- Utilise le modèle EfficientNet-B2 pré-entraîné
- Publie les résultats de détection dans Kafka (disease.detected)
"""

import json
import time
import io
import random
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms as transforms
from torchvision import models
from PIL import Image
import numpy as np
from huggingface_hub import hf_hub_download

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from minio import Minio
from minio.error import S3Error

import config


class PlantDiseaseClassifier(nn.Module):
    """
    Architecture du modèle de détection de maladies foliaires
    Backbone: EfficientNet-B2 + Attention + Classifier personnalisé
    """
    def __init__(self, num_classes, dropout_rate=0.3):
        super(PlantDiseaseClassifier, self).__init__()
        
        # Use EfficientNet as backbone
        self.backbone = models.efficientnet_b2(pretrained=False)
        
        # Get feature dimension
        num_features = self.backbone.classifier[1].in_features
        
        # Replace classifier with custom head
        self.backbone.classifier = nn.Identity()
        
        # Attention mechanism
        self.attention = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(num_features, num_features // 4),
            nn.ReLU(),
            nn.Linear(num_features // 4, num_features),
            nn.Sigmoid()
        )
        
        # Custom classifier head
        self.classifier = nn.Sequential(
            nn.Dropout(dropout_rate),
            nn.Linear(num_features, 512),
            nn.BatchNorm1d(512),
            nn.ReLU(),
            nn.Dropout(dropout_rate * 0.5),
            nn.Linear(512, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(dropout_rate * 0.3),
            nn.Linear(256, num_classes)
        )
    
    def forward(self, x):
        features = self.backbone.features(x)
        pooled = F.adaptive_avg_pool2d(features, 1)
        pooled = torch.flatten(pooled, 1)
        attention_weights = self.attention(features)
        attended_features = pooled * attention_weights
        output = self.classifier(attended_features)
        return output


class VisionPlanteService:
    """
    Service de détection de maladies foliaires
    - Charge le modèle Abuzaid01/plant-disease-classifier depuis HuggingFace
    - Lit les images depuis MinIO
    - Détecte les maladies
    - Publie les résultats dans Kafka
    """
    
    def __init__(self):
        self.kafka_bootstrap_servers = config.KAFKA_BOOTSTRAP_SERVERS
        self.kafka_image_topic = config.KAFKA_IMAGE_TOPIC
        self.kafka_disease_topic = config.KAFKA_DISEASE_TOPIC
        self.kafka_group_id = config.KAFKA_GROUP_ID
        
        self.consumer = None
        self.producer = None
        self.minio_client = None
        
        # Modèle IA
        self.model = None
        self.transform = None
        self.device = None
        self.class_names = None
        
        # Statistiques
        self.images_processed = 0
        self.diseases_detected = 0
        self.error_count = 0
        
        print(f"🌿 VisionPlante Service - Initialisation")
        print(f"   📦 Modèle: {config.MODEL_NAME}")
        print(f"   💾 Device: {config.MODEL_DEVICE}")
        print(f"   📊 Seuil de confiance: {config.CONFIDENCE_THRESHOLD}")
    
    def init_minio(self):
        """Initialiser le client MinIO"""
        print(f"\n🔌 Connexion à MinIO: {config.MINIO_ENDPOINT}")
        
        try:
            self.minio_client = Minio(
                config.MINIO_ENDPOINT,
                access_key=config.MINIO_ACCESS_KEY,
                secret_key=config.MINIO_SECRET_KEY,
                secure=config.MINIO_SECURE
            )
            
            # Vérifier que le bucket source existe
            if not self.minio_client.bucket_exists(config.MINIO_RAW_BUCKET):
                print(f"⚠️  Bucket {config.MINIO_RAW_BUCKET} n'existe pas, création...")
                self.minio_client.make_bucket(config.MINIO_RAW_BUCKET)
            
            # Créer le bucket de résultats s'il n'existe pas
            if not self.minio_client.bucket_exists(config.MINIO_RESULTS_BUCKET):
                self.minio_client.make_bucket(config.MINIO_RESULTS_BUCKET)
                print(f"✅ Bucket créé: {config.MINIO_RESULTS_BUCKET}")
            
            print(f"✅ Connecté à MinIO")
            
        except Exception as e:
            print(f"❌ Erreur connexion MinIO: {e}")
            raise
    
    def init_kafka(self):
        """Initialiser les connexions Kafka"""
        print(f"\n🔌 Connexion à Kafka: {self.kafka_bootstrap_servers}")
        
        try:
            # Consumer pour écouter les événements d'upload d'images
            self.consumer = KafkaConsumer(
                self.kafka_image_topic,
                bootstrap_servers=self.kafka_bootstrap_servers,
                group_id=self.kafka_group_id,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='earliest',
                enable_auto_commit=True
            )
            
            # Producer pour publier les résultats de détection
            self.producer = KafkaProducer(
                bootstrap_servers=self.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                retries=3
            )
            
            print(f"✅ Connecté à Kafka")
            print(f"   📥 Consumer topic: {self.kafka_image_topic}")
            print(f"   📤 Producer topic: {self.kafka_disease_topic}")
            
        except Exception as e:
            print(f"❌ Erreur connexion Kafka: {e}")
            raise
    
    def load_model(self):
        """Charger le modèle depuis HuggingFace"""
        print(f"\n🤖 Chargement du modèle: {config.MODEL_NAME}")
        
        try:
            # Déterminer le device (GPU ou CPU)
            if config.MODEL_DEVICE == "cuda" and torch.cuda.is_available():
                self.device = torch.device("cuda")
                print(f"   🚀 GPU détecté: {torch.cuda.get_device_name(0)}")
            else:
                self.device = torch.device("cpu")
                print(f"   💻 Utilisation du CPU")
            
            # Définir les transformations d'image (selon la doc du modèle)
            print(f"   🖼️  Configuration des transformations d'images...")
            self.transform = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
            
            # Télécharger les fichiers du modèle depuis HuggingFace
            print(f"   📥 Téléchargement des fichiers depuis HuggingFace...")
            model_path = hf_hub_download(repo_id=config.MODEL_NAME, filename="model.pth")
            config_path = hf_hub_download(repo_id=config.MODEL_NAME, filename="config.json")
            
            # Charger la configuration
            print(f"   📄 Lecture de la configuration...")
            with open(config_path, 'r') as f:
                model_config = json.load(f)
            
            self.class_names = model_config['class_names']
            num_classes = model_config['num_classes']
            
            # Charger le checkpoint
            print(f"   ⚙️  Chargement du checkpoint...")
            checkpoint = torch.load(model_path, map_location=self.device)
            
            # Créer le modèle avec l'architecture correcte
            print(f"   🔧 Création du modèle PlantDiseaseClassifier...")
            self.model = PlantDiseaseClassifier(num_classes=num_classes, dropout_rate=0.3)
            
            # Charger les poids pré-entraînés
            state_dict = checkpoint.get('model_state_dict', checkpoint)
            result = self.model.load_state_dict(state_dict, strict=False)
            
            # Déplacer vers le device et mode évaluation
            self.model.to(self.device)
            self.model.eval()
            
            print(f"✅ Modèle chargé avec succès")
            print(f"   📊 Nombre de classes: {num_classes}")
            print(f"   📦 Poids chargés: {len(state_dict)}")
            
            if result.missing_keys:
                print(f"   ⚠️  Clés manquantes: {len(result.missing_keys)}")
            if result.unexpected_keys:
                print(f"   ⚠️  Clés inattendues: {len(result.unexpected_keys)}")
            
            # Afficher les performances d'entraînement si disponibles
            if 'training_info' in checkpoint:
                training_info = checkpoint['training_info']
                if 'best_val_acc' in training_info:
                    print(f"   🎯 Accuracy validation: {training_info['best_val_acc']:.2f}%")
            
        except Exception as e:
            print(f"❌ Erreur chargement du modèle: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def download_image_from_minio(self, object_name: str) -> Optional[Image.Image]:
        """
        Télécharger une image depuis MinIO
        
        Args:
            object_name: Chemin de l'objet dans MinIO (ex: "color/Apple___Apple_scab/image1.jpg")
            
        Returns:
            Image PIL ou None si erreur
        """
        try:
            response = self.minio_client.get_object(config.MINIO_RAW_BUCKET, object_name)
            image_data = response.read()
            response.close()
            response.release_conn()
            
            # Ouvrir avec PIL
            image = Image.open(io.BytesIO(image_data))
            
            # Convertir en RGB si nécessaire
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            return image
            
        except S3Error as e:
            print(f"❌ Erreur téléchargement MinIO {object_name}: {e}")
            return None
        except Exception as e:
            print(f"❌ Erreur ouverture image {object_name}: {e}")
            return None
    
    def detect_disease(self, image: Image.Image) -> Dict[str, Any]:
        """
        Détecter les maladies sur une image
        
        Args:
            image: Image PIL
            
        Returns:
            Dictionnaire avec les prédictions (label, confidence, top_k)
        """
        try:
            # Prétraitement de l'image (convertir en RGB si nécessaire)
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Appliquer les transformations
            inputs = self.transform(image).unsqueeze(0).to(self.device)
            
            # Inférence (sans calcul de gradients)
            with torch.no_grad():
                outputs = self.model(inputs)
            
            # Obtenir les probabilités (softmax)
            probabilities = F.softmax(outputs, dim=-1)
            
            # Top-5 prédictions
            top5_prob, top5_idx = torch.topk(probabilities, k=5, dim=-1)
            
            # Prédiction principale
            predicted_idx = top5_idx[0][0].item()
            predicted_prob = top5_prob[0][0].item()
            predicted_label = self.class_names[predicted_idx]
            
            # Construire les résultats
            results = {
                "predicted_class": predicted_label,
                "confidence": round(predicted_prob, 4),
                "top_5_predictions": [
                    {
                        "class": self.class_names[top5_idx[0][i].item()],
                        "confidence": round(top5_prob[0][i].item(), 4)
                    }
                    for i in range(5)
                ],
                "is_diseased": predicted_prob >= config.CONFIDENCE_THRESHOLD and "healthy" not in predicted_label.lower()
            }
            
            return results
            
        except Exception as e:
            print(f"❌ Erreur détection: {e}")
            return {
                "error": str(e),
                "predicted_class": "unknown",
                "confidence": 0.0,
                "is_diseased": False
            }
    
    def _get_all_images_by_folder(self, bucket: str = None, prefix: str = None) -> Dict[str, List[str]]:
        """
        Récupère toutes les images groupées par classe (extraite du nom de fichier)
        
        Args:
            bucket: Bucket MinIO (par défaut: MINIO_RAW_BUCKET)
            prefix: Préfixe de dossier (par défaut: IMAGE_FOLDER_PREFIX)
        
        Returns:
            Dict[classe] = [liste d'images]
        """
        bucket = bucket or config.MINIO_RAW_BUCKET
        prefix = prefix or config.IMAGE_FOLDER_PREFIX
        
        images_by_folder = {}
        
        # Lister tous les objets
        objects = self.minio_client.list_objects(bucket, prefix=prefix, recursive=True)
        
        for obj in objects:
            # Filtrer les images
            if obj.object_name.lower().endswith(tuple(config.SUPPORTED_FORMATS)):
                # Extraire le nom de classe depuis le nom de fichier
                # Ex: mixed_images/Apple___Apple_scab_1_image.jpg -> Apple___Apple_scab
                filename = Path(obj.object_name).stem
                
                # Le nom de classe est avant le premier chiffre suivi d'underscore
                # Format: ClassName_1_originalname.jpg
                parts = filename.split('_')
                
                # Trouver l'index du premier nombre pour extraire la classe
                class_name = None
                for i, part in enumerate(parts):
                    if part.isdigit():
                        # La classe est tout ce qui précède ce nombre
                        class_name = '_'.join(parts[:i])
                        break
                
                # Si pas de nombre trouvé, utiliser le nom complet
                if not class_name:
                    class_name = filename
                
                if class_name not in images_by_folder:
                    images_by_folder[class_name] = []
                
                images_by_folder[class_name].append(obj.object_name)
        
        # Mélanger les images dans chaque dossier
        for class_name in images_by_folder:
            random.shuffle(images_by_folder[class_name])
        
        return images_by_folder
    
    def _create_round_robin_queue(self, images_by_folder: Dict[str, List[str]]) -> List[str]:
        """
        Crée une file d'images en rotation (round-robin)
        Prend 1 image de chaque classe à la fois pour diversifier les résultats
        
        Args:
            images_by_folder: Dict[classe] = [liste d'images]
        
        Returns:
            Liste ordonnée d'images en rotation
        """
        # Liste des classes
        classes = list(images_by_folder.keys())
        random.shuffle(classes)  # Mélanger l'ordre des classes
        
        queue = []
        max_images = max(len(imgs) for imgs in images_by_folder.values())
        
        # Round-robin : prendre 1 image de chaque classe à tour de rôle
        for round_idx in range(max_images):
            for class_name in classes:
                images = images_by_folder[class_name]
                
                if round_idx < len(images):
                    queue.append(images[round_idx])
        
        return queue
    
    def publish_all_images(self, bucket: str = None):
        """
        Publie toutes les images dans Kafka en ordre aléatoire avec rotation
        Appelé automatiquement au démarrage si AUTO_PUBLISH_ON_STARTUP=True
        
        Args:
            bucket: Bucket MinIO (par défaut: MINIO_RAW_BUCKET)
        """
        bucket = bucket or config.MINIO_RAW_BUCKET
        
        print(f"\n{'='*70}")
        print(f"📤 PUBLICATION AUTOMATIQUE DES IMAGES")
        print(f"{'='*70}")
        
        # 1. Récupérer toutes les images groupées par classe
        print(f"🔍 Scan des images dans s3://{bucket}/{config.IMAGE_FOLDER_PREFIX}")
        images_by_folder = self._get_all_images_by_folder(bucket)
        
        if not images_by_folder:
            print(f"⚠️  Aucune image trouvée")
            return
        
        # Statistiques
        total_images = sum(len(imgs) for imgs in images_by_folder.values())
        
        print(f"📊 {len(images_by_folder)} classes • {total_images} images")
        
        # 2. Créer la file en rotation (round-robin)
        image_queue = self._create_round_robin_queue(images_by_folder)
        
        print(f"🔀 File en rotation créée (1 image/classe)")
        
        # 3. Publier les événements
        published = 0
        start_time = time.time()
        
        for idx, image_path in enumerate(image_queue, 1):
            try:
                # Extraire infos
                image_name = Path(image_path).name
                filename = Path(image_path).stem
                
                # Extraire la classe depuis le nom de fichier
                # Format: ClassName_1_originalname.jpg
                parts = filename.split('_')
                class_name = "unknown"
                for i, part in enumerate(parts):
                    if part.isdigit():
                        class_name = '_'.join(parts[:i])
                        break
                
                # Créer l'événement
                event = {
                    "event_type": "image_uploaded",
                    "timestamp": datetime.now().isoformat(),
                    "bucket": bucket,
                    "image_path": image_path,
                    "object_name": image_path,
                    "class_name": class_name,
                    "image_name": image_name,
                    "progress": f"{idx}/{total_images}"
                }
                
                # Publier dans Kafka
                future = self.producer.send(config.KAFKA_IMAGE_TOPIC, value=event)
                future.get(timeout=5)
                
                published += 1
                
                # Afficher progression tous les 100 ou dernier
                if idx % 100 == 0 or idx == total_images:
                    elapsed = time.time() - start_time
                    rate = published / elapsed if elapsed > 0 else 0
                    
                    print(f"⏳ [{idx}/{total_images}] {rate:.1f} img/s | "
                          f"Dernier: {class_name}/{image_name}")
                
            except Exception as e:
                print(f"❌ Erreur {image_path}: {e}")
        
        # Flush final
        self.producer.flush()
        
        elapsed = time.time() - start_time
        
        print(f"✅ Publication terminée : {published}/{total_images} images en {elapsed:.1f}s ({published/elapsed:.1f} img/s)")
        print(f"{'='*70}\n")
    
    def process_image_event(self, event: Dict[str, Any]):
        """
        Traiter un événement Kafka d'upload d'image
        
        Args:
            event: Événement Kafka contenant les infos de l'image
        """
        try:
            image_path = event.get("image_path") or event.get("object_name")
            
            if not image_path:
                print(f"⚠️  Événement sans chemin d'image: {event}")
                return
            
            print(f"\n{'='*70}")
            print(f"🖼️  TRAITEMENT: {image_path}")
            print(f"{'='*70}")
            
            # Télécharger l'image depuis MinIO
            image = self.download_image_from_minio(image_path)
            
            if image is None:
                self.error_count += 1
                print(f"❌ Impossible de charger l'image")
                return
            
            print(f"   📐 Dimensions: {image.size[0]}×{image.size[1]}")
            
            # Détection de maladie
            start_time = time.time()
            results = self.detect_disease(image)
            inference_time = time.time() - start_time
            
            # Afficher les résultats
            print(f"   🎯 Prédiction: {results['predicted_class']}")
            print(f"   📊 Confiance: {results['confidence']*100:.2f}%")
            print(f"   🩺 Malade: {'Oui' if results['is_diseased'] else 'Non'}")
            print(f"   ⏱️  Temps d'inférence: {inference_time:.3f}s")
            
            # Construire le message de résultat
            result_message = {
                "image_path": image_path,
                "image_size": list(image.size),
                "detection_results": results,
                "inference_time_ms": round(inference_time * 1000, 2),
                "model_name": config.MODEL_NAME,
                "timestamp": datetime.now().isoformat(),
                "device": str(self.device)
            }
            
            # Publier dans Kafka
            future = self.producer.send(
                self.kafka_disease_topic,
                value=result_message
            )
            
            # Attendre la confirmation
            record_metadata = future.get(timeout=10)
            
            print(f"   ✅ Résultat publié dans Kafka")
            print(f"      Topic: {record_metadata.topic}")
            print(f"      Partition: {record_metadata.partition}")
            print(f"      Offset: {record_metadata.offset}")
            
            # Sauvegarder les résultats dans MinIO (optionnel)
            self.save_results_to_minio(image_path, result_message)
            
            # Mettre à jour les statistiques
            self.images_processed += 1
            if results['is_diseased']:
                self.diseases_detected += 1
            
            print(f"   📊 Stats: {self.images_processed} images, {self.diseases_detected} maladies détectées")
            
        except Exception as e:
            self.error_count += 1
            print(f"❌ Erreur traitement événement: {e}")
            import traceback
            traceback.print_exc()
    
    def save_results_to_minio(self, image_path: str, results: Dict[str, Any]):
        """
        Sauvegarder les résultats de détection dans MinIO
        
        Args:
            image_path: Chemin de l'image source
            results: Résultats de détection
        """
        try:
            # Construire le chemin de sortie
            # Ex: mixed_images/Apple___Apple_scab_1_image.jpg -> results/Apple___Apple_scab/image.json
            filename = Path(image_path).stem
            
            # Extraire la classe depuis le nom de fichier
            parts = filename.split('_')
            class_name = "unknown"
            for i, part in enumerate(parts):
                if part.isdigit():
                    class_name = '_'.join(parts[:i])
                    break
            
            if not class_name or class_name == "unknown":
                class_name = "mixed"
            
            output_path = f"results/{class_name}/{filename}.json"
            
            # Convertir en JSON
            results_json = json.dumps(results, indent=2).encode('utf-8')
            
            # Upload vers MinIO
            self.minio_client.put_object(
                config.MINIO_RESULTS_BUCKET,
                output_path,
                io.BytesIO(results_json),
                length=len(results_json),
                content_type="application/json"
            )
            
            print(f"   💾 Résultats sauvegardés: s3://{config.MINIO_RESULTS_BUCKET}/{output_path}")
            
        except Exception as e:
            print(f"⚠️  Erreur sauvegarde résultats MinIO: {e}")
    
    def run(self):
        """Boucle principale du service"""
        print(f"\n{'='*70}")
        print(f"🌿 VISIONPLANTE SERVICE - DÉMARRAGE")
        print(f"{'='*70}")
        
        # Initialisation
        self.init_minio()
        self.init_kafka()
        self.load_model()
        
        print(f"\n✅ Service initialisé avec succès")
        
        # Publication automatique des images si activée
        if config.AUTO_PUBLISH_ON_STARTUP:
            self.publish_all_images()
        else:
            print(f"⚠️  Publication automatique désactivée (AUTO_PUBLISH_ON_STARTUP=False)")
        
        print(f"👂 Écoute des événements sur topic: {self.kafka_image_topic}")
        print(f"{'='*70}\n")
        
        # Boucle de consommation Kafka
        try:
            for message in self.consumer:
                event = message.value
                self.process_image_event(event)
                
        except KeyboardInterrupt:
            print(f"\n\n⚠️  Arrêt demandé par l'utilisateur")
        except Exception as e:
            print(f"\n❌ Erreur fatale: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Fermer les connexions proprement"""
        print(f"\n{'='*70}")
        print(f"🛑 ARRÊT DU SERVICE")
        print(f"{'='*70}")
        print(f"📊 Statistiques finales:")
        print(f"   • Images traitées: {self.images_processed}")
        print(f"   • Maladies détectées: {self.diseases_detected}")
        print(f"   • Erreurs: {self.error_count}")
        
        if self.consumer:
            self.consumer.close()
            print(f"✅ Consumer Kafka fermé")
        
        if self.producer:
            self.producer.flush()
            self.producer.close()
            print(f"✅ Producer Kafka fermé")
        
        print(f"{'='*70}\n")


def main():
    """Point d'entrée du service"""
    service = VisionPlanteService()
    service.run()


if __name__ == "__main__":
    main()
