# 🚀 Guide d'utilisation - Analyse d'images MS3

## 📋 Vue d'ensemble

Ce guide explique comment MS3 VisionPlante analyse automatiquement toutes vos images en ordre **aléatoire avec rotation** entre classes dès son démarrage.

## 🎯 Pourquoi l'ordre aléatoire avec rotation ?

### ❌ **Problème avec l'ordre alphabétique :**
```
Résultats dans Kafka:
1-504.   Apple___Apple_scab     (tous d'affilée)
505-1001. Apple___Black_rot      (tous d'affilée)
1002-...  Apple___Cedar_rust     (tous d'affilée)
...
```
→ Résultats monotones, pas représentatifs

### ✅ **Solution avec rotation aléatoire :**
```
Résultats dans Kafka:
1. Apple___Apple_scab/img_042.jpg
2. Tomato___healthy/img_103.jpg
3. Corn___Common_rust/img_078.jpg
4. Apple___Black_rot/img_015.jpg
5. Pepper___Bacterial_spot/img_091.jpg
6. Apple___Apple_scab/img_127.jpg
7. Tomato___Early_blight/img_054.jpg
...
```
→ Résultats diversifiés, meilleure représentation du dataset

## 🔧 Prérequis

### 1. Services actifs

```bash
# Vérifier que tous les services sont lancés
docker compose ps

# Devrait afficher:
# ✅ kafka-broker (healthy)
# ✅ minio (healthy)
# ✅ vision-plante (running)
```

### 2. Images dans MinIO

```bash
# Vérifier que les images sont uploadées
mc ls local/raw-uav-images/color/

# Devrait afficher 38 dossiers avec images
```

## 🚀 Lancer l'analyse

### Publication automatique au démarrage

Le service MS3 VisionPlante publie **automatiquement** toutes les images dès son lancement :

```bash
# Démarrer le service
docker compose up -d vision-plante
```

Le service va automatiquement :
1. ✅ Initialiser MinIO, Kafka et le modèle
2. 📤 Scanner et publier toutes les images (10,861 images)
3. 🔀 Ordre : rotation entre 38 classes (1 image/classe)
4. 🎯 Commencer l'analyse immédiatement

### Désactiver la publication automatique (optionnel)

Si vous voulez démarrer MS3 sans publication automatique :

```bash
# Modifier docker-compose.yml
# AUTO_PUBLISH_ON_STARTUP=False

# Ou via ligne de commande
docker compose up -d vision-plante -e AUTO_PUBLISH_ON_STARTUP=False
```

## 📊 Suivre l'analyse en temps réel

### Logs du service

```bash
# Voir les logs MS3 VisionPlante
docker compose logs -f vision-plante
```

**Sortie attendue au démarrage :**

```
======================================================================
🌿 VISIONPLANTE SERVICE - DÉMARRAGE
======================================================================

🔧 Initialisation MinIO...
✅ MinIO connecté: minio:9000
   Bucket raw-uav-images: ✅
   Bucket disease-detection-results: ✅

🔧 Initialisation Kafka...
✅ Kafka connecté: kafka-broker:9092
   Consumer topic: image.uploaded
   Producer topic: disease.detected

🔧 Chargement du modèle...
✅ Modèle chargé: Abuzaid01/plant-disease-classifier
   Device: cpu
   Classes: 38

✅ Service initialisé avec succès

======================================================================
📤 PUBLICATION AUTOMATIQUE DES IMAGES
======================================================================
🔍 Scan des images dans s3://raw-uav-images/color/
📊 38 classes • 10861 images
🔀 File en rotation créée (1 image/classe)
⏳ [100/10861] 12.1 img/s | Dernier: Tomato___Leaf_Mold/image_042.jpg
⏳ [200/10861] 11.8 img/s | Dernier: Apple___Apple_scab/image_103.jpg
...
⏳ [10861/10861] 12.3 img/s | Dernier: Corn___healthy/image_403.jpg
✅ Publication terminée : 10861/10861 images en 883.2s (12.3 img/s)
======================================================================

👂 Écoute des événements sur topic: image.uploaded
======================================================================

======================================================================
🖼️  TRAITEMENT: color/Tomato___Leaf_Mold/image_042.jpg
======================================================================
   📐 Dimensions: 256×256
   🎯 Prédiction: Tomato___Leaf_Mold
   📊 Confiance: 97.82%
   🩺 Malade: Oui
   ⏱️  Temps d'inférence: 0.234s
   ✅ Résultat publié dans Kafka
      Topic: disease.detected
      Partition: 0
      Offset: 0
   💾 Résultats sauvegardés: s3://disease-detection-results/results/Tomato___Leaf_Mold/image_042.json
   📊 Stats: 1 images, 1 maladies détectées

======================================================================
🖼️  TRAITEMENT: color/Apple___Apple_scab/image_103.jpg
======================================================================
   📐 Dimensions: 256×256
   🎯 Prédiction: Apple___Apple_scab
   📊 Confiance: 98.91%
   🩺 Malade: Oui
   ⏱️  Temps d'inférence: 0.241s
   ✅ Résultat publié dans Kafka
   💾 Résultats sauvegardés: s3://disease-detection-results/results/Apple___Apple_scab/image_103.json
   📊 Stats: 2 images, 2 maladies détectées
...
```

### Option 2 : Kafka UI

```bash
# Ouvrir dans le navigateur
http://localhost:8080

# Aller dans:
# Topics → disease.detected → Messages

# Vous verrez les résultats arriver en temps réel
```

### Option 3 : MinIO Console

```bash
# Ouvrir dans le navigateur
http://localhost:9001

# Login: minioadmin / minioadmin

# Aller dans:
# Buckets → disease-detection-results → results/

# Vous verrez les fichiers JSON se créer en temps réel
```

## 📈 Résultats attendus

### Structure MinIO

```
disease-detection-results/
├── results/
│   ├── Apple___Apple_scab/
│   │   ├── image_042_result.json
│   │   ├── image_127_result.json
│   │   └── ... (504 fichiers)
│   ├── Tomato___healthy/
│   │   ├── image_103_result.json
│   │   └── ... (403 fichiers)
│   └── ... (38 dossiers, 10861 fichiers JSON au total)
```

### Format des résultats (JSON)

```json
{
  "image_path": "color/Tomato___Leaf_Mold/image_042.jpg",
  "image_size": [256, 256],
  "detection_results": {
    "predicted_class": "Tomato___Leaf_Mold",
    "confidence": 0.9782,
    "top_5_predictions": [
      {"class": "Tomato___Leaf_Mold", "confidence": 0.9782},
      {"class": "Tomato___Early_blight", "confidence": 0.0134},
      {"class": "Tomato___Septoria_leaf_spot", "confidence": 0.0051},
      {"class": "Tomato___Late_blight", "confidence": 0.0023},
      {"class": "Tomato___healthy", "confidence": 0.0008}
    ],
    "is_diseased": true
  },
  "inference_time_ms": 234.56,
  "model_name": "Abuzaid01/plant-disease-classifier",
  "timestamp": "2025-12-04T16:45:23.456789",
  "device": "cpu"
}
```

### Messages Kafka (`disease.detected`)

```json
{
  "event_type": "disease_detected",
  "timestamp": "2025-12-04T16:45:23.456789",
  "image_path": "color/Tomato___Leaf_Mold/image_042.jpg",
  "class_name": "Tomato___Leaf_Mold",
  "detection_results": { ... },
  "result_path": "s3://disease-detection-results/results/Tomato___Leaf_Mold/image_042_result.json"
}
```

## ⏱️ Temps estimé

| Configuration | Vitesse | Durée (10,861 images) |
|---------------|---------|----------------------|
| **CPU Intel i5/i7** | 2-3 img/s | 60-90 minutes |
| **CPU AMD Ryzen** | 3-4 img/s | 45-60 minutes |
| **GPU NVIDIA RTX 3060** | 10-15 img/s | 12-18 minutes |
| **GPU NVIDIA RTX 4090** | 20-30 img/s | 6-9 minutes |

## 🛑 Arrêter l'analyse

### Arrêt MS3 VisionPlante

```bash
docker compose stop vision-plante

# Relancer plus tard (reprendra automatiquement)
docker compose start vision-plante
```

## 🔍 Vérifications

### Vérifier que MS3 analyse bien les images

```bash
# Compter les messages dans Kafka
docker compose exec kafka-broker kafka-run-class.sh kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic disease.detected

# Sortie: disease.detected:0:1234
# → 1234 images analysées
```

### Vérifier les résultats dans MinIO

```bash
# Compter les fichiers JSON
mc ls --recursive local/disease-detection-results/results/ | wc -l

# Devrait afficher le nombre d'images analysées
```

## ❓ Dépannage

### Problème : "Connection refused" Kafka

```bash
# Vérifier que Kafka est actif
docker compose ps kafka-broker

# Relancer si nécessaire
docker compose restart kafka-broker
docker compose restart vision-plante
```

### Problème : "Bucket does not exist" MinIO

```bash
# Vérifier que le bucket existe
mc ls local/raw-uav-images/color/

# Si vide, réuploader les images
mc cp --recursive ./color/ local/raw-uav-images/color/
```

### Problème : MS3 ne traite pas les images

```bash
# Vérifier les logs MS3
docker compose logs vision-plante

# Devrait afficher: "🎧 Écoute du topic 'image.uploaded'..."

# Si le service est bloqué, relancer
docker compose restart vision-plante
```

## 📊 Statistiques attendues

Après analyse complète, vous aurez :

```
✅ 10,861 images analysées
✅ 10,861 fichiers JSON dans MinIO
✅ 10,861 événements dans Kafka (disease.detected)
✅ ~38 classes de maladies détectées
✅ Précision moyenne : 92-96%
```

## 🎯 Prochaines étapes

Une fois l'analyse terminée :

1. **Analyser les résultats** : Consulter les JSON dans MinIO
2. **Créer des statistiques** : Agréger les résultats par classe
3. **Visualiser** : Dashboard avec graphiques (à venir)
4. **Exporter** : CSV pour analyse externe

---

**Bon courage ! 🚀**
