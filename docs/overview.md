---
title: Architecture Overview
layout: default
nav_order: 2
has_children: false
---

# Architecture Overview
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## System Context

The Health Matrix Portal sits between two upstream data platforms and a set of downstream consumers (human users and automated alerting systems).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          UPSTREAM DATA SOURCES                          │
│                                                                         │
│  ┌─────────────────────────┐     ┌─────────────────────────────────┐   │
│  │       Apache DevLake    │     │         Apache Metron           │   │
│  │  (Engineering Metrics)  │     │  (Infrastructure / Security)    │   │
│  │                         │     │                                 │   │
│  │  • DORA metrics         │     │  • Real-time system telemetry   │   │
│  │  • Deployment frequency │     │  • Network health signals       │   │
│  │  • Lead time for change │     │  • Anomaly detection events     │   │
│  │  • MTTR                 │     │  • Host/container vitals        │   │
│  │  • Change failure rate  │     │  • Security event streams       │   │
│  └────────────┬────────────┘     └───────────────┬─────────────────┘   │
│               │                                  │                     │
└───────────────┼──────────────────────────────────┼─────────────────────┘
                │  REST / GraphQL Pull              │  Kafka / REST Pull
                ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       HEALTH MATRIX PORTAL                              │
│                                                                         │
│  ┌───────────────┐  ┌───────────────┐  ┌────────────────────────────┐  │
│  │  Ingestion    │  │  Aggregation  │  │     API Gateway            │  │
│  │  Service      │  │  & Storage    │  │  (REST + GraphQL)          │  │
│  └───────────────┘  └───────────────┘  └────────────────────────────┘  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                     Dashboard UI (React SPA)                      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         DOWNSTREAM CONSUMERS                            │
│                                                                         │
│   Browser Users   │   PagerDuty / Alerting   │   BI / Reporting Tools  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Map

The portal is composed of six logical components:

| Component | Technology | Responsibility |
|---|---|---|
| **Ingestion Service** | Python / FastAPI | Polls DevLake REST API and Metron Kafka topics; normalises raw events into the canonical health model |
| **Time-Series Store** | TimescaleDB (PostgreSQL extension) | Persists all health metric time-series with automatic retention policies |
| **Cache Layer** | Redis | Caches aggregated metric snapshots to serve dashboard queries with sub-100 ms latency |
| **API Gateway** | Node.js / Apollo GraphQL | Exposes a unified GraphQL API and REST endpoints; handles auth (OIDC) and RBAC |
| **Dashboard UI** | React + TypeScript | Single-page application; renders health matrix tiles, trend charts, and drill-down views |
| **Alerting Engine** | Python | Evaluates threshold rules against incoming metrics; dispatches notifications to PagerDuty / Slack |

---

## Data Flow

### 1. Ingestion Flow (Pull-based – DevLake)

```
DevLake REST API
      │
      │  HTTP GET /api/metrics?...  (every 60s)
      ▼
Ingestion Service
      │
      │  Normalise → HealthMetricEvent (Canonical Schema)
      ▼
TimescaleDB   ──────►  Redis (write-through cache for latest snapshot)
```

### 2. Ingestion Flow (Streaming – Metron)

```
Metron → Kafka Topic: health.raw.events
                │
                │  Consumer Group: portal-ingestion
                ▼
        Ingestion Service
                │
                │  Normalise → HealthMetricEvent
                ▼
        TimescaleDB   ──────►  Redis
```

### 3. Query Flow (Dashboard)

```
Browser → React SPA
              │
              │  GraphQL / REST query
              ▼
        API Gateway
              │
              ├── Cache HIT  ──────────► Redis → Response
              │
              └── Cache MISS ──────────► TimescaleDB → Response + Cache warm
```

### 4. Alert Flow

```
Ingestion Service
        │
        │  Publishes HealthMetricEvent to internal event bus
        ▼
Alerting Engine
        │
        │  Evaluates rules (threshold, anomaly, trend)
        ▼
Notification Dispatcher
        │
        ├──► PagerDuty (on-call incidents)
        ├──► Slack (team channels)
        └──► Portal (in-app notification banner)
```

---

## Key Architectural Decisions

### ADR-001 – Pull vs Push for DevLake

**Decision:** Pull (polling) every 60 seconds via DevLake's REST API.

**Rationale:** DevLake does not expose a native event stream. Its REST API provides point-in-time metric snapshots. A 60-second poll interval meets the near-real-time SLO without overwhelming DevLake's database.

**Trade-offs:** Polling adds latency proportional to the interval. If DevLake introduces webhooks in the future, the ingestion service can be switched to a push model with minimal API changes.

---

### ADR-002 – Streaming for Metron

**Decision:** Consume from Apache Kafka topics that Metron writes to.

**Rationale:** Metron is built around Kafka. Consuming directly from Kafka topics is the lowest-latency integration path and decouples the portal from Metron's internal processing pipeline.

---

### ADR-003 – TimescaleDB as the primary store

**Decision:** Use TimescaleDB (PostgreSQL with time-series extension) rather than InfluxDB or Prometheus remote write.

**Rationale:** TimescaleDB provides SQL query semantics (familiar to the team), automatic hypertable partitioning for time-series, built-in compression, and continuous aggregates. It integrates easily with standard PostgreSQL tooling.

---

### ADR-004 – GraphQL API gateway

**Decision:** Expose a GraphQL API (via Apollo Server) as the primary query interface, with a thin REST shim for alerting webhooks.

**Rationale:** GraphQL allows the dashboard to fetch only the fields it needs, reducing over-fetching. It also makes it easier for third-party consumers to compose custom queries without requiring new REST endpoints.

---

## Non-Functional Requirements

| NFR | Target |
|---|---|
| Metric freshness (DevLake) | ≤ 60 seconds behind source |
| Metric freshness (Metron) | ≤ 5 seconds behind source |
| Dashboard query P95 latency | < 200 ms (cached), < 2 s (uncached) |
| Availability | 99.5% monthly (portal UI + API) |
| Data retention | 12 months raw; 3 years aggregated (daily rollups) |
| Auth | OIDC (SSO); RBAC with team-scoped visibility |
| Audit log | All API mutations logged with actor + timestamp |
