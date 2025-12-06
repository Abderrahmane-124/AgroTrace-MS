"""
Script pour vérifier les résultats de détection
Statistiques sur les prédictions par classe
"""

from minio import Minio
import json
from collections import defaultdict
from typing import Dict, List
import config


class ResultsAnalyzer:
    """
    Analyse les résultats de détection depuis MinIO
    """
    
    def __init__(self):
        self.minio = Minio(
            config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE
        )
        
        self.results_bucket = config.MINIO_RESULTS_BUCKET
    
    def get_all_results(self) -> List[Dict]:
        """
        Récupère tous les résultats JSON depuis MinIO
        """
        print(f"🔍 Scan des résultats dans s3://{self.results_bucket}/results/")
        
        results = []
        
        objects = self.minio.list_objects(self.results_bucket, prefix="results/", recursive=True)
        
        for obj in objects:
            if obj.object_name.endswith('.json'):
                try:
                    response = self.minio.get_object(self.results_bucket, obj.object_name)
                    data = json.loads(response.read().decode('utf-8'))
                    response.close()
                    response.release_conn()
                    
                    results.append(data)
                    
                except Exception as e:
                    print(f"⚠️  Erreur lecture {obj.object_name}: {e}")
        
        print(f"✅ {len(results)} résultats chargés\n")
        
        return results
    
    def analyze_results(self, results: List[Dict]):
        """
        Analyse les résultats et affiche des statistiques
        """
        if not results:
            print("❌ Aucun résultat à analyser")
            return
        
        print(f"{'='*70}")
        print(f"  ANALYSE DES RÉSULTATS DE DÉTECTION")
        print(f"{'='*70}\n")
        
        # Statistiques globales
        total = len(results)
        
        # Par classe réelle (depuis image_path)
        by_true_class = defaultdict(list)
        
        # Par classe prédite
        by_predicted_class = defaultdict(int)
        
        # Confiances
        confidences = []
        
        # Maladies détectées
        diseased_count = 0
        
        # Temps d'inférence
        inference_times = []
        
        for result in results:
            # Classe réelle (depuis le chemin)
            image_path = result.get('image_path', '')
            if 'color/' in image_path:
                parts = image_path.split('/')
                if len(parts) >= 3:
                    true_class = parts[1]
                else:
                    true_class = "unknown"
            else:
                true_class = "unknown"
            
            # Résultats de détection
            detection = result.get('detection_results', {})
            predicted_class = detection.get('predicted_class', 'unknown')
            confidence = detection.get('confidence', 0.0)
            is_diseased = detection.get('is_diseased', False)
            
            # Temps d'inférence
            inference_time = result.get('inference_time_ms', 0)
            
            # Stocker
            by_true_class[true_class].append({
                'predicted': predicted_class,
                'confidence': confidence,
                'correct': predicted_class == true_class
            })
            
            by_predicted_class[predicted_class] += 1
            confidences.append(confidence)
            
            if is_diseased:
                diseased_count += 1
            
            inference_times.append(inference_time)
        
        # Afficher statistiques globales
        print(f"📊 STATISTIQUES GLOBALES")
        print(f"{'='*70}")
        print(f"   Total images analysées : {total}")
        print(f"   Maladies détectées : {diseased_count} ({diseased_count/total*100:.1f}%)")
        print(f"   Saines détectées : {total - diseased_count} ({(total-diseased_count)/total*100:.1f}%)")
        print(f"   Confiance moyenne : {sum(confidences)/len(confidences)*100:.2f}%")
        print(f"   Confiance min : {min(confidences)*100:.2f}%")
        print(f"   Confiance max : {max(confidences)*100:.2f}%")
        print(f"   Temps inférence moyen : {sum(inference_times)/len(inference_times):.1f}ms")
        print()
        
        # Précision par classe
        print(f"📊 PRÉCISION PAR CLASSE (TOP 10)")
        print(f"{'='*70}")
        
        accuracies = []
        
        for true_class in sorted(by_true_class.keys()):
            predictions = by_true_class[true_class]
            correct = sum(1 for p in predictions if p['correct'])
            total_class = len(predictions)
            accuracy = (correct / total_class * 100) if total_class > 0 else 0
            
            accuracies.append((true_class, accuracy, total_class, correct))
        
        # Trier par précision décroissante
        accuracies.sort(key=lambda x: x[1], reverse=True)
        
        for i, (class_name, acc, total_class, correct) in enumerate(accuracies[:10], 1):
            print(f"   {i:2d}. {class_name:40s} : {acc:5.1f}% ({correct}/{total_class})")
        
        print()
        
        # Classes les moins bien prédites
        print(f"📊 CLASSES MOINS BIEN PRÉDITES (BOTTOM 5)")
        print(f"{'='*70}")
        
        for i, (class_name, acc, total_class, correct) in enumerate(accuracies[-5:], 1):
            print(f"   {i}. {class_name:40s} : {acc:5.1f}% ({correct}/{total_class})")
        
        print()
        
        # Précision globale
        total_correct = sum(acc[3] for acc in accuracies)
        global_accuracy = (total_correct / total * 100) if total > 0 else 0
        
        print(f"📊 PRÉCISION GLOBALE")
        print(f"{'='*70}")
        print(f"   Correct : {total_correct}/{total}")
        print(f"   Précision : {global_accuracy:.2f}%")
        print()
        
        # Classes les plus prédites
        print(f"📊 CLASSES LES PLUS PRÉDITES (TOP 10)")
        print(f"{'='*70}")
        
        top_predicted = sorted(by_predicted_class.items(), key=lambda x: x[1], reverse=True)[:10]
        
        for i, (class_name, count) in enumerate(top_predicted, 1):
            print(f"   {i:2d}. {class_name:40s} : {count} prédictions")
        
        print()
        print(f"{'='*70}\n")


def main():
    """Point d'entrée"""
    print(f"\n{'#'*70}")
    print(f"  ANALYSE DES RÉSULTATS DE DÉTECTION MS3")
    print(f"{'#'*70}\n")
    
    try:
        analyzer = ResultsAnalyzer()
        results = analyzer.get_all_results()
        analyzer.analyze_results(results)
        
    except Exception as e:
        print(f"\n❌ Erreur : {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
