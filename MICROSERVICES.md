# 🔧 Microservices - AgroTrace

Documentation détaillée de tous les microservices du projet AgroTrace.

---

## 📋 Table des matières

1. [MS0 : Simulateur de Capteurs](#ms0--simulateur-de-capteurs)
2. [MS1 : Ingestion Capteurs](#ms1--ingestion-capteurs)
3. [MS2 : Prétraitement](#ms2--prétraitement)
4. [MS3 : VisionPlante](#ms3--visionplante)

---
3. [MS2 : Prétraitement](#ms2--prétraitement)

---

## MS0 : Simulateur de Capteurs

**Rôle** : Générer des données capteurs réalistes pour le développement et les tests

```
📁 0-Simulateur-Capteurs/
├── simulator.py         # Code principal
├── config.py           # Configuration Kafka
├── Dataset/            # Données CSV sources
│   └── iot_telemetry_data_1000.csv
├── requirements.txt
└── Dockerfile

⚙️  Configuration:
- Intervalle d'envoi: 2 secondes
- Topic Kafka: "sensor-data"
- Format: JSON

📤 Sortie:
{
  "sensor_type": "Environment Temperature",
  "timestamp": "2025-12-02T10:30:00Z",
  "data_index": 42,
  "measurements": {
    "Temperature (°C)": 25.3,
    "Environment Humidity (%)": 65.2
  },
  "created_at": "2025-12-02T10:30:00Z"
}
```

---

## MS1 : Ingestion Capteurs

**Rôle** : Collecter et stocker les données brutes des capteurs IoT

```
📁 1-IngestionCapteurs/
├── ingestion.py        # Code principal
├── config.py          # Configuration
├── init_db.sql        # Schéma base de données
├── requirements.txt
└── Dockerfile

📥 Entrée: 
- Source: Kafka Topic "sensor-data"
- Format: JSON (messages du simulateur)

⚙️  Traitement:
1. Validation du format JSON
2. Vérification de la cohérence
3. Horodatage d'insertion

💾 Sortie: 
- TimescaleDB → Table "sensor_data"
- Stockage permanent des données brutes
- Pas de publication Kafka (stockage uniquement)

🔍 Métriques:
- Messages reçus
- Messages stockés
- Erreurs de validation
- Taux de succès
```

---

## MS2 : Prétraitement

**Rôle** : Nettoyer, normaliser et enrichir les données capteurs + Traiter les images UAV

```
📁 2-Pretraitement/
├── preprocessing.py    # Code principal (sensors + images)
├── image_processor.py  # Module traitement images UAV
├── config.py          # Configuration
├── requirements.txt
└── Dockerfile

═══════════════════════════════════════════════════════════════
                    PARTIE 1: DONNÉES CAPTEURS
═══════════════════════════════════════════════════════════════

📥 Entrée:
- Source: Kafka Topic "sensor-data" (même que MS1)
- Format: JSON (données brutes)

⚙️  Pipeline de traitement:

   1️⃣  VALIDATION
       ├─ Vérification structure
       └─ Extraction valeur principale

   2️⃣  DÉTECTION ANOMALIES
       ├─ Plages de valeurs (min/max)
       ├─ Z-score (écart-type)
       └─ Seuil: Z > 3.0 = anomalie

   3️⃣  NETTOYAGE
       ├─ Remplacement anomalies
       └─ Interpolation (moyenne mobile)

   4️⃣  NORMALISATION
       ├─ Min-Max scaling [0-1]
       └─ Formule: (val-min)/(max-min)

   5️⃣  FEATURES
       ├─ Moyenne mobile (5 valeurs)
       └─ Tendances

   6️⃣  QUALITÉ
       ├─ Score [0-1]
       └─ Pénalités (anomalies, données manquantes)

📤 Sortie DOUBLE:
   A) TimescaleDB → "sensor_data_processed"
      └─ Stockage permanent pour analytics
   
   B) Kafka → "sensor-data-processed"
      └─ Notification temps réel pour futurs MS

🎯 Plages de normalisation:
- Temperature: -10°C à 50°C
- Humidity: 0% à 100%
- Soil Moisture: 0% à 100%
- Soil pH: 0 à 14
- Light Intensity: 0 à 100000 lux

═══════════════════════════════════════════════════════════════
                    PARTIE 2: IMAGES UAV
═══════════════════════════════════════════════════════════════

## MS3 : VisionPlante

**Rôle** : Détection de maladies foliaires avec IA

```
📁 3-VisionPlante/
├── vision_plante.py    # Service principal
├── config.py          # Configuration
├── requirements.txt
├── Dockerfile
└── README.md

⚙️  Configuration:
- Topic Kafka input: "image.uploaded"
- Topic Kafka output: "disease.detected"
- MinIO bucket: "raw-uav-images"
- Modèle: Abuzaid01/plant-disease-classifier (EfficientNet-B2)
- Seuil de confiance: 0.5

🤖 Modèle IA:
- Architecture: EfficientNet-B2
- Source: HuggingFace
- Dataset: PlantVillage (38 classes)
- Input: Images RGB (any size)
- Output: Classification multi-classes

🎯 Classes détectées (38):
- Apple: Apple_scab, Black_rot, Cedar_apple_rust, healthy
- Corn: Cercospora_leaf_spot, Common_rust, Northern_Leaf_Blight, healthy
- Tomato: 10 maladies + healthy
- Et autres cultures...

📥 Input (Kafka "image.uploaded"):
{
  "image_path": "color/Apple___Apple_scab/image_001.jpg",
  "bucket": "raw-uav-images",
  "timestamp": "2025-12-04T15:30:45.123456",
  "size_bytes": 2457600
}

📤 Output (Kafka "disease.detected"):
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

💾 Sauvegarde MinIO:
- Bucket: disease-detection-results
- Format: JSON par image
- Path: results/{class_name}/{image_name}.json

⚡ Performance:
- CPU: ~200-500ms par image (2-5 images/s)
- GPU: ~50-100ms par image (10-20 images/s)

📚 Librairies:
- transformers: 4.36.0 (HuggingFace)
- torch: 2.1.2 (PyTorch)
- torchvision: 0.16.2
- Pillow: 10.1.0
- kafka-python: 2.0.2
- minio: 7.2.0
```
