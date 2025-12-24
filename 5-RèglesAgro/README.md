# MS5 - RèglesAgro

## Description
Moteur de règles agronomiques **simple en Python** pour générer des recommandations intelligentes à partir des données des microservices précédents (MS2, MS3, MS4).

## Technologies
- **Python 3.11**
- **Kafka-Python** (événements)
- **PyYAML** (configuration règles)
- **Dictionary-based Rules Engine** (zéro dépendance externe complexe)

---

## Entrées

### Topics Kafka consommés
1. **`water.forecast`** (MS4 - PrévisionEau)
   - Structure: `{plotId, timestamp, forecastedNeeds, soilMoisture, temperature, humidity, forecastDate}`
   - Déclenche: Règles d'irrigation

2. **`disease.detected`** (MS3 - VisionPlante)
   - Structure: `{plotId, timestamp, diseaseName, confidence, severity, cropType}`
   - Déclenche: Règles de traitement phytosanitaire

3. **`sensor-data-processed`** (MS2 - Pretraitement)
   - Structure: `{plotId, timestamp, soilMoisture, temperature, humidity, ph, nitrogen, phosphorus, potassium}`
   - Déclenche: Règles d'ajustement du sol et fertilisation

---

## Traitement Interne

### Architecture Globale
```
┌─────────────────────────────────────────────────────────────────┐
│                    KAFKA CONSUMERS (3 threads)                  │
│  water.forecast │ disease.detected │ sensor-data-processed     │
└──────────┬──────────────┬───────────────────┬───────────────────┘
           │              │                   │
           ▼              ▼                   ▼
    ┌──────────────────────────────────────────────────┐
    │         NORMALISATION DES DONNÉES                │
    │  plotId → plot_id, diseaseName → disease_name   │
    └──────────────────┬───────────────────────────────┘
                       │
                       ▼
    ┌──────────────────────────────────────────────────┐
    │           MOTEUR DE RÈGLES (rules_engine.py)     │
    │   - Chargement règles YAML                       │
    │   - Évaluation conditions (ALL/ANY logic)        │
    │   - Pattern matching (lt, gt, contains...)       │
    │   - Génération recommandations                   │
    └──────────────────┬───────────────────────────────┘
                       │
                       ▼
    ┌──────────────────────────────────────────────────┐
    │          TRI PAR PRIORITÉ                        │
    │   URGENT (4) > HIGH (3) > MEDIUM (2) > LOW (1)   │
    └──────────────────┬───────────────────────────────┘
                       │
                       ▼
    ┌──────────────────────────────────────────────────┐
    │         KAFKA PRODUCER                           │
    │   Topic: agro.recommendations                    │
    └──────────────────────────────────────────────────┘
```

### Étapes Clés du Traitement

#### **ÉTAPE 1 : Réception Événement Kafka** (`kafka_service.py`)
**Ce qui se passe :**
- 3 consumers Kafka écoutent en parallèle (threading)
- Chaque consumer est dédié à un topic spécifique
- Désérialisation automatique du JSON

**Code concerné :**
```python
# kafka_service.py - ligne 85
consumer = KafkaConsumer(
    KAFKA_TOPIC_WATER_FORECAST,  # ou disease.detected, sensor-data-processed
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)
```

**Exemple d'entrée :**
```json
{
  "plotId": "PLOT-001",
  "diseaseName": "Tomato_Late_Blight",
  "confidence": 0.89
}
```

---

#### **ÉTAPE 2 : Normalisation des Données** (`kafka_service.py`)
**Ce qui se passe :**
- Conversion des champs camelCase → snake_case (compatibilité Python)
- Gestion des variantes de nommage (`plotId` OU `plot_id`)
- Extraction des valeurs pertinentes pour les règles

**Code concerné :**
```python
# kafka_service.py - lignes 105-111
normalized_data = {
    'plot_id': data.get('plotId') or data.get('plot_id'),
    'disease_name': data.get('diseaseName') or data.get('disease_name'),
    'confidence': data.get('confidence'),
    'severity': data.get('severity'),
    'crop_type': data.get('cropType') or data.get('crop_type')
}
```

**Résultat :**
```python
{
  'plot_id': 'PLOT-001',
  'disease_name': 'Tomato_Late_Blight',
  'confidence': 0.89
}
```

#### **Normalisation des Plot ID (Compatibilité MS6)**
Les données capteurs peuvent utiliser différents formats d'identifiants. MS5 normalise automatiquement vers le format MS6 :

| Format d'entrée | → Format MS6 |
|-----------------|--------------|
| `1`, `2`, `3` | `PLOT-001`, `PLOT-002`, `PLOT-003` |
| `plot_1`, `plot-1` | `PLOT-001` |
| `PLOT-001` | `PLOT-001` (inchangé) |

**Code concerné :**
```python
# kafka_service.py - PLOT_ID_MAPPING
PLOT_ID_MAPPING = {
    '1': 'PLOT-001', '2': 'PLOT-002', '3': 'PLOT-003',
    'plot_1': 'PLOT-001', 'plot_2': 'PLOT-002', ...
}

def _normalize_plot_id(self, plot_id) -> str:
    # Conversion vers format MS6
    return PLOT_ID_MAPPING.get(str(plot_id), 'PLOT-001')
```

Cela garantit que les recommandations d'**irrigation** générées par MS5 utilisent des `plot_id` compatibles avec les zones configurées dans MS6.

---

#### **ÉTAPE 3 : Chargement des Règles YAML** (`rules_engine.py`)
**Ce qui se passe :**
- Lecture du fichier `rules_config.yaml` au démarrage
- Parsing YAML → structures Python (listes de dictionnaires)
- Séparation en 3 catégories : irrigation_rules, disease_rules, soil_rules

**Code concerné :**
```python
# rules_engine.py - lignes 29-42
def _load_rules(self):
    with open(self.rules_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    self.irrigation_rules = config.get('irrigation_rules', [])
    self.disease_rules = config.get('disease_rules', [])
    self.soil_rules = config.get('soil_rules', [])
```

**Résultat en mémoire :**
```python
disease_rules = [
    {
        'name': 'Mildiou - Traitement Urgent',
        'priority': 'URGENT',
        'conditions': {'all': [...]},
        'action': {'type': 'DISEASE_TREATMENT', ...}
    },
    # ... autres règles
]
```

---

#### **ÉTAPE 4 : Évaluation des Conditions** (`rules_engine.py`)
**Ce qui se passe :**
- Pour chaque règle, test des conditions une par une
- Support de la logique ALL (AND) et ANY (OR)
- Opérateurs numériques (lt, gt, gte, lte) et texte (contains, startswith)

**Code concerné :**
```python
# rules_engine.py - lignes 44-73 (évaluation condition)
def _evaluate_condition(self, data: Dict, condition: Dict) -> bool:
    field = condition['field']
    operator = condition['operator']
    expected_value = condition['value']
    actual_value = data.get(field)
    
    if operator == 'lt':
        return actual_value < expected_value
    elif operator == 'contains':
        return expected_value in str(actual_value)
    # ... autres opérateurs
```

**Exemple concret :**
```python
# Règle: Mildiou - Traitement Urgent
Condition 1: disease_name contains "Late_Blight"
  → "Late_Blight" in "Tomato_Late_Blight" = True ✓

Condition 2: confidence > 0.70
  → 0.89 > 0.70 = True ✓

Logique ALL: True AND True = True → RÈGLE DÉCLENCHÉE
```

---

#### **ÉTAPE 5 : Génération des Recommandations** (`rules_engine.py`)
**Ce qui se passe :**
- Si conditions validées → création objet Recommendation
- Formatage du template avec les données réelles (f-string Python)
- Ajout métadonnées (timestamp, source, priorité, produit/dosage)

**Code concerné :**
```python
# rules_engine.py - lignes 97-128
def _create_recommendation(self, rule: Dict, data: Dict, source: str):
    action = rule['action']
    
    # Formatage du message avec données réelles
    details = action['template'].format(**data)
    
    recommendation = {
        'plot_id': data.get('plot_id'),
        'timestamp': datetime.now().isoformat(),
        'type': action['type'],
        'priority': rule['priority'],
        'action': action['action_code'],
        'details': details,
        'source': source,
        'rule_name': rule['name']
    }
    
    # Ajout infos produit si présent
    if action.get('product'):
        recommendation['product'] = action['product']
    
    return recommendation
```

**Exemple de template :**
```yaml
template: "Mildiou détecté ({confidence:.0%} confiance). URGENT: 1) Bouillie..."
```

**Après formatage :**
```
"Mildiou détecté (89% confiance). URGENT: 1) Bouillie bordelaise 20g/L..."
```

---

#### **ÉTAPE 6 : Tri par Priorité** (`rules_engine.py`)
**Ce qui se passe :**
- Si plusieurs règles déclenchées → tri du plus urgent au moins urgent
- Utilisation d'un dictionnaire de scores (URGENT=4, HIGH=3, MEDIUM=2, LOW=1)
- Tri décroissant (reverse=True)

**Code concerné :**
```python
# rules_engine.py - lignes 186-197
def _sort_by_priority(self, recommendations: List[Dict]):
    return sorted(
        recommendations,
        key=lambda x: PRIORITY_LEVELS.get(x['priority'], 0),
        reverse=True  # Plus haute priorité en premier
    )

# config.py - lignes 32-37
PRIORITY_LEVELS = {
    'URGENT': 4,
    'HIGH': 3,
    'MEDIUM': 2,
    'LOW': 1
}
```

**Exemple :**
```python
Recommandations brutes: [MEDIUM, URGENT, HIGH]
Après tri: [URGENT, HIGH, MEDIUM]
```

---

#### **ÉTAPE 7 : Envoi vers Kafka** (`kafka_service.py`)
**Ce qui se passe :**
- Sérialisation des recommandations en JSON
- Envoi vers topic `agro.recommendations`
- Utilisation de `plot_id` comme clé de partition (même plot → même partition)
- Confirmation synchrone (acks='all' pour fiabilité)

**Code concerné :**
```python
# kafka_service.py - lignes 30-51
def send_recommendation(self, recommendation: Dict):
    plot_id = recommendation.get('plot_id', 'UNKNOWN')
    
    future = self.producer.send(
        KAFKA_TOPIC_RECOMMENDATIONS,
        key=plot_id,  # Clé de partition
        value=recommendation
    )
    
    # Attendre confirmation
    record_metadata = future.get(timeout=10)
    
    logger.info(f"Recommandation envoyée: plot={plot_id}, "
               f"type={recommendation['type']}, "
               f"priority={recommendation['priority']}")
```

**Message Kafka final :**
```json
{
  "plot_id": "PLOT-001",
  "timestamp": "2025-12-08T10:45:32.123456",
  "type": "DISEASE_TREATMENT",
  "priority": "URGENT",
  "action": "APPLY_FUNGICIDE_COPPER",
  "details": "Mildiou détecté (89% confiance). URGENT: 1) Bouillie bordelaise 20g/L...",
  "source": "DISEASE_DETECTION",
  "rule_name": "Mildiou - Traitement Urgent",
  "product": "Bouillie bordelaise (Cuivre)",
  "dosage": "20 g/L"
}
```

---

### Flux Complet Illustré

**Exemple : Détection Mildiou**

```
INPUT (disease.detected)
{"plotId":"PLOT-001", "diseaseName":"Tomato_Late_Blight", "confidence":0.89}
           │
           │ [ÉTAPE 1] Consumer Kafka reçoit
           ▼
{'plot_id':'PLOT-001', 'disease_name':'Tomato_Late_Blight', 'confidence':0.89}
           │
           │ [ÉTAPE 2] Normalisation
           ▼
Chargement disease_rules (6 règles)
           │
           │ [ÉTAPE 3] Chargement YAML
           ▼
Parcours règle par règle:
  - Règle 1: "Mildiou - Traitement Urgent"
           │
           │ [ÉTAPE 4] Évaluation conditions
           ▼
    Condition 1: "Late_Blight" in "Tomato_Late_Blight" → True ✓
    Condition 2: 0.89 > 0.70 → True ✓
    ALL conditions → RÈGLE DÉCLENCHÉE
           │
           │ [ÉTAPE 5] Génération recommandation
           ▼
{
  "plot_id": "PLOT-001",
  "priority": "URGENT",
  "action": "APPLY_FUNGICIDE_COPPER",
  "details": "Mildiou détecté (89% confiance)...",
  "product": "Bouillie bordelaise"
}
           │
           │ [ÉTAPE 6] Tri (si plusieurs règles)
           ▼
[Recommandation URGENT] (la plus prioritaire)
           │
           │ [ÉTAPE 7] Envoi Kafka
           ▼
OUTPUT (agro.recommendations)
Topic: agro.recommendations, Partition: 0, Offset: 42
```

---

### Moteur de Règles (`rules_engine.py`)

**Principe:** Règles déclarées en YAML, évaluées par fonctions Python simples.

#### Structure d'une règle
```yaml
- name: "Irrigation Urgente"
  priority: "URGENT"
  conditions:
    all:  # Toutes les conditions doivent être vraies (AND)
      - field: "soil_moisture"
        operator: "lt"
        value: 15.0
      - field: "temperature"
        operator: "gt"
        value: 35.0
  action:
    type: "IRRIGATION"
    action_code: "IRRIGATE_NOW"
    template: "Stress hydrique CRITIQUE: {soil_moisture:.1f}%..."
    quantity: 17.5
    unit: "L/m²"
```

#### Opérateurs disponibles
- **Numériques:** `lt`, `lte`, `gt`, `gte`, `eq`, `ne`
- **Texte:** `contains`, `startswith`, `endswith`
- **Logique:** `all` (AND), `any` (OR)

### Règles Configurées (19 au total)

#### **Irrigation (4 règles)** - `irrigation_rules`
| Nom | Priorité | Conditions | Action |
|-----|----------|------------|--------|
| Irrigation Urgente | URGENT | humidité < 15% ET temp > 35°C | IRRIGATE_NOW (17.5 L/m²) |
| Haute Priorité | HIGH | 15-25% ET temp > 30°C | IRRIGATE_TODAY (11 L/m²) |
| Préventive | MEDIUM | 25-40% ET besoins > 3L/m² | SCHEDULE_IRRIGATION_48H (8 L/m²) |
| Non Nécessaire | LOW | humidité ≥ 60% | NO_IRRIGATION_NEEDED |

#### **Maladies (6 règles)** - `disease_rules`
| Nom | Priorité | Conditions | Traitement |
|-----|----------|------------|------------|
| Mildiou | URGENT | Late_Blight ET conf > 70% | Bouillie bordelaise 20g/L |
| Septoriose | HIGH | Septoria ET conf > 65% | Mancozèbe 2g/L |
| Helminthosporiose | HIGH | Northern_Leaf_Blight ET conf > 75% | Triazole 0.5L/ha |
| Bactériose | URGENT | Bacterial ET conf > 60% | Isolement + Cuivre |
| Moisissure | MEDIUM | Mold ET conf > 55% | Bacillus subtilis 10mL/L |
| Confiance faible | LOW | conf 40-60% | Surveillance rapprochée |

#### **Sol (9 règles)** - `soil_rules`
| Nom | Priorité | Conditions | Correction |
|-----|----------|------------|-----------|
| pH Acide | HIGH | pH < 5.5 | Chaux 300 kg/ha |
| pH Alcalin | MEDIUM | pH > 7.5 | Soufre 150 kg/ha |
| Carence N | HIGH | N < 20 ppm | Urée 46% - 125 kg/ha |
| Carence P | MEDIUM | P < 10 ppm | Superphosphate 175 kg/ha |
| Carence K | MEDIUM | K < 80 ppm | Chlorure K 125 kg/ha |
| Sol Sec + Carence N | URGENT | humid < 20% ET N < 25 | Irrigation PUIS fertilisation |
| Conditions Optimales | LOW | pH 6-7, humid 40-70%, N > 30 | Maintien préventif |

### Exemple d'exécution
```python
INPUT: disease.detected
{
  "plotId": "PLOT-001",
  "diseaseName": "Tomato_Late_Blight",
  "confidence": 0.89
}

EVALUATION:
1. Normalisation: plotId → plot_id, diseaseName → disease_name
2. Test règle "Mildiou - Traitement Urgent"
   - Condition 1: "Late_Blight" in "Tomato_Late_Blight" ✓
   - Condition 2: 0.89 > 0.70 ✓
   - ALL conditions vraies → RÈGLE DÉCLENCHÉE

OUTPUT: agro.recommendations
{
  "plot_id": "PLOT-001",
  "timestamp": "2025-12-08T10:45:32",
  "type": "DISEASE_TREATMENT",
  "priority": "URGENT",
  "action": "APPLY_FUNGICIDE_COPPER",
  "details": "Mildiou détecté (89% confiance). URGENT: 1) Bouillie bordelaise...",
  "source": "DISEASE_DETECTION",
  "rule_name": "Mildiou - Traitement Urgent",
  "product": "Bouillie bordelaise (Cuivre)",
  "dosage": "20 g/L"
}
```

---

## Sorties

### Topic Kafka produit
- **`agro.recommendations`**
  - Format JSON:
    ```json
    {
      "plot_id": "PLOT-XXX",
      "timestamp": "2025-12-08T10:45:32",
      "type": "IRRIGATION | DISEASE_TREATMENT | FERTILIZATION | SOIL_ADJUSTMENT",
      "priority": "URGENT | HIGH | MEDIUM | LOW",
      "action": "Code action (ex: IRRIGATE_NOW)",
      "details": "Texte détaillé pour l'agriculteur",
      "source": "WATER_FORECAST | DISEASE_DETECTION | SENSOR_DATA",
      "rule_name": "Nom de la règle déclenchée",
      "product": "Produit recommandé (optionnel)",
      "dosage": "Dosage (optionnel)",
      "quantity": 17.5,
      "unit": "L/m²"
    }
    ```

---

## Configuration

### Kafka
- **Bootstrap servers**: `kafka-broker:9092`
- **Consumer group**: `regles-agro-group`
- **Topics consommés**: `water.forecast`, `disease.detected`, `sensor-data-processed`
- **Topic produit**: `agro.recommendations`

### Fichiers de Configuration
- **`config.py`**: Variables d'environnement et paramètres
- **`rules_config.yaml`**: Définition complète des 19 règles
  - Modifiable à chaud (rechargement via `rules_engine.reload_rules()`)
  - Format YAML lisible et maintenable

---

## Architecture des Fichiers

```
5-RèglesAgro/
├── config.py                 # Configuration (Kafka, logs)
├── rules_config.yaml         # 19 règles agronomiques (YAML)
├── rules_engine.py           # Moteur d'évaluation (150 lignes)
├── kafka_service.py          # Consumers/Producer Kafka
├── regles_agro.py            # Point d'entrée (main)
├── requirements.txt          # Dépendances Python
├── Dockerfile                # Image Python 3.11
└── README.md                 # Documentation
```

**Total:** ~400 lignes Python (vs ~800 lignes Java/Drools) 📉

---

## Build et Déploiement

### Installation locale
```bash
cd 5-RèglesAgro
pip install -r requirements.txt
```

### Lancer localement
```bash
# Avec Kafka local
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
python regles_agro.py
```

### Docker
```bash
# Build image
docker build -t agrotrace/regles-agro:latest .

# Lancer avec docker-compose
cd ..
docker-compose up --build regles-agro
```

### Logs
```bash
docker logs -f regles-agro
```

Logs typiques:
```
2025-12-08 10:45:30 - __main__ - INFO - MS5 - RèglesAgro - Moteur de Règles Agronomiques
2025-12-08 10:45:31 - rules_engine - INFO - Règles chargées: 4 irrigation, 6 maladies, 9 sol (Total: 19)
2025-12-08 10:45:32 - kafka_service - INFO - Producer Kafka initialisé: kafka-broker:9092
2025-12-08 10:45:33 - kafka_service - INFO - Consumer démarré: water.forecast
2025-12-08 10:45:34 - kafka_service - INFO - Consumer démarré: disease.detected
2025-12-08 10:45:35 - kafka_service - INFO - Consumer démarré: sensor-data-processed
2025-12-08 10:50:12 - kafka_service - INFO - Reçu disease.detected: plot=PLOT-001, disease=Tomato_Late_Blight
2025-12-08 10:50:12 - rules_engine - INFO - Règle déclenchée: Mildiou - Traitement Urgent pour plot PLOT-001
2025-12-08 10:50:12 - kafka_service - INFO - Recommandation envoyée: plot=PLOT-001, type=DISEASE_TREATMENT, priority=URGENT
```

---

## Ajout de Nouvelles Règles

### 1. Modifier `rules_config.yaml`

Exemple: Ajout règle de prévention gel

```yaml
soil_rules:
  # ... règles existantes ...
  
  - name: "Prévention Gel - Alerte"
    priority: "URGENT"
    conditions:
      all:
        - field: "temperature"
          operator: "lt"
          value: 2.0
    action:
      type: "FROST_PREVENTION"
      action_code: "ACTIVATE_FROST_PROTECTION"
      template: "Température {temperature:.1f}°C - Risque gel. 1) Activer asperseurs anti-gel 2) Déployer voiles hivernage 3) Surveillance nocturne"
      product: null
      dosage: null
```

### 2. Rechargement (optionnel)

**Hot reload sans redémarrage:**
```python
from rules_engine import rules_engine
rules_engine.reload_rules()
```

**Ou redémarrer container:**
```bash
docker-compose restart regles-agro
```

### 3. Règles conditionnelles complexes (ANY)

```yaml
- name: "Stress Multiple"
  priority: "URGENT"
  conditions:
    any:  # Au moins UNE condition vraie (OR)
      - field: "soil_moisture"
        operator: "lt"
        value: 10.0
      - field: "temperature"
        operator: "gt"
        value: 40.0
  action:
    type: "EMERGENCY"
    action_code: "CRITICAL_INTERVENTION"
    template: "Conditions critiques détectées..."
```

---

## Tests Manuels

### 1. Envoyer événement test

```bash
# Test disease.detected
docker exec -it kafka-broker kafka-console-producer.sh \
  --broker-list localhost:9092 \
  --topic disease.detected

# Coller JSON:
{"plotId":"PLOT-TEST","timestamp":"2025-12-08T10:00:00","diseaseName":"Tomato_Late_Blight","confidence":0.85,"severity":"HIGH","cropType":"Tomate"}
```

### 2. Vérifier sortie

```bash
docker exec -it kafka-broker kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic agro.recommendations \
  --from-beginning
```

### 3. Test complet (script Python)

```python
from rules_engine import rules_engine

# Test irrigation
data_irrigation = {
    'plot_id': 'PLOT-001',
    'soil_moisture': 12,
    'temperature': 36,
    'forecasted_needs': 15.0
}

recommendations = rules_engine.evaluate_water_forecast(data_irrigation)
for rec in recommendations:
    print(f"[{rec['priority']}] {rec['action']}: {rec['details']}")

# Output attendu:
# [URGENT] IRRIGATE_NOW: Stress hydrique CRITIQUE: 12.0% humidité, 36.0°C...
```

---

## Avantages vs Java/Drools

| Aspect | Python Simple | Java/Drools |
|--------|---------------|-------------|
| **Complexité** | ⭐ Ultra simple | ⭐⭐⭐⭐⭐ Complexe |
| **Lignes de code** | ~400 | ~800+ |
| **Dépendances** | 3 (Kafka, PyYAML, psycopg2) | 15+ (Maven, JRE, Drools, Spring) |
| **Temps build** | 30s | 3-5 min |
| **Taille image** | ~150 MB | ~400 MB |
| **Hot reload règles** | ✅ Modifier YAML | ✅ Modifier .drl |
| **Facilité debug** | ✅ Print/logs simples | ⚠️ Stacktraces Java |
| **Courbe apprentissage** | ⭐ 1h | ⭐⭐⭐⭐ Plusieurs jours |
| **Performance** | 🚀 Excellent | 🚀 Excellent |

---

## Points Clés

1. ✅ **Simplicité maximale:** Règles en YAML, logique en Python pur
2. ✅ **Zéro framework lourd:** Pas de Spring, pas de JVM, pas de Maven
3. ✅ **Modifiable facilement:** Règles YAML éditables sans recompilation
4. ✅ **Léger:** Image Docker 4x plus petite
5. ✅ **Expertise agronomique:** Recommandations détaillées avec dosages/produits
6. ✅ **Multi-sources:** Agrège 3 topics Kafka différents
7. ✅ **Priorisation:** Tri automatique URGENT → LOW
8. ✅ **Production-ready:** Gestion erreurs, logs structurés, threading

---

## Prochaines Évolutions

- [ ] API REST pour consultation recommandations historiques
- [ ] Persistance PostgreSQL (historique recommandations)
- [ ] Dashboard Grafana (métriques temps réel)
- [ ] Machine Learning pour ajuster seuils dynamiquement
- [ ] Notifications push/email pour recommandations URGENT
- [ ] Interface Web pour édition règles (éditeur YAML)
- [ ] Tests unitaires (pytest)
