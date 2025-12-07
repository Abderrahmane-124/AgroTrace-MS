# MS3 - VisionPlante (Détection de Maladies Foliaires)

## 📋 Description
Microservice de vision par ordinateur utilisant un modèle EfficientNet-B2 pour détecter et classifier les maladies des plantes à partir d'images de feuilles.

---

## 📥 ENTRÉES

### Source Primaire : MinIO (Object Storage)
- **Bucket** : `raw-uav-images`
- **Dossier** : `mixed_images/`
- **Format** : Images `.jpg`, `.jpeg`, `.png`, `.bmp`, `.gif`
- **Contenu** : Images de feuilles capturées par drones UAV

### Flux d'Entrée ("Self-Feeding Pattern")

**Mode AUTO_PUBLISH (démarrage):**
1. MS3 scanne MinIO `raw-uav-images/mixed_images/`
2. MS3 **crée et publie** des événements Kafka pour chaque image trouvée
3. MS3 **consomme** ces mêmes événements pour traiter les images

**Mode Normal (runtime):**
- MS3 consomme le topic Kafka `image.uploaded`
- Les événements peuvent venir de MS3 lui-même ou d'autres services

### Format Événement Kafka
**Topic** : `image.uploaded`
```json
{
  "event_type": "image_uploaded",
  "timestamp": "2024-01-15T10:30:00Z",
  "bucket": "raw-uav-images",
  "image_path": "mixed_images/Apple_scab_1.jpg",
  "class_name": "Apple_scab"
}
```

> **Note**: Kafka sert de **queue de travail** entre le scan et le traitement. Avantage: si MS3 crash, les événements restent dans Kafka et peuvent être reconsommés.

---

## ⚙️ TRAITEMENT

### Pipeline de Détection
```
Image MinIO → Prétraitement → Modèle IA → Post-traitement → Résultats
```

### Étapes Détaillées

1. **Chargement Image**
   - Téléchargement depuis MinIO
   - Conversion RGB si nécessaire

2. **Prétraitement**
   - Resize: 256×256 px
   - Crop central: 224×224 px
   - Normalisation: ImageNet (mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

3. **Inférence Deep Learning**
   - **Modèle** : PlantDiseaseClassifier (EfficientNet-B2 + Attention)
   - **Source** : HuggingFace (`Abuzaid01/plant-disease-classifier`)
   - **Classes** : 14 maladies végétales
   - **Device** : CPU (ou GPU si disponible)

4. **Post-traitement**
   - Softmax sur logits → probabilités
   - Extraction Top-5 prédictions
   - Classification: maladie vs sain (seuil 50%)

---

## 📤 SORTIES

### 1️⃣ Apache Kafka
- **Topic publié** : `disease.detected`
- **Format** :
  ```json
  {
    "image_path": "mixed_images/Apple_scab_1.jpg",
    "image_size": [256, 256],
    "detection_results": {
      "predicted_class": "Apple___Apple_scab",
      "confidence": 0.9523,
      "top_5_predictions": [
        {"class": "Apple___Apple_scab", "confidence": 0.9523},
        {"class": "Apple___Black_rot", "confidence": 0.0312}
      ],
      "is_diseased": true
    },
    "inference_time_ms": 45.67,
    "model_name": "Abuzaid01/plant-disease-classifier",
    "timestamp": "2024-01-15T10:30:05Z",
    "device": "cpu"
  }
  ```

### 2️⃣ MinIO (Stockage Résultats)
- **Bucket** : `disease-detection-results`
- **Chemin** : `results/{class_name}/{filename}.json`
- **Format** : JSON identique aux messages Kafka

---

## 🔧 Configuration

| Variable | Défaut | Description |
|----------|--------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Adresse Kafka |
| `KAFKA_IMAGE_TOPIC` | `image.uploaded` | Topic entrée |
| `KAFKA_DISEASE_TOPIC` | `disease.detected` | Topic sortie |
| `MINIO_ENDPOINT` | `localhost:9000` | Adresse MinIO |
| `MINIO_RAW_BUCKET` | `raw-uav-images` | Bucket images |
| `MINIO_RESULTS_BUCKET` | `disease-detection-results` | Bucket résultats |
| `MODEL_NAME` | `Abuzaid01/plant-disease-classifier` | Modèle HuggingFace |
| `MODEL_DEVICE` | `cpu` | Device inférence |
| `CONFIDENCE_THRESHOLD` | `0.5` | Seuil détection |
| `AUTO_PUBLISH_ON_STARTUP` | `True` | Mode auto-scan |

---

## 🚀 Mode Auto-Publish (Self-Feeding)

Au démarrage, si `AUTO_PUBLISH_ON_STARTUP=True`:

### Phase 1: Production (MS3 → Kafka)
1. Scan du bucket `raw-uav-images/mixed_images/`
2. Groupement images par classe
3. Création d'événements `image.uploaded` (round-robin: 1 image/classe en rotation)
4. Publication dans Kafka topic `image.uploaded`
5. Confirmation: "✅ Publication terminée: 10858/10858 images"

### Phase 2: Consommation (Kafka → MS3)
6. MS3 écoute le topic `image.uploaded`
7. Pour chaque événement: télécharge l'image → inférence → publie résultats
8. Traitement asynchrone et résilient (crash = reprise depuis Kafka)

**Avantages du pattern:**
- ✅ **Découplage**: Scan et traitement séparés via Kafka
- ✅ **Résilience**: Événements persistés, reprise possible après crash
- ✅ **Distribution équilibrée**: Round-robin assure diversité des classes traitées

---

## 📊 Métriques

- **Images traitées** : Compteur total
- **Maladies détectées** : Nombre de plantes malades
- **Temps d'inférence** : ~50ms/image (CPU), ~10ms (GPU)
- **Confiance moyenne** : Score de confiance du modèle

---

## 🛠️ Dépendances

- `torch` + `torchvision` : Deep learning
- `huggingface_hub` : Chargement modèle
- `Pillow` : Traitement images
- `kafka-python` : Client Kafka
- `minio` : Client MinIO
