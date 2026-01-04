pipeline {
    agent any
    
    environment {
        SONAR_HOST_URL = 'http://sonarqube:9000'
        DOCKER_REGISTRY = 'agrotrace'
        DOCKER_NETWORK = 'projet-agrotrace-ms_agrotrace-network'
        DOCKER_HOST = 'tcp://docker:2376'
        DOCKER_CERT_PATH = '/certs/client'
        DOCKER_TLS_VERIFY = '1'
    }
    
    stages {
        stage('Checkout') {
            steps {
                git branch: 'main', url: 'https://github.com/Abderrahmane-124/AgroTrace-MS.git'
                echo '✅ Code source récupéré'
            }
        }
        
        stage('Build Docker Images') {
            parallel {
                stage('MS0 - Simulateur') {
                    steps {
                        dir('0-Simulateur-Capteurs') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/simulateur-capteurs:${BUILD_NUMBER} -t ${DOCKER_REGISTRY}/simulateur-capteurs:latest .'
                        }
                    }
                }
                stage('MS1 - Ingestion') {
                    steps {
                        dir('1-IngestionCapteurs') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/ingestion-capteurs:${BUILD_NUMBER} -t ${DOCKER_REGISTRY}/ingestion-capteurs:latest .'
                        }
                    }
                }
                stage('MS2 - Pretraitement') {
                    steps {
                        dir('2-Pretraitement') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/pretraitement:${BUILD_NUMBER} -t ${DOCKER_REGISTRY}/pretraitement:latest .'
                        }
                    }
                }
                stage('MS3 - VisionPlante') {
                    steps {
                        dir('3-VisionPlante') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/vision-plante:${BUILD_NUMBER} -t ${DOCKER_REGISTRY}/vision-plante:latest .'
                        }
                    }
                }
                stage('MS4 - PrevisionEau') {
                    steps {
                        dir('4-PrévisionEau') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/prevision-eau:${BUILD_NUMBER} -t ${DOCKER_REGISTRY}/prevision-eau:latest .'
                        }
                    }
                }
                stage('MS5 - ReglesAgro') {
                    steps {
                        dir('5-RèglesAgro') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/regles-agro:${BUILD_NUMBER} -t ${DOCKER_REGISTRY}/regles-agro:latest .'
                        }
                    }
                }
                stage('MS6 - RecoIrrigation') {
                    steps {
                        dir('6-RecoIrrigation') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/reco-irrigation:${BUILD_NUMBER} -t ${DOCKER_REGISTRY}/reco-irrigation:latest .'
                        }
                    }
                }
                stage('MS7 - Dashboard Backend') {
                    steps {
                        dir('7-DashboardSIG/backend') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/dashboard-backend:${BUILD_NUMBER} -t ${DOCKER_REGISTRY}/dashboard-backend:latest .'
                        }
                    }
                }
                stage('MS7 - Dashboard Frontend') {
                    steps {
                        dir('7-DashboardSIG/frontend') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/dashboard-frontend:${BUILD_NUMBER} -t ${DOCKER_REGISTRY}/dashboard-frontend:latest .'
                        }
                    }
                }
            }
        }
        
        
        
        
        stage('Deploy to Production') {
            when {
                branch 'main'
            }
            steps {
                echo '🚀 Déploiement sur environnement de production...'
                sh 'docker compose -f docker-compose.yml up -d'
            }
        }
    }
    
    post {
        always {
            echo '🧹 Nettoyage des images non utilisées...'
            sh 'docker system prune -f || true'
        }
        success {
            echo '✅ Pipeline CI/CD terminé avec succès!'
            echo '📊 Rapport SonarQube disponible sur: ${SONAR_HOST_URL}'
        }
        failure {
            echo '❌ Pipeline échoué! Vérifiez les logs ci-dessus.'
        }
    }
}
