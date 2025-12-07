# MS4 - PrévisionEau (Prévision du Besoin en Eau)

## 📋 Description
Microservice de prévision du besoin en eau à court terme (1-7 jours) utilisant Prophet (Facebook) pour l'analyse de séries temporelles et la prédiction des conditions agricoles.

---

## 📥 ENTRÉES

### Source Unique : TimescaleDB
**Table** : `sensor_data_processed`

**Capteurs consommés** :
- **Soil Moisture** (humidité du sol) - 60% du score
- **Environment Temperature** (température ambiante) - 25% du score
- **Soil Temperature** (température du sol) - fallback si env. temp manquante
- **Environment Humidity** (humidité de l'air) - 15% du score

**Fenêtre historique** : 30 derniers jours (configurable via `TRAINING_WINDOW_DAYS`)

**Requête SQL typique** :
```sql
SELECT timestamp as ds, clean_value as y
FROM sensor_data_processed
WHERE sensor_type = 'Soil Moisture'
  AND timestamp >= NOW() - INTERVAL '30 days'
  AND clean_value > 0.1 AND clean_value <= 100
ORDER BY timestamp ASC
```

---

## ⚙️ TRAITEMENT

### Pipeline de Prévision
```
TimescaleDB → Prophet (ML) → Prévisions 7 jours → Agrégation → Kafka + DB
```

### Étapes Détaillées

#### 1. **Entraînement Modèles Prophet**
- **Un modèle par capteur** (Soil Moisture, Temperature, Humidity)
- **Configuration** :
  - Saisonnalité journalière (`daily_seasonality=True`)
  - Saisonnalité hebdomadaire (`weekly_seasonality=True`)
  - Intervalle de confiance 95% (`interval_width=0.95`)
  - Sensibilité aux changements : 0.05
- **Réentraînement** : Automatique toutes les `RETRAINING_INTERVAL_HOURS` (défaut: 24h)
- **Condition** : Minimum `MIN_DATA_POINTS` (défaut: 50 points)

#### 2. **Génération Prévisions**
Pour chaque capteur, prévision sur `FORECAST_HORIZON` jours (défaut: 7):
- `predicted_value` : Valeur centrale (yhat)
- `lower_bound` : Borne inférieure (yhat_lower)
- `upper_bound` : Borne supérieure (yhat_upper)
- `model_confidence` : Basée sur largeur intervalle

**Filtres de validation** :
- Soil Moisture: 0.1-100%
- Temperature: -50°C à 60°C
- Humidity: 0-100%
- Rejet valeurs aberrantes (< -100 ou > 10000)

#### 3. **Calcul Stress Hydrique**
Uniquement pour **Soil Moisture**:

```python
score = soil_moisture / 100.0

# Ajustements contextuels
if temperature > 30°C:  score *= 0.9
if temperature > 35°C:  score *= 0.8
if humidity < 40%:      score *= 0.95
if humidity < 30%:      score *= 0.85
```

**Classification** :
- Score < 0.30 → `HIGH_STRESS` (irrigation obligatoire)
- Score < 0.50 → `MEDIUM_STRESS` (irrigation recommandée)
- Score > 0.70 → `OPTIMAL` (pas d'irrigation)
- Sinon → `LOW_STRESS` (surveillance)

#### 4. **Agrégation Besoin en Eau**
Combinaison des 3 capteurs par date cible:

```python
water_need_score = 0

# Contribution humidité sol (60%)
soil_contribution = (100 - soil_moisture) * 0.6
water_need_score += soil_contribution

# Contribution température (25%)
temp_factor = (temperature - 15) / 30  # Normalisation 15-45°C
temp_contribution = temp_factor * 100 * 0.25
water_need_score += temp_contribution

# Contribution humidité air (15%)
humidity_factor = (100 - humidity) / 100
humidity_contribution = humidity_factor * 100 * 0.15
water_need_score += humidity_contribution
```

**Niveaux de besoin** :
- Score > 70 → `CRITICAL` (priorité HIGH)
- Score 50-70 → `HIGH` (priorité MEDIUM)
- Score 30-50 → `MODERATE` (priorité LOW)
- Score < 30 → `LOW` (aucune priorité)

**Quantité d'eau recommandée** :
```python
water_amount_mm = (water_need_score / 100) * 10  # Maximum 10 mm/jour
```

---

## 📤 SORTIES

### 1️⃣ Kafka Topic: `water.forecast`
**Contenu** : Prévisions individuelles par capteur et par jour

**Structure** :
```json
{
  "forecast_date": "2025-12-07T10:30:00",
  "target_date": "2025-12-08T00:00:00",
  "sensor_type": "Soil Moisture",
  "predicted_value": 45.23,
  "lower_bound": 40.15,
  "upper_bound": 50.31,
  "water_stress_level": "MEDIUM_STRESS",
  "water_stress_score": 0.4523,
  "irrigation_recommended": true,
  "horizon_days": 1,
  "model_confidence": 0.8974
}
```

**Volume** : ~21 messages (3 capteurs × 7 jours)

### 2️⃣ Kafka Topic: `water.needs`
**Contenu** : Besoins en eau agrégés par date

**Structure** :
```json
{
  "forecast_date": "2025-12-07T10:30:00",
  "target_date": "2025-12-08",
  "water_need_score": 68.5,
  "need_level": "HIGH",
  "irrigation_recommended": true,
  "irrigation_priority": "MEDIUM",
  "recommended_water_mm": 6.85,
  "soil_moisture_percent": 42.0,
  "temperature_celsius": 32.5,
  "humidity_percent": 55.0,
  "horizon_days": 1
}
```

**Volume** : 7 messages (1 par jour)

### 3️⃣ TimescaleDB: Table `water_forecast`
**Persistance** : Toutes les prévisions individuelles sauvegardées

**Schéma** :
- `forecast_date` : Date de génération
- `target_date` : Date cible prévue
- `sensor_type` : Type de capteur
- `predicted_value`, `lower_bound`, `upper_bound`
- `water_stress_level`, `water_stress_score`
- `irrigation_recommended`, `horizon_days`, `model_confidence`

**Index** : Sur `target_date`, `sensor_type`, `stress_level`

---

## 📊 Guide de Lecture des Messages

### Message `water.needs` - Interprétation

| Champ | Description | Valeurs |
|-------|-------------|---------|
| `water_need_score` | Score global 0-100 | Plus élevé = plus de besoin |
| `need_level` | Niveau critique | LOW / MODERATE / HIGH / CRITICAL |
| `irrigation_recommended` | Décision binaire | true = irriguer, false = attendre |
| `irrigation_priority` | Urgence | NONE / LOW / MEDIUM / HIGH |
| `recommended_water_mm` | Quantité d'eau | En millimètres par jour |
| `soil_moisture_percent` | Humidité sol prévue | 0-100% |
| `temperature_celsius` | Température prévue | -50 à 60°C |
| `humidity_percent` | Humidité air prévue | 0-100% |
| `horizon_days` | Jours dans le futur | 1 à 7 |

### Exemples de Scénarios

**Scénario 1 - Conditions Optimales** :
```json
{
  "water_need_score": 18.5,
  "need_level": "LOW",
  "irrigation_recommended": false,
  "soil_moisture_percent": 85.0,
  "temperature_celsius": 22.0
}
```
✅ Sol humide (85%), température modérée → Pas d'irrigation

**Scénario 2 - Irrigation Recommandée** :
```json
{
  "water_need_score": 62.0,
  "need_level": "HIGH",
  "irrigation_recommended": true,
  "irrigation_priority": "MEDIUM",
  "recommended_water_mm": 6.2,
  "soil_moisture_percent": 35.0,
  "temperature_celsius": 33.0
}
```
⚠️ Sol sec (35%), chaleur (33°C) → Irrigation 6.2 mm

**Scénario 3 - Alerte Critique** :
```json
{
  "water_need_score": 85.0,
  "need_level": "CRITICAL",
  "irrigation_recommended": true,
  "irrigation_priority": "HIGH",
  "recommended_water_mm": 8.5,
  "soil_moisture_percent": 12.0,
  "temperature_celsius": 38.0,
  "humidity_percent": 25.0
}
```
🚨 Sol très sec (12%), canicule (38°C), air sec (25%) → Irrigation urgente 8.5 mm

---

## 🔧 Configuration

| Variable | Défaut | Description |
|----------|--------|-------------|
| `FORECAST_HORIZON` | 7 | Jours de prévision |
| `TRAINING_WINDOW_DAYS` | 30 | Historique pour entraînement |
| `RETRAINING_INTERVAL_HOURS` | 24 | Fréquence réentraînement |
| `PUBLISH_INTERVAL_MINUTES` | 60 | Fréquence génération prévisions |
| `MIN_DATA_POINTS` | 50 | Minimum de points pour entraîner |
| `WATER_STRESS_THRESHOLD_LOW` | 30 | Seuil stress élevé (%) |
| `WATER_STRESS_THRESHOLD_MEDIUM` | 50 | Seuil stress moyen (%) |
| `WATER_STRESS_THRESHOLD_HIGH` | 70 | Seuil optimal (%) |
| `WEIGHT_SOIL_MOISTURE` | 0.6 | Poids humidité sol (60%) |
| `WEIGHT_TEMPERATURE` | 0.25 | Poids température (25%) |
| `WEIGHT_HUMIDITY` | 0.15 | Poids humidité air (15%) |

---

## 🔄 Cycle de Fonctionnement

```
Toutes les 60 minutes (configurable):
1. Vérifier si réentraînement nécessaire (>24h depuis dernier)
2. Si oui: récupérer 30 jours de données depuis TimescaleDB
3. Entraîner modèles Prophet (Soil/Temp/Humidity)
4. Générer prévisions 7 jours avec intervalles confiance
5. Calculer stress hydrique pour Soil Moisture
6. Agréger besoins en eau par date (combinaison 3 capteurs)
7. Sauvegarder dans TimescaleDB (table water_forecast)
8. Publier dans Kafka (water.forecast + water.needs)
9. Afficher statistiques (modèles, prévisions, erreurs)
```

---

## 🛠️ Dépendances

- `prophet` : Modèle de prévision Facebook (Prophet)
- `pandas` : Manipulation DataFrames
- `numpy` : Calculs numériques
- `psycopg2` : Client PostgreSQL/TimescaleDB
- `kafka-python` : Producer Kafka
