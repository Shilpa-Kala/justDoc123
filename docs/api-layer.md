---
title: API Layer & Data Model
layout: default
nav_order: 5
---

# API Layer & Data Model
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Overview

The API layer is the single entry point between the Dashboard UI (and any external consumers) and the portal's internal data stores. It is built with **Node.js + Apollo Server** and exposes:

- A **GraphQL API** for flexible, field-selective queries (primary interface)
- A thin **REST API** for webhook integrations and simple health checks

Authentication uses **OpenID Connect (OIDC)** – every request must carry a valid JWT issued by the configured Identity Provider (Okta / Keycloak). RBAC rules are enforced at the resolver level.

---

## Canonical Data Model

All metrics from DevLake and Metron are normalised into a single **`HealthMetricEvent`** schema before storage.

### `HealthMetricEvent`

```
HealthMetricEvent {
  id            UUID          -- generated on ingest
  source        ENUM          -- "devlake" | "metron"
  category      VARCHAR(64)   -- e.g. "dora", "infrastructure.host", "anomaly"
  name          VARCHAR(128)  -- e.g. "deployment_frequency", "cpu_utilization"
  value         DOUBLE        -- numeric metric value
  unit          VARCHAR(32)   -- e.g. "count/day", "percent", "hours", "ms"
  timestamp     TIMESTAMPTZ   -- event time (from source)
  ingested_at   TIMESTAMPTZ   -- when the portal received it

  -- Optional dimensional labels (nullable)
  team          VARCHAR(64)
  project       VARCHAR(64)
  host          VARCHAR(128)
  service       VARCHAR(128)
  environment   VARCHAR(32)   -- "prod" | "staging" | "dev"
  severity      VARCHAR(16)   -- "critical" | "high" | "medium" | "low" | null

  extra_labels  JSONB         -- catch-all for source-specific fields
}
```

### TimescaleDB Hypertable

```sql
CREATE TABLE health_metric_events (
  id            UUID          DEFAULT gen_random_uuid(),
  source        VARCHAR(16)   NOT NULL,
  category      VARCHAR(64)   NOT NULL,
  name          VARCHAR(128)  NOT NULL,
  value         DOUBLE PRECISION NOT NULL,
  unit          VARCHAR(32),
  timestamp     TIMESTAMPTZ   NOT NULL,
  ingested_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  team          VARCHAR(64),
  project       VARCHAR(64),
  host          VARCHAR(128),
  service       VARCHAR(128),
  environment   VARCHAR(32),
  severity      VARCHAR(16),
  extra_labels  JSONB
);

SELECT create_hypertable('health_metric_events', 'timestamp');

-- Indexes for common query patterns
CREATE INDEX ON health_metric_events (source, name, timestamp DESC);
CREATE INDEX ON health_metric_events (team, category, timestamp DESC);
CREATE INDEX ON health_metric_events (host, name, timestamp DESC);
CREATE INDEX ON health_metric_events (service, name, timestamp DESC);
```

### Continuous Aggregates (Roll-ups)

```sql
-- Hourly roll-up (retained 1 year)
CREATE MATERIALIZED VIEW health_metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 hour', timestamp) AS bucket,
  source, category, name, team, project, host, service, environment,
  AVG(value)  AS avg_value,
  MIN(value)  AS min_value,
  MAX(value)  AS max_value,
  COUNT(*)    AS sample_count
FROM health_metric_events
GROUP BY bucket, source, category, name, team, project, host, service, environment;

-- Daily roll-up (retained 3 years)
CREATE MATERIALIZED VIEW health_metrics_daily
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 day', timestamp) AS bucket,
  source, category, name, team, project, host, service, environment,
  AVG(value)  AS avg_value,
  MIN(value)  AS min_value,
  MAX(value)  AS max_value,
  COUNT(*)    AS sample_count
FROM health_metric_events
GROUP BY bucket, source, category, name, team, project, host, service, environment;
```

---

## GraphQL API

### Schema

```graphql
type HealthMetric {
  id:          ID!
  source:      MetricSource!
  category:    String!
  name:        String!
  value:       Float!
  unit:        String
  timestamp:   DateTime!
  team:        String
  project:     String
  host:        String
  service:     String
  environment: String
  severity:    AlertSeverity
  extraLabels: JSON
}

type MetricSummary {
  name:        String!
  avgValue:    Float!
  minValue:    Float!
  maxValue:    Float!
  trend:       [TimePoint!]!    # (timestamp, value) pairs
  sampleCount: Int!
}

type HealthMatrix {
  dora:           DoraSummary!
  infrastructure: InfraSummary!
  anomalies:      [HealthMetric!]!
  alerts:         [HealthMetric!]!
}

type DoraSummary {
  deploymentFrequency: MetricSummary!
  leadTimeForChanges:  MetricSummary!
  changeFailureRate:   MetricSummary!
  mttr:                MetricSummary!
  doraLevel:           DoraLevel!   # "elite" | "high" | "medium" | "low"
}

type InfraSummary {
  cpuUtilization:    MetricSummary!
  memoryUtilization: MetricSummary!
  serviceAvailability: MetricSummary!
  networkLatencyP95: MetricSummary!
}

enum MetricSource { DEVLAKE METRON }
enum AlertSeverity { CRITICAL HIGH MEDIUM LOW }
enum DoraLevel { ELITE HIGH MEDIUM LOW }

type Query {
  # Current health matrix for a team/project
  healthMatrix(
    team:        String
    project:     String
    environment: String
    timeRange:   TimeRangeInput!
  ): HealthMatrix!

  # Raw metric time-series
  metrics(
    source:      MetricSource
    category:    String
    name:        String
    team:        String
    project:     String
    host:        String
    service:     String
    environment: String
    timeRange:   TimeRangeInput!
    resolution:  Resolution      # "raw" | "hourly" | "daily"
    limit:       Int
  ): [HealthMetric!]!

  # Latest snapshot per service/host
  latestSnapshots(
    category:    String!
    environment: String
  ): [HealthMetric!]!
}

input TimeRangeInput {
  from: DateTime!
  to:   DateTime!
}

enum Resolution { RAW HOURLY DAILY }
```

### Example Queries

**Get current DORA health matrix for the `backend` team:**

```graphql
query BackendHealth {
  healthMatrix(team: "backend", timeRange: { from: "2026-02-03", to: "2026-03-05" }) {
    dora {
      deploymentFrequency { avgValue unit trend { timestamp value } }
      leadTimeForChanges  { avgValue unit }
      changeFailureRate   { avgValue unit }
      mttr                { avgValue unit }
      doraLevel
    }
    infrastructure {
      serviceAvailability { avgValue minValue }
      networkLatencyP95   { avgValue maxValue }
    }
    anomalies { name value severity timestamp host }
  }
}
```

**Get hourly CPU trend for a specific host:**

```graphql
query HostCpuTrend {
  metrics(
    source: METRON
    name: "cpu_utilization"
    host: "prod-api-server-01"
    timeRange: { from: "2026-03-04T00:00:00Z", to: "2026-03-05T00:00:00Z" }
    resolution: HOURLY
  ) {
    timestamp value unit host
  }
}
```

---

## REST API

The REST API handles webhook callbacks and provides simple health endpoints for load balancers and synthetic monitors.

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Portal liveness probe (returns `200 OK`) |
| GET | `/ready` | Portal readiness probe (checks DB + Redis connectivity) |
| POST | `/webhooks/alerts` | Inbound webhook for PagerDuty / Alertmanager |
| GET | `/api/v1/metrics/export` | Prometheus-compatible metrics scrape endpoint |

---

## Authentication & RBAC

### OIDC Flow

```
Browser → Portal UI → API Gateway → OIDC Provider (Okta/Keycloak)
                          │
                   JWT validation
                   (RS256, JWKS endpoint)
                          │
                   Extract claims:
                   - sub (user ID)
                   - email
                   - groups (team memberships)
                   - roles
```

### Roles

| Role | Access |
|---|---|
| `viewer` | Read-only access to metrics for their own team |
| `team-lead` | Read-only access to all teams |
| `ops-engineer` | Read access + acknowledge alerts |
| `security-analyst` | Full access including `metron.alerts.triage` data |
| `admin` | Full access; can manage alert rules and RBAC assignments |

### Field-level visibility

- `severity: CRITICAL` alerts and `category: security.alert` events are hidden from `viewer` and `team-lead` roles.
- Host IP addresses are masked for `viewer` role (replaced with `host-{hash}`).

---

## Caching Strategy

```
GraphQL Resolver
       │
       ├── Check Redis key: "snapshot:{category}:{team}:{environment}"
       │
       ├── HIT  → return cached value (TTL: 60s for snapshots, 5m for summaries)
       │
       └── MISS → query TimescaleDB
                      │
                      └── write to Redis with TTL
                      └── return result
```

Cache invalidation is **TTL-based** (no active invalidation). The 60-second TTL aligns with DevLake's poll interval, ensuring the dashboard never shows data older than ~2 minutes.
