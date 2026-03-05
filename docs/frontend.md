---
title: Frontend Portal
layout: default
nav_order: 6
---

# Frontend Portal
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Framework | React 18 + TypeScript | Strong ecosystem, strict typing, component reuse |
| State management | Zustand + React Query | React Query handles server state (caching, polling); Zustand for UI state |
| GraphQL client | Apollo Client | Integrates with the portal's GraphQL API; normalised cache |
| Charts | Recharts | Lightweight, composable, SVG-based charting |
| UI component library | shadcn/ui + Tailwind CSS | Accessible, unstyled primitives; easy to theme |
| Build | Vite | Fast HMR; small production bundles |
| Testing | Vitest + React Testing Library + Playwright | Unit, integration, and E2E coverage |

---

## Page Map

```
/                          ← Health Matrix Dashboard (default)
/teams/{team}              ← Team-specific drill-down
/services/{service}        ← Service-level health
/hosts/{host}              ← Host-level infrastructure detail
/alerts                    ← Alert list + acknowledgement
/settings                  ← User preferences, alert rule management (admin)
```

---

## Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  HEADER                                                                 │
│  [Logo] Health Matrix Portal    [Team filter ▼] [Env filter ▼]  [👤]  │
├─────────────────────────────────────────────────────────────────────────┤
│  DORA METRICS BAND                                                      │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────┐ ┌───────┐ │
│  │ Deploy Frequency │ │ Lead Time        │ │ Change Fail  │ │ MTTR  │ │
│  │  4.2 / day  ●    │ │  1.3 days  ●     │ │  2.1%   ●   │ │ 0.4h  │ │
│  │  [sparkline]     │ │  [sparkline]     │ │  [sparkline] │ │  ●    │ │
│  │  ELITE           │ │  HIGH            │ │  ELITE       │ │ ELITE │ │
│  └──────────────────┘ └──────────────────┘ └──────────────┘ └───────┘ │
├──────────────────────────────────────┬──────────────────────────────────┤
│  INFRASTRUCTURE HEALTH               │  ACTIVE ALERTS                  │
│                                      │                                  │
│  Service Availability  99.8%  ●      │  ● CRITICAL  api-gateway OOM    │
│  CPU Utilisation       62%    ●      │    5 min ago  [Ack]             │
│  Memory Utilisation    74%    ●      │                                  │
│  Network Latency P95   38ms   ●      │  ● HIGH  Deploy failure: mobile │
│                                      │    12 min ago  [Ack]            │
│  [View host breakdown →]             │                                  │
│                                      │  [View all alerts →]            │
├──────────────────────────────────────┴──────────────────────────────────┤
│  TREND CHART (selected metric over time)                                │
│                                                                         │
│  [Metric selector ▼]  [Time range ▼: last 30 days]                     │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~  │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Legend:** ● Green = healthy, ● Yellow = degraded, ● Red = critical

---

## Component Breakdown

### `HealthMatrixDashboard` (page container)

Responsible for:
- Fetching `healthMatrix` GraphQL query with selected filters
- Passing data to child components
- Managing auto-refresh (polling every 60 seconds via React Query)

```typescript
function HealthMatrixDashboard() {
  const { team, environment } = useFilters();
  const { data, isLoading, error } = useHealthMatrix({ team, environment });

  if (isLoading) return <LoadingSkeleton />;
  if (error)     return <ErrorBanner error={error} />;

  return (
    <DashboardLayout>
      <DoraBand metrics={data.dora} />
      <InfraPanel metrics={data.infrastructure} />
      <AlertPanel alerts={data.alerts} anomalies={data.anomalies} />
      <TrendChart />
    </DashboardLayout>
  );
}
```

---

### `DoraBand`

Renders four DORA metric tiles in a horizontal band. Each tile shows:
- Current value + unit
- Coloured status indicator (green / amber / red) based on DORA performance level thresholds
- 7-day sparkline
- DORA level label (Elite / High / Medium / Low)

**DORA level thresholds** (industry standard):

| Metric | Elite | High | Medium | Low |
|---|---|---|---|---|
| Deploy Frequency | > 1/day | 1/week–1/day | 1/month–1/week | < 1/month |
| Lead Time | < 1 hour | 1 day | 1 week | > 1 month |
| Change Failure Rate | < 5% | 5–10% | 10–15% | > 15% |
| MTTR | < 1 hour | < 1 day | < 1 week | > 1 week |

---

### `InfraPanel`

Renders key infrastructure health metrics sourced from Metron:
- **Gauge / Progress bars** for CPU, memory, disk utilisation
- **Coloured status badge** for service availability
- **Network latency pill** with P95 value
- Link to the host breakdown page (`/hosts`)

---

### `AlertPanel`

Shows the latest active alerts from Metron's triage topic and the portal's alerting engine:
- Sorted by severity then by recency
- **Acknowledge** button (calls REST `POST /api/v1/alerts/{id}/ack`)
- Severity badges using colour coding: Red = CRITICAL, Orange = HIGH, Yellow = MEDIUM
- Auto-refreshes every 15 seconds

---

### `TrendChart`

An interactive line chart backed by the `metrics` GraphQL query:
- Metric selector dropdown (lists all `name` values available in the selected time range)
- Time range selector (last 1h, 6h, 24h, 7d, 30d)
- Resolution auto-selected based on time range (RAW for < 6h, HOURLY for < 7d, DAILY otherwise)
- Zoom + pan via mouse interactions
- Tooltip shows value, unit, timestamp on hover

---

### `TeamDrillDown` (`/teams/{team}`)

Identical layout to `HealthMatrixDashboard` but scoped to a single team:
- Shows per-project DORA breakdown
- Shows team-level PR cycle time and bug rate metrics (from DevLake)
- Lists contributors with recent activity (anonymised for viewers)

---

## Real-Time Updates

The portal uses **React Query polling** rather than WebSockets for simplicity:

| Panel | Poll Interval |
|---|---|
| DORA metrics band | 60 seconds |
| Infrastructure panel | 30 seconds |
| Alert panel | 15 seconds |
| Trend chart | Manual refresh (user-triggered) |

If the user's browser tab is hidden (Page Visibility API), polling is paused and resumes on tab focus to avoid unnecessary load.

---

## Error & Empty States

| State | UI Treatment |
|---|---|
| Source unavailable (DevLake down) | Orange banner: "Engineering metrics are delayed – last updated X min ago" |
| Source unavailable (Metron down) | Orange banner: "Infrastructure metrics are delayed" |
| No data for selected filters | Empty state illustration + "No metrics found for selected team/environment" |
| Auth token expired | Redirect to OIDC login; preserves current URL as `redirect_uri` |
| API error (5xx) | Red error banner with retry button; previous cached data still displayed |

---

## Accessibility

- All interactive elements have ARIA labels
- DORA status colours are accompanied by text labels (not colour-only indicators)
- Keyboard navigation supported throughout
- Charts include accessible data tables as fallback (toggleable)
- Meets WCAG 2.1 AA contrast requirements
