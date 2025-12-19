"""
MS6 - RecoIrrigation
API REST FastAPI pour la génération de plans d'irrigation tactiques.
Consomme les recommandations stratégiques de MS5 pour créer des calendriers d'irrigation détaillés.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional, List
from datetime import datetime, timedelta, date
import logging

from models import IrrigationPlan, ZoneConfiguration, IrrigationSession, SessionStatus
from planner import IrrigationPlanner
from kafka_consumer import kafka_consumer, get_latest_irrigation_recommendation
from database import db, Zone, IrrigationPlan as IrrigationPlanDB
from config import API_HOST, API_PORT

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ========================================
# LIFECYCLE
# ========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    # Startup
    logger.info("🚀 Démarrage MS6 - RecoIrrigation")
    
    # Initialiser la base de données
    try:
        db.init_db()
        logger.info("✅ Base de données initialisée")
    except Exception as e:
        logger.error(f"❌ Erreur initialisation DB: {e}")
    
    # Démarrer le consumer Kafka
    try:
        kafka_consumer.start()
        logger.info("✅ Consumer Kafka démarré")
    except Exception as e:
        logger.error(f"❌ Erreur démarrage Kafka: {e}")
    
    yield
    
    # Shutdown
    logger.info("🛑 Arrêt MS6 - RecoIrrigation")
    try:
        kafka_consumer.stop()
        logger.info("✅ Consumer Kafka arrêté")
    except Exception as e:
        logger.error(f"❌ Erreur arrêt Kafka: {e}")


# ========================================
# APPLICATION FASTAPI
# ========================================

app = FastAPI(
    title="MS6 - RecoIrrigation",
    description="API de planification tactique d'irrigation basée sur les recommandations MS5",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instance du planificateur
planner = IrrigationPlanner()


# ========================================
# ENDPOINTS - HEALTH CHECK
# ========================================

@app.get("/health")
async def health_check():
    """Health check avec statut des dépendances"""
    db_healthy = db.health_check()
    kafka_healthy = kafka_consumer.is_running()
    
    return {
        "status": "healthy" if (db_healthy and kafka_healthy) else "degraded",
        "service": "MS6-RecoIrrigation",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {
            "database": "ok" if db_healthy else "error",
            "kafka_consumer": "ok" if kafka_healthy else "error"
        }
    }


# ========================================
# ENDPOINTS - PLANS D'IRRIGATION
# ========================================

@app.get("/api/irrigation/plan", response_model=IrrigationPlan)
async def get_irrigation_plan(
    zone_id: str = Query(..., description="ID de la zone d'irrigation"),
    days_ahead: int = Query(7, ge=1, le=30, description="Nombre de jours à planifier")
):
    """
    Génère un plan d'irrigation complet pour une zone donnée.
    
    - Récupère la configuration de la zone depuis la DB
    - Cherche la dernière recommandation MS5 pour la parcelle
    - Calcule le plan d'irrigation (sessions, volumes, dates)
    - Sauvegarde le plan en base de données
    - Retourne le plan détaillé
    """
    try:
        # 1. Récupérer la configuration de la zone
        zone = db.get_zone(zone_id)
        if not zone:
            raise HTTPException(status_code=404, detail=f"Zone {zone_id} introuvable")
        
        if not zone.active:
            raise HTTPException(status_code=400, detail=f"Zone {zone_id} désactivée")
        
        # 2. Récupérer la dernière recommandation MS5
        recommendation = get_latest_irrigation_recommendation(zone.plot_id)
        
        if not recommendation:
            raise HTTPException(
                status_code=404, 
                detail=f"Aucune recommandation d'irrigation disponible pour la parcelle {zone.plot_id}"
            )
        
        logger.info(f"Recommandation trouvée pour {zone.plot_id}: {recommendation.get('action')} (priorité: {recommendation.get('priority')})")
        
        # 3. Créer l'objet ZoneConfiguration pour le planner
        zone_config = ZoneConfiguration(
            zone_id=zone.zone_id,
            plot_id=zone.plot_id,
            area_hectares=float(zone.area_hectares),
            soil_type=zone.soil_type,
            crop_type=zone.crop_type,
            growth_stage=zone.growth_stage,
            irrigation_type=zone.irrigation_type,
            flow_rate_lpm=float(zone.flow_rate_lpm),
            equipment_name=zone.equipment_name,
            water_source=zone.water_source,
            water_cost_per_m3=float(zone.water_cost_per_m3) if zone.water_cost_per_m3 else 1.50,
            soil_moisture_current=float(zone.soil_moisture_current) if zone.soil_moisture_current else None
        )
        
        # 4. Générer le plan d'irrigation
        plan = planner.create_irrigation_plan(
            zone_config=zone_config,
            recommendation=recommendation,
            days_ahead=days_ahead
        )
        
        # 5. Sauvegarder le plan en base de données
        plan_db = IrrigationPlanDB(
            zone_id=zone_id,
            plot_id=zone.plot_id,
            valid_until=datetime.utcnow() + timedelta(days=days_ahead),
            soil_type=zone.soil_type,
            crop_type=zone.crop_type,
            growth_stage=zone.growth_stage,
            irrigation_type=zone.irrigation_type,
            total_volume_liters=float(plan.total_volume_liters),
            estimated_cost_eur=float(plan.estimated_cost_eur),
            water_source=zone.water_source,
            recommendation_source=f"MS5-{recommendation.get('source', 'unknown')}",
            notes=f"Priority: {recommendation.get('priority')} | Action: {recommendation.get('action')}"
        )
        
        plan_db = db.create_plan(plan_db.__dict__)
        plan_id = plan_db.plan_id
        
        logger.info(f"Plan {plan_id} créé pour zone {zone_id}: {len(plan.sessions)} sessions, {plan.total_volume_liters}L")
        
        # 6. Sauvegarder les sessions
        sessions_data = []
        for session in plan.sessions:
            sessions_data.append({
                "plan_id": plan_id,
                "zone_id": zone_id,
                "scheduled_date": session.date,
                "scheduled_time": session.time,
                "duration_minutes": session.duration_minutes,
                "planned_volume_liters": float(session.volume_liters),
                "flow_rate_lpm": float(zone.flow_rate_lpm),
                "equipment": zone.equipment_name,
                "status": SessionStatus.SCHEDULED.value
            })
        
        db.create_sessions(sessions_data)
        
        # 7. Logger la recommandation comme traitée
        db.log_recommendation({
            "plot_id": zone.plot_id,
            "recommendation_type": recommendation.get("type", "IRRIGATION"),
            "priority": recommendation.get("priority", "MEDIUM"),
            "action": recommendation.get("action", "IRRIGATE"),
            "details": recommendation.get("details", ""),
            "source": recommendation.get("source", "MS5-unknown"),
            "quantity": recommendation.get("quantity"),
            "unit": recommendation.get("unit"),
            "soil_moisture": recommendation.get("soil_moisture"),
            "temperature": recommendation.get("temperature"),
            "processed": True,
            "plan_id": plan_id
        })
        
        return plan
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur génération plan pour {zone_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


@app.get("/api/irrigation/plans/history")
async def get_plan_history(
    zone_id: str = Query(..., description="ID de la zone"),
    limit: int = Query(20, ge=1, le=100, description="Nombre maximum de plans")
):
    """Récupère l'historique des plans d'irrigation pour une zone"""
    try:
        plans = db.get_plan_history(zone_id, limit)
        
        result = []
        for plan in plans:
            result.append({
                "plan_id": plan.plan_id,
                "created_at": plan.created_at.isoformat(),
                "valid_until": plan.valid_until.isoformat(),
                "status": plan.status,
                "total_volume_liters": float(plan.total_volume_liters),
                "estimated_cost_eur": float(plan.estimated_cost_eur) if plan.estimated_cost_eur else None,
                "sessions_count": len(plan.sessions),
                "recommendation_source": plan.recommendation_source,
                "notes": plan.notes
            })
        
        return {
            "zone_id": zone_id,
            "total_plans": len(result),
            "plans": result
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération historique pour {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


# ========================================
# ENDPOINTS - ZONES
# ========================================

@app.get("/api/zones", response_model=List[dict])
async def get_zones(
    active_only: bool = Query(True, description="Afficher uniquement les zones actives")
):
    """Liste toutes les zones d'irrigation"""
    try:
        zones = db.get_active_zones() if active_only else db.get_session().query(Zone).all()
        
        result = []
        for zone in zones:
            result.append({
                "zone_id": zone.zone_id,
                "plot_id": zone.plot_id,
                "name": zone.name,
                "area_hectares": float(zone.area_hectares),
                "soil_type": zone.soil_type,
                "crop_type": zone.crop_type,
                "growth_stage": zone.growth_stage,
                "irrigation_type": zone.irrigation_type,
                "soil_moisture_current": float(zone.soil_moisture_current) if zone.soil_moisture_current else None,
                "last_irrigation": zone.last_irrigation.isoformat() if zone.last_irrigation else None,
                "active": zone.active
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Erreur récupération zones: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


@app.get("/api/zones/{zone_id}", response_model=dict)
async def get_zone_details(zone_id: str):
    """Détails complets d'une zone d'irrigation"""
    try:
        zone = db.get_zone(zone_id)
        if not zone:
            raise HTTPException(status_code=404, detail=f"Zone {zone_id} introuvable")
        
        # Récupérer les plans actifs
        active_plans = db.get_active_plans(zone_id)
        
        # Récupérer les sessions à venir
        upcoming_sessions = db.get_upcoming_sessions(zone_id, days=7)
        
        return {
            "zone_id": zone.zone_id,
            "plot_id": zone.plot_id,
            "name": zone.name,
            "area_hectares": float(zone.area_hectares),
            "soil_type": zone.soil_type,
            "crop_type": zone.crop_type,
            "growth_stage": zone.growth_stage,
            "planting_date": zone.planting_date.isoformat() if zone.planting_date else None,
            "irrigation_type": zone.irrigation_type,
            "flow_rate_lpm": float(zone.flow_rate_lpm),
            "equipment_name": zone.equipment_name,
            "water_source": zone.water_source,
            "water_cost_per_m3": float(zone.water_cost_per_m3),
            "soil_moisture_current": float(zone.soil_moisture_current) if zone.soil_moisture_current else None,
            "last_irrigation": zone.last_irrigation.isoformat() if zone.last_irrigation else None,
            "active": zone.active,
            "created_at": zone.created_at.isoformat(),
            "updated_at": zone.updated_at.isoformat(),
            "active_plans_count": len(active_plans),
            "upcoming_sessions_count": len(upcoming_sessions)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération zone {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


@app.post("/api/zones", response_model=dict, status_code=201)
async def create_zone(zone: ZoneConfiguration):
    """Crée une nouvelle zone d'irrigation"""
    try:
        # Vérifier si la zone existe déjà
        existing = db.get_zone(zone.zone_id)
        if existing:
            raise HTTPException(status_code=400, detail=f"Zone {zone.zone_id} existe déjà")
        
        # Créer la zone
        zone_data = zone.dict()
        zone_data["created_at"] = datetime.utcnow()
        zone_data["active"] = True
        
        new_zone = db.create_zone(zone_data)
        
        return {
            "message": "Zone créée avec succès",
            "zone_id": new_zone.zone_id,
            "created_at": new_zone.created_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur création zone: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


# ========================================
# ENDPOINTS - SESSIONS
# ========================================

@app.get("/api/sessions/upcoming")
async def get_upcoming_sessions(
    zone_id: Optional[str] = Query(None, description="ID de la zone (optionnel)"),
    days: int = Query(7, ge=1, le=30, description="Nombre de jours à venir")
):
    """Récupère les sessions d'irrigation à venir"""
    try:
        if zone_id:
            sessions = db.get_upcoming_sessions(zone_id, days)
        else:
            # Toutes les zones
            with db.get_session() as session:
                from database import IrrigationSession
                end_date = date.today() + timedelta(days=days)
                sessions = session.query(IrrigationSession).filter(
                    IrrigationSession.status == "scheduled",
                    IrrigationSession.scheduled_date <= end_date
                ).order_by(IrrigationSession.scheduled_date, IrrigationSession.scheduled_time).all()
        
        result = []
        for session in sessions:
            result.append({
                "session_id": session.session_id,
                "zone_id": session.zone_id,
                "plan_id": session.plan_id,
                "scheduled_date": session.scheduled_date.isoformat(),
                "scheduled_time": session.scheduled_time.isoformat(),
                "duration_minutes": session.duration_minutes,
                "planned_volume_liters": float(session.planned_volume_liters),
                "equipment": session.equipment,
                "status": session.status
            })
        
        return {
            "zone_id": zone_id,
            "days_ahead": days,
            "total_sessions": len(result),
            "sessions": result
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


@app.patch("/api/sessions/{session_id}/status")
async def update_session_status(
    session_id: int,
    status: SessionStatus,
    actual_volume_liters: Optional[float] = None,
    success_rate: Optional[float] = None,
    operator_notes: Optional[str] = None
):
    """Met à jour le statut d'une session d'irrigation"""
    try:
        kwargs = {}
        if actual_volume_liters is not None:
            kwargs["actual_volume_liters"] = actual_volume_liters
        if success_rate is not None:
            kwargs["success_rate"] = success_rate
        if operator_notes:
            kwargs["operator_notes"] = operator_notes
        
        db.update_session_status(session_id, status.value, **kwargs)
        
        return {
            "message": "Statut de session mis à jour",
            "session_id": session_id,
            "new_status": status.value
        }
        
    except Exception as e:
        logger.error(f"Erreur mise à jour session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


# ========================================
# ENDPOINTS - STATISTIQUES
# ========================================

@app.get("/api/statistics/zones")
async def get_zone_statistics():
    """Statistiques d'utilisation par zone"""
    try:
        with db.get_session() as session:
            result = session.execute("""
                SELECT * FROM zone_statistics
            """).fetchall()
            
            stats = []
            for row in result:
                stats.append({
                    "zone_id": row[0],
                    "name": row[1],
                    "plot_id": row[2],
                    "total_plans": row[3],
                    "active_plans": row[4],
                    "total_water_used_liters": float(row[5]) if row[5] else 0,
                    "completed_sessions": row[6],
                    "failed_sessions": row[7],
                    "avg_success_rate": float(row[8]) if row[8] else None,
                    "last_irrigation": row[9].isoformat() if row[9] else None,
                    "soil_moisture_current": float(row[10]) if row[10] else None
                })
            
            return {
                "total_zones": len(stats),
                "zones": stats
            }
            
    except Exception as e:
        logger.error(f"Erreur récupération statistiques: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


# ========================================
# POINT D'ENTRÉE
# ========================================

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"🌱 Démarrage MS6 - RecoIrrigation sur {API_HOST}:{API_PORT}")
    
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level="info"
    )
