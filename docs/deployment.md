---
title: Deployment & Infrastructure
layout: default
nav_order: 7
---

# Deployment & Infrastructure
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Deployment Platform

The portal is deployed on **Kubernetes** (targeting EKS / GKE / AKS or on-prem K8s 1.28+). All components are containerised with Docker and managed via **Helm charts**.

---

## Kubernetes Topology

```
Kubernetes Cluster
│
├── Namespace: health-matrix-portal
│   │
│   ├── Deployment: portal-ingestion         (2–6 replicas, HPA)
│   │     ├── Container: devlake-adapter
│   │     └── Container: metron-adapter
│   │
│   ├── Deployment: portal-api               (2–4 replicas, HPA)
│   │     └── Container: apollo-graphql-server
│   │
│   ├── Deployment: portal-ui                (2 replicas)
│   │     └── Container: nginx (serves React SPA static assets)
│   │
│   ├── Deployment: portal-alerting          (1–2 replicas)
│   │     └── Container: alerting-engine
│   │
│   ├── StatefulSet: timescaledb             (1 primary + 1 read replica)
│   │
│   ├── StatefulSet: redis                   (1 primary + 1 replica, Redis Sentinel)
│   │
│   ├── Service: portal-api-svc              (ClusterIP)
│   ├── Service: portal-ui-svc              (ClusterIP)
│   ├── Ingress: portal-ingress             (NGINX Ingress Controller + TLS)
│   │
│   ├── HorizontalPodAutoscaler: portal-ingestion  (CPU + custom Kafka lag metric)
│   └── HorizontalPodAutoscaler: portal-api        (CPU + RPS)
│
└── Namespace: health-matrix-monitoring
    ├── Deployment: prometheus
    ├── Deployment: grafana
    └── Deployment: alertmanager
```

---

## Network Topology

```
Internet
    │
    │  HTTPS :443
    ▼
[AWS ALB / Cloud Load Balancer]
    │
    ▼
[NGINX Ingress Controller]
    │
    ├──  /          → portal-ui-svc       → React SPA
    └──  /graphql   → portal-api-svc      → Apollo GraphQL
    └──  /api       → portal-api-svc      → REST endpoints
    └──  /webhooks  → portal-api-svc      → Alert webhooks

Internal cluster traffic (no external exposure):
    portal-api ──► timescaledb:5432
    portal-api ──► redis:6379
    portal-ingestion ──► timescaledb:5432
    portal-ingestion ──► redis:6379
    portal-ingestion ──► devlake.internal:4000   (HTTPS)
    portal-ingestion ──► kafka-broker:9092        (SASL/TLS)
```

---

## Container Images

| Component | Base Image | Approx Size |
|---|---|---|
| `portal-ingestion` | `python:3.12-slim` | ~180 MB |
| `portal-api` | `node:22-alpine` | ~120 MB |
| `portal-ui` | `nginx:1.26-alpine` | ~25 MB |
| `portal-alerting` | `python:3.12-slim` | ~150 MB |

All images are built via **GitHub Actions**, pushed to a private container registry, and scanned with **Trivy** for vulnerabilities before deployment.

---

## Helm Chart Structure

```
helm/
└── health-matrix-portal/
    ├── Chart.yaml
    ├── values.yaml              # default values
    ├── values-staging.yaml
    ├── values-production.yaml
    └── templates/
        ├── ingestion/
        │   ├── deployment.yaml
        │   ├── hpa.yaml
        │   └── configmap.yaml
        ├── api/
        │   ├── deployment.yaml
        │   ├── service.yaml
        │   └── hpa.yaml
        ├── ui/
        │   ├── deployment.yaml
        │   └── service.yaml
        ├── alerting/
        │   └── deployment.yaml
        ├── ingress.yaml
        ├── secrets.yaml         # ExternalSecrets operator references
        └── keda-scaledobject.yaml
```

---

## CI/CD Pipeline

```
Git Push → GitHub Actions
                │
                ├── 1. Lint + Unit Tests (Vitest, pytest)
                ├── 2. Integration Tests (Testcontainers: TimescaleDB + Redis)
                ├── 3. E2E Tests (Playwright, staging env)
                ├── 4. Docker Build + Trivy Scan
                ├── 5. Push to container registry
                └── 6. Helm Deploy
                         │
                         ├── main branch  → staging (auto)
                         └── tag v*.*.*   → production (manual approval gate)
```

**Rollback strategy:** Helm rollback to the previous revision (`helm rollback health-matrix-portal`). TimescaleDB schema migrations use **Flyway** with `undo` scripts for safe rollback.

---

## Secrets Management

Secrets are managed with the **External Secrets Operator (ESO)** and stored in **AWS Secrets Manager** (or HashiCorp Vault for on-prem). Kubernetes `Secret` objects are never committed to git.

| Secret | Source | Consumed By |
|---|---|---|
| `DEVLAKE_API_KEY` | AWS Secrets Manager | portal-ingestion |
| `KAFKA_SASL_PASSWORD` | AWS Secrets Manager | portal-ingestion |
| `DB_PASSWORD` | AWS Secrets Manager | portal-ingestion, portal-api |
| `REDIS_PASSWORD` | AWS Secrets Manager | portal-ingestion, portal-api |
| `OIDC_CLIENT_SECRET` | AWS Secrets Manager | portal-api |
| `JWT_SIGNING_KEY` | AWS Secrets Manager | portal-api |

---

## Autoscaling

### portal-ingestion (HPA + KEDA)

```yaml
# KEDA ScaledObject – scale on Kafka consumer lag
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: portal-ingestion-kafka-scaler
spec:
  scaleTargetRef:
    name: portal-ingestion
  minReplicaCount: 2
  maxReplicaCount: 6
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: "kafka-broker-1:9092,kafka-broker-2:9092"
        consumerGroup: portal-metron-consumer
        topic: metron.host.vitals
        lagThreshold: "5000"    # scale up if lag > 5000
```

### portal-api (HPA)

```yaml
# HPA – scale on CPU + custom RPS metric
minReplicas: 2
maxReplicas: 4
metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

---

## Observability

The portal is fully instrumented using the **OpenTelemetry** standard.

### Metrics (Prometheus)

All components expose a `/metrics` endpoint. Key metrics:

| Metric | Description |
|---|---|
| `portal_devlake_poll_duration_seconds` | Histogram of DevLake polling duration |
| `portal_devlake_metrics_fetched_total` | Counter of metrics fetched from DevLake |
| `portal_kafka_consumer_lag` | Gauge for Kafka consumer lag (per topic) |
| `portal_events_ingested_total` | Counter of events written to TimescaleDB |
| `portal_api_request_duration_seconds` | HTTP/GraphQL request latency histogram |
| `portal_cache_hit_ratio` | Redis cache hit rate |
| `portal_alerts_fired_total` | Counter of alerts dispatched |

### Tracing (Jaeger / Tempo)

Distributed traces propagated via W3C Trace Context headers:
- `portal-ui` → `portal-api` → `timescaledb` / `redis`
- `portal-ingestion` → DevLake REST
- `portal-ingestion` ← Kafka → `portal-alerting`

### Logging (Structured JSON → Loki / OpenSearch)

All components log structured JSON to stdout. Log levels: `debug`, `info`, `warn`, `error`.

```json
{
  "timestamp": "2026-03-05T10:23:44.123Z",
  "level": "info",
  "service": "portal-ingestion",
  "component": "devlake-adapter",
  "message": "metrics fetched",
  "project": "backend",
  "metric_count": 42,
  "duration_ms": 183,
  "trace_id": "a1b2c3d4e5f6"
}
```

---

## Grafana Dashboards

| Dashboard | Description |
|---|---|
| **Portal Overview** | API request rates, error rates, latency percentiles |
| **Ingestion Health** | Poll success rates, Kafka consumer lag, ingest throughput |
| **Database Health** | TimescaleDB query latency, connection pool, disk usage |
| **DORA Metrics** | Health matrix trends over time (re-uses portal's own data) |

---

## Data Backup & Recovery

| Component | Backup Strategy | RPO | RTO |
|---|---|---|---|
| TimescaleDB | Daily `pg_dump` to S3 + WAL archiving (PITR) | 1 hour | 2 hours |
| Redis | RDB snapshot every 15 min; AOF logging | 15 min | 30 min |
| Kafka (Metron topics) | Managed by Metron ops; 7-day retention | 7 days | N/A (replay) |

---

## Resource Estimates (Production)

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit | Replicas |
|---|---|---|---|---|---|
| portal-ingestion | 250m | 1000m | 256Mi | 512Mi | 2–6 |
| portal-api | 250m | 500m | 256Mi | 512Mi | 2–4 |
| portal-ui | 50m | 100m | 64Mi | 128Mi | 2 |
| portal-alerting | 100m | 500m | 128Mi | 256Mi | 1–2 |
| timescaledb | 2000m | 4000m | 4Gi | 8Gi | 2 |
| redis | 200m | 500m | 256Mi | 512Mi | 2 |
