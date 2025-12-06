# VisionPlante - Détection de Maladies Foliaires

## Description
Microservice de vision par ordinateur qui utilise un modèle d'intelligence artificielle (EfficientNet-B2) pour détecter et classifier les maladies des plantes à partir d'images de feuilles. Le service lit les images depuis MinIO, applique le modèle de détection, puis publie les résultats dans Kafka et les stocke dans MinIO.

---

## Données en Entrée

### Source 1 : Apache Kafka
- **Topic** : `image.uploaded` (configurable via `KAFKA_IMAGE_TOPIC`)
- **Groupe de consommateurs** : `vision-plante-group`
- **Format** : Événements JSON d'upload d'images
  ```json
  {
    "event_type": "image_uploaded",
    "timestamp": "ISO-8601",
    "bucket": "raw-uav-images",
    "image_path": "mixed_images/ClassName_1_image.jpg",
    "object_name": "chemin/image.jpg",
    "class_name": "nom_classe"
  }
  ```

### Source 2 : MinIO (Object Storage)
- **Bucket source** : `raw-uav-images` (configurable via `MINIO_RAW_BUCKET`)
- **Dossier** : `mixed_images/` (configurable via `IMAGE_FOLDER_PREFIX`)
- **Formats supportés** : `.jpg`, `.jpeg`, `.png`, `.bmp`, `.gif`
- **Contenu** : Images de feuilles de plantes capturées par drones UAV

### Configuration
**Kafka** :
- `KAFKA_BOOTSTRAP_SERVERS` : Adresse du broker (défaut: `localhost:9092`)
- `KAFKA_IMAGE_TOPIC` : Topic d'entrée (défaut: `image.uploaded`)
- `KAFKA_DISEASE_TOPIC` : Topic de sortie (défaut: `disease.detected`)
- `KAFKA_GROUP_ID` : Groupe de consommateurs (défaut: `vision-plante-group`)

**MinIO** :
- `MINIO_ENDPOINT` : Adresse du serveur (défaut: `localhost:9000`)
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` : Identifiants
- `MINIO_RAW_BUCKET` : Bucket source (défaut: `raw-uav-images`)
- `MINIO_RESULTS_BUCKET` : Bucket résultats (défaut: `disease-detection-results`)

**Modèle IA** :
- `MODEL_NAME` : HuggingFace model ID (défaut: `Abuzaid01/plant-disease-classifier`)
- `MODEL_DEVICE` : Device d'inférence (défaut: `cpu`, option: `cuda`)
- `CONFIDENCE_THRESHOLD` : Seuil de confiance (défaut: `0.5`)

**Mode automatique** :
- `AUTO_PUBLISH_ON_STARTUP` : Publier toutes les images au démarrage (défaut: `True`)

---

## Traitement Interne

### 1. Initialisation du Modèle
- **Architecture** : PlantDiseaseClassifier avec backbone EfficientNet-B2
- **Composants** :
  - Backbone EfficientNet pré-entraîné
  - Mécanisme d'attention (améliore la détection)
  - Classificateur personnalisé avec dropout et batch normalization
- **Chargement** : Téléchargement automatique depuis HuggingFace Hub
- **Device** : GPU (CUDA) si disponible, sinon CPU

### 2. Prétraitement des Images
Transformations appliquées avant inférence :
- **Redimensionnement** : 256×256 pixels
- **Crop central** : 224×224 pixels
- **Conversion** : Tenseur PyTorch
- **Normalisation** : Moyenne [0.485, 0.456, 0.406], Écart-type [0.229, 0.224, 0.225]
- **Conversion RGB** : Si l'image n'est pas en RGB

### 3. Détection de Maladies
- **Inférence** : Forward pass avec `torch.no_grad()` (pas de calcul de gradients)
- **Sortie** : Logits convertis en probabilités via softmax
- **Top-5** : Extraction des 5 prédictions les plus probables
- **Classification** : Détermine si la plante est malade ou saine

### 4. Mode Round-Robin (Publication Automatique)
Si `AUTO_PUBLISH_ON_STARTUP=True` :
- Scan de toutes les images dans `mixed_images/`
- Groupement par classe (extrait du nom de fichier)
- Création d'une file en rotation (1 image/classe à tour de rôle)
- Publication séquentielle des événements dans Kafka
- Assure une distribution équilibrée entre les classes

---

## Données en Sortie

### Destination 1 : Apache Kafka
- **Topic** : `disease.detected` (configurable)
- **Format** : Résultats de détection au format JSON

#### Structure des Messages Kafka
```json
{
  "image_path": "mixed_images/Apple___Apple_scab_1.jpg",
  "image_size": [width, height],
  "detection_results": {
    "predicted_class": "Apple___Apple_scab",
    "confidence": 0.9523,
    "top_5_predictions": [
      {"class": "Apple___Apple_scab", "confidence": 0.9523},
      {"class": "Apple___Black_rot", "confidence": 0.0312},
      ...
    ],
    "is_diseased": true
  },
  "inference_time_ms": 245.67,
  "model_name": "Abuzaid01/plant-disease-classifier",
  "timestamp": "ISO-8601",
  "device": "cuda:0"
}
```

#### Champs Clés
- `predicted_class` : Classe prédite (plante + maladie)
- `confidence` : Score de confiance [0-1]
- `top_5_predictions` : Top 5 prédictions alternatives
- `is_diseased` : `true` si maladie détectée (seuil ≥ 0.5 et pas "healthy")
- `inference_time_ms` : Temps de calcul en millisecondes

### Destination 2 : MinIO
- **Bucket** : `disease-detection-results`
- **Structure** : `results/{class_name}/{filename}.json`
- **Format** : JSON identique aux messages Kafka
- **Usage** : Stockage persistant et analyse batch

---

## Flux de Traitement

### Séquence Standard
1. **Écoute Kafka** : Attente d'événements sur topic `image.uploaded`
2. **Réception événement** : Parse du message JSON avec chemin image
3. **Téléchargement** : Récupération de l'image depuis MinIO
4. **Validation** : Vérification format et conversion RGB si nécessaire
5. **Prétraitement** : Application des transformations (resize, crop, normalize)
6. **Inférence** : Passage dans le modèle deep learning
7. **Post-traitement** : Softmax, extraction top-5, classification maladie/sain
8. **Double publication** :
   - Message Kafka vers topic `disease.detected`
   - JSON dans MinIO bucket `disease-detection-results`

### Mode Auto-Publish (Démarrage)
Si `AUTO_PUBLISH_ON_STARTUP=True` :
1. Scan complet du bucket `raw-uav-images/mixed_images/`
2. Groupement par classe (extraction du nom de fichier)
3. Création file round-robin (rotation équitable)
4. Publication séquentielle de tous les événements
5. Traitement automatique via la boucle standard

---

## Architecture du Modèle

### PlantDiseaseClassifier
- **Backbone** : EfficientNet-B2 (features extraction)
- **Attention** : Mécanisme d'attention spatiale
  - AdaptiveAvgPool2d → Linear (compression) → ReLU → Linear → Sigmoid
  - Pondère les features importantes
- **Classificateur** : 3 couches fully-connected
  - Features → 512 → 256 → num_classes
  - Dropout (30%, 15%, 9%) pour régularisation
  - Batch Normalization pour stabilité

### Caractéristiques
- **Entrée** : Images RGB 224×224
- **Sortie** : Probabilités pour ~38 classes de maladies
- **Source** : HuggingFace (`Abuzaid01/plant-disease-classifier`)
- **Performance** : Accuracy validation incluse dans le checkpoint

---

## Script d'Analyse (analyze_results.py)

Script utilitaire pour analyser les résultats de détection :

### Fonctionnalités
- Lecture de tous les JSON dans `disease-detection-results/results/`
- Calcul de statistiques globales :
  - Total images analysées
  - Taux de détection maladies vs saines
  - Confiance moyenne/min/max
  - Temps d'inférence moyen
- **Précision par classe** : Top 10 et Bottom 5
- **Précision globale** : Taux de prédictions correctes
- **Classes les plus prédites** : Distribution des prédictions

### Usage
Permet d'évaluer les performances du modèle sur un dataset complet et identifier les classes problématiques.

---

## Monitoring et Statistiques

### Métriques en Temps Réel
- **Images traitées** : Compteur total
- **Maladies détectées** : Nombre de plantes malades identifiées
- **Erreurs** : Compteur d'échecs
- **Temps d'inférence** : Par image (en millisecondes)

### Logs Détaillés
Pour chaque image :
- Chemin et dimensions
- Classe prédite avec confiance
- Statut malade/sain
- Temps d'inférence
- Confirmation publication Kafka (topic, partition, offset)
- Sauvegarde MinIO

### Publication Automatique
- Progression en temps réel (tous les 100 images)
- Taux de traitement (images/seconde)
- Distribution équilibrée par rotation

---

## Arrêt Gracieux

- Fermeture propre du Consumer Kafka
- Flush et fermeture du Producer Kafka
- Affichage statistiques finales :
  - Total images traitées
  - Total maladies détectées
  - Total erreurs

---

## Dépendances

- `torch` / `torchvision` : Framework deep learning et transformations
- `transformers` / `huggingface_hub` : Chargement modèle depuis HuggingFace
- `Pillow` : Manipulation d'images
- `numpy` : Calculs numériques
- `kafka-python` : Client Kafka Consumer/Producer
- `minio` : Client object storage MinIO
