---
title: DevLake Integration
layout: default
nav_order: 3
---

# DevLake Integration
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## What is Apache DevLake?

[Apache DevLake](https://devlake.apache.org/) is an open-source dev data platform that ingests data from the entire software development lifecycle (GitHub, GitLab, Jira, Jenkins, PagerDuty, etc.) and computes **DORA metrics** and other engineering productivity signals.

The portal treats DevLake as a **read-only upstream source**. DevLake manages its own data collection; the portal only consumes aggregated metric results from DevLake's REST API.

---

## Metrics Retrieved from DevLake

The portal retrieves the following metric groups from DevLake:

### DORA Metrics

| Metric | DevLake API Field | Description |
|---|---|---|
| Deployment Frequency | `deploymentFrequency.count` | Number of deployments per day/week |
| Lead Time for Changes | `leadTimeForChanges.daysToMerge` | Time from first commit to deployment |
| Change Failure Rate | `changeFailureRate.rate` | % of deployments causing incidents |
| Mean Time to Restore (MTTR) | `mttr.hours` | Avg time to recover from a production failure |

### Team & Velocity Metrics

| Metric | DevLake API Field | Description |
|---|---|---|
| PR Cycle Time | `prCycleTime.hours` | Open → Merged duration for pull requests |
| PR Review Depth | `prReviewDepth.comments` | Average review comments per PR |
| Bug Rate | `bugRate.perSprint` | Bugs filed per sprint by team |
| Incident Volume | `incidentVolume.count` | Total incidents in the period |

---

## Connection Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      DevLake Instance                           │
│                                                                 │
│  ┌────────────┐   ┌──────────────┐   ┌──────────────────────┐  │
│  │  GitHub    │   │    Jira      │   │  Jenkins / GitLab CI │  │
│  │  Plugin    │   │   Plugin     │   │       Plugin         │  │
│  └────────────┘   └──────────────┘   └──────────────────────┘  │
│         │                │                       │             │
│         └────────────────┴───────────────────────┘             │
│                          │                                      │
│                   ┌──────▼──────┐                               │
│                   │  DevLake DB │  (MySQL / PostgreSQL)         │
│                   └──────┬──────┘                               │
│                          │                                      │
│                   ┌──────▼──────┐                               │
│                   │  REST API   │  :4000/api                    │
│                   └─────────────┘                               │
└───────────────────────────────────────────────────────────────────┘
                              │
                              │  HTTPS REST (polling every 60s)
                              │  API Key auth (X-Api-Token header)
                              ▼
                  ┌───────────────────────┐
                  │   Ingestion Service   │
                  │   (DevLake Adapter)   │
                  └───────────────────────┘
```

---

## Ingestion Service – DevLake Adapter

The **DevLake Adapter** is a module within the Ingestion Service responsible for:

1. Authenticating with DevLake using a pre-shared API key
2. Polling configured metric endpoints on a 60-second schedule
3. Transforming DevLake's response schema into the portal's **canonical `HealthMetricEvent`**
4. Writing normalised events to TimescaleDB
5. Updating the Redis cache with the latest snapshot

### Polling Schedule

```
Scheduler (APScheduler)
        │
        ├── Every 60s  ──►  fetch_dora_metrics()
        ├── Every 60s  ──►  fetch_velocity_metrics()
        └── Every 300s ──►  fetch_team_roster()   (slower-changing)
```

### Adapter Pseudo-code

```python
class DevLakeAdapter:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.session = httpx.AsyncClient(
            headers={"X-Api-Token": api_key},
            timeout=30.0
        )

    async def fetch_dora_metrics(self, project: str, period: str) -> list[HealthMetricEvent]:
        url = f"{self.base_url}/api/projects/{project}/dora"
        params = {"timeRange": period}
        response = await self.session.get(url, params=params)
        response.raise_for_status()
        raw = response.json()
        return [self._normalise(metric, source="devlake") for metric in raw["data"]]

    def _normalise(self, raw: dict, source: str) -> HealthMetricEvent:
        return HealthMetricEvent(
            source=source,
            category="dora",
            name=raw["metricName"],
            value=raw["value"],
            unit=raw["unit"],
            team=raw.get("team"),
            project=raw.get("project"),
            timestamp=datetime.fromisoformat(raw["calculatedAt"]),
        )
```

---

## DevLake API Endpoints Used

| Purpose | HTTP Method | Endpoint |
|---|---|---|
| DORA metrics for a project | GET | `/api/projects/{project}/dora` |
| All projects list | GET | `/api/projects` |
| PR cycle time | GET | `/api/projects/{project}/pr-metrics` |
| Incident metrics | GET | `/api/projects/{project}/incident-metrics` |
| Team list | GET | `/api/teams` |

---

## Error Handling & Resilience

| Failure Mode | Handling Strategy |
|---|---|
| DevLake API timeout | Retry 3× with exponential backoff (2 s, 4 s, 8 s); log warning |
| DevLake API 5xx | Retry same as above; after 3 failures, emit `source_unavailable` alert |
| DevLake API 4xx (auth) | No retry; emit critical alert; stop polling until key is rotated |
| Partial data (missing fields) | Log missing fields; write partial event with `null` values; do not drop |
| DevLake schema change | Schema validation on ingest; on mismatch, quarantine raw payload for manual review |

---

## Configuration

The DevLake adapter is configured via environment variables:

```yaml
# devlake adapter config (injected as K8s secret)
DEVLAKE_BASE_URL: "https://devlake.internal.example.com"
DEVLAKE_API_KEY: "<secret>"
DEVLAKE_POLL_INTERVAL_SECONDS: "60"
DEVLAKE_PROJECTS: "frontend,backend,platform,mobile"
DEVLAKE_DEFAULT_TIME_RANGE: "last30days"
```

---

## Security Considerations

- The API key is stored in a Kubernetes Secret and mounted as an environment variable; never hardcoded.
- All traffic between the Ingestion Service and DevLake is over TLS (mutual TLS within the cluster).
- DevLake's API key is rotated every 90 days via the secret management pipeline.
- The adapter uses a **read-only** DevLake API key scoped only to the metric endpoints listed above.
