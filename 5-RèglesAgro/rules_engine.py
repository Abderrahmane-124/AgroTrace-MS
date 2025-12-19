"""
Moteur de règles agronomiques simple basé sur dictionnaires
Évalue les conditions et génère des recommandations
"""
import yaml
import logging
from typing import List, Dict, Any
from datetime import datetime
from config import RULES_CONFIG_FILE, PRIORITY_LEVELS

logger = logging.getLogger(__name__)


class RulesEngine:
    """Moteur d'évaluation de règles agronomiques"""
    
    def __init__(self, rules_file: str = RULES_CONFIG_FILE):
        """
        Initialise le moteur avec le fichier de configuration des règles
        
        Args:
            rules_file: Chemin vers le fichier YAML de configuration
        """
        self.rules_file = rules_file
        self.irrigation_rules = []
        self.disease_rules = []
        self.soil_rules = []
        self._load_rules()
    
    def _load_rules(self):
        """Charge les règles depuis le fichier YAML"""
        try:
            with open(self.rules_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self.irrigation_rules = config.get('irrigation_rules', [])
            self.disease_rules = config.get('disease_rules', [])
            self.soil_rules = config.get('soil_rules', [])
            
            total_rules = len(self.irrigation_rules) + len(self.disease_rules) + len(self.soil_rules)
            logger.info(f"Règles chargées: {len(self.irrigation_rules)} irrigation, "
                       f"{len(self.disease_rules)} maladies, {len(self.soil_rules)} sol (Total: {total_rules})")
        
        except Exception as e:
            logger.error(f"Erreur chargement règles: {e}")
            raise
    
    def _evaluate_condition(self, data: Dict, condition: Dict) -> bool:
        """
        Évalue une condition individuelle
        
        Args:
            data: Données d'entrée
            condition: Condition à évaluer {field, operator, value}
        
        Returns:
            True si la condition est satisfaite
        """
        field = condition['field']
        operator = condition['operator']
        expected_value = condition['value']
        
        # Récupérer la valeur du champ
        actual_value = data.get(field)
        
        if actual_value is None:
            return False
        
        # Opérateurs numériques
        if operator == 'lt':
            return actual_value < expected_value
        elif operator == 'lte':
            return actual_value <= expected_value
        elif operator == 'gt':
            return actual_value > expected_value
        elif operator == 'gte':
            return actual_value >= expected_value
        elif operator == 'eq':
            return actual_value == expected_value
        elif operator == 'ne':
            return actual_value != expected_value
        
        # Opérateurs texte
        elif operator == 'contains':
            return expected_value in str(actual_value)
        elif operator == 'startswith':
            return str(actual_value).startswith(expected_value)
        elif operator == 'endswith':
            return str(actual_value).endswith(expected_value)
        
        return False
    
    def _evaluate_conditions(self, data: Dict, conditions: Dict) -> bool:
        """
        Évalue un ensemble de conditions (all/any)
        
        Args:
            data: Données d'entrée
            conditions: Structure de conditions {all: [...]} ou {any: [...]}
        
        Returns:
            True si les conditions sont satisfaites
        """
        # Mode ALL (toutes les conditions doivent être vraies)
        if 'all' in conditions:
            return all(
                self._evaluate_condition(data, cond) 
                for cond in conditions['all']
            )
        
        # Mode ANY (au moins une condition doit être vraie)
        elif 'any' in conditions:
            return any(
                self._evaluate_condition(data, cond) 
                for cond in conditions['any']
            )
        
        return False
    
    def _create_recommendation(self, rule: Dict, data: Dict, source: str) -> Dict:
        """
        Crée une recommandation à partir d'une règle déclenchée
        
        Args:
            rule: Règle déclenchée
            data: Données ayant déclenché la règle
            source: Source des données (WATER_FORECAST, DISEASE_DETECTION, SENSOR_DATA)
        
        Returns:
            Dict de recommandation
        """
        action = rule['action']
        
        # Formater le message avec les données
        try:
            details = action['template'].format(**data)
        except KeyError as e:
            logger.warning(f"Clé manquante dans template: {e}. Utilisation template brut.")
            details = action['template']
        
        recommendation = {
            'plot_id': data.get('plot_id', 'UNKNOWN'),
            'timestamp': datetime.now().isoformat(),
            'type': action['type'],
            'priority': rule['priority'],
            'action': action['action_code'],
            'details': details,
            'source': source,
            'rule_name': rule['name']
        }
        
        # Ajouter info produit/dosage si présent
        if action.get('product'):
            recommendation['product'] = action['product']
        if action.get('dosage'):
            recommendation['dosage'] = action['dosage']
        if action.get('quantity'):
            recommendation['quantity'] = action['quantity']
        if action.get('unit'):
            recommendation['unit'] = action['unit']
        
        return recommendation
    
    def evaluate_water_forecast(self, data: Dict) -> List[Dict]:
        """
        Évalue les règles d'irrigation
        
        Args:
            data: Données de prévision d'eau
        
        Returns:
            Liste de recommandations
        """
        recommendations = []
        
        for rule in self.irrigation_rules:
            if self._evaluate_conditions(data, rule['conditions']):
                rec = self._create_recommendation(rule, data, 'WATER_FORECAST')
                recommendations.append(rec)
                logger.info(f"Règle déclenchée: {rule['name']} pour plot {data.get('plot_id')}")
        
        return self._sort_by_priority(recommendations)
    
    def evaluate_disease_detection(self, data: Dict) -> List[Dict]:
        """
        Évalue les règles de traitement des maladies
        
        Args:
            data: Données de détection de maladie
        
        Returns:
            Liste de recommandations
        """
        recommendations = []
        
        for rule in self.disease_rules:
            if self._evaluate_conditions(data, rule['conditions']):
                rec = self._create_recommendation(rule, data, 'DISEASE_DETECTION')
                recommendations.append(rec)
                logger.info(f"Règle déclenchée: {rule['name']} pour plot {data.get('plot_id')}")
        
        return self._sort_by_priority(recommendations)
    
    def evaluate_sensor_data(self, data: Dict) -> List[Dict]:
        """
        Évalue les règles d'ajustement du sol
        
        Args:
            data: Données capteurs
        
        Returns:
            Liste de recommandations
        """
        recommendations = []
        
        for rule in self.soil_rules:
            if self._evaluate_conditions(data, rule['conditions']):
                rec = self._create_recommendation(rule, data, 'SENSOR_DATA')
                recommendations.append(rec)
                logger.info(f"Règle déclenchée: {rule['name']} pour plot {data.get('plot_id')}")
        
        return self._sort_by_priority(recommendations)
    
    def _sort_by_priority(self, recommendations: List[Dict]) -> List[Dict]:
        """
        Trie les recommandations par priorité (URGENT en premier)
        
        Args:
            recommendations: Liste de recommandations
        
        Returns:
            Liste triée
        """
        return sorted(
            recommendations,
            key=lambda x: PRIORITY_LEVELS.get(x['priority'], 0),
            reverse=True
        )
    
    def reload_rules(self):
        """Recharge les règles depuis le fichier (hot reload)"""
        logger.info("Rechargement des règles...")
        self._load_rules()


# Instance globale
rules_engine = RulesEngine()
