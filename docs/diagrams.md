---
title: Architecture Diagrams
layout: default
nav_order: 8
---

# Architecture Diagrams
{: .no_toc }

Visual diagrams for all layers of the Health Matrix Portal.

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 1. System Context (C4 Level 1)

High-level view of the portal and its external actors.

<div class="mermaid">
C4Context
  title System Context – Health Matrix Portal

  Person(user, "Engineer / Ops", "Views health metrics and DORA data on the portal dashboard")
  Person(admin, "Admin", "Manages alert rules and RBAC assignments")

  System(portal, "Health Matrix Portal", "Aggregates engineering and infrastructure health data into a unified dashboard")

  System_Ext(devlake, "Apache DevLake", "Collects DORA metrics from GitHub, Jira, Jenkins, etc.")
  System_Ext(metron, "Apache Metron", "Collects infrastructure telemetry and security alerts via Kafka")
  System_Ext(oidc, "Identity Provider (Okta / Keycloak)", "OIDC authentication and JWT issuance")
  System_Ext(pagerduty, "PagerDuty / Slack", "Receives alert notifications from the portal")

  Rel(user, portal, "Views dashboards, drills into metrics", "HTTPS")
  Rel(admin, portal, "Manages rules and RBAC", "HTTPS")
  Rel(portal, devlake, "Polls DORA metrics every 60s", "REST / HTTPS")
  Rel(portal, metron, "Consumes health telemetry", "Kafka / SASL-TLS")
  Rel(portal, oidc, "Validates JWT tokens", "OIDC / HTTPS")
  Rel(portal, pagerduty, "Fires alert notifications", "HTTPS webhook")
</div>

---

## 2. Container Diagram (C4 Level 2)

Internal containers that make up the portal.

<div class="mermaid">
C4Container
  title Container Diagram – Health Matrix Portal

  System_Ext(devlake, "Apache DevLake", "REST API on :4000")
  System_Ext(metron_kafka, "Metron Kafka", "Output topics: host.vitals, anomaly.scores, etc.")
  System_Ext(oidc, "OIDC Provider", "JWT issuer")

  Container_Boundary(portal, "Health Matrix Portal") {
    Container(ui, "Dashboard UI", "React 18 / TypeScript", "SPA served by nginx; renders health matrix, trends, alerts")
    Container(api, "API Gateway", "Node.js / Apollo GraphQL", "Unified GraphQL + REST API; enforces OIDC auth and RBAC")
    Container(ingestion, "Ingestion Service", "Python / FastAPI", "Polls DevLake (60s) and consumes Metron Kafka topics; normalises events")
    Container(alerting, "Alerting Engine", "Python", "Evaluates threshold / anomaly rules; dispatches notifications")
    ContainerDb(tsdb, "TimescaleDB", "PostgreSQL + TimescaleDB", "Stores all health metric time-series with hypertables and roll-ups")
    ContainerDb(redis, "Redis", "Redis Sentinel", "Caches latest metric snapshots; serves sub-100ms dashboard queries")
  }

  Rel(ui, api, "GraphQL queries / REST calls", "HTTPS")
  Rel(api, redis, "Read cached snapshots", "Redis protocol")
  Rel(api, tsdb, "Query historical time-series", "SQL / TLS")
  Rel(api, oidc, "Validate JWT", "HTTPS")
  Rel(ingestion, devlake, "Poll DORA + velocity metrics", "REST / HTTPS")
  Rel(ingestion, metron_kafka, "Consume health events", "Kafka / SASL-TLS")
  Rel(ingestion, tsdb, "Write normalised metric events", "SQL / TLS")
  Rel(ingestion, redis, "Update latest snapshots", "Redis protocol")
  Rel(alerting, tsdb, "Read metrics for rule evaluation", "SQL / TLS")
</div>

---

## 3. End-to-End Data Flow

Full journey of a metric from source to dashboard.

<div class="mermaid">
flowchart TD
    subgraph Sources["Upstream Sources"]
        DL["Apache DevLake\nREST API :4000"]
        MK["Apache Metron\nKafka Topics"]
    end

    subgraph Ingestion["Ingestion Service"]
        DA["DevLake Adapter\n(poll every 60s)"]
        MA["Metron Adapter\n(Kafka consumer group)"]
        NM["Normaliser\n→ HealthMetricEvent"]
    end

    subgraph Storage["Storage Layer"]
        TS["TimescaleDB\nHypertable + Roll-ups"]
        RD["Redis\nLatest Snapshot Cache"]
    end

    subgraph API["API Gateway (Apollo GraphQL)"]
        GQL["GraphQL Resolvers\n+ RBAC enforcement"]
        CH["Cache Lookup\n(HIT / MISS)"]
    end

    subgraph Alert["Alerting Engine"]
        RE["Rule Evaluator\n(threshold / anomaly)"]
        ND["Notification Dispatcher"]
    end

    subgraph UI["Dashboard UI (React SPA)"]
        DB["Health Matrix\nDashboard"]
        TR["Trend Chart"]
        AL["Alert Panel"]
    end

    subgraph Notify["Notifications"]
        PD["PagerDuty"]
        SL["Slack"]
    end

    DL -- "REST pull" --> DA
    MK -- "Kafka consume" --> MA
    DA --> NM
    MA --> NM
    NM -- "bulk insert" --> TS
    NM -- "write-through" --> RD
    NM -- "event bus" --> RE
    RE --> ND
    ND --> PD
    ND --> SL

    DB -- "GraphQL query" --> GQL
    TR -- "GraphQL query" --> GQL
    AL -- "GraphQL query" --> GQL
    GQL --> CH
    CH -- "MISS" --> TS
    CH -- "HIT" --> RD
    TS -- "result + warm cache" --> RD
    RD -- "response" --> GQL
    GQL -- "data" --> DB
    GQL -- "data" --> TR
    GQL -- "data" --> AL

    style Sources fill:#e8f4e8,stroke:#4caf50
    style Ingestion fill:#e3f2fd,stroke:#1976d2
    style Storage fill:#fce4ec,stroke:#c62828
    style API fill:#f3e5f5,stroke:#7b1fa2
    style Alert fill:#fff3e0,stroke:#e65100
    style UI fill:#e0f7fa,stroke:#00838f
    style Notify fill:#f5f5f5,stroke:#616161
</div>

---

## 4. DevLake Integration Sequence

How the Ingestion Service polls DevLake and stores results.

<div class="mermaid">
sequenceDiagram
    autonumber
    participant SCH as Scheduler (APScheduler)
    participant DA  as DevLake Adapter
    participant DL  as DevLake REST API
    participant NM  as Normaliser
    participant TS  as TimescaleDB
    participant RD  as Redis

    loop Every 60 seconds
        SCH->>DA: trigger fetch_dora_metrics(project, period)
        DA->>DL: GET /api/projects/{project}/dora<br/>X-Api-Token: ***
        alt HTTP 200 OK
            DL-->>DA: JSON { data: [...metrics] }
            DA->>NM: raw metrics[]
            NM-->>DA: HealthMetricEvent[]
            DA->>TS: bulk INSERT health_metric_events
            TS-->>DA: rows inserted
            DA->>RD: SET snapshot:{category}:{team} TTL 60s
            RD-->>DA: OK
        else HTTP 5xx (retry up to 3×)
            DL-->>DA: 5xx Error
            DA->>DA: wait 2s / 4s / 8s then retry
        else HTTP 401 Unauthorized
            DL-->>DA: 401
            DA->>DA: emit CRITICAL alert<br/>stop polling until key rotated
        end
    end
</div>

---

## 5. Metron Kafka Streaming Sequence

How the Ingestion Service consumes and processes Metron events.

<div class="mermaid">
sequenceDiagram
    autonumber
    participant MK  as Metron Kafka
    participant MA  as Metron Adapter
    participant DLQ as Dead-Letter Topic
    participant NM  as Normaliser
    participant TS  as TimescaleDB
    participant RD  as Redis
    participant AE  as Alerting Engine

    loop Continuous consume loop
        MA->>MK: poll(max_records=500, timeout=1s)
        MK-->>MA: batch of messages

        loop For each message
            alt Valid JSON / Avro
                MA->>NM: raw event payload
                NM-->>MA: HealthMetricEvent
            else Deserialisation failure
                MA->>DLQ: publish to portal.dlq.metron
                MA->>MA: log + skip
            end
        end

        MA->>TS: bulk INSERT health_metric_events
        alt Write success
            TS-->>MA: rows inserted
            MA->>RD: update snapshot cache
            MA->>AE: publish events to internal bus
            MA->>MK: commitSync() offsets
        else Write failure (retry)
            MA->>MA: hold offsets<br/>retry with backoff
        end

        AE->>AE: evaluate threshold rules
        opt Alert triggered
            AE-->>MA: fire notification<br/>(PagerDuty / Slack)
        end
    end
</div>

---

## 6. GraphQL Query Flow (Cache Hit vs Miss)

How the API Gateway resolves a dashboard query.

<div class="mermaid">
sequenceDiagram
    autonumber
    participant UI  as React Dashboard
    participant GW  as API Gateway (Apollo)
    participant OI  as OIDC Provider
    participant RD  as Redis Cache
    participant TS  as TimescaleDB

    UI->>GW: POST /graphql  { query: healthMatrix(...) }<br/>Authorization: Bearer <JWT>

    GW->>OI: validate JWT (JWKS endpoint)
    OI-->>GW: token valid, claims: { sub, roles, team }

    GW->>GW: enforce RBAC<br/>(check roles vs requested fields)

    GW->>RD: GET snapshot:dora:backend:prod

    alt Cache HIT (TTL not expired)
        RD-->>GW: cached metric snapshot
        GW-->>UI: GraphQL response (< 100ms)
    else Cache MISS
        RD-->>GW: nil
        GW->>TS: SELECT ... FROM health_metrics_hourly<br/>WHERE team='backend' AND ...
        TS-->>GW: metric rows
        GW->>RD: SET snapshot:dora:backend:prod  TTL 60s
        GW-->>UI: GraphQL response (< 2s)
    end
</div>

---

## 7. Alert Lifecycle

From metric ingestion to alert acknowledgement.

<div class="mermaid">
stateDiagram-v2
    direction LR
    [*] --> MetricIngested : HealthMetricEvent received

    MetricIngested --> RuleEvaluation : publish to internal event bus

    RuleEvaluation --> Firing : threshold / anomaly breached
    RuleEvaluation --> OK : all rules pass

    OK --> [*]

    Firing --> NotificationSent : dispatch to PagerDuty + Slack
    NotificationSent --> ActiveAlert : stored in TimescaleDB\nvisible on dashboard

    ActiveAlert --> Acknowledged : ops engineer clicks Ack\n(POST /api/v1/alerts/{id}/ack)
    Acknowledged --> Resolved : metric returns to healthy range
    Resolved --> [*]

    ActiveAlert --> AutoResolved : metric recovers before ack
    AutoResolved --> [*]
</div>

---

## 8. Kubernetes Deployment Topology

How portal components are arranged across Kubernetes.

<div class="mermaid">
graph TB
    subgraph Internet
        USR["Browser / Users"]
        EXT["External Services\n(PagerDuty, Slack)"]
    end

    subgraph Cloud_LB["Cloud Load Balancer"]
        ALB["AWS ALB / GCP GLB"]
    end

    subgraph K8s["Kubernetes Cluster"]
        subgraph NS_Portal["Namespace: health-matrix-portal"]
            ING["NGINX Ingress\n(TLS termination)"]

            subgraph UI_Deploy["Deployment: portal-ui (×2)"]
                UI1["nginx container\n(React SPA)"]
            end

            subgraph API_Deploy["Deployment: portal-api (×2–4, HPA)"]
                API1["Apollo GraphQL\nNode.js"]
            end

            subgraph ING_Deploy["Deployment: portal-ingestion (×2–6, KEDA)"]
                DA1["DevLake\nAdapter"]
                MA1["Metron\nAdapter"]
            end

            subgraph ALT_Deploy["Deployment: portal-alerting (×1–2)"]
                AE1["Alerting\nEngine"]
            end

            subgraph TSDB_SS["StatefulSet: timescaledb (primary + replica)"]
                TS1["TimescaleDB\nPrimary"]
                TS2["TimescaleDB\nRead Replica"]
            end

            subgraph Redis_SS["StatefulSet: redis (sentinel)"]
                RD1["Redis Primary"]
                RD2["Redis Replica"]
            end
        end

        subgraph NS_Monitor["Namespace: health-matrix-monitoring"]
            PROM["Prometheus"]
            GRAF["Grafana"]
            ALRT["Alertmanager"]
        end
    end

    subgraph Upstream["Upstream Systems"]
        DL["Apache DevLake\n:4000"]
        MK["Metron Kafka\n:9092"]
    end

    USR --> ALB --> ING
    ING -- "/" --> UI1
    ING -- "/graphql /api" --> API1
    API1 --> TS2
    API1 --> RD1
    DA1 --> DL
    MA1 --> MK
    DA1 --> TS1
    MA1 --> TS1
    DA1 --> RD1
    MA1 --> RD1
    AE1 --> TS2
    AE1 --> EXT
    PROM -- "scrape /metrics" --> API1
    PROM -- "scrape /metrics" --> DA1
    GRAF --> PROM

    style NS_Portal fill:#e3f2fd,stroke:#1976d2
    style NS_Monitor fill:#f3e5f5,stroke:#7b1fa2
    style Upstream fill:#e8f4e8,stroke:#4caf50
    style Internet fill:#fff8e1,stroke:#f57f17
</div>

---

## 9. CI/CD Pipeline

From code commit to production deployment.

<div class="mermaid">
flowchart LR
    DEV["Developer\nPush / PR"] --> GHA["GitHub Actions\nWorkflow"]

    subgraph GHA["GitHub Actions Pipeline"]
        direction TB
        S1["1. Lint\n(ESLint, flake8, mypy)"]
        S2["2. Unit Tests\n(Vitest, pytest)"]
        S3["3. Integration Tests\n(Testcontainers:\nTimescaleDB + Redis)"]
        S4["4. E2E Tests\n(Playwright – staging)"]
        S5["5. Docker Build\n+ Trivy Security Scan"]
        S6["6. Push Image\nto Container Registry"]
        S7A["7a. Helm Deploy\n→ Staging (auto)"]
        S7B["7b. Helm Deploy\n→ Production\n(manual approval gate)"]

        S1 --> S2 --> S3 --> S4 --> S5 --> S6
        S6 --> S7A
        S6 -- "git tag v*.*.*" --> S7B
    end

    S7A --> STG["Staging\nEnvironment"]
    S7B --> PRD["Production\nEnvironment"]

    PRD -- "rollback on failure" --> RB["helm rollback\nto previous revision"]

    style S7B fill:#fff3e0,stroke:#e65100
    style PRD fill:#e8f5e9,stroke:#388e3c
    style STG fill:#e3f2fd,stroke:#1976d2
</div>

---

## 10. Data Retention & Roll-up Strategy

<div class="mermaid">
flowchart TD
    RAW["Raw HealthMetricEvent\nTimescaleDB Hypertable\n(partitioned by day)"]

    subgraph Retention["Retention Policies"]
        R1["DevLake DORA events\n12 months raw"]
        R2["Metron host vitals\n30 days raw"]
        R3["Security alerts\n365 days raw (compliance)"]
        R4["Anomaly scores\n90 days raw"]
    end

    subgraph Rollups["Continuous Aggregates"]
        HR["Hourly Roll-up\navg / min / max per metric\nRetained: 1 year"]
        DR["Daily Roll-up\navg / min / max per metric\nRetained: 3 years"]
    end

    subgraph Backup["Backup"]
        S3["AWS S3\n(pg_dump daily\n+ WAL archiving PITR)"]
    end

    RAW --> R1 & R2 & R3 & R4
    RAW -- "TimescaleDB\ncontinuous aggregate job" --> HR
    HR -- "TimescaleDB\ncontinuous aggregate job" --> DR
    RAW --> S3

    subgraph QueryLayer["Query Resolution"]
        QR["API Gateway\nselects resolution based on\ntime range requested"]
        QR -- "range < 6h" --> RAW
        QR -- "range 6h – 7d" --> HR
        QR -- "range > 7d" --> DR
    end

    style Retention fill:#fce4ec,stroke:#c62828
    style Rollups fill:#e8f5e9,stroke:#388e3c
    style Backup fill:#fff3e0,stroke:#e65100
    style QueryLayer fill:#e3f2fd,stroke:#1976d2
</div>
