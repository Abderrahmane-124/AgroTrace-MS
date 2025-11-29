from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from collections import deque
from datetime import datetime
import time
import config
from models import SensorData, SensorDataResponse, StatsResponse

# Initialisation de l'application FastAPI
app = FastAPI(
    title="AgroTrace - API REST Capteurs IoT",
    description="API REST pour la réception et la distribution des données de capteurs IoT",
    version="1.0.0"
)

# Configuration CORS pour permettre les requêtes cross-origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Buffer circulaire pour stocker les dernières données reçues
sensor_data_buffer = deque(maxlen=config.MAX_BUFFER_SIZE)

# Statistiques
stats = {
    "total_received": 0,
    "sensors_count": {},
    "start_time": time.time()
}

@app.get("/", tags=["Root"])
async def root():
    """Point d'entrée de l'API"""
    return {
        "service": "AgroTrace API REST",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "POST /api/sensor-data": "Recevoir des données de capteurs",
            "GET /api/sensor-data": "Récupérer les dernières données",
            "GET /api/stats": "Statistiques du service"
        }
    }

@app.post("/api/sensor-data", 
          response_model=SensorDataResponse, 
          status_code=status.HTTP_201_CREATED,
          tags=["Sensor Data"])
async def receive_sensor_data(data: SensorData):
    """
    Reçoit les données d'un capteur IoT
    
    - **sensor_type**: Type du capteur
    - **timestamp**: Horodatage de la mesure
    - **data_index**: Index des données
    - **measurements**: Dictionnaire des mesures
    """
    try:
        # Ajouter timestamp de réception
        received_at = datetime.now().isoformat()
        
        # Stocker dans le buffer
        sensor_data_buffer.append({
            "data": data.model_dump(),
            "received_at": received_at
        })
        
        # Mettre à jour les statistiques
        stats["total_received"] += 1
        sensor_type = data.sensor_type
        stats["sensors_count"][sensor_type] = stats["sensors_count"].get(sensor_type, 0) + 1
        
        return SensorDataResponse(
            message="Données reçues avec succès",
            data=data,
            received_at=received_at
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du traitement des données: {str(e)}"
        )

@app.get("/api/sensor-data", tags=["Sensor Data"])
async def get_sensor_data(limit: int = 1):
    """
    Récupère les dernières données de capteurs
    
    - **limit**: Nombre de données à récupérer (par défaut: 1, max: 100)
    """
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le paramètre 'limit' doit être entre 1 et 100"
        )
    
    if not sensor_data_buffer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune donnée disponible"
        )
    
    # Récupérer les dernières données
    data_list = list(sensor_data_buffer)[-limit:]
    
    # Si limit=1, retourner un seul objet, sinon une liste
    if limit == 1:
        return data_list[-1]["data"]
    else:
        return {
            "count": len(data_list),
            "data": [item["data"] for item in data_list]
        }

@app.get("/api/stats", response_model=StatsResponse, tags=["Statistics"])
async def get_statistics():
    """Récupère les statistiques du service"""
    uptime = time.time() - stats["start_time"]
    
    return StatsResponse(
        total_received=stats["total_received"],
        buffer_size=len(sensor_data_buffer),
        buffer_max_size=config.MAX_BUFFER_SIZE,
        sensors_types=stats["sensors_count"],
        uptime_seconds=round(uptime, 2)
    )

@app.delete("/api/sensor-data", tags=["Sensor Data"])
async def clear_buffer():
    """Vide le buffer de données"""
    sensor_data_buffer.clear()
    return {
        "message": "Buffer vidé avec succès",
        "buffer_size": len(sensor_data_buffer)
    }

@app.on_event("startup")
async def startup_event():
    """Événement au démarrage de l'application"""
    print("="*70)
    print("🚀 API REST AgroTrace - Démarrage")
    print("="*70)
    print(f"📍 Host: {config.HOST}")
    print(f"🔌 Port: {config.PORT}")
    print(f"💾 Taille buffer: {config.MAX_BUFFER_SIZE}")
    print("="*70)
    print(f"📚 Documentation: http://localhost:{config.PORT}/docs")
    print(f"📋 ReDoc: http://localhost:{config.PORT}/redoc")
    print("="*70)

@app.on_event("shutdown")
async def shutdown_event():
    """Événement à l'arrêt de l'application"""
    print("\n" + "="*70)
    print("🛑 Arrêt de l'API REST AgroTrace")
    print("="*70)
    print(f"📊 Total données reçues: {stats['total_received']}")
    print(f"📦 Données en buffer: {len(sensor_data_buffer)}")
    print("="*70 + "\n")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
        log_level="info"
    )
