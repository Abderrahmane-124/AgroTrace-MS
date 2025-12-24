"""
Modèles de données pour MS6 - RecoIrrigation
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date, time
from enum import Enum


class IrrigationType(str, Enum):
    """Types de systèmes d'irrigation"""
    DRIP = "drip"
    SPRINKLER = "sprinkler"
    FURROW = "furrow"
    FLOOD = "flood"


class SoilType(str, Enum):
    """Types de sol"""
    SANDY = "sandy"
    LOAMY = "loamy"
    CLAY = "clay"
    ORGANIC = "organic"


class GrowthStage(str, Enum):
    """Stades de croissance"""
    GERMINATION = "germination"
    VEGETATIVE = "vegetative"
    FLOWERING = "flowering"
    FRUITING = "fruiting"
    MATURATION = "maturation"


class SessionStatus(str, Enum):
    """Statut d'une session d'irrigation"""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class IrrigationSession(BaseModel):
    """Session d'irrigation individuelle"""
    session_date: date = Field(..., description="Date de la session")
    session_time: time = Field(..., description="Heure de début")
    duration_minutes: int = Field(..., ge=5, le=180, description="Durée en minutes")
    volume_liters: float = Field(..., ge=0, description="Volume d'eau en litres")
    flow_rate_lpm: float = Field(..., gt=0, description="Débit en L/min")
    equipment: str = Field(..., description="Équipement utilisé")
    status: SessionStatus = Field(default=SessionStatus.SCHEDULED)


class IrrigationPlan(BaseModel):
    """Plan d'irrigation complet pour une zone"""
    zone_id: str = Field(..., description="Identifiant de la zone")
    plot_id: str = Field(..., description="Identifiant de la parcelle")
    created_at: datetime = Field(default_factory=datetime.now)
    valid_until: datetime = Field(..., description="Validité du plan")
    
    # Contexte agronomique
    soil_type: SoilType
    crop_type: str
    growth_stage: GrowthStage
    irrigation_type: IrrigationType
    
    # Sessions planifiées
    sessions: List[IrrigationSession] = Field(..., min_items=1)
    
    # Métriques
    total_volume_liters: float = Field(..., ge=0)
    estimated_cost_eur: Optional[float] = Field(None, ge=0)
    water_source: Optional[str] = None
    
    # Métadonnées
    can_reschedule: bool = Field(default=True)
    notes: Optional[str] = None
    recommendation_source: str = Field(..., description="Source de la recommandation (MS5)")


class ZoneConfiguration(BaseModel):
    """Configuration d'une zone d'irrigation"""
    zone_id: str
    plot_id: str
    name: str
    area_hectares: float = Field(..., gt=0)
    
    # Propriétés agronomiques
    soil_type: SoilType
    crop_type: str
    growth_stage: GrowthStage
    planting_date: Optional[date] = None
    
    # Équipement
    irrigation_type: IrrigationType
    flow_rate_lpm: float = Field(..., gt=0)
    equipment_name: str
    water_source: str
    
    # Coûts
    water_cost_per_m3: float = Field(default=1.5, ge=0)
    
    # État actuel
    last_irrigation: Optional[datetime] = None
    soil_moisture_current: Optional[float] = Field(None, ge=0, le=100)


class RecommendationInput(BaseModel):
    """Donnée de recommandation MS5 (consommée depuis Kafka)"""
    plot_id: str
    timestamp: datetime
    type: str  # IRRIGATION, DISEASE_TREATMENT, etc.
    priority: str  # URGENT, HIGH, MEDIUM, LOW
    action: str
    details: str
    source: str
    
    # Champs optionnels spécifiques irrigation
    quantity: Optional[float] = None
    unit: Optional[str] = None
    soil_moisture: Optional[float] = None
    temperature: Optional[float] = None


class IrrigationPlanRequest(BaseModel):
    """Requête pour générer un plan d'irrigation"""
    zone_id: str = Field(..., description="ID de la zone")
    days_ahead: int = Field(default=7, ge=1, le=14, description="Nombre de jours à planifier")
    force_regenerate: bool = Field(default=False, description="Forcer la régénération même si plan existe")


class IrrigationPlanResponse(BaseModel):
    """Réponse contenant le plan d'irrigation"""
    success: bool
    message: str
    plan: Optional[IrrigationPlan] = None


class HealthResponse(BaseModel):
    """Réponse de santé de l'API"""
    status: str
    timestamp: datetime
    version: str
    kafka_connected: bool
    database_connected: bool
