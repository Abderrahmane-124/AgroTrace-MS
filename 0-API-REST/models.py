from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime

class SensorData(BaseModel):
    sensor_type: str = Field(..., description="Type du capteur")
    timestamp: str = Field(..., description="Horodatage de la mesure")
    data_index: int = Field(..., description="Index des données dans le dataset")
    measurements: Dict[str, Any] = Field(..., description="Mesures du capteur")
    
    class Config:
        json_schema_extra = {
            "example": {
                "sensor_type": "temperature_sensor",
                "timestamp": "2024-01-01T12:00:00",
                "data_index": 42,
                "measurements": {
                    "temperature": 25.5,
                    "humidity": 60.2,
                    "unit": "celsius"
                }
            }
        }

class SensorDataResponse(BaseModel):
    message: str
    data: SensorData
    received_at: str

class StatsResponse(BaseModel):
    total_received: int
    buffer_size: int
    buffer_max_size: int
    sensors_types: Dict[str, int]
    uptime_seconds: float
