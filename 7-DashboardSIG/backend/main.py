# ========================================
# API FastAPI DashboardSIG
# ========================================

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime
import io
import csv
import httpx

from config import API_HOST, API_PORT, RECO_IRRIGATION_API_URL
from models import (
    ParcelStatus, ParcelDetail, WaterForecast, 
    DiseaseDetection, Recommendation, DashboardStats
)
from database import (
    db_manager, init_database,
    get_all_parcels, get_parcel_detail,
    get_water_forecasts, get_disease_detections,
    get_active_recommendations, get_dashboard_stats,
    get_export_data
)
from kafka_consumer import kafka_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager pour l'application"""
    # Startup
    print("🚀 Démarrage DashboardSIG API...")
    try:
        db_manager.initialize_pool()
        init_database()
        kafka_consumer.start()
        print("✅ DashboardSIG API prêt")
    except Exception as e:
        print(f"❌ Erreur démarrage: {e}")
    
    yield
    
    # Shutdown
    print("🛑 Arrêt DashboardSIG API...")
    kafka_consumer.stop()
    db_manager.close_pool()


app = FastAPI(
    title="AgroTrace DashboardSIG API",
    description="API pour le tableau de bord SIG - Visualisation des parcelles agricoles",
    version="1.0.0",
    lifespan=lifespan
)

# CORS pour le frontend React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, spécifier les origines
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== ROUTES ====================

@app.get("/")
async def root():
    """Point d'entrée racine"""
    return {
        "service": "DashboardSIG API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "parcels": "/api/parcels",
            "forecasts": "/api/forecasts",
            "diseases": "/api/diseases",
            "recommendations": "/api/recommendations",
            "stats": "/api/stats",
            "export_csv": "/api/export/csv",
            "export_pdf": "/api/export/pdf",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """Vérification de santé"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ==================== PARCELS ====================

@app.get("/api/parcels", response_model=List[dict])
async def list_parcels():
    """
    Liste toutes les parcelles avec leur état actuel.
    Retourne les géométries au format GeoJSON pour Leaflet.
    """
    try:
        parcels = get_all_parcels()
        return parcels
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/parcels/{parcel_id}")
async def get_parcel(parcel_id: int):
    """
    Récupère le détail d'une parcelle avec son historique.
    """
    try:
        parcel = get_parcel_detail(parcel_id)
        if not parcel:
            raise HTTPException(status_code=404, detail="Parcelle non trouvée")
        return parcel
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/parcels/geojson")
async def get_parcels_geojson():
    """
    Retourne toutes les parcelles au format GeoJSON FeatureCollection.
    Prêt à être utilisé directement par Leaflet.
    """
    try:
        parcels = get_all_parcels()
        
        features = []
        for p in parcels:
            feature = {
                "type": "Feature",
                "id": p['id'],
                "geometry": p['geometry'],
                "properties": {
                    "id": p['id'],
                    "name": p['name'],
                    "culture_type": p['culture_type'],
                    "area_hectares": p['area_hectares'],
                    "health_status": p['health_status'],
                    "water_stress_level": p['water_stress_level'],
                    "soil_moisture": p['soil_moisture'],
                    "temperature": p['temperature'],
                    "disease_detected": p['disease_detected'],
                    "recommendation": p['recommendation'],
                    "last_updated": p['last_updated'].isoformat() if p['last_updated'] else None
                }
            }
            features.append(feature)
        
        return {
            "type": "FeatureCollection",
            "features": features
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== FORECASTS ====================

@app.get("/api/forecasts", response_model=List[dict])
async def list_forecasts():
    """
    Liste les prévisions hydriques actuelles.
    """
    try:
        forecasts = get_water_forecasts()
        return forecasts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== DISEASES ====================

@app.get("/api/diseases", response_model=List[dict])
async def list_diseases():
    """
    Liste les détections de maladies non résolues.
    """
    try:
        diseases = get_disease_detections()
        return diseases
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== RECOMMENDATIONS ====================

@app.get("/api/recommendations", response_model=List[dict])
async def list_recommendations():
    """
    Liste les recommandations actives.
    """
    try:
        recommendations = get_active_recommendations()
        return recommendations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== IRRIGATION PLANS (MS6) ====================

@app.get("/api/irrigation/plans/{zone_id}")
async def get_irrigation_plan(zone_id: str, days_ahead: int = 7):
    """
    Récupère le plan d'irrigation depuis MS6 RecoIrrigation.
    Proxy vers l'API MS6 pour obtenir les recommandations tactiques.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{RECO_IRRIGATION_API_URL}/api/irrigation/plan",
                params={"zone_id": zone_id, "days_ahead": days_ahead},
                timeout=10.0
            )
            if response.status_code == 200:
                return {"status": "success", "plan": response.json()}
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="Zone ou recommandation non trouvée. Assurez-vous que MS5 a généré des recommandations.")
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="MS6 RecoIrrigation timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"MS6 RecoIrrigation indisponible: {str(e)}")


@app.get("/api/irrigation/zones")
async def get_irrigation_zones():
    """
    Liste les zones d'irrigation depuis MS6.
    """
    # Zones par défaut si MS6 n'est pas disponible
    default_zones = [
        {
            "zone_id": "ZONE-NORTH-01",
            "plot_id": "PLOT-001",
            "name": "Parcelle Nord - Tomates",
            "area_hectares": 2.5,
            "soil_type": "loamy",
            "crop_type": "Tomato",
            "growth_stage": "flowering",
            "irrigation_type": "drip",
            "soil_moisture_current": 45.0,
            "active": True
        },
        {
            "zone_id": "ZONE-SOUTH-01",
            "plot_id": "PLOT-002",
            "name": "Parcelle Sud - Maïs",
            "area_hectares": 5.0,
            "soil_type": "sandy_loam",
            "crop_type": "Corn",
            "growth_stage": "vegetative",
            "irrigation_type": "sprinkler",
            "soil_moisture_current": 38.0,
            "active": True
        },
        {
            "zone_id": "ZONE-EAST-01",
            "plot_id": "PLOT-003",
            "name": "Parcelle Est - Laitue",
            "area_hectares": 1.2,
            "soil_type": "clay_loam",
            "crop_type": "Lettuce",
            "growth_stage": "vegetative",
            "irrigation_type": "drip",
            "soil_moisture_current": 55.0,
            "active": True
        }
    ]
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{RECO_IRRIGATION_API_URL}/api/zones",
                timeout=5.0
            )
            if response.status_code == 200:
                zones = response.json()
                return {"zones": zones, "source": "MS6"}
            else:
                return {"zones": default_zones, "source": "fallback"}
    except Exception as e:
        print(f"⚠️ MS6 indisponible, utilisation des zones par défaut: {e}")
        return {"zones": default_zones, "source": "fallback"}


@app.get("/api/irrigation/sessions")
async def get_irrigation_sessions(zone_id: Optional[str] = None, days: int = 7):
    """
    Récupère les sessions d'irrigation à venir depuis MS6.
    """
    try:
        async with httpx.AsyncClient() as client:
            params = {"days": days}
            if zone_id:
                params["zone_id"] = zone_id
            response = await client.get(
                f"{RECO_IRRIGATION_API_URL}/api/sessions/upcoming",
                params=params,
                timeout=5.0
            )
            if response.status_code == 200:
                return response.json()
            else:
                return {"sessions": [], "source": "fallback"}
    except Exception as e:
        print(f"⚠️ MS6 sessions indisponibles: {e}")
        return {"sessions": [], "source": "fallback"}


# ==================== STATS ====================

@app.get("/api/stats", response_model=dict)
async def get_stats():
    """
    Récupère les statistiques du tableau de bord.
    """
    try:
        stats = get_dashboard_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== EXPORT ====================

@app.get("/api/export/csv")
async def export_csv(
    parcel_ids: Optional[str] = Query(None, description="IDs des parcelles séparés par virgule")
):
    """
    Exporte les données en format CSV.
    """
    try:
        # Parser les IDs
        ids = None
        if parcel_ids:
            ids = [int(x.strip()) for x in parcel_ids.split(',')]
        
        data = get_export_data(parcel_ids=ids)
        
        # Créer le CSV
        output = io.StringIO()
        
        # Section Parcelles
        output.write("=== PARCELLES ===\n")
        if data['parcels']:
            writer = csv.DictWriter(output, fieldnames=data['parcels'][0].keys())
            writer.writeheader()
            writer.writerows(data['parcels'])
        
        output.write("\n=== RECOMMANDATIONS ===\n")
        if data['recommendations']:
            writer = csv.DictWriter(output, fieldnames=data['recommendations'][0].keys())
            writer.writeheader()
            writer.writerows(data['recommendations'])
        
        output.write("\n=== PREVISIONS ===\n")
        if data['forecasts']:
            writer = csv.DictWriter(output, fieldnames=data['forecasts'][0].keys())
            writer.writeheader()
            writer.writerows(data['forecasts'])
        
        output.seek(0)
        
        filename = f"agrotrace_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export/pdf")
async def export_pdf(
    parcel_ids: Optional[str] = Query(None, description="IDs des parcelles séparés par virgule")
):
    """
    Exporte un rapport PDF.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.units import cm
        
        # Parser les IDs
        ids = None
        if parcel_ids:
            ids = [int(x.strip()) for x in parcel_ids.split(',')]
        
        data = get_export_data(parcel_ids=ids)
        stats = get_dashboard_stats()
        
        # Créer le PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.darkgreen,
            spaceAfter=30
        )
        
        elements = []
        
        # Titre
        elements.append(Paragraph("Rapport AgroTrace - Tableau de Bord SIG", title_style))
        elements.append(Paragraph(f"Généré le: {datetime.now().strftime('%d/%m/%Y à %H:%M')}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Statistiques
        elements.append(Paragraph("Résumé", styles['Heading2']))
        stats_data = [
            ["Indicateur", "Valeur"],
            ["Total Parcelles", str(stats['total_parcels'])],
            ["Parcelles Critiques", str(stats['parcels_critical'])],
            ["Stress Élevé", str(stats['parcels_high_stress'])],
            ["Alertes Maladies", str(stats['active_disease_alerts'])],
            ["Recommandations en attente", str(stats['pending_recommendations'])],
            ["Humidité moyenne", f"{stats['avg_soil_moisture']:.1f}%"],
            ["Température moyenne", f"{stats['avg_temperature']:.1f}°C"],
        ]
        
        t = Table(stats_data, colWidths=[8*cm, 4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))
        
        # Parcelles
        elements.append(Paragraph("État des Parcelles", styles['Heading2']))
        if data['parcels']:
            parcel_data = [["ID", "Nom", "Culture", "État", "Humidité"]]
            for p in data['parcels'][:10]:  # Limiter à 10
                parcel_data.append([
                    str(p['id']),
                    str(p['name'])[:20],
                    str(p['culture_type'] or '-'),
                    str(p['health_status'] or 'HEALTHY'),
                    f"{p['soil_moisture']:.1f}%" if p['soil_moisture'] else '-'
                ])
            
            t = Table(parcel_data, colWidths=[1.5*cm, 5*cm, 3*cm, 3*cm, 2.5*cm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(t)
        
        elements.append(Spacer(1, 20))
        
        # Recommandations
        elements.append(Paragraph("Recommandations Actives", styles['Heading2']))
        if data['recommendations']:
            for r in data['recommendations'][:5]:  # Limiter à 5
                priority_color = colors.red if r['priority'] == 'CRITICAL' else colors.orange if r['priority'] == 'HIGH' else colors.black
                elements.append(Paragraph(
                    f"<b>[{r['priority']}]</b> {r['parcel_name']}: {r['description'][:100]}...",
                    styles['Normal']
                ))
                elements.append(Spacer(1, 5))
        else:
            elements.append(Paragraph("Aucune recommandation en attente.", styles['Normal']))
        
        # Construire le PDF
        doc.build(elements)
        
        buffer.seek(0)
        filename = f"agrotrace_rapport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except ImportError:
        raise HTTPException(
            status_code=501, 
            detail="Export PDF non disponible - reportlab non installé"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== MAIN ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
