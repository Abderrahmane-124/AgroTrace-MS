# AgroTrace - Microservices IoT avec Kafka

Système de collecte et traitement de données de capteurs IoT utilisant Apache Kafka.

## 📝 Résumé Simple

**Kafka = Système de messagerie ultra-rapide entre applications**

- 🏢 **Broker** (Serveur Kafka) : Le serveur central qui stocke et distribue les messages
- 📂 **Topic** (`sensor-data`) : Canal de discussion où transitent les données des capteurs
- 📤 **Producer** (Simulateur) : Envoie les données vers Kafka toutes les 2 secondes
- 📥 **Consumer** (Ingestion) : Reçoit et traite les données en temps réel
- 🎯 **Partitions** (3) : Division du topic pour traiter plusieurs messages en parallèle
- 👥 **Consumer Group** : Permet à plusieurs consommateurs de partager le travail

**Flux de données :** Simulateur génère des données Excel → Convertit en JSON → Envoie vers Kafka → Kafka stocke temporairement → Ingestion récupère et traite

## Configuration Kafka

| Variable | Description |
|----------|-------------|
| `KAFKA_NODE_ID=1` | ID unique du nœud Kafka (obligatoire en mode KRaft) |
| `KAFKA_PROCESS_ROLES=broker,controller` | Combine le rôle de broker (stockage) et controller (gestion) en un seul nœud |
| `KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093` | Définit les ports d'écoute : 9092 pour les clients, 9093 pour le contrôle interne |
| `KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092` | Adresse publique que les clients utilisent pour se connecter à Kafka |
| `KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER` | Nom du listener utilisé pour la communication entre contrôleurs |
| `KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT` | Mappe les listeners à leurs protocoles de sécurité (PLAINTEXT = non chiffré) |
| `KAFKA_CONTROLLER_QUORUM_VOTERS=1@kafka:9093` | Liste des nœuds participant à l'élection du leader (nœud 1 sur port 9093) |
| `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1` | Nombre de copies des offsets de consommation (1 = pas de réplication) |
| `KAFKA_NUM_PARTITIONS=2` | Nombre de partitions par défaut pour chaque topic (permet le traitement parallèle) |


## Démarrage

```bash
docker-compose up -d
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| Kafka | 9092 | Broker Kafka |
| Kafka UI | 8080 | Interface web |
| Simulateur | - | Producer Kafka |
| Ingestion | - | Consumer Kafka |

## Logs

```bash
docker-compose logs -f
```

## Arrêt

```bash
docker-compose down
```

