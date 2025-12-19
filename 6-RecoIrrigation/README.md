# MS6 - RecoIrrigation 💧

**API REST de planification tactique d'irrigation**

Transforme les recommandations stratégiques de MS5 en plans d'irrigation concrets et détaillés.

---

## 📋 Vue d'ensemble

### Différence MS5 vs MS6

| MS5 (RèglesAgro) | MS6 (RecoIrrigation) |
|------------------|----------------------|
| Recommandations **stratégiques** | Plans **tactiques** |
| "IRRIGATE_TODAY - Priorité URGENT" | "9000L le 09/12 à 06:00 pendant 45min" |
| Event-driven (Kafka) | Request-driven (REST API) |

---

## 📥 Données en entrée

### 1. Recommandation MS5 (via Kafka `agro.recommendations`)
```json
{
  "plot_id": "PLOT-001",
  "type": "IRRIGATION",
  "priority": "URGENT",
  "action": "IRRIGATE_TODAY",
  "quantity": 15.0,
  "unit": "mm",
  "soil_moisture": 35.0,
  "source": "water-forecast"
}
```

### 2. Configuration zone (PostgreSQL `zones`)
```json
{
  "zone_id": "ZONE-NORTH-01",
  "plot_id": "PLOT-001",
  "area_hectares": 2.5,
  "soil_type": "loamy",
  "crop_type": "Tomato",
  "growth_stage": "flowering",
  "irrigation_type": "drip",
  "flow_rate_lpm": 200.0,
  "soil_moisture_current": 45.0
}
```

### 3. Requête HTTP
```bash
GET /api/irrigation/plan?zone_id=ZONE-NORTH-01&days_ahead=7
```

---

## ⚙️ Traitement interne (étapes clés)

### Étape 1 : Calcul du besoin en eau (mm)
```python
water_need_mm = BASE_WATER_NEED_MM × GROWTH_STAGE_FACTOR × PRIORITY_FACTOR + MOISTURE_DEFICIT
```
- **Facteurs de croissance** : `germination` 0.3, `flowering` 1.3, `fruiting` 1.5
- **Facteurs de priorité** : `URGENT` 1.5, `HIGH` 1.2, `MEDIUM` 1.0

**Exemple** : `5mm × 1.3 (flowering) × 1.5 (URGENT) = 9.75mm`

---

### Étape 2 : Conversion en volume (litres)
```python
volume_liters = water_need_mm × area_m²  # 1mm × 1m² = 1L
```
**Exemple** : `9.75mm × 25000m² (2.5ha) = 243,750L`

---

### Étape 3 : Ajustement d'efficacité
```python
adjusted_volume = volume_liters / EFFICIENCY_FACTOR
```
- **Efficacité** : `drip` 90%, `sprinkler` 75%, `furrow` 60%, `flood` 50%

**Exemple** : `243,750L / 0.90 (drip) = 270,833L`

---

### Étape 4 : Fractionnement en sessions
Selon la **priorité** et le **volume** :

| Priorité | Sessions | Répartition | Timing |
|----------|----------|-------------|--------|
| **URGENT** | 2-3 | 60% + 40% | 18:00 (J) + 06:00 (J+1) |
| **HIGH** | 2 | 50% + 50% | 06:00 (J) + 06:00 (J+2) |
| **MEDIUM/LOW** | 1 | 100% | 06:00 (J) |

**Exemple URGENT** :
- Session 1 : `270,833L × 60% = 162,500L` → 09/12 à 18:00
- Session 2 : `270,833L × 40% = 108,333L` → 10/12 à 06:00

---

### Étape 5 : Calcul des durées
```python
duration_minutes = volume_liters / flow_rate_lpm
```
**Exemple** :
- Session 1 : `162,500L / 200 L/min = 812 minutes (13h32)`
- Session 2 : `108,333L / 200 L/min = 541 minutes (9h01)`

---

### Étape 6 : Estimation du coût
```python
cost_eur = (total_volume_liters / 1000) × water_cost_per_m³
```
**Exemple** : `(270,833L / 1000) × 1.50€ = 406.25€`

---

### Étape 7 : Sauvegarde PostgreSQL
- Table `irrigation_plans` : plan global
- Table `irrigation_sessions` : sessions individuelles
- Table `recommendations_log` : traçabilité MS5

---

## 📤 Données en sortie

### Plan d'irrigation complet (JSON)
```json
{
  "zone_id": "ZONE-NORTH-01",
  "plot_id": "PLOT-001",
  "crop_type": "Tomato",
  "growth_stage": "flowering",
  "irrigation_type": "drip",
  "sessions": [
    {
      "date": "2024-12-09",
      "time": "18:00:00",
      "duration_minutes": 812,
      "volume_liters": 162500.0,
      "equipment": "Système goutte-à-goutte Nord"
    },
    {
      "date": "2024-12-10",
      "time": "06:00:00",
      "duration_minutes": 541,
      "volume_liters": 108333.0,
      "equipment": "Système goutte-à-goutte Nord"
    }
  ],
  "total_volume_liters": 270833.0,
  "estimated_cost_eur": 406.25,
  "recommendation_context": {
    "priority": "URGENT",
    "action": "IRRIGATE_TODAY",
    "source": "MS5-water-forecast"
  }
}
```

### Informations stockées en base
- **Plan persistant** avec ID unique
- **Sessions planifiées** avec statuts (`scheduled`, `in_progress`, `completed`)
- **Historique** pour analyse et reporting

---

## 🚀 Démarrage rapide

```bash
# Lancer MS6 + PostgreSQL
docker-compose up -d postgres-irrigation reco-irrigation

# Vérifier le statut
curl http://localhost:8086/health

# Accéder à Swagger UI
# http://localhost:8086/docs
```

---

## 📡 API REST - Endpoints principaux

### Générer un plan d'irrigation
```bash
curl "http://localhost:8086/api/irrigation/plan?zone_id=ZONE-NORTH-01&days_ahead=7"
```

### Lister les zones
```bash
curl "http://localhost:8086/api/zones"
```

### Créer une zone
```bash
curl -X POST "http://localhost:8086/api/zones" \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": "ZONE-01",
    "plot_id": "PLOT-001",
    "area_hectares": 2.5,
    "soil_type": "loamy",
    "crop_type": "Tomato",
    "growth_stage": "flowering",
    "irrigation_type": "drip",
    "flow_rate_lpm": 200.0,
    "equipment_name": "Système goutte-à-goutte",
    "water_source": "Puits #1"
  }'
```

### Sessions à venir
```bash
curl "http://localhost:8086/api/sessions/upcoming?zone_id=ZONE-NORTH-01"
```

### Mettre à jour une session
```bash
curl -X PATCH "http://localhost:8086/api/sessions/15/status" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "completed",
    "actual_volume_liters": 162000.0,
    "success_rate": 98.5
  }'
```

---

## 💾 Base de données

### Tables principales
- **zones** : Configuration des zones d'irrigation
- **irrigation_plans** : Plans d'irrigation générés
- **irrigation_sessions** : Sessions individuelles (date, heure, volume)
- **recommendations_log** : Historique MS5

### Connexion PostgreSQL
```bash
# Host: localhost:5434
# Database: irrigation
# User: irrigation_user
# Password: irrigation_pass
```

---

## 🛠️ Configuration

### Variables d'environnement clés
- `API_PORT=8086` : Port de l'API
- `KAFKA_BOOTSTRAP_SERVERS=kafka-broker:9092` : Serveurs Kafka
- `KAFKA_TOPIC_RECOMMENDATIONS=agro.recommendations` : Topic MS5
- `POSTGRES_HOST=postgres-irrigation` : Hôte PostgreSQL
- `POSTGRES_DB=irrigation` : Base de données

---

## 🐛 Dépannage

### Erreur : "Aucune recommandation disponible"
1. Vérifier que MS5 est démarré
2. Vérifier le topic Kafka :
   ```bash
   docker exec kafka-broker kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic agro.recommendations --from-beginning
   ```

### Erreur : "Connexion PostgreSQL refusée"
```bash
docker ps | grep postgres-irrigation
docker logs postgres-irrigation
```

### Vérifier les logs MS6
```bash
docker logs -f reco-irrigation
```

---

## 📚 Technologies
- **Python 3.11** + **FastAPI** + **Pydantic**
- **SQLAlchemy** + **PostgreSQL 16**
- **Kafka-Python** + **Uvicorn**

---

## 🔗 Liens utiles
- **Swagger UI** : http://localhost:8086/docs
- **ReDoc** : http://localhost:8086/redoc
- **Kafka UI** : http://localhost:8080

---

**AgroTrace Team** - Projet MS6
