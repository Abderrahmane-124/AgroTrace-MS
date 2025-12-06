# Prévision du Besoin en Eau

Microservice de prévision du besoin en eau à court terme (1-7 jours) utilisant Prophet pour l'analyse de séries temporelles.

---

## 📥 Données en Entrée

**Source** : Table `sensor_data_processed` (TimescaleDB)

**Capteurs utilisés** :
- Humidité du sol (Soil Moisture) - prioritaire
- Température ambiante (Environment Temperature)
- Température du sol (Soil Temperature)
- Humidité de l'air (Environment Humidity)

**Historique** : 30 derniers jours minimum

---

## ⚙️ Traitement Interne

### 1. Entraînement des Modèles
- Un modèle Prophet par type de capteur
- Réentraînement automatique toutes les 6 heures
- Prévision sur 7 jours avec intervalle de confiance à 95%

### 2. Calcul du Besoin en Eau (Agrégé par Date)
**Formule pondérée** :
```
Score = (Humidité_sol × 60%) + (Température × 25%) + (Humidité_air × 15%)
```

**Niveaux de besoin** :
- `CRITICAL` : Score > 75 → Irrigation urgente
- `HIGH` : Score 50-75 → Irrigation recommandée
- `MODERATE` : Score 30-50 → Surveillance
- `LOW` : Score < 30 → Conditions bonnes

**Quantité d'eau recommandée** :
```
Eau (mm/jour) = Score / 10
```
Exemple : Score de 65 → 6.5 mm/jour d'irrigation

---

## 📤 Données en Sortie

### Topic Kafka 1 : `water.forecast`
Prévisions individuelles par capteur (24 messages pour 4 capteurs × 6 jours)

### Topic Kafka 2 : `water.needs`
Besoins en eau agrégés par date (6 messages pour 6 jours)

---

## 📖 Comment Lire les Messages Kafka

### Message `water.needs` - Ligne par Ligne

```json
{
  "forecast_date": "2025-12-08T00:00:00",
  "water_need_score": 23.3,
  "need_level": "LOW",
  "irrigation_recommended": false,
  "irrigation_priority": "NONE",
  "recommended_water_mm": 2.33,
  "soil_moisture_percent": 100.0,
  "temperature_celsius": 42.0,
  "humidity_percent": 95.0
}
```

#### Explication Champ par Champ

| Champ | Description | Exemple |
|-------|-------------|---------|
| `forecast_date` | Date cible de la prévision | `"2025-12-08T00:00:00"` = 8 décembre 2025 |
| `water_need_score` | Score de besoin en eau sur 100 | `23.3` = Besoin faible (23.3/100) |
| `need_level` | Niveau de besoin | `"LOW"` = Faible / `"MODERATE"` = Moyen / `"HIGH"` = Élevé / `"CRITICAL"` = Urgent |
| `irrigation_recommended` | Décision d'irrigation | `false` = Pas d'irrigation / `true` = Irrigation nécessaire |
| `irrigation_priority` | Priorité d'intervention | `"NONE"` = Pas urgent / `"LOW"` / `"MEDIUM"` / `"HIGH"` / `"CRITICAL"` |
| `recommended_water_mm` | Quantité d'eau (mm/jour) | `2.33` = 2.33 millimètres d'eau par jour |
| `soil_moisture_percent` | Humidité du sol prédite | `100.0` = Sol saturé (valeur validée 0-100%) |
| `temperature_celsius` | Température moyenne prédite | `42.0` = 42°C (valeur validée -50 à 60°C) |
| `humidity_percent` | Humidité de l'air prédite | `95.0` = 95% (valeur validée 0-100%) |

#### Exemples de Lecture

**Exemple 1 - Pas d'irrigation nécessaire** :
```json
{
  "forecast_date": "2025-12-08",
  "water_need_score": 23.3,
  "need_level": "LOW",
  "irrigation_recommended": false,
  "recommended_water_mm": 2.33
}
```
✅ **Lecture** : Le 8 décembre, besoin en eau faible (23.3%), pas d'irrigation nécessaire. Sol suffisamment humide.

**Exemple 2 - Irrigation recommandée** :
```json
{
  "forecast_date": "2025-12-10",
  "water_need_score": 68.5,
  "need_level": "HIGH",
  "irrigation_recommended": true,
  "irrigation_priority": "HIGH",
  "recommended_water_mm": 6.85
}
```
⚠️ **Lecture** : Le 10 décembre, besoin élevé (68.5%), irrigation recommandée avec priorité haute. Appliquer ~7 mm d'eau.

**Exemple 3 - Irrigation urgente** :
```json
{
  "forecast_date": "2025-12-12",
  "water_need_score": 82.0,
  "need_level": "CRITICAL",
  "irrigation_recommended": true,
  "irrigation_priority": "CRITICAL",
  "recommended_water_mm": 8.2,
  "soil_moisture_percent": 15.0
}
```
🚨 **Lecture** : Le 12 décembre, besoin critique (82%), sol très sec (15% humidité). Irrigation urgente de 8.2 mm/jour requise.
