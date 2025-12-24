# ========================================
# Modèles Pydantic pour l'API DashboardSIG
# ========================================

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from enum import Enum


class HealthStatus(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    HEALTHY = "HEALTHY"


class Coordinates(BaseModel):
    """Coordonnées GeoJSON"""
    type: str = "Polygon"
    coordinates: List[List[List[float]]]


class ParcelBase(BaseModel):
    """Modèle de base pour une parcelle"""
    id: int
    name: str
    culture_type: Optional[str] = None
    area_hectares: float
    geometry: Optional[Coordinates] = None


class ParcelStatus(ParcelBase):
    """Parcelle avec son état actuel"""
    health_status: HealthStatus = HealthStatus.HEALTHY
    water_stress_level: float = 0.0  # 0-100
    soil_moisture: Optional[float] = None
    temperature: Optional[float] = None
    last_updated: datetime
    disease_detected: Optional[str] = None
    disease_confidence: Optional[float] = None
    recommendation: Optional[str] = None


class ParcelDetail(ParcelStatus):
    """Détail complet d'une parcelle avec historique"""
    history: List[dict] = []
    forecasts: List[dict] = []
    recommendations: List[dict] = []


class WaterForecast(BaseModel):
    """Prévision hydrique"""
    id: int
    parcel_id: int
    parcel_name: str
    forecast_date: datetime
    predicted_need: float  # L/m²
    stress_level: HealthStatus
    confidence: float
    recommendation: str


class DiseaseDetection(BaseModel):
    """Détection de maladie"""
    id: int
    parcel_id: int
    parcel_name: str
    disease_name: str
    confidence: float
    detected_at: datetime
    treatment_recommendation: Optional[str] = None
    image_url: Optional[str] = None


class Recommendation(BaseModel):
    """Recommandation agronomique"""
    id: int
    parcel_id: int
    parcel_name: str
    type: str  # IRRIGATION, DISEASE_TREATMENT, FERTILIZATION
    priority: HealthStatus
    action_code: str
    description: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime] = None


class DashboardStats(BaseModel):
    """Statistiques du tableau de bord"""
    total_parcels: int
    parcels_critical: int
    parcels_high_stress: int
    parcels_moderate: int
    parcels_healthy: int
    active_disease_alerts: int
    pending_recommendations: int
    avg_soil_moisture: float
    avg_temperature: float


class ExportRequest(BaseModel):
    """Paramètres d'export"""
    parcel_ids: Optional[List[int]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    include_forecasts: bool = True
    include_recommendations: bool = True
