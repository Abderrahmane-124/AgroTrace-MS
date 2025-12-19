"""
Calculateur de plans d'irrigation personnalisés
"""
import logging
from datetime import datetime, timedelta, time, date
from typing import List, Optional
from models import (
    IrrigationPlan, IrrigationSession, ZoneConfiguration,
    RecommendationInput, SessionStatus, IrrigationType
)
from config import (
    IRRIGATION_EFFICIENCY, SOIL_WATER_RETENTION,
    EARLY_MORNING_START, EVENING_START, DEFAULT_SESSION_MAX_MINUTES
)

logger = logging.getLogger(__name__)


class IrrigationPlanner:
    """Calculateur de plans d'irrigation optimisés"""
    
    def __init__(self):
        self.efficiency = IRRIGATION_EFFICIENCY
        self.soil_retention = SOIL_WATER_RETENTION
    
    def create_plan(
        self,
        zone_config: ZoneConfiguration,
        recommendation: RecommendationInput,
        days_ahead: int = 7
    ) -> IrrigationPlan:
        """
        Crée un plan d'irrigation complet
        
        Args:
            zone_config: Configuration de la zone
            recommendation: Recommandation MS5
            days_ahead: Nombre de jours à planifier
        
        Returns:
            Plan d'irrigation détaillé
        """
        logger.info(f"Création plan irrigation pour zone {zone_config.zone_id}")
        
        # 1. Calculer le besoin en eau total
        water_need_mm = self._calculate_water_need(zone_config, recommendation)
        
        # 2. Convertir en volume (litres)
        total_volume_liters = self._convert_to_volume(
            water_need_mm,
            zone_config.area_hectares
        )
        
        # 3. Ajuster selon efficacité du système
        adjusted_volume = self._adjust_for_efficiency(
            total_volume_liters,
            zone_config.irrigation_type
        )
        
        # 4. Fractionner en sessions optimales
        sessions = self._create_sessions(
            adjusted_volume,
            zone_config,
            recommendation.priority,
            days_ahead
        )
        
        # 5. Calculer le coût
        cost = self._calculate_cost(
            adjusted_volume,
            zone_config.water_cost_per_m3
        )
        
        # 6. Créer le plan complet
        plan = IrrigationPlan(
            zone_id=zone_config.zone_id,
            plot_id=zone_config.plot_id,
            created_at=datetime.now(),
            valid_until=datetime.now() + timedelta(days=days_ahead),
            soil_type=zone_config.soil_type,
            crop_type=zone_config.crop_type,
            growth_stage=zone_config.growth_stage,
            irrigation_type=zone_config.irrigation_type,
            sessions=sessions,
            total_volume_liters=adjusted_volume,
            estimated_cost_eur=cost,
            water_source=zone_config.water_source,
            recommendation_source=f"MS5-{recommendation.source}",
            notes=f"Plan généré suite à: {recommendation.details[:100]}"
        )
        
        logger.info(f"Plan créé: {len(sessions)} sessions, {adjusted_volume:.0f}L total")
        return plan
    
    def _calculate_water_need(
        self,
        zone_config: ZoneConfiguration,
        recommendation: RecommendationInput
    ) -> float:
        """
        Calcule le besoin en eau en mm
        
        Returns:
            Besoin en eau en millimètres
        """
        # Besoin de base selon stade de croissance
        growth_stage_multipliers = {
            'germination': 0.3,
            'vegetative': 1.0,
            'flowering': 1.3,
            'fruiting': 1.5,
            'maturation': 0.8
        }
        
        base_need_mm = 30  # Base: 30mm par semaine
        stage_multiplier = growth_stage_multipliers.get(
            zone_config.growth_stage.value,
            1.0
        )
        
        # Ajustement selon humidité actuelle
        moisture_deficit = 0
        if zone_config.soil_moisture_current is not None:
            optimal_moisture = 60  # Objectif: 60%
            moisture_deficit = max(0, optimal_moisture - zone_config.soil_moisture_current)
            # 1% de déficit = 1mm d'eau nécessaire
            moisture_deficit = moisture_deficit * 0.8
        
        # Si recommandation MS5 a une quantité spécifique
        if recommendation.quantity and recommendation.unit == "L/m²":
            # Convertir L/m² en mm (1 L/m² = 1 mm)
            return recommendation.quantity
        
        # Sinon, calculer selon priorité
        priority_multipliers = {
            'URGENT': 1.5,
            'HIGH': 1.2,
            'MEDIUM': 1.0,
            'LOW': 0.8
        }
        
        priority_mult = priority_multipliers.get(recommendation.priority, 1.0)
        
        total_need_mm = (base_need_mm * stage_multiplier * priority_mult) + moisture_deficit
        
        logger.debug(f"Besoin calculé: {total_need_mm:.1f}mm "
                    f"(base: {base_need_mm}, stade: {stage_multiplier}, "
                    f"priorité: {priority_mult}, déficit: {moisture_deficit:.1f})")
        
        return total_need_mm
    
    def _convert_to_volume(self, water_need_mm: float, area_hectares: float) -> float:
        """
        Convertit besoin en mm vers volume en litres
        
        Args:
            water_need_mm: Besoin en millimètres
            area_hectares: Surface en hectares
        
        Returns:
            Volume en litres
        """
        # 1 hectare = 10,000 m²
        # 1 mm sur 1 m² = 1 litre
        area_m2 = area_hectares * 10000
        volume_liters = water_need_mm * area_m2
        
        return volume_liters
    
    def _adjust_for_efficiency(
        self,
        volume_liters: float,
        irrigation_type: IrrigationType
    ) -> float:
        """
        Ajuste le volume selon l'efficacité du système
        
        Args:
            volume_liters: Volume théorique
            irrigation_type: Type d'irrigation
        
        Returns:
            Volume ajusté (plus élevé pour compenser pertes)
        """
        efficiency = self.efficiency.get(irrigation_type.value, 0.75)
        adjusted_volume = volume_liters / efficiency
        
        logger.debug(f"Volume ajusté pour efficacité {efficiency:.0%}: "
                    f"{volume_liters:.0f}L → {adjusted_volume:.0f}L")
        
        return adjusted_volume
    
    def _create_sessions(
        self,
        total_volume: float,
        zone_config: ZoneConfiguration,
        priority: str,
        days_ahead: int
    ) -> List[IrrigationSession]:
        """
        Crée les sessions d'irrigation optimales
        
        Args:
            total_volume: Volume total à apporter
            zone_config: Configuration zone
            priority: Priorité (URGENT, HIGH, etc.)
            days_ahead: Jours à planifier
        
        Returns:
            Liste de sessions planifiées
        """
        sessions = []
        flow_rate = zone_config.flow_rate_lpm
        
        # Déterminer le nombre de sessions selon priorité et volume
        if priority == 'URGENT' or total_volume > 50000:
            # Urgent ou gros volume: fractionner en 2-3 sessions
            num_sessions = 3 if total_volume > 80000 else 2
        elif priority == 'HIGH':
            num_sessions = 2
        else:
            num_sessions = 1
        
        # Répartir le volume
        volume_per_session = total_volume / num_sessions
        
        # Planifier les sessions
        start_date = date.today()
        
        if priority == 'URGENT':
            # Commencer aujourd'hui
            time_slots = [
                self._parse_time(EVENING_START),
                self._parse_time(EARLY_MORNING_START)
            ]
            
            for i in range(num_sessions):
                session_date = start_date + timedelta(days=i // 2)
                session_time = time_slots[i % 2]
                
                duration = min(
                    int(volume_per_session / flow_rate),
                    DEFAULT_SESSION_MAX_MINUTES
                )
                
                sessions.append(IrrigationSession(
                    date=session_date,
                    time=session_time,
                    duration_minutes=duration,
                    volume_liters=volume_per_session,
                    flow_rate_lpm=flow_rate,
                    equipment=zone_config.equipment_name,
                    status=SessionStatus.SCHEDULED
                ))
        
        elif priority == 'HIGH':
            # Dans les 2 prochains jours
            for i in range(num_sessions):
                session_date = start_date + timedelta(days=i + 1)
                session_time = self._parse_time(EARLY_MORNING_START)
                
                duration = min(
                    int(volume_per_session / flow_rate),
                    DEFAULT_SESSION_MAX_MINUTES
                )
                
                sessions.append(IrrigationSession(
                    date=session_date,
                    time=session_time,
                    duration_minutes=duration,
                    volume_liters=volume_per_session,
                    flow_rate_lpm=flow_rate,
                    equipment=zone_config.equipment_name,
                    status=SessionStatus.SCHEDULED
                ))
        
        else:
            # MEDIUM/LOW: répartir sur la semaine
            interval_days = days_ahead // num_sessions
            
            for i in range(num_sessions):
                session_date = start_date + timedelta(days=(i + 1) * interval_days)
                session_time = self._parse_time(EARLY_MORNING_START)
                
                duration = min(
                    int(volume_per_session / flow_rate),
                    DEFAULT_SESSION_MAX_MINUTES
                )
                
                sessions.append(IrrigationSession(
                    date=session_date,
                    time=session_time,
                    duration_minutes=duration,
                    volume_liters=volume_per_session,
                    flow_rate_lpm=flow_rate,
                    equipment=zone_config.equipment_name,
                    status=SessionStatus.SCHEDULED
                ))
        
        logger.info(f"Créé {len(sessions)} sessions: "
                   f"{[f'{s.date} {s.time}' for s in sessions]}")
        
        return sessions
    
    def _calculate_cost(self, volume_liters: float, cost_per_m3: float) -> float:
        """
        Calcule le coût de l'irrigation
        
        Args:
            volume_liters: Volume en litres
            cost_per_m3: Coût par m³
        
        Returns:
            Coût en euros
        """
        volume_m3 = volume_liters / 1000
        cost = volume_m3 * cost_per_m3
        
        return round(cost, 2)
    
    def _parse_time(self, time_str: str) -> time:
        """Parse une heure au format HH:MM"""
        hour, minute = map(int, time_str.split(':'))
        return time(hour, minute)


# Instance globale
planner = IrrigationPlanner()
