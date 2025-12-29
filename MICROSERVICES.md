# Architecture des Microservices - AgroTrace

## Vue d'ensemble

```
MS0 → MS1 → MS2 → MS5 → MS6 → MS7
                    ↑
MS3 ────────────────┘
                    ↑
MS4 ────────────────┘
```

---

## MS0 - Simulateur de Capteurs
**Rôle :** Simule des capteurs IoT agricoles (température, humidité sol, pH, etc.)  
**Sortie :** Publie vers **Kafka** (`sensor-data`)  
**Dashboard (MS7) ?** ❌ Non — sortie intermédiaire

| Modèle IA | Dataset |
|-----------|---------|
| ❌ Aucun | Fichiers Excel IoT : `Environment Humidity.xlsx`, `Environment Temperature.xlsx`, `Soil Moisture.xlsx`, `Soil pH.xlsx`, `Soil Temperature.xlsx`, `Environment Light Intensity.xlsx`, `Solar Panel Battery Voltage.xlsx`, `Water TDS.xlsx` |

---

## MS1 - Ingestion Capteurs  
**Rôle :** Consomme les données brutes des capteurs, les harmonise et les stocke  
**Entrée :** Kafka (`sensor-data`)  
**Sortie :** Stockage **TimescaleDB** → publication Kafka (`sensor-data` pour MS2)  
**Dashboard (MS7) ?** ❌ Non — sortie intermédiaire

| Modèle IA | Dataset |
|-----------|---------|
| ❌ Aucun | ❌ Aucun (consomme MS0) |

---

## MS2 - Prétraitement
**Rôle :** Nettoie, normalise et détecte les anomalies dans les données capteurs  
**Entrée :** Kafka (`sensor-data`)  
**Sortie :** Kafka (`sensor-data-processed`) + stockage **TimescaleDB**  
**Dashboard (MS7) ?** ❌ Non — alimente MS4 et MS5

| Modèle IA | Dataset |
|-----------|---------|
| ❌ Aucun (algorithmes statistiques : Z-score, moyenne mobile) | ❌ Aucun (consomme MS1) |

---

## MS3 - VisionPlante
**Rôle :** Détection de maladies foliaires par IA  
**Entrée :** Images depuis **MinIO** (bucket `raw-uav-images`)  
**Sortie :** Kafka (`disease.detected`) avec classe maladie + confiance  
**Dashboard (MS7) ?** ✅ **Oui** — les alertes maladies sont affichées dans le panel "Alertes"

| Modèle IA | Dataset |
|-----------|---------|
| **EfficientNet-B2 + Attention** (`Abuzaid01/plant-disease-classifier` via HuggingFace) | **PlantVillage** : ~10,858 images de feuilles (14 classes de maladies) stockées dans MinIO `raw-uav-images/mixed_images/` |

---

## MS4 - PrévisionEau
**Rôle :** Prévision des besoins en eau (1-7 jours)  
**Entrée :** Données prétraitées depuis **TimescaleDB**  
**Sortie :** Kafka (`water.forecast`, `water.needs`) + stockage **TimescaleDB**  
**Dashboard (MS7) ?** ✅ **Oui** — les prévisions alimentent le panel "Prévisions"

| Modèle IA | Dataset |
|-----------|---------|
| **Prophet** (Facebook/Meta) — modèle de séries temporelles | Données capteurs prétraitées depuis TimescaleDB (Soil Moisture, Temperature, Humidity) — entraînement dynamique |

---

## MS5 - RèglesAgro (Moteur de Règles)
**Rôle :** Applique des règles agronomiques pour générer des recommandations  
**Entrée :** Kafka (`water.forecast`, `disease.detected`, `sensor-data-processed`)  
**Sortie :** Kafka (`recommendations`) — types: IRRIGATION, TREATMENT, SOIL, FERTILIZATION  
**Dashboard (MS7) ?** ✅ **Oui** — les recommandations sont affichées dans le panel "Actions"

| Modèle IA | Dataset |
|-----------|---------|
| ❌ Aucun (moteur de règles if/then basé sur seuils agronomiques) | ❌ Aucun |

---

## MS6 - RecoIrrigation
**Rôle :** Génère des plans d'irrigation tactiques (calendrier, volumes, durées)  
**Entrée :** Kafka (`recommendations` type IRRIGATION) depuis MS5  
**Sortie :** API REST (plans d'irrigation détaillés avec sessions)  
**Dashboard (MS7) ?** ✅ **Oui** — le dashboard appelle l'API MS6 pour afficher les plans

| Modèle IA | Dataset |
|-----------|---------|
| ❌ Aucun (algorithmes de planification basés sur paramètres agronomiques) | ❌ Aucun |

---

## MS7 - DashboardSIG
**Rôle :** Interface de visualisation cartographique (React + Leaflet) + API backend (FastAPI + PostGIS)  
**Entrées directes via Kafka :** 
- `disease.detected` (MS3) → Alertes maladies
- `water.forecast` (MS4) → Prévisions hydriques  
- `recommendations` (MS5) → Actions recommandées

**Entrées via API proxy (MS6) :**
- `/api/irrigation/plans` → Plans d'irrigation tactiques
- `/api/irrigation/zones` → Zones d'irrigation

| Modèle IA | Dataset |
|-----------|---------|
| ❌ Aucun (visualisation uniquement) | ❌ Aucun |

---

## Résumé : Modèles IA et Datasets

| MS | Modèle IA | Dataset | Dashboard ? |
|----|-----------|---------|-------------|
| MS0 | ❌ | Excel IoT (8 fichiers capteurs) | ❌ |
| MS1 | ❌ | ❌ | ❌ |
| MS2 | ❌ (statistiques) | ❌ | ❌ |
| **MS3** | **EfficientNet-B2** (HuggingFace) | **PlantVillage** (~10,858 images) | ✅ |
| **MS4** | **Prophet** (Facebook) | Données TimescaleDB (dynamique) | ✅ |
| MS5 | ❌ (règles) | ❌ | ✅ |
| MS6 | ❌ (planification) | ❌ | ✅ |
| MS7 | ❌ | ❌ | — |
