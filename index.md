---
title: Home
layout: home
nav_order: 1
---

# Health Matrix Portal – Architecture Design

This site documents the architecture for a **Health Matrix Portal** that aggregates engineering and infrastructure health data from two primary sources:

- **[Apache DevLake](https://devlake.apache.org/)** – collects DORA metrics and engineering productivity signals from DevOps toolchains (GitHub, Jira, Jenkins, etc.)
- **[Apache Metron](https://metron.apache.org/)** – collects real-time infrastructure and security telemetry (system health, network events, anomaly signals)

The portal unifies these data streams into a single, queryable health matrix dashboard, giving engineering and operations teams a shared view of system and team health.

---

## Documentation Sections

| Section | Description |
|---|---|
| [Architecture Overview](./docs/overview) | High-level system design, component map, and data flow |
| [DevLake Integration](./docs/devlake-integration) | How the portal connects to and ingests data from DevLake |
| [Metron Integration](./docs/metron-integration) | How the portal connects to and ingests data from Metron |
| [API Layer & Data Model](./docs/api-layer) | Backend REST/GraphQL API design and canonical data model |
| [Frontend Portal](./docs/frontend) | Dashboard UI design, component breakdown, and UX flows |
| [Deployment & Infrastructure](./docs/deployment) | Kubernetes deployment topology, scaling, and observability |
| [Architecture Diagrams](./docs/diagrams) | Mermaid visual diagrams for all layers (C4, sequence, flow, state) |

---

## Key Design Goals

1. **Unified health view** – DORA metrics + infrastructure signals on one dashboard
2. **Near-real-time** – metric refresh latency under 60 seconds
3. **Extensible** – new data sources can be plugged in without breaking existing consumers
4. **Secure** – role-based access control (RBAC) with audit logging
5. **Observable** – the portal itself is fully instrumented with metrics, traces, and logs
