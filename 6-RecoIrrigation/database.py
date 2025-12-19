"""
Database Layer - MS6 RecoIrrigation
Gestion PostgreSQL avec SQLAlchemy pour les zones, plans et sessions d'irrigation.
"""

from sqlalchemy import create_engine, Column, String, Integer, Numeric, Boolean, DateTime, Date, Time, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, date, time
from typing import Optional, List
import logging

from config import POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

# Configuration
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

logger = logging.getLogger(__name__)


# ========================================
# MODÈLES SQLAlchemy
# ========================================

class Zone(Base):
    """Table zones - Configuration d'une zone d'irrigation"""
    __tablename__ = "zones"
    
    zone_id = Column(String(50), primary_key=True)
    plot_id = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    area_hectares = Column(Numeric(10, 4), nullable=False)
    
    # Propriétés agronomiques
    soil_type = Column(String(20), nullable=False)
    crop_type = Column(String(100), nullable=False)
    growth_stage = Column(String(20), nullable=False)
    planting_date = Column(Date, nullable=True)
    
    # Équipement
    irrigation_type = Column(String(20), nullable=False)
    flow_rate_lpm = Column(Numeric(10, 2), nullable=False)
    equipment_name = Column(String(200), nullable=False)
    water_source = Column(String(200), nullable=False)
    
    # Coûts
    water_cost_per_m3 = Column(Numeric(6, 2), default=1.50)
    
    # État actuel
    last_irrigation = Column(DateTime, nullable=True)
    soil_moisture_current = Column(Numeric(5, 2), nullable=True)
    
    # Métadonnées
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active = Column(Boolean, default=True)
    
    # Relations
    irrigation_plans = relationship("IrrigationPlan", back_populates="zone")
    sessions = relationship("IrrigationSession", back_populates="zone")


class IrrigationPlan(Base):
    """Table irrigation_plans - Plan d'irrigation complet"""
    __tablename__ = "irrigation_plans"
    
    plan_id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(50), ForeignKey("zones.zone_id"), nullable=False, index=True)
    plot_id = Column(String(50), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    valid_until = Column(DateTime, nullable=False, index=True)
    
    # Contexte agronomique (snapshot)
    soil_type = Column(String(20), nullable=False)
    crop_type = Column(String(100), nullable=False)
    growth_stage = Column(String(20), nullable=False)
    irrigation_type = Column(String(20), nullable=False)
    
    # Métriques
    total_volume_liters = Column(Numeric(12, 2), nullable=False)
    estimated_cost_eur = Column(Numeric(10, 2), nullable=True)
    water_source = Column(String(200), nullable=True)
    
    # Métadonnées
    recommendation_source = Column(String(100), nullable=False)
    notes = Column(Text, nullable=True)
    can_reschedule = Column(Boolean, default=True)
    
    # Statut
    status = Column(String(20), default="active", index=True)
    
    # Relations
    zone = relationship("Zone", back_populates="irrigation_plans")
    sessions = relationship("IrrigationSession", back_populates="plan", cascade="all, delete-orphan")


class IrrigationSession(Base):
    """Table irrigation_sessions - Session d'irrigation individuelle"""
    __tablename__ = "irrigation_sessions"
    
    session_id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("irrigation_plans.plan_id", ondelete="CASCADE"), nullable=False, index=True)
    zone_id = Column(String(50), ForeignKey("zones.zone_id"), nullable=False, index=True)
    
    # Planification
    scheduled_date = Column(Date, nullable=False, index=True)
    scheduled_time = Column(Time, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    
    # Volumes et débits
    planned_volume_liters = Column(Numeric(12, 2), nullable=False)
    actual_volume_liters = Column(Numeric(12, 2), nullable=True)
    flow_rate_lpm = Column(Numeric(10, 2), nullable=False)
    
    # Équipement
    equipment = Column(String(200), nullable=False)
    
    # Exécution
    status = Column(String(20), default="scheduled", index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Feedback
    success_rate = Column(Numeric(5, 2), nullable=True)
    operator_notes = Column(Text, nullable=True)
    
    # Métadonnées
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    plan = relationship("IrrigationPlan", back_populates="sessions")
    zone = relationship("Zone", back_populates="sessions")


class RecommendationLog(Base):
    """Table recommendations_log - Historique des recommandations MS5"""
    __tablename__ = "recommendations_log"
    
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    plot_id = Column(String(50), nullable=False, index=True)
    received_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Données recommandation
    recommendation_type = Column(String(50), nullable=False)
    priority = Column(String(20), nullable=False)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    source = Column(String(50), nullable=False)
    
    # Données contextuelles
    quantity = Column(Numeric(10, 2), nullable=True)
    unit = Column(String(20), nullable=True)
    soil_moisture = Column(Numeric(5, 2), nullable=True)
    temperature = Column(Numeric(5, 2), nullable=True)
    
    # Traitement
    processed = Column(Boolean, default=False, index=True)
    plan_id = Column(Integer, ForeignKey("irrigation_plans.plan_id"), nullable=True)


# ========================================
# OPÉRATIONS CRUD
# ========================================

class DatabaseManager:
    """Gestionnaire de base de données avec opérations CRUD"""
    
    def __init__(self):
        self.engine = engine
        self.SessionLocal = SessionLocal
    
    def get_session(self):
        """Retourne une session de base de données"""
        return self.SessionLocal()
    
    # ========== ZONES ==========
    
    def get_zone(self, zone_id: str) -> Optional[Zone]:
        """Récupère une zone par ID"""
        with self.get_session() as session:
            return session.query(Zone).filter(Zone.zone_id == zone_id).first()
    
    def get_active_zones(self) -> List[Zone]:
        """Récupère toutes les zones actives"""
        with self.get_session() as session:
            return session.query(Zone).filter(Zone.active == True).all()
    
    def get_zones_by_plot(self, plot_id: str) -> List[Zone]:
        """Récupère toutes les zones d'une parcelle"""
        with self.get_session() as session:
            return session.query(Zone).filter(Zone.plot_id == plot_id, Zone.active == True).all()
    
    def create_zone(self, zone_data: dict) -> Zone:
        """Crée une nouvelle zone"""
        with self.get_session() as session:
            zone = Zone(**zone_data)
            session.add(zone)
            session.commit()
            session.refresh(zone)
            logger.info(f"Zone créée: {zone.zone_id}")
            return zone
    
    def update_zone(self, zone_id: str, updates: dict) -> Optional[Zone]:
        """Met à jour une zone existante"""
        with self.get_session() as session:
            zone = session.query(Zone).filter(Zone.zone_id == zone_id).first()
            if zone:
                for key, value in updates.items():
                    if hasattr(zone, key):
                        setattr(zone, key, value)
                session.commit()
                session.refresh(zone)
                logger.info(f"Zone mise à jour: {zone_id}")
                return zone
            return None
    
    def update_zone_moisture(self, zone_id: str, moisture: float):
        """Met à jour l'humidité du sol d'une zone"""
        with self.get_session() as session:
            zone = session.query(Zone).filter(Zone.zone_id == zone_id).first()
            if zone:
                zone.soil_moisture_current = moisture
                zone.updated_at = datetime.utcnow()
                session.commit()
    
    # ========== PLANS ==========
    
    def create_plan(self, plan_data: dict) -> IrrigationPlan:
        """Crée un nouveau plan d'irrigation"""
        with self.get_session() as session:
            plan = IrrigationPlan(**plan_data)
            session.add(plan)
            session.commit()
            session.refresh(plan)
            logger.info(f"Plan créé: {plan.plan_id} pour zone {plan.zone_id}")
            return plan
    
    def get_plan(self, plan_id: int) -> Optional[IrrigationPlan]:
        """Récupère un plan par ID"""
        with self.get_session() as session:
            return session.query(IrrigationPlan).filter(IrrigationPlan.plan_id == plan_id).first()
    
    def get_active_plans(self, zone_id: str) -> List[IrrigationPlan]:
        """Récupère tous les plans actifs pour une zone"""
        with self.get_session() as session:
            return session.query(IrrigationPlan).filter(
                IrrigationPlan.zone_id == zone_id,
                IrrigationPlan.status == "active",
                IrrigationPlan.valid_until >= datetime.utcnow()
            ).all()
    
    def get_plan_history(self, zone_id: str, limit: int = 20) -> List[IrrigationPlan]:
        """Récupère l'historique des plans pour une zone"""
        with self.get_session() as session:
            return session.query(IrrigationPlan).filter(
                IrrigationPlan.zone_id == zone_id
            ).order_by(IrrigationPlan.created_at.desc()).limit(limit).all()
    
    def update_plan_status(self, plan_id: int, status: str):
        """Met à jour le statut d'un plan"""
        with self.get_session() as session:
            plan = session.query(IrrigationPlan).filter(IrrigationPlan.plan_id == plan_id).first()
            if plan:
                plan.status = status
                session.commit()
                logger.info(f"Plan {plan_id} statut changé: {status}")
    
    # ========== SESSIONS ==========
    
    def create_sessions(self, sessions_data: List[dict]) -> List[IrrigationSession]:
        """Crée plusieurs sessions d'irrigation"""
        with self.get_session() as session:
            sessions = [IrrigationSession(**data) for data in sessions_data]
            session.bulk_save_objects(sessions, return_defaults=True)
            session.commit()
            logger.info(f"{len(sessions)} sessions créées")
            return sessions
    
    def get_upcoming_sessions(self, zone_id: str, days: int = 7) -> List[IrrigationSession]:
        """Récupère les sessions à venir pour une zone"""
        from datetime import date, timedelta
        end_date = date.today() + timedelta(days=days)
        
        with self.get_session() as session:
            return session.query(IrrigationSession).filter(
                IrrigationSession.zone_id == zone_id,
                IrrigationSession.status == "scheduled",
                IrrigationSession.scheduled_date <= end_date
            ).order_by(IrrigationSession.scheduled_date, IrrigationSession.scheduled_time).all()
    
    def update_session_status(self, session_id: int, status: str, **kwargs):
        """Met à jour le statut d'une session avec données optionnelles"""
        with self.get_session() as session:
            irrigation_session = session.query(IrrigationSession).filter(
                IrrigationSession.session_id == session_id
            ).first()
            
            if irrigation_session:
                irrigation_session.status = status
                
                if status == "in_progress":
                    irrigation_session.started_at = kwargs.get("started_at", datetime.utcnow())
                elif status == "completed":
                    irrigation_session.completed_at = kwargs.get("completed_at", datetime.utcnow())
                    irrigation_session.actual_volume_liters = kwargs.get("actual_volume_liters")
                    irrigation_session.success_rate = kwargs.get("success_rate")
                
                irrigation_session.operator_notes = kwargs.get("operator_notes")
                session.commit()
                logger.info(f"Session {session_id} statut changé: {status}")
    
    # ========== RECOMMANDATIONS LOG ==========
    
    def log_recommendation(self, reco_data: dict) -> RecommendationLog:
        """Enregistre une recommandation MS5 reçue"""
        with self.get_session() as session:
            log = RecommendationLog(**reco_data)
            session.add(log)
            session.commit()
            session.refresh(log)
            return log
    
    def mark_recommendation_processed(self, log_id: int, plan_id: int):
        """Marque une recommandation comme traitée"""
        with self.get_session() as session:
            log = session.query(RecommendationLog).filter(RecommendationLog.log_id == log_id).first()
            if log:
                log.processed = True
                log.plan_id = plan_id
                session.commit()
    
    # ========== UTILITAIRES ==========
    
    def init_db(self):
        """Initialise la base de données (crée les tables)"""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Base de données initialisée")
    
    def health_check(self) -> bool:
        """Vérifie la connexion à la base de données"""
        try:
            with self.get_session() as session:
                session.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"Health check échoué: {e}")
            return False


# Instance globale
db = DatabaseManager()
