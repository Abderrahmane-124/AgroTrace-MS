# DashboardSIG - Tableau de Bord SIG AgroTrace

## Description
Microservice de visualisation géospatiale pour la plateforme AgroTrace. Permet de visualiser l'état sanitaire et hydrique des parcelles agricoles sur une carte interactive.

## Architecture d'Intégration

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SOURCES D'ENTRÉES                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐   Kafka: sensor-data-processed                        │
│  │     MS2      │ ──────────────────────────────────►                    │
│  │ Pretraitement│   Données capteurs prétraitées                        │
│  └──────────────┘                                                        │
│                                                                          │
│  ┌──────────────┐   Kafka: disease.detected                             │
│  │     MS3      │ ──────────────────────────────────►                    │
│  │ VisionPlante │   Détections de maladies foliaires                    │
│  └──────────────┘                                                        │
│                                          ┌───────────────────────────┐  │
│  ┌──────────────┐   Kafka: water.forecast│                           │  │
│  │     MS4      │ ──────────────────────►│      MS7 - DashboardSIG   │  │
│  │ PrévisionEau │   Prévisions hydriques │                           │  │
│  └──────────────┘                        │   Backend (FastAPI)       │  │
│                                          │   + PostGIS               │  │
│  ┌──────────────┐   Kafka: agro.recommend│   + Kafka Consumer        │  │
│  │     MS5      │ ──────────────────────►│                           │  │
│  │ RèglesAgro   │   Recommandations agro │                           │  │
│  └──────────────┘                        └───────────────────────────┘  │
│                                                     │                    │
│  ┌──────────────┐   REST API (HTTP)                 │                    │
│  │     MS6      │ ◄─────────────────────────────────┘                    │
│  │RecoIrrigation│   Plans d'irrigation tactiques                        │
│  └──────────────┘                                                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Entrées (Sources de Données)

| Source | Type | Topic/Endpoint | Données |
|--------|------|----------------|---------|
| **MS2 - Prétraitement** | Kafka | `sensor-data-processed` | Données capteurs filtrées (humidité, température, etc.) |
| **MS3 - VisionPlante** | Kafka | `disease.detected` | Détections de maladies (classe, confiance, image) |
| **MS4 - PrévisionEau** | Kafka | `water.forecast` | Prévisions besoins hydriques (stress, recommandations) |
| **MS5 - RèglesAgro** | Kafka | `agro.recommendations` | Recommandations stratégiques (priorité, actions) |
| **MS6 - RecoIrrigation** | REST API | `http://reco-irrigation:8086/` | Plans d'irrigation tactiques (sessions, doses) |

## Sorties

| Type | Format | Destination | Description |
|------|--------|-------------|-------------|
| **API REST** | JSON | Frontend React | Données parcelles, prévisions, recommandations |
| **GeoJSON** | JSON | Leaflet (carte) | Géométries parcelles avec propriétés |
| **Export CSV** | CSV | Téléchargement | Rapport données parcelles |
| **Export PDF** | PDF | Téléchargement | Rapport formaté avec graphiques |

## Composants

### Backend (FastAPI)
- API REST avec 15+ endpoints
- Connexion PostGIS pour données spatiales
- Consumer Kafka pour mises à jour temps réel
- Proxy vers MS6 pour plans d'irrigation
- Export PDF/CSV

### Frontend (React + Leaflet)
- Carte interactive centrée sur ferme fictive "AgroTrace" (48.855, 2.35)
- Polygones des 3 zones d'irrigation (Tomates, Maïs, Laitue) avec couleurs distinctes
- 4 onglets : Vue d'ensemble, Irrigation, Alertes, Actions
- Popups cliquables avec détails zone + bouton "Générer Plan"
- Légende dynamique des cultures
- Panneaux de statistiques et alertes
- Boutons d'export CSV/PDF

## Endpoints API

| Méthode | Endpoint | Description | Source |
|---------|----------|-------------|--------|
| GET | /api/parcels | Liste des parcelles | PostGIS |
| GET | /api/parcels/geojson | Parcelles au format GeoJSON | PostGIS |
| GET | /api/parcels/{id} | Détail d'une parcelle | PostGIS |
| GET | /api/forecasts | Prévisions hydriques | Kafka (MS4) |
| GET | /api/diseases | Détections de maladies | Kafka (MS3) |
| GET | /api/recommendations | Recommandations actives | Kafka (MS5) |
| GET | /api/irrigation/zones | Zones d'irrigation | **MS6 API** |
| GET | /api/irrigation/plans/{zone_id} | Plan d'irrigation par zone | **MS6 API** |
| GET | /api/irrigation/sessions | Sessions d'irrigation | **MS6 API** |
| GET | /api/stats | Statistiques dashboard | PostGIS |
| GET | /api/export/csv | Export CSV | PostGIS |
| GET | /api/export/pdf | Export rapport PDF | PostGIS |

## Configuration

### Variables d'environnement

**Backend:**
- `POSTGIS_HOST` - Hôte PostGIS (défaut: postgis)
- `POSTGIS_PORT` - Port PostGIS (défaut: 5432)
- `POSTGIS_DB` - Base de données (défaut: agrotrace_sig)
- `KAFKA_BOOTSTRAP_SERVERS` - Serveurs Kafka
- `RECO_IRRIGATION_API_URL` - URL API MS6 (défaut: http://reco-irrigation:8086)

## Lancement

```bash
# Avec Docker Compose (depuis la racine du projet)
docker-compose up -d postgis dashboard-backend dashboard-frontend

# Accès
# Frontend: http://localhost:3000
# API: http://localhost:8085
# Docs API: http://localhost:8085/docs
```

## Technologies

- **Backend:** Python 3.11, FastAPI, psycopg2, kafka-python, httpx, reportlab
- **Frontend:** React 18, Vite, Leaflet, react-leaflet
- **Base de données:** PostGIS (PostgreSQL + extensions spatiales)
- **Serveur web:** Nginx
