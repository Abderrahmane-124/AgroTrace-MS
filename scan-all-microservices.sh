#!/bin/bash
# Script pour scanner tous les microservices avec SonarQube
# Usage: ./scan-all-microservices.sh <SONAR_TOKEN>

SONAR_TOKEN=$1
SONAR_HOST="http://sonarqube:9000"

if [ -z "$SONAR_TOKEN" ]; then
    echo "Usage: ./scan-all-microservices.sh <SONAR_TOKEN>"
    exit 1
fi

MICROSERVICES=(
    "0-Simulateur-Capteurs"
    "1-IngestionCapteurs"
    "2-Pretraitement"
    "3-VisionPlante"
    "4-PrévisionEau"
    "5-RèglesAgro"
    "6-RecoIrrigation"
    "7-DashboardSIG/backend"
    "7-DashboardSIG/frontend"
)

echo "=========================================="
echo "🔍 SonarQube Scan - All Microservices"
echo "=========================================="

for ms in "${MICROSERVICES[@]}"; do
    echo ""
    echo "📦 Scanning: $ms"
    echo "------------------------------------------"
    
    docker run --rm \
        --network projet-agrotrace-ms_agrotrace-network \
        -e SONAR_HOST_URL=$SONAR_HOST \
        -e SONAR_TOKEN=$SONAR_TOKEN \
        -v "$(pwd)/$ms:/usr/src" \
        sonarsource/sonar-scanner-cli
    
    if [ $? -eq 0 ]; then
        echo "✅ $ms: Scan completed"
    else
        echo "❌ $ms: Scan failed"
    fi
done

echo ""
echo "=========================================="
echo "✅ All scans completed!"
echo "View results at: http://localhost:9090"
echo "=========================================="
