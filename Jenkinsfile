pipeline {
    agent any
    
    environment {
        SONAR_HOST_URL = 'http://sonarqube:9000'
        DOCKER_REGISTRY = 'agrotrace'
    }
    
    stages {
        stage('Checkout') {
            steps {
                checkout scm
                echo '✅ Code source récupéré'
            }
        }
        
        stage('Build Docker Images') {
            parallel {
                stage('MS0 - Simulateur') {
                    steps {
                        dir('0-Simulateur-Capteurs') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/simulateur-capteurs:${BUILD_NUMBER} .'
                        }
                    }
                }
                stage('MS1 - Ingestion') {
                    steps {
                        dir('1-IngestionCapteurs') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/ingestion-capteurs:${BUILD_NUMBER} .'
                        }
                    }
                }
                stage('MS2 - Pretraitement') {
                    steps {
                        dir('2-Pretraitement') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/pretraitement:${BUILD_NUMBER} .'
                        }
                    }
                }
                stage('MS3 - VisionPlante') {
                    steps {
                        dir('3-VisionPlante') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/vision-plante:${BUILD_NUMBER} .'
                        }
                    }
                }
                stage('MS4 - PrevisionEau') {
                    steps {
                        dir('4-PrévisionEau') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/prevision-eau:${BUILD_NUMBER} .'
                        }
                    }
                }
                stage('MS5 - ReglesAgro') {
                    steps {
                        dir('5-RèglesAgro') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/regles-agro:${BUILD_NUMBER} .'
                        }
                    }
                }
                stage('MS6 - RecoIrrigation') {
                    steps {
                        dir('6-RecoIrrigation') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/reco-irrigation:${BUILD_NUMBER} .'
                        }
                    }
                }
                stage('MS7 - Dashboard Backend') {
                    steps {
                        dir('7-DashboardSIG/backend') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/dashboard-backend:${BUILD_NUMBER} .'
                        }
                    }
                }
                stage('MS7 - Dashboard Frontend') {
                    steps {
                        dir('7-DashboardSIG/frontend') {
                            sh 'docker build -t ${DOCKER_REGISTRY}/dashboard-frontend:${BUILD_NUMBER} .'
                        }
                    }
                }
            }
        }
        
        stage('SonarQube Analysis') {
            steps {
                script {
                    def microservices = [
                        '0-Simulateur-Capteurs',
                        '1-IngestionCapteurs',
                        '2-Pretraitement',
                        '3-VisionPlante',
                        '4-PrévisionEau',
                        '5-RèglesAgro',
                        '6-RecoIrrigation',
                        '7-DashboardSIG/backend',
                        '7-DashboardSIG/frontend'
                    ]
                    
                    microservices.each { ms ->
                        dir(ms) {
                            withSonarQubeEnv('SonarQube') {
                                sh '''
                                    docker run --rm \
                                        --network projet-agrotrace-ms_agrotrace-network \
                                        -e SONAR_HOST_URL=${SONAR_HOST_URL} \
                                        -e SONAR_TOKEN=${SONAR_AUTH_TOKEN} \
                                        -v "$(pwd):/usr/src" \
                                        sonarsource/sonar-scanner-cli
                                '''
                            }
                        }
                    }
                }
            }
        }
        
        stage('Quality Gate') {
            steps {
                timeout(time: 5, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: false
                }
            }
        }
        
        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                echo '🚀 Déploiement sur environnement de production...'
                sh 'docker compose up -d'
            }
        }
    }
    
    post {
        always {
            echo '🧹 Nettoyage...'
            sh 'docker system prune -f || true'
        }
        success {
            echo '✅ Pipeline terminé avec succès!'
        }
        failure {
            echo '❌ Pipeline échoué!'
        }
    }
}
