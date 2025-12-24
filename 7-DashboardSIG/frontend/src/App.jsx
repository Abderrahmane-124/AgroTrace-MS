import { useState, useEffect } from 'react'
import { MapContainer, Polygon, Popup, Rectangle } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

// API Base URL
const API_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8085'
    : '/api';

// Couleurs par statut
const statusColors = {
    CRITICAL: '#d62828',
    HIGH: '#f77f00',
    MODERATE: '#fcbf49',
    LOW: '#90be6d',
    HEALTHY: '#43aa8b'
};

// Couleurs pour les types de culture
const cultureColors = {
    Tomato: '#e63946',
    Corn: '#f4a261',
    Lettuce: '#2a9d8f',
    default: '#457b9d'
};

// Zones d'irrigation par défaut (données fictives)
const DEFAULT_ZONES = [
    {
        zone_id: 'ZONE-NORTH-01',
        name: 'Parcelle Nord - Tomates',
        crop_type: 'Tomato',
        growth_stage: 'flowering',
        area_hectares: 2.5,
        soil_moisture_current: 45,
        irrigation_type: 'drip',
        water_source: 'Puits #1',
        color: '#e63946',
        bounds: [[-0.3, -0.6], [0.3, -0.1]]
    },
    {
        zone_id: 'ZONE-SOUTH-01',
        name: 'Parcelle Sud - Maïs',
        crop_type: 'Corn',
        growth_stage: 'vegetative',
        area_hectares: 5.0,
        soil_moisture_current: 38,
        irrigation_type: 'sprinkler',
        water_source: 'Réservoir principal',
        color: '#f4a261',
        bounds: [[-0.3, 0.1], [0.3, 0.6]]
    },
    {
        zone_id: 'ZONE-EAST-01',
        name: 'Parcelle Est - Laitue',
        crop_type: 'Lettuce',
        growth_stage: 'vegetative',
        area_hectares: 1.2,
        soil_moisture_current: 55,
        irrigation_type: 'drip',
        water_source: 'Puits #2',
        color: '#2a9d8f',
        bounds: [[-0.6, -0.25], [-0.35, 0.25]]
    }
];

// Pagination
const ITEMS_PER_PAGE = 10;

function App() {
    const [stats, setStats] = useState({
        total_parcels: 3,
        parcels_critical: 0,
        parcels_high_stress: 0,
        parcels_healthy: 3,
        avg_soil_moisture: 46,
        avg_temperature: 22,
        pending_recommendations: 0,
        active_disease_alerts: 0
    });
    const [recommendations, setRecommendations] = useState([]);
    const [diseases, setDiseases] = useState([]);
    const [irrigationZones, setIrrigationZones] = useState(DEFAULT_ZONES);
    const [irrigationSessions, setIrrigationSessions] = useState([]);
    const [activeTab, setActiveTab] = useState('overview');
    const [loading, setLoading] = useState(true);
    const [selectedZone, setSelectedZone] = useState(null);
    const [selectedItem, setSelectedItem] = useState(null);

    // Pagination states
    const [alertsPage, setAlertsPage] = useState(1);
    const [actionsPage, setActionsPage] = useState(1);

    // Charger les données
    useEffect(() => {
        loadData();
        const interval = setInterval(loadData, 30000);
        return () => clearInterval(interval);
    }, []);

    const loadData = async () => {
        try {
            const results = await Promise.allSettled([
                fetch(`${API_URL}/api/stats`),
                fetch(`${API_URL}/api/recommendations`),
                fetch(`${API_URL}/api/diseases`),
                fetch(`${API_URL}/api/irrigation/zones`),
                fetch(`${API_URL}/api/irrigation/sessions`)
            ]);

            // Stats - avec fallback
            if (results[0].status === 'fulfilled' && results[0].value.ok) {
                const data = await results[0].value.json();
                if (data && typeof data === 'object') {
                    setStats(prev => ({ ...prev, ...data }));
                }
            }

            // Recommendations - trier par date, plus récent d'abord
            if (results[1].status === 'fulfilled' && results[1].value.ok) {
                const data = await results[1].value.json();
                const sorted = (Array.isArray(data) ? data : []).sort((a, b) =>
                    new Date(b.created_at || b.timestamp || 0) - new Date(a.created_at || a.timestamp || 0)
                );
                setRecommendations(sorted);
            }

            // Diseases - trier par date, plus récent d'abord
            if (results[2].status === 'fulfilled' && results[2].value.ok) {
                const data = await results[2].value.json();
                const sorted = (Array.isArray(data) ? data : []).sort((a, b) =>
                    new Date(b.detected_at || b.timestamp || 0) - new Date(a.detected_at || a.timestamp || 0)
                );
                setDiseases(sorted);
            }

            // Irrigation zones - utiliser les données par défaut si erreur
            if (results[3].status === 'fulfilled' && results[3].value.ok) {
                const data = await results[3].value.json();
                const zones = data.zones || data || [];
                if (Array.isArray(zones) && zones.length > 0) {
                    const zonesWithBounds = zones.map((zone, i) => ({
                        ...zone,
                        color: cultureColors[zone.crop_type] || cultureColors.default,
                        bounds: DEFAULT_ZONES[i]?.bounds || [[-0.2 + i * 0.3, -0.5], [0.2 + i * 0.3, 0.5]]
                    }));
                    setIrrigationZones(zonesWithBounds);
                }
            }

            // Sessions
            if (results[4].status === 'fulfilled' && results[4].value.ok) {
                const data = await results[4].value.json();
                const sessions = data.sessions || data || [];
                if (Array.isArray(sessions)) {
                    setIrrigationSessions(sessions);
                }
            }
        } catch (error) {
            console.error('Erreur chargement données:', error);
        } finally {
            setLoading(false);
        }
    };

    // Générer un plan d'irrigation pour une zone
    const generateIrrigationPlan = async (zoneId) => {
        try {
            const response = await fetch(`${API_URL}/api/irrigation/plans/${zoneId}?days_ahead=7`);
            if (response.ok) {
                const plan = await response.json();
                alert(`✅ Plan généré!\n\nZone: ${zoneId}\nVolume total: ${plan.plan?.total_volume_liters?.toFixed(0) || 'N/A'} L\nSessions: ${plan.plan?.sessions?.length || 0}`);
                loadData();
            } else {
                const error = await response.json().catch(() => ({}));
                alert(`❌ Erreur: ${error.detail || 'MS6 non disponible - Reconstruisez le backend'}`);
            }
        } catch (error) {
            console.error('Erreur génération plan:', error);
            alert('❌ Erreur de connexion à MS6 - Vérifiez que les services sont démarrés');
        }
    };

    // Export CSV
    const exportCSV = () => window.open(`${API_URL}/api/export/csv`, '_blank');
    const exportPDF = () => window.open(`${API_URL}/api/export/pdf`, '_blank');

    // Obtenir le statut d'humidité
    const getMoistureStatus = (moisture) => {
        if (moisture < 30) return { status: 'critical', label: 'Critique', icon: '🔴' };
        if (moisture < 45) return { status: 'warning', label: 'Bas', icon: '🟡' };
        if (moisture < 60) return { status: 'good', label: 'Optimal', icon: '🟢' };
        return { status: 'high', label: 'Élevé', icon: '🔵' };
    };

    // Pagination helpers
    const paginateArray = (array, page) => {
        const start = (page - 1) * ITEMS_PER_PAGE;
        return array.slice(start, start + ITEMS_PER_PAGE);
    };

    const getTotalPages = (array) => Math.ceil(array.length / ITEMS_PER_PAGE);

    // Click handler pour items
    const handleItemClick = (item, type) => {
        setSelectedItem({ ...item, itemType: type });
    };

    // Fermer le detail panel
    const closeDetailPanel = () => setSelectedItem(null);

    return (
        <div className="app">
            {/* Header */}
            <header className="header">
                <div className="header-left">
                    <h1>🌱 AgroTrace Dashboard</h1>
                    <span className="header-subtitle">Ferme Intelligente</span>
                </div>
                <div className="export-buttons">
                    <button className="btn btn-secondary" onClick={exportCSV}>📊 CSV</button>
                    <button className="btn btn-primary" onClick={exportPDF}>📄 PDF</button>
                </div>
            </header>

            <div className="main-content">
                {/* Sidebar */}
                <aside className="sidebar">
                    <div className="sidebar-tabs">
                        <button
                            className={`sidebar-tab ${activeTab === 'overview' ? 'active' : ''}`}
                            onClick={() => setActiveTab('overview')}
                        >
                            📊 Résumé
                        </button>
                        <button
                            className={`sidebar-tab ${activeTab === 'irrigation' ? 'active' : ''}`}
                            onClick={() => setActiveTab('irrigation')}
                        >
                            💧 Irrigation
                        </button>
                        <button
                            className={`sidebar-tab ${activeTab === 'alerts' ? 'active' : ''}`}
                            onClick={() => setActiveTab('alerts')}
                        >
                            ⚠️ Alertes ({diseases.length})
                        </button>
                        <button
                            className={`sidebar-tab ${activeTab === 'actions' ? 'active' : ''}`}
                            onClick={() => setActiveTab('actions')}
                        >
                            📋 Actions ({recommendations.length})
                        </button>
                    </div>

                    <div className="sidebar-content">
                        {loading ? (
                            <div className="loading"><div className="spinner"></div></div>
                        ) : (
                            <>
                                {/* Vue d'ensemble */}
                                {activeTab === 'overview' && (
                                    <>
                                        <div className="stats-grid">
                                            <div className="stat-card">
                                                <div className="stat-value">{irrigationZones.length}</div>
                                                <div className="stat-label">Zones</div>
                                            </div>
                                            <div className={`stat-card ${diseases.length > 0 ? 'critical' : ''}`}>
                                                <div className="stat-value">{diseases.length}</div>
                                                <div className="stat-label">Maladies</div>
                                            </div>
                                            <div className={`stat-card ${recommendations.filter(r => r.priority === 'CRITICAL').length > 0 ? 'warning' : ''}`}>
                                                <div className="stat-value">{recommendations.length}</div>
                                                <div className="stat-label">Actions</div>
                                            </div>
                                            <div className="stat-card">
                                                <div className="stat-value">{irrigationSessions.length}</div>
                                                <div className="stat-label">Sessions</div>
                                            </div>
                                        </div>

                                        <div className="stats-grid">
                                            <div className="stat-card">
                                                <div className="stat-value">
                                                    {(irrigationZones.reduce((sum, z) => sum + (z.soil_moisture_current || 0), 0) / irrigationZones.length || 0).toFixed(0)}%
                                                </div>
                                                <div className="stat-label">Humidité moy.</div>
                                            </div>
                                            <div className="stat-card">
                                                <div className="stat-value">
                                                    {irrigationZones.reduce((sum, z) => sum + (z.area_hectares || 0), 0).toFixed(1)} ha
                                                </div>
                                                <div className="stat-label">Surface totale</div>
                                            </div>
                                        </div>

                                        {/* Zones rapide */}
                                        <div className="list-section">
                                            <h3>🌿 Zones d'irrigation</h3>
                                            {irrigationZones.map((zone, i) => {
                                                const moistureStatus = getMoistureStatus(zone.soil_moisture_current || 50);
                                                return (
                                                    <div
                                                        key={i}
                                                        className={`list-item clickable ${moistureStatus.status}`}
                                                        onClick={() => {
                                                            setSelectedZone(zone.zone_id);
                                                            setActiveTab('irrigation');
                                                        }}
                                                    >
                                                        <div className="list-item-header">
                                                            <span className="list-item-title">{zone.name}</span>
                                                            <span className={`list-item-badge ${moistureStatus.status}`}>
                                                                {moistureStatus.icon} {zone.soil_moisture_current?.toFixed(0) || '-'}%
                                                            </span>
                                                        </div>
                                                        <div className="list-item-desc">
                                                            {zone.crop_type} • {zone.growth_stage} • {zone.area_hectares} ha
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>

                                        {/* Dernières alertes */}
                                        {diseases.length > 0 && (
                                            <div className="list-section">
                                                <h3>🦠 Dernières alertes</h3>
                                                {diseases.slice(0, 3).map((d, i) => (
                                                    <div
                                                        key={i}
                                                        className="list-item clickable critical"
                                                        onClick={() => handleItemClick(d, 'disease')}
                                                    >
                                                        <div className="list-item-header">
                                                            <span className="list-item-title">{d.parcel_name || `Parcelle ${d.parcel_id}`}</span>
                                                            <span className="list-item-badge critical">
                                                                {((d.confidence || 0) * 100).toFixed(0)}%
                                                            </span>
                                                        </div>
                                                        <div className="list-item-desc">{d.disease_name}</div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </>
                                )}

                                {/* Irrigation Tab */}
                                {activeTab === 'irrigation' && (
                                    <>
                                        <div className="list-section">
                                            <h3>🌿 Zones d'irrigation ({irrigationZones.length})</h3>
                                            {irrigationZones.map((zone, i) => {
                                                const moistureStatus = getMoistureStatus(zone.soil_moisture_current || 50);
                                                const isSelected = selectedZone === zone.zone_id;
                                                return (
                                                    <div
                                                        key={i}
                                                        className={`list-item irrigation-zone clickable ${isSelected ? 'selected' : ''} ${moistureStatus.status}`}
                                                        onClick={() => setSelectedZone(isSelected ? null : zone.zone_id)}
                                                    >
                                                        <div className="list-item-header">
                                                            <span className="list-item-title">{zone.name}</span>
                                                            <span className={`list-item-badge ${moistureStatus.status}`}>
                                                                {moistureStatus.icon} {zone.soil_moisture_current?.toFixed(0) || '-'}%
                                                            </span>
                                                        </div>
                                                        <div className="list-item-desc">
                                                            <strong>Culture:</strong> {zone.crop_type}<br />
                                                            <strong>Stade:</strong> {zone.growth_stage}<br />
                                                            <strong>Surface:</strong> {zone.area_hectares} ha<br />
                                                            <strong>Type:</strong> {zone.irrigation_type}
                                                        </div>
                                                        <button
                                                            className="btn btn-small btn-primary"
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                generateIrrigationPlan(zone.zone_id);
                                                            }}
                                                        >
                                                            💧 Générer Plan
                                                        </button>
                                                    </div>
                                                );
                                            })}
                                        </div>

                                        <div className="list-section">
                                            <h3>📅 Sessions planifiées ({irrigationSessions.length})</h3>
                                            {irrigationSessions.length === 0 ? (
                                                <div className="empty-state">
                                                    <div className="empty-state-icon">📅</div>
                                                    <p>Aucune session planifiée</p>
                                                    <small>Cliquez sur "Générer Plan" pour créer des sessions</small>
                                                </div>
                                            ) : (
                                                irrigationSessions.slice(0, 5).map((session, i) => (
                                                    <div key={i} className={`list-item ${session.status}`}>
                                                        <div className="list-item-header">
                                                            <span className="list-item-title">
                                                                {session.scheduled_date} {session.scheduled_time?.substring(0, 5)}
                                                            </span>
                                                            <span className={`list-item-badge ${session.status}`}>
                                                                {session.status}
                                                            </span>
                                                        </div>
                                                        <div className="list-item-desc">
                                                            Zone: {session.zone_id}<br />
                                                            Volume: {session.planned_volume_liters?.toFixed(0)} L
                                                        </div>
                                                    </div>
                                                ))
                                            )}
                                        </div>
                                    </>
                                )}

                                {/* Alertes avec pagination */}
                                {activeTab === 'alerts' && (
                                    <div className="list-section">
                                        <div className="list-header">
                                            <h3>🦠 Maladies ({diseases.length})</h3>
                                            {getTotalPages(diseases) > 1 && (
                                                <div className="pagination">
                                                    <button
                                                        className="btn-page"
                                                        disabled={alertsPage === 1}
                                                        onClick={() => setAlertsPage(p => p - 1)}
                                                    >←</button>
                                                    <span>{alertsPage}/{getTotalPages(diseases)}</span>
                                                    <button
                                                        className="btn-page"
                                                        disabled={alertsPage === getTotalPages(diseases)}
                                                        onClick={() => setAlertsPage(p => p + 1)}
                                                    >→</button>
                                                </div>
                                            )}
                                        </div>

                                        {diseases.length === 0 ? (
                                            <div className="empty-state">
                                                <div className="empty-state-icon">🌿</div>
                                                <p>Aucune maladie détectée</p>
                                            </div>
                                        ) : (
                                            paginateArray(diseases, alertsPage).map((d, i) => (
                                                <div
                                                    key={i}
                                                    className="list-item clickable critical"
                                                    onClick={() => handleItemClick(d, 'disease')}
                                                >
                                                    <div className="list-item-header">
                                                        <span className="list-item-title">{d.parcel_name || `Parcelle ${d.parcel_id}`}</span>
                                                        <span className="list-item-badge critical">
                                                            {((d.confidence || 0) * 100).toFixed(0)}%
                                                        </span>
                                                    </div>
                                                    <div className="list-item-content">
                                                        <div className="list-item-text">
                                                            <strong>{d.disease_name}</strong>
                                                            {d.treatment_recommendation && (
                                                                <p className="treatment">{d.treatment_recommendation}</p>
                                                            )}
                                                        </div>
                                                        {d.image_url && (
                                                            <img
                                                                src={d.image_url}
                                                                alt={d.disease_name}
                                                                className="disease-thumbnail"
                                                                onError={(e) => e.target.style.display = 'none'}
                                                            />
                                                        )}
                                                    </div>
                                                    <div className="list-item-meta">
                                                        {d.detected_at && new Date(d.detected_at).toLocaleString('fr-FR')}
                                                    </div>
                                                </div>
                                            ))
                                        )}
                                    </div>
                                )}

                                {/* Actions avec pagination */}
                                {activeTab === 'actions' && (
                                    <div className="list-section">
                                        <div className="list-header">
                                            <h3>📋 Recommandations ({recommendations.length})</h3>
                                            {getTotalPages(recommendations) > 1 && (
                                                <div className="pagination">
                                                    <button
                                                        className="btn-page"
                                                        disabled={actionsPage === 1}
                                                        onClick={() => setActionsPage(p => p - 1)}
                                                    >←</button>
                                                    <span>{actionsPage}/{getTotalPages(recommendations)}</span>
                                                    <button
                                                        className="btn-page"
                                                        disabled={actionsPage === getTotalPages(recommendations)}
                                                        onClick={() => setActionsPage(p => p + 1)}
                                                    >→</button>
                                                </div>
                                            )}
                                        </div>

                                        {recommendations.length === 0 ? (
                                            <div className="empty-state">
                                                <div className="empty-state-icon">✅</div>
                                                <p>Aucune action en attente</p>
                                            </div>
                                        ) : (
                                            paginateArray(recommendations, actionsPage).map((rec, i) => (
                                                <div
                                                    key={i}
                                                    className={`list-item clickable ${(rec.priority || 'medium').toLowerCase()}`}
                                                    onClick={() => handleItemClick(rec, 'recommendation')}
                                                >
                                                    <div className="list-item-header">
                                                        <span className="list-item-title">{rec.parcel_name || `Parcelle ${rec.parcel_id}`}</span>
                                                        <span className={`list-item-badge ${(rec.priority || 'medium').toLowerCase()}`}>
                                                            {rec.priority || 'MEDIUM'}
                                                        </span>
                                                    </div>
                                                    <div className="list-item-desc">
                                                        <strong>{rec.type || rec.action_code || 'Action'}</strong>
                                                        <p>{rec.description || rec.action || rec.details || 'Voir les détails'}</p>
                                                        {rec.quantity && (
                                                            <em>Dose: {rec.quantity} {rec.unit}</em>
                                                        )}
                                                    </div>
                                                    <div className="list-item-meta">
                                                        {rec.created_at && new Date(rec.created_at).toLocaleString('fr-FR')}
                                                    </div>
                                                </div>
                                            ))
                                        )}
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </aside>

                {/* Map - Zone fictive plein écran */}
                <div className="map-container">
                    <MapContainer
                        bounds={[[-0.8, -0.8], [0.5, 0.8]]}
                        style={{ height: '100%', width: '100%' }}
                        zoomControl={true}
                        scrollWheelZoom={true}
                        dragging={true}
                    >
                        {/* Fond de carte fictif vert foncé */}
                        <Rectangle
                            bounds={[[-2, -3], [2, 3]]}
                            pathOptions={{
                                fillColor: '#1a472a',
                                fillOpacity: 1,
                                stroke: false
                            }}
                        />

                        {/* Grille de fond */}
                        {[-0.5, 0, 0.5].map(lng => (
                            <Rectangle
                                key={`v${lng}`}
                                bounds={[[-1, lng - 0.005], [1, lng + 0.005]]}
                                pathOptions={{ fillColor: '#2d5a3d', fillOpacity: 0.3, stroke: false }}
                            />
                        ))}
                        {[-0.5, 0, 0.5].map(lat => (
                            <Rectangle
                                key={`h${lat}`}
                                bounds={[[lat - 0.005, -1], [lat + 0.005, 1]]}
                                pathOptions={{ fillColor: '#2d5a3d', fillOpacity: 0.3, stroke: false }}
                            />
                        ))}

                        {/* Polygones des zones d'irrigation */}
                        {irrigationZones.map((zone) => (
                            <Rectangle
                                key={zone.zone_id}
                                bounds={zone.bounds}
                                pathOptions={{
                                    fillColor: zone.color,
                                    fillOpacity: selectedZone === zone.zone_id ? 0.9 : 0.7,
                                    weight: selectedZone === zone.zone_id ? 4 : 2,
                                    color: selectedZone === zone.zone_id ? '#fff' : zone.color,
                                    opacity: 1
                                }}
                                eventHandlers={{
                                    click: () => {
                                        setSelectedZone(zone.zone_id);
                                        setActiveTab('irrigation');
                                    }
                                }}
                            >
                                <Popup>
                                    <div className="popup-content">
                                        <h3>{zone.name}</h3>
                                        <div className="popup-info">
                                            <span><strong>Zone ID:</strong> {zone.zone_id}</span>
                                            <span><strong>Culture:</strong> {zone.crop_type}</span>
                                            <span><strong>Stade:</strong> {zone.growth_stage}</span>
                                            <span><strong>Surface:</strong> {zone.area_hectares} ha</span>
                                            <span><strong>Humidité:</strong> {zone.soil_moisture_current?.toFixed(1) || '-'}%</span>
                                            <span><strong>Irrigation:</strong> {zone.irrigation_type}</span>
                                        </div>
                                        <button
                                            className="btn btn-primary popup-btn"
                                            onClick={() => generateIrrigationPlan(zone.zone_id)}
                                        >
                                            💧 Générer Plan
                                        </button>
                                    </div>
                                </Popup>
                            </Rectangle>
                        ))}
                    </MapContainer>

                    {/* Légende */}
                    <div className="map-legend">
                        <h4>🗺️ Ferme AgroTrace</h4>
                        {irrigationZones.map(zone => (
                            <div
                                key={zone.zone_id}
                                className={`legend-item ${selectedZone === zone.zone_id ? 'selected' : ''}`}
                                onClick={() => setSelectedZone(zone.zone_id)}
                            >
                                <span className="legend-color" style={{ backgroundColor: zone.color }}></span>
                                {zone.crop_type} ({zone.area_hectares} ha)
                            </div>
                        ))}
                    </div>

                    {/* Info zone */}
                    <div className="map-info">
                        <span>🌾 Zone Agricole Fictive</span>
                        <span>•</span>
                        <span>{irrigationZones.length} parcelles</span>
                        <span>•</span>
                        <span>{irrigationZones.reduce((s, z) => s + (z.area_hectares || 0), 0).toFixed(1)} ha total</span>
                    </div>
                </div>

                {/* Detail Panel */}
                {selectedItem && (
                    <div className="detail-panel">
                        <div className="detail-header">
                            <h3>{selectedItem.itemType === 'disease' ? '🦠 Détail Maladie' : '📋 Détail Action'}</h3>
                            <button className="btn-close" onClick={closeDetailPanel}>✕</button>
                        </div>
                        <div className="detail-content">
                            {selectedItem.itemType === 'disease' ? (
                                <>
                                    <div className="detail-row">
                                        <strong>Parcelle:</strong>
                                        <span>{selectedItem.parcel_name || `Parcelle ${selectedItem.parcel_id}`}</span>
                                    </div>
                                    <div className="detail-row">
                                        <strong>Maladie:</strong>
                                        <span>{selectedItem.disease_name}</span>
                                    </div>
                                    <div className="detail-row">
                                        <strong>Confiance:</strong>
                                        <span className="confidence-bar">
                                            <span
                                                className="confidence-fill"
                                                style={{ width: `${(selectedItem.confidence || 0) * 100}%` }}
                                            ></span>
                                            {((selectedItem.confidence || 0) * 100).toFixed(1)}%
                                        </span>
                                    </div>
                                    <div className="detail-row">
                                        <strong>Traitement:</strong>
                                        <span>{selectedItem.treatment_recommendation || 'Consulter un agronome'}</span>
                                    </div>
                                    {selectedItem.image_url && (
                                        <div className="detail-image">
                                            <strong>Image:</strong>
                                            <img
                                                src={selectedItem.image_url}
                                                alt={selectedItem.disease_name}
                                                onError={(e) => {
                                                    e.target.style.display = 'none';
                                                    e.target.nextSibling.style.display = 'block';
                                                }}
                                            />
                                            <p className="image-fallback" style={{ display: 'none' }}>
                                                Image non disponible: {selectedItem.image_url}
                                            </p>
                                        </div>
                                    )}
                                    {selectedItem.detected_at && (
                                        <div className="detail-row">
                                            <strong>Détecté le:</strong>
                                            <span>{new Date(selectedItem.detected_at).toLocaleString('fr-FR')}</span>
                                        </div>
                                    )}
                                </>
                            ) : (
                                <>
                                    <div className="detail-row">
                                        <strong>Parcelle:</strong>
                                        <span>{selectedItem.parcel_name || `Parcelle ${selectedItem.parcel_id}`}</span>
                                    </div>
                                    <div className="detail-row">
                                        <strong>Type:</strong>
                                        <span>{selectedItem.type || selectedItem.action_code || 'Action'}</span>
                                    </div>
                                    <div className="detail-row">
                                        <strong>Priorité:</strong>
                                        <span className={`priority-badge priority-${(selectedItem.priority || 'medium').toLowerCase()}`}>
                                            {selectedItem.priority || 'MEDIUM'}
                                        </span>
                                    </div>
                                    <div className="detail-row">
                                        <strong>Action:</strong>
                                        <span>{selectedItem.action || selectedItem.action_code || 'Non spécifié'}</span>
                                    </div>
                                    <div className="detail-row full-width">
                                        <strong>Description:</strong>
                                        <p>{selectedItem.description || selectedItem.details || 'Aucune description disponible'}</p>
                                    </div>
                                    {selectedItem.quantity && (
                                        <div className="detail-row">
                                            <strong>Dose:</strong>
                                            <span>{selectedItem.quantity} {selectedItem.unit}</span>
                                        </div>
                                    )}
                                    {selectedItem.created_at && (
                                        <div className="detail-row">
                                            <strong>Créé le:</strong>
                                            <span>{new Date(selectedItem.created_at).toLocaleString('fr-FR')}</span>
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default App
