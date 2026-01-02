@echo off
REM Script pour scanner tous les microservices avec SonarQube (Windows)
REM Usage: scan-all-microservices.bat VOTRE_TOKEN

set SONAR_TOKEN=%1
set SONAR_HOST=http://sonarqube:9000

if "%SONAR_TOKEN%"=="" (
    echo Usage: scan-all-microservices.bat VOTRE_TOKEN
    exit /b 1
)

echo ==========================================
echo 🔍 SonarQube Scan - All Microservices
echo ==========================================

REM MS0: Simulateur Capteurs
echo.
echo 📦 Scanning: 0-Simulateur-Capteurs
docker run --rm --network projet-agrotrace-ms_agrotrace-network -e SONAR_HOST_URL=%SONAR_HOST% -e SONAR_TOKEN=%SONAR_TOKEN% -v "%cd%\0-Simulateur-Capteurs:/usr/src" sonarsource/sonar-scanner-cli

REM MS1: Ingestion Capteurs
echo.
echo 📦 Scanning: 1-IngestionCapteurs
docker run --rm --network projet-agrotrace-ms_agrotrace-network -e SONAR_HOST_URL=%SONAR_HOST% -e SONAR_TOKEN=%SONAR_TOKEN% -v "%cd%\1-IngestionCapteurs:/usr/src" sonarsource/sonar-scanner-cli

REM MS2: Pretraitement
echo.
echo 📦 Scanning: 2-Pretraitement
docker run --rm --network projet-agrotrace-ms_agrotrace-network -e SONAR_HOST_URL=%SONAR_HOST% -e SONAR_TOKEN=%SONAR_TOKEN% -v "%cd%\2-Pretraitement:/usr/src" sonarsource/sonar-scanner-cli

REM MS3: VisionPlante
echo.
echo 📦 Scanning: 3-VisionPlante
docker run --rm --network projet-agrotrace-ms_agrotrace-network -e SONAR_HOST_URL=%SONAR_HOST% -e SONAR_TOKEN=%SONAR_TOKEN% -v "%cd%\3-VisionPlante:/usr/src" sonarsource/sonar-scanner-cli

REM MS4: Prevision Eau
echo.
echo 📦 Scanning: 4-PrevisionEau
docker run --rm --network projet-agrotrace-ms_agrotrace-network -e SONAR_HOST_URL=%SONAR_HOST% -e SONAR_TOKEN=%SONAR_TOKEN% -v "%cd%\4-PrévisionEau:/usr/src" sonarsource/sonar-scanner-cli

REM MS5: Regles Agro
echo.
echo 📦 Scanning: 5-ReglesAgro
docker run --rm --network projet-agrotrace-ms_agrotrace-network -e SONAR_HOST_URL=%SONAR_HOST% -e SONAR_TOKEN=%SONAR_TOKEN% -v "%cd%\5-RèglesAgro:/usr/src" sonarsource/sonar-scanner-cli

REM MS6: Reco Irrigation
echo.
echo 📦 Scanning: 6-RecoIrrigation
docker run --rm --network projet-agrotrace-ms_agrotrace-network -e SONAR_HOST_URL=%SONAR_HOST% -e SONAR_TOKEN=%SONAR_TOKEN% -v "%cd%\6-RecoIrrigation:/usr/src" sonarsource/sonar-scanner-cli

REM MS7: Dashboard Backend
echo.
echo 📦 Scanning: 7-DashboardSIG/backend
docker run --rm --network projet-agrotrace-ms_agrotrace-network -e SONAR_HOST_URL=%SONAR_HOST% -e SONAR_TOKEN=%SONAR_TOKEN% -v "%cd%\7-DashboardSIG\backend:/usr/src" sonarsource/sonar-scanner-cli

REM MS7: Dashboard Frontend
echo.
echo 📦 Scanning: 7-DashboardSIG/frontend
docker run --rm --network projet-agrotrace-ms_agrotrace-network -e SONAR_HOST_URL=%SONAR_HOST% -e SONAR_TOKEN=%SONAR_TOKEN% -v "%cd%\7-DashboardSIG\frontend:/usr/src" sonarsource/sonar-scanner-cli

echo.
echo ==========================================
echo ✅ All scans completed!
echo View results at: http://localhost:9090
echo ==========================================
