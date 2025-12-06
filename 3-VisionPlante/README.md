# 🌿 MS3 - VisionPlante

## Description

Microservice de détection de maladies foliaires utilisant le modèle **Abuzaid01/plant-disease-classifier** depuis HuggingFace.

### Fonctionnalités

- 🖼️ **Lecture d'images depuis MinIO** : Traite les images depuis `raw-uav-images/color/`
- 🤖 **Détection de maladies** : Architecture PlantDiseaseClassifier (EfficientNet-B2 + Attention + Classifier)
- 📊 **Classification multi-classes** : Détecte 14 classes de maladies foliaires avec 99.23% accuracy
- 📤 **Publication Kafka** : Publie les résultats dans le topic `disease.detected`
- 💾 **Sauvegarde des résultats** : JSON dans MinIO (`disease-detection-results`)
- 🔄 **Auto-publish**: Publication automatique de toutes les images au démarrage (round-robin)

## Architecture

```
┌─────────────────┐
│  Kafka Topic    │
│ image.uploaded  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│     VisionPlante Service            │
│                                     │
│  1. Écoute événements Kafka        │
│  2. Télécharge image depuis MinIO  │
│  3. Détection avec EfficientNet-B2 │
│  4. Publie résultats Kafka         │
│  5. Sauvegarde JSON dans MinIO     │
└─────────┬───────────────────────────┘
          │
          ├──────────────┬─────────────┐
          ▼              ▼             ▼
  ┌──────────────┐  ┌─────────┐  ┌──────────┐
  │ Kafka Topic  │  │  MinIO  │  │  Logs    │
  │disease.detected│ │ Results │  │          │
  └──────────────┘  └─────────┘  └──────────┘
```

## Modèle IA

**Nom**: `Abuzaid01/plant-disease-classifier`

### Architecture

Le modèle utilise une architecture personnalisée `PlantDiseaseClassifier` composée de:

1. **Backbone**: EfficientNet-B2 pré-entraîné
   - Extraction de features à partir des images
   - 506 couches de poids

2. **Attention Mechanism**
   - Mécanisme d'attention adaptatif
   - Pondération des features importantes
   - 4 couches de poids

3. **Custom Classifier**
   - Couches fully-connected avec BatchNorm et Dropout
   - 512 → 256 → 14 classes
   - 16 couches de poids

**Total**: 526 couches de poids chargées depuis HuggingFace

### Performance

- **Accuracy validation**: 99.23%
- **Epochs d'entraînement**: 30
- **Optimiseur**: AdamW
- **Scheduler**: CosineAnnealingWarmRestarts

### Classes détectées

14 classes de maladies foliaires:
- **Apple**: Apple_scab, Black_rot, Cedar_apple_rust, healthy
- **Corn**: Cercospora_leaf_spot, Common_rust, Northern_Leaf_Blight, healthy  
- **Tomato**: Bacterial_spot, Early_blight, Late_blight, Leaf_Mold, Septoria_leaf_spot, Target_Spot, healthy

### Prétraitement des images

- **Resize**: 256×256
- **Center Crop**: 224×224
- **Normalisation**: ImageNet (mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
- **Format**: RGB uniquement

## Configuration

### Variables d'environnement

```bash
# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka-broker:9092
KAFKA_IMAGE_TOPIC=image.uploaded
KAFKA_DISEASE_TOPIC=disease.detected
KAFKA_GROUP_ID=vision-plante-group

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=False
MINIO_RAW_BUCKET=raw-uav-images
MINIO_RESULTS_BUCKET=disease-detection-results

# Modèle
MODEL_NAME=Abuzaid01/plant-disease-classifier
MODEL_DEVICE=cpu  # ou "cuda" si GPU disponible
CONFIDENCE_THRESHOLD=0.5

# Traitement
BATCH_SIZE=1
IMAGE_FOLDER_PREFIX=color/
AUTO_PUBLISH_ON_STARTUP=True  # Publication automatique des images au démarrage
```

## Utilisation

### Démarrage local

```bash
cd 3-VisionPlante

# Installer les dépendances
pip install -r requirements.txt

# Lancer le service
python vision_plante.py
```

### Avec Docker

```bash
# Build
docker build -t agrotrace-vision-plante:latest .

# Run
docker run -it --rm \
  -e KAFKA_BOOTSTRAP_SERVERS=kafka-broker:9092 \
  -e MINIO_ENDPOINT=minio:9000 \
  agrotrace-vision-plante:latest
```

### Avec Docker Compose

```bash
# Démarrer le service (publication automatique des images activée par défaut)
docker compose up vision-plante

# Pour désactiver la publication automatique
docker compose up vision-plante -e AUTO_PUBLISH_ON_STARTUP=False
```

**Note**: Le service publie automatiquement toutes les images de MinIO (`raw-uav-images/color/`) au démarrage en ordre aléatoire avec rotation entre classes.

## Format des événements

### Input (Kafka `image.uploaded`)

```json
{
  "image_path": "color/Apple___Apple_scab/image_001.jpg",
  "bucket": "raw-uav-images",
  "timestamp": "2025-12-04T15:30:45.123456",
  "size_bytes": 2457600
}
```

### Output (Kafka `disease.detected`)

```json
{
  "image_path": "color/Apple___Apple_scab/image_001.jpg",
  "image_size": [256, 256],
  "detection_results": {
    "predicted_class": "Apple___Apple_scab",
    "confidence": 0.9823,
    "top_5_predictions": [
      {"class": "Apple___Apple_scab", "confidence": 0.9823},
      {"class": "Apple___Black_rot", "confidence": 0.0124},
      {"class": "Apple___Cedar_apple_rust", "confidence": 0.0034},
      {"class": "Apple___healthy", "confidence": 0.0012},
      {"class": "Tomato___Early_blight", "confidence": 0.0005}
    ],
    "is_diseased": true
  },
  "inference_time_ms": 234.56,
  "model_name": "Abuzaid01/plant-disease-classifier",
  "timestamp": "2025-12-04T15:30:45.456789",
  "device": "cpu"
}
```

## Performance

## Dépendances

- **torch**: 2.1.2 (PyTorch CPU-optimized)
- **torchvision**: 0.16.2
- **transformers**: 4.40.0 (HuggingFace)
- **huggingface_hub**: 0.20.0 (Téléchargement modèle)
- **Pillow**: 10.1.0 (Traitement d'images)
- **kafka-python**: 2.0.2
- **minio**: 7.2.0
- **numpy**: 1.24.3

### Optimisation Docker

- **Image size**: ~1.93 GB (optimisé avec PyTorch CPU-only)
- **Index PyTorch**: `https://download.pytorch.org/whl/cpu`
- **Build time**: ~5-10 minutes (selon connexion)
## Monitoring

Le service affiche les statistiques en temps réel:

```
========================================================================
🖼️  TRAITEMENT: color/Apple___Apple_scab/image_001.jpg
========================================================================
   📐 Dimensions: 256×256
   🎯 Prédiction: Apple___Apple_scab
   📊 Confiance: 98.23%
   🩺 Malade: Oui
   ⏱️  Temps d'inférence: 0.235s
   ✅ Résultat publié dans Kafka
      Topic: disease.detected
      Partition: 0
      Offset: 1234
   💾 Résultats sauvegardés: s3://disease-detection-results/results/Apple___Apple_scab/image_001.json
   📊 Stats: 1 images, 1 maladies détectées
```

## Dépendances

- **transformers**: 4.36.0 (HuggingFace)
- **torch**: 2.1.2 (PyTorch)
- **torchvision**: 0.16.2
- **Pillow**: 10.1.0 (Traitement d'images)
- **kafka-python**: 2.0.2
- **minio**: 7.2.0

## Licence

Projet AgroTrace - MS3 VisionPlante
