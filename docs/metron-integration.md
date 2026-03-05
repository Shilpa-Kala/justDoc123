---
title: Metron Integration
layout: default
nav_order: 4
---

# Metron Integration
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## What is Apache Metron?

[Apache Metron](https://metron.apache.org/) is a real-time big data security analytics platform built on top of **Apache Kafka** and **Apache Storm**. It ingests telemetry from network sensors, host agents, and cloud logs, enriches events, runs anomaly detection, and publishes results to Kafka output topics.

The portal consumes Metron's **enriched, parsed output topics** to extract infrastructure and system health signals.

---

## Health Signals Retrieved from Metron

The portal subscribes to the following Metron output signals:

### Infrastructure Health

| Signal | Kafka Topic | Description |
|---|---|---|
| Host CPU / Memory / Disk | `metron.host.vitals` | Per-host resource utilisation (sampled every 30 s) |
| Container Health | `metron.container.health` | Container restart counts, OOM kills, CrashLoopBackOffs |
| Network Latency | `metron.network.latency` | P50/P95/P99 RTT between services |
| Service Availability | `metron.service.availability` | Up/down status and response-time per service |

### Anomaly & Security Signals

| Signal | Kafka Topic | Description |
|---|---|---|
| Anomaly Score | `metron.anomaly.scores` | Metron's ML anomaly score per host/service (0–1) |
| Threat Alert | `metron.alerts.triage` | Triaged security alerts with severity level |
| Error Rate Spike | `metron.error.spikes` | Detected spikes in application error rates |

---

## Connection Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Apache Metron                               │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │  Network     │  │  Host Agent  │  │  Cloud Log Ingest      │   │
│  │  Sensor      │  │  (Telegraf)  │  │  (S3, CloudWatch, etc) │   │
│  └──────────────┘  └──────────────┘  └────────────────────────┘   │
│          │                │                       │               │
│          └────────────────┴───────────────────────┘               │
│                           │  Raw events                           │
│                    ┌──────▼──────┐                                │
│                    │   Kafka     │  (input topics)                │
│                    └──────┬──────┘                                │
│                           │                                       │
│             ┌─────────────▼──────────────┐                        │
│             │  Storm Topology            │                        │
│             │  (parse → enrich → triage) │                        │
│             └─────────────┬──────────────┘                        │
│                           │  Enriched events                      │
│                    ┌──────▼──────┐                                │
│                    │   Kafka     │  (output topics)               │
│                    └─────────────┘                                │
└───────────────────────────────────────────────────────────────────┘
                            │  Kafka Consumer (SASL/TLS)
                            ▼
                ┌───────────────────────┐
                │   Ingestion Service   │
                │   (Metron Adapter)    │
                └───────────────────────┘
```

---

## Ingestion Service – Metron Adapter

The **Metron Adapter** is a module within the Ingestion Service that:

1. Maintains a Kafka consumer group (`portal-metron-consumer`) subscribed to Metron output topics
2. Deserialises Avro / JSON events from Metron
3. Transforms each event into the portal's **canonical `HealthMetricEvent`**
4. Writes normalised events to TimescaleDB
5. Updates Redis with the latest snapshot for affected services/hosts

### Kafka Consumer Configuration

```yaml
bootstrap.servers: "kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092"
group.id: "portal-metron-consumer"
auto.offset.reset: "latest"           # only live data; no historical replay
enable.auto.commit: false             # manual commit after successful write
max.poll.records: 500
security.protocol: SASL_SSL
sasl.mechanism: SCRAM-SHA-256
sasl.username: "<secret>"
sasl.password: "<secret>"
ssl.ca.location: "/etc/ssl/kafka-ca.pem"
```

### Adapter Pseudo-code

```python
class MetronAdapter:
    def __init__(self, kafka_config: dict, topics: list[str]):
        self.consumer = confluent_kafka.Consumer(kafka_config)
        self.consumer.subscribe(topics)

    async def run(self):
        while True:
            messages = self.consumer.consume(num_messages=500, timeout=1.0)
            events = []
            for msg in messages:
                if msg.error():
                    handle_kafka_error(msg.error())
                    continue
                raw = json.loads(msg.value())
                events.append(self._normalise(raw))

            if events:
                await self.store.bulk_insert(events)
                await self.cache.update_snapshots(events)
                self.consumer.commit()

    def _normalise(self, raw: dict) -> HealthMetricEvent:
        return HealthMetricEvent(
            source="metron",
            category=raw.get("source_type", "infrastructure"),
            name=raw["metric_name"],
            value=raw["value"],
            unit=raw.get("unit", ""),
            host=raw.get("ip_src_addr") or raw.get("host"),
            service=raw.get("service"),
            severity=raw.get("alert_severity"),
            timestamp=datetime.utcfromtimestamp(raw["timestamp"] / 1000),
        )
```

---

## Topic-to-Category Mapping

| Kafka Topic | Portal Category | Retention in TimescaleDB |
|---|---|---|
| `metron.host.vitals` | `infrastructure.host` | 30 days raw, 1 year hourly rollup |
| `metron.container.health` | `infrastructure.container` | 30 days raw, 1 year hourly rollup |
| `metron.network.latency` | `infrastructure.network` | 30 days raw, 1 year hourly rollup |
| `metron.service.availability` | `infrastructure.service` | 30 days raw, 1 year daily rollup |
| `metron.anomaly.scores` | `anomaly` | 90 days raw |
| `metron.alerts.triage` | `security.alert` | 365 days raw (compliance) |
| `metron.error.spikes` | `error.spike` | 90 days raw |

---

## Error Handling & Resilience

| Failure Mode | Handling Strategy |
|---|---|
| Kafka broker unreachable | Consumer retries with exponential backoff; no messages lost (Kafka retains offsets) |
| Deserialization failure | Log raw payload to dead-letter topic `portal.dlq.metron`; skip event; continue |
| TimescaleDB write failure | Hold un-committed Kafka offsets; retry write; reprocess on restart |
| Consumer lag spike (> 10k messages) | Emit `consumer_lag` alert; scale consumer replicas via HPA |
| Metron schema change (new field) | Unknown fields are passed through as `extra_labels` map; no hard failure |

---

## Backpressure & Scaling

- The Metron Adapter scales horizontally. Each replica is a member of the same Kafka consumer group; Kafka distributes partition assignments automatically.
- At peak load (estimated 50k events/minute), 3 replicas of the adapter with `max.poll.records=500` comfortably keep consumer lag below 1,000.
- Auto-scaling is triggered when consumer lag on any topic exceeds 5,000 messages (monitored via Prometheus Kafka exporter + KEDA ScaledObject).

---

## Security Considerations

- Kafka credentials (SASL) are stored in Kubernetes Secrets and never logged.
- The adapter connects only to Metron's **output** topics; it has no write access to Metron's input or configuration topics.
- TLS encryption is enforced on all Kafka connections (no plain-text fallback).
- Security alert events (`metron.alerts.triage`) are accessible only to users with the `security-analyst` role in the portal's RBAC model.
